# payments/views.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import logging
from urllib.parse import urlparse, urlencode
from typing import Optional
import re

from django.conf import settings
from django.db import transaction
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.test.client import RequestFactory
from django.core.exceptions import ValidationError


from accounts.models import UserProfile



from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from azbankgateways.bankfactories_interface import BankFactory
from azbankgateways import models as bank_models, default_settings as gw_settings
from azbankgateways.exceptions import AZBankGatewaysException
from azbankgateways.views.banks import (
    callback_view as pkg_callback_view,
    go_to_bank_gateway as pkg_go_to_bank_gateway,
)

from competitions.models import KyorugiCompetition, PoomsaeCompetition,GroupRegistrationPayment, Enrollment
from .discounts import apply_discount_for_competition
from .models import PaymentIntent
from .serializers import InitiateSerializer

log = logging.getLogger("payments")

try:
    log.info(
        "ENV_LOAD base=%s exists=%s",
        settings.BASE_DIR,
        os.path.exists(settings.BASE_DIR / ".env"),
    )
except Exception:
    pass


class PaymentIntentEnrollmentsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pid):
        intent = PaymentIntent.objects.filter(public_id=pid).first()
        if not intent:
            return Response({"detail": "PaymentIntent یافت نشد."}, status=404)

        # امنیت: فقط صاحب intent
        if intent.user_id and intent.user_id != request.user.id:
            return Response({"detail": "دسترسی غیرمجاز."}, status=403)

        ids = []

        # ✅ bulk
        if hasattr(intent, "kyorugi_enrollments"):
            ids += list(intent.kyorugi_enrollments.values_list("id", flat=True))

        # ✅ تکی
        if intent.kyorugi_enrollment_id:
            ids.append(intent.kyorugi_enrollment_id)

        ids = sorted(set(int(x) for x in ids if x))
        return Response({"enrollment_ids": ids})


# ───────────────────────── Helpers ─────────────────────────
def _split_amounts(total, n):
    total = int(total or 0)
    n = int(n or 0)
    if n <= 0:
        return []
    base = total // n
    rem = total - (base * n)
    parts = [base] * n
    for i in range(rem):
        parts[i] += 1
    return parts


@transaction.atomic
def _finalize_group_payment_if_needed(intent: PaymentIntent, ref_code: str):
    """
    اگر intent مربوط به ثبت‌نام گروهی باشد (description شامل GP#id)،
    Enrollment ها را می‌سازد و paid می‌کند و gp را paid می‌کند.
    خروجی: لیست enrollment_ids
    """
    desc = (getattr(intent, "description", "") or "")
    m = re.search(r"GP#(\d+)", desc)
    if not m:
        return []

    gp_id = int(m.group(1))
    gp = GroupRegistrationPayment.objects.select_for_update().filter(id=gp_id).first()
    if not gp:
        return []

    payload = gp.payload or {}
    if gp.is_paid:
        return list(payload.get("enrollment_ids") or [])

    items = payload.get("items") or []
    if not items:
        return []

    coach = gp.coach
    comp = gp.competition

    # مبلغ پرداختی کل (ریال)
    payable_amount = int(payload.get("payable_amount") or gp.total_amount or 0)
    parts = _split_amounts(payable_amount, len(items))

    created_ids = []
    coach_name = f"{coach.first_name} {coach.last_name}".strip()

    for idx, it in enumerate(items):
        pid = int(it["player_id"])
        player = UserProfile.objects.get(id=pid)

        ins_date = it.get("insurance_issue_date")
        if isinstance(ins_date, str) and ins_date:
            from datetime import date as _date
            ins_date = _date.fromisoformat(ins_date)

        e = Enrollment.objects.create(
            competition=comp,
            player=player,
            coach=coach,
            coach_name=coach_name,

            club_id=it.get("club_id") or None,
            club_name=str(it.get("club_name") or ""),

            board_id=it.get("board_id") or None,
            board_name=str(it.get("board_name") or ""),

            belt_group_id=it.get("belt_group_id") or None,
            weight_category_id=it.get("weight_category_id") or None,

            declared_weight=float(it.get("declared_weight") or 0),
            insurance_number=str(it.get("insurance_number") or ""),
            insurance_issue_date=ins_date,

            discount_code=payload.get("discount_code") or None,
            discount_amount=0,

            payable_amount=int(parts[idx] if idx < len(parts) else 0),

            status="pending_payment",
            is_paid=False,
            paid_amount=0,
            bank_ref_code="",
        )

        # paid کن
        e.mark_paid(
            amount=int(parts[idx] if idx < len(parts) else 0),
            ref_code=str(ref_code or ""),
        )
        created_ids.append(e.id)

    # gp را paid کن
    gp.is_paid = True
    gp.bank_ref_code = str(ref_code or "")
    payload["enrollment_ids"] = created_ids
    payload["paid_at"] = timezone.now().isoformat()
    gp.payload = payload
    gp.save(update_fields=["is_paid", "bank_ref_code", "payload"])

    return created_ids



def _bridge_bank_gateways_to_enum():
    """
    Patch BANK_GATEWAYS to accept both str and Enum (BankType.*)
    """
    from azbankgateways import models as _bank_models

    bmi_enum = getattr(_bank_models.BankType, "BMI")
    if not hasattr(settings, "BANK_GATEWAYS"):
        return

    conf = dict(settings.BANK_GATEWAYS)

    class SmartDict(dict):
        def __getitem__(self, key):
            if dict.__contains__(self, key):
                return dict.__getitem__(self, key)
            if hasattr(key, "name") and key.name in self:
                return dict.__getitem__(self, key.name)
            if hasattr(key, "value") and key.value in self:
                return dict.__getitem__(self, key.value)
            if str(key) in self:
                return dict.__getitem__(self, str(key))
            if "BMI" in self:
                return dict.__getitem__(self, "BMI")
            raise KeyError(key)

    if bmi_enum not in conf:
        conf[bmi_enum] = conf.get("BMI", {})

    settings.BANK_GATEWAYS = SmartDict(conf)


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")


def _return_url():
    return (getattr(settings, "PAYMENTS", {}) or {}).get("RETURN_URL") or "/"


def _callback_allowed(host):
    allowed = set((getattr(settings, "PAYMENTS", {}) or {}).get("ALLOWED_CALLBACK_HOSTS", []))
    if not allowed:
        allowed = {"chbtkd.ir", "www.chbtkd.ir", "api.chbtkd.ir", "localhost", "127.0.0.1"}
    return (host or "").lower() in {h.lower() for h in allowed}


def _payments_enabled():
    return bool((getattr(settings, "PAYMENTS", {}) or {}).get("ENABLED", False))


def _payments_dummy():
    return bool((getattr(settings, "PAYMENTS", {}) or {}).get("DUMMY", False))


def _continue_gateway_url(request, token):
    p = gw_settings.TRACKING_CODE_QUERY_PARAM
    base_path = reverse("bankgateways:go-to-bank-gateway")
    return request.build_absolute_uri(f"{base_path}?{p}={token}")


def _sadad_dict():
    cfg_all = getattr(settings, "AZ_IRANIAN_BANK_GATEWAYS", {}) or {}
    gws = (cfg_all.get("GATEWAYS") or {})
    return gws.get("SADAD") or gws.get("BMI") or {}


def _get_sadad_creds():
    sadad = _sadad_dict()
    m = sadad.get("MERCHANT_ID") or getattr(settings, "BANK_SADAD_MERCHANT_ID", "")
    t = sadad.get("TERMINAL_ID") or getattr(settings, "BANK_SADAD_TERMINAL_ID", "")
    k = sadad.get("TERMINAL_KEY") or getattr(settings, "BANK_SADAD_KEY", "")
    return m, t, k


def _sadad_creds_ok():
    m, t, k = _get_sadad_creds()
    return all([m, t, k])


def _normalize_gateway_name(name: Optional[str]) -> str:
    n = (name or "").strip().lower()
    if n in {"dummy", "test"}:
        return "dummy"
    if n in {"sodad", "saddad", "sadad"}:
        return "sadad"
    if n == "bmi":
        return "bmi"
    if n == "fake":
        return "fake"
    return n or "sadad"


def _bankfactory_create_from_record(factory, bank_type_value, request, amount, callback_url):
    try:
        return factory.create(bank_type=bank_type_value, request=request, amount=amount, callback_url=callback_url)
    except TypeError:
        return factory.create(bank_type_value, request, amount, callback_url)


# ───────────────────────── BankGateways Overrides ─────────────────────────

try:
    from azbankgateways.exceptions import BankGatewayTokenExpired, AmountDoesNotSupport
except Exception:
    BankGatewayTokenExpired = Exception
    AmountDoesNotSupport = Exception



@csrf_exempt
def bankgateways_callback_override(request, bank_type: Optional[str] = None, *args, **kwargs):
    tracking_param = getattr(gw_settings, "TRACKING_CODE_QUERY_PARAM", "tc")

    # داده‌های برگشتی سداد
    token = (request.POST.get("token") or request.POST.get("Token") or "").strip()
    order_id = (
        request.POST.get("OrderId")
        or request.POST.get("orderId")
        or request.POST.get("OrderID")
        or ""
    )
    order_id = str(order_id).strip()
    res_code = (request.POST.get("ResCode") or request.POST.get("resCode") or "").strip()

    bank_type_q = (request.GET.get("bank_type") or bank_type or "").strip()

    log.warning(
        "CALLBACK_IN | method=%s ResCode=%s OrderId=%s token=%s qs=%s bank_type=%s",
        request.method, res_code, order_id, token, dict(request.GET.lists()), bank_type_q
    )

    # 1) پیدا کردن رکورد Bank
    Bank = bank_models.Bank
    b = None
    try:
        if order_id:
            b = Bank.objects.filter(tracking_code=order_id).first()
        if not b and token:
            b = Bank.objects.filter(reference_number=token).first()
        if not b and order_id:
            b = Bank.objects.filter(extra_information__icontains=order_id).first()
        if not b and token:
            b = Bank.objects.filter(extra_information__icontains=token).first()
    except Exception:
        log.exception("CALLBACK_RESOLVE_BANK_EXCEPTION")
        b = None

    if not b:
        log.error("CALLBACK_RESOLVE_BANK_FAILED | order_id=%s token=%s", order_id, token)
        return HttpResponse("OK", status=200)

    log.warning(
        "CALLBACK_RESOLVED_BANK | id=%s bank_type=%s tracking_code=%s amount=%s callback_url=%s ref=%s",
        b.id, b.bank_type, b.tracking_code, b.amount, b.callback_url, b.reference_number
    )

    # 2) مقصد ثابت برای نتیجه (تا لوپ/ابهام status حل شود)
    try:
        final_url = request.build_absolute_uri(
            reverse("payments:payment_result_redirect", kwargs={"tc": str(b.tracking_code).strip()})
        )
    except Exception:
        # fallback خیلی امن
        final_url = f"https://api.chbtkd.ir/api/payments/result/{str(b.tracking_code).strip()}/"

    # حتماً callback_url رکورد Bank مقدار داشته باشد (برای هرچیزی که بعداً بخواهد بخواند)
    try:
        if not getattr(b, "callback_url", None) or b.callback_url != final_url:
            b.callback_url = final_url
            b.save(update_fields=["callback_url"])
            log.warning("CALLBACK_SET_FINAL_REDIRECT | bank_id=%s url=%s", b.id, final_url)
    except Exception:
        log.exception("CALLBACK_SET_FINAL_REDIRECT_FAILED")

    # 3) ✅ اینجا اصل کار: verify را خودمان انجام می‌دهیم و دیگر pkg_callback_view را صدا نمی‌زنیم
    try:
        _bridge_bank_gateways_to_enum()

        factory = BankFactory()

        # BankType مناسب
        bt_name = str(getattr(b, "bank_type", "") or bank_type_q or "BMI").upper()
        bt = getattr(bank_models.BankType, bt_name, bank_models.BankType.BMI)

        amount = int(getattr(b, "amount", 0) or 0)

        # callback_url برای factory (هر URL معتبر داخل همین دامنه)
        cb_for_factory = (
            getattr(settings, "PAY_CALLBACK_URL", None)
            or (getattr(settings, "PAYMENTS", {}) or {}).get("CALLBACK_URL")
            or request.build_absolute_uri("/bankgateways/callback/")
        )

        bank = _bankfactory_create_from_record(
            factory=factory,
            bank_type_value=bt,
            request=request,
            amount=amount,
            callback_url=cb_for_factory,
        )

        # خیلی مهم: رکورد DB را به adapter بچسبان
        bank._bank = b

        # verify با همین request واقعی (POST سداد)
        bank.verify_from_gateway(request)

        b.refresh_from_db()
        log.warning(
            "CALLBACK_VERIFY_DONE | bank_id=%s tc=%s is_success=%s status=%s",
            b.id, b.tracking_code, b.is_success, b.status
        )

    except Exception as e:
        # حتی اگر verify ترکید، باز نتیجه را به فرانت هدایت کن تا کاربر معطل نشود
        log.exception("CALLBACK_VERIFY_ERROR | bank_id=%s tc=%s err=%s", b.id, b.tracking_code, e)

    # 4) در نهایت همیشه به endpoint نتیجه خودمان redirect می‌کنیم
    return HttpResponseRedirect(final_url)





def _extract_ref_from_extra(extra) -> str:
    if not extra:
        return ""

    # اگر dict بود
    if isinstance(extra, dict):
        for k in ["RetrivalRefNo", "RetrievalRefNo", "SystemTraceNo", "ref", "RefNo", "reference_number"]:
            v = extra.get(k)
            if v:
                return str(v).strip()

        # بعضی وقت‌ها اطلاعات توی زیرکلیدهاست
        for subk in ["result", "data", "bank", "extra"]:
            sub = extra.get(subk)
            if isinstance(sub, dict):
                for k in ["RetrivalRefNo", "RetrievalRefNo", "SystemTraceNo", "ref", "RefNo"]:
                    v = sub.get(k)
                    if v:
                        return str(v).strip()

        return ""

    # اگر string/متن بود
    s = str(extra)

    m = re.search(r"RetrivalRefNo\s*=\s*(\d+)", s, re.IGNORECASE)
    if m:
        return m.group(1)

    m = re.search(r"RetrievalRefNo\s*=\s*(\d+)", s, re.IGNORECASE)
    if m:
        return m.group(1)

    m = re.search(r"SystemTraceNo\s*=\s*(\d+)", s, re.IGNORECASE)
    if m:
        return m.group(1)

    return ""




@csrf_exempt
def payment_result_redirect(request, tc: str):
    tc = (tc or "").strip()
    if not tc:
        return HttpResponse("OK", status=200)

    b = bank_models.Bank.objects.filter(tracking_code=tc).first()
    if not b:
        return HttpResponse("OK", status=200)

    # پیدا کردن intent
    intent = PaymentIntent.objects.filter(token=tc).first()
    if not intent and getattr(b, "id", None):
        intent = PaymentIntent.objects.filter(ref_id=str(b.id)).first()

    enrollment_ids = []  # ✅ جدید

    # اگر intent پیدا شد، وضعیت را نهایی کن
    if intent:
        ref = _extract_ref_from_extra(getattr(b, "extra_information", "")) or ""
        token = (getattr(b, "reference_number", None) or "").strip()

        if getattr(b, "is_success", False):
            if intent.status != "paid":
                with transaction.atomic():
                    intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
                    if intent.status != "paid":
                        intent.mark_paid(
                            ref_id=ref or token or intent.ref_id or tc,
                            card_pan=getattr(intent, "card_pan", "") or "",
                            extra={"bank_id": b.id, "bank_status": b.status, "bank_extra": b.extra_information},
                        )

            # ✅ جدید: بعد از paid شدن intent، ثبت‌نام گروهی را finalize کن
            try:
                enrollment_ids = _finalize_group_payment_if_needed(
                    intent,
                    ref_code=(ref or token or tc),
                )
            except Exception:
                log.exception("FINALIZE_GROUP_PAYMENT_FAILED | tc=%s pid=%s", tc, getattr(intent, "public_id", None))
                enrollment_ids = []

        else:
            if intent.status != "paid":
                intent.status = "failed"
                intent.extra = {"bank_id": b.id, "bank_status": b.status, "bank_extra": b.extra_information}
                intent.save(update_fields=["status", "extra", "updated_at"])

    # بعدش redirect به فرانت
    return_url = (
        getattr(settings, "PAY_RETURN_URL", None)
        or (getattr(settings, "PAYMENTS", {}) or {}).get("RETURN_URL")
        or "https://chbtkd.ir/#/payment/result"
    )
    ok = "1" if getattr(b, "is_success", False) else "0"
    ref = _extract_ref_from_extra(getattr(b, "extra_information", "")) or ""
    token = (getattr(b, "reference_number", None) or "").strip()

    params = {"ok": ok, "tc": tc}
    if ref:
        params["ref"] = ref
    elif token:
        params["ref"] = token
    if token:
        params["token"] = token
    if intent:
        params["pid"] = str(intent.public_id)

    # ✅ جدید: پاس دادن enrollment_ids برای نمایش کارت‌ها
    if enrollment_ids:
        params["enrollment_ids"] = ",".join(str(x) for x in enrollment_ids)

    sep = "&" if "?" in return_url else "?"
    return HttpResponseRedirect(f"{return_url}{sep}{urlencode(params)}")



@method_decorator(csrf_exempt, name="dispatch")
class SadadBankReturnView(APIView):
    permission_classes = [permissions.AllowAny]

    def _forward_to_pkg_callback(self, request, public_id: str):
        intent = get_object_or_404(PaymentIntent, public_id=public_id)

        tc = (intent.token or "").strip()

        if not tc:
            try:
                if intent.ref_id:
                    b = bank_models.Bank.objects.filter(id=int(intent.ref_id)).only("tracking_code").first()
                    if b and b.tracking_code:
                        tc = str(b.tracking_code).strip()
            except Exception:
                tc = ""

        if not tc:
            log.error("BANK_RETURN_NO_TC pid=%s intent_id=%s ref_id=%s", public_id, intent.id, intent.ref_id)
            return HttpResponse("OK", status=200)

        qs = urlencode({gw_settings.TRACKING_CODE_QUERY_PARAM: tc})
        path = "/bankgateways/callback/?" + qs

        rf = RequestFactory()

        meta = {}
        for k in ["HTTP_USER_AGENT", "HTTP_X_FORWARDED_FOR", "REMOTE_ADDR", "CONTENT_TYPE"]:
            if k in request.META:
                meta[k] = request.META[k]

        new_req = rf.post(path, data=request.POST, **meta)
        new_req.META.update(request.META)

        try:
            new_req.COOKIES = request.COOKIES
        except Exception:
            pass

        return pkg_callback_view(new_req)

    def post(self, request, public_id: str):
        return self._forward_to_pkg_callback(request, public_id)

    def get(self, request, public_id: str):
        return self._forward_to_pkg_callback(request, public_id)


@csrf_exempt
def go_to_bank_gateway_override(request, *args, **kwargs):
    token = request.GET.get("Token") or request.GET.get("token")
    url = request.GET.get("url")
    method = request.GET.get("method")
    if token and url and method:
        return pkg_go_to_bank_gateway(request, *args, **kwargs)

    tc = request.GET.get("tc") or request.GET.get("tracking_code")
    if not tc:
        raise Http404("tc is required")

    try:
        b = bank_models.Bank.objects.get(tracking_code=str(tc))
    except bank_models.Bank.DoesNotExist:
        raise Http404("Bank record not found")

    factory = BankFactory()
    amount = int(getattr(b, "amount", 0) or 0)

    callback_url = getattr(b, "callback_url", None) or (
        getattr(settings, "PAY_CALLBACK_URL", None)
        or (getattr(settings, "PAYMENTS", {}) or {}).get("CALLBACK_URL")
        or (getattr(settings, "AZ_IRANIAN_BANK_GATEWAYS", {}) or {}).get("CALLBACK_URL")
        or request.build_absolute_uri("/bankgateways/callback/")
    )

    bank = _bankfactory_create_from_record(
        factory=factory,
        bank_type_value=b.bank_type,
        request=request,
        amount=amount,
        callback_url=callback_url,
    )

    bank._bank = b

    try:
        bank.set_amount(int(b.amount or 0))
    except Exception:
        bank._amount = int(b.amount or 0)

    def _has_db_token(obj) -> bool:
        t = getattr(obj, "token", None)
        if t:
            return True
        extra = getattr(obj, "extra_information", None) or getattr(obj, "extra", None)
        return isinstance(extra, dict) and bool(extra.get("token"))

    if not _has_db_token(b):
        log.warning("No token in DB for tc=%s; generating token via bank.ready()", tc)
        try:
            b.created_at = timezone.now()
            b.save(update_fields=["created_at"])
        except Exception:
            b.created_at = timezone.now()
            b.save()
        bank._bank = b
        bank.ready()

    try:
        return bank.redirect_gateway()
    except BankGatewayTokenExpired:
        log.warning("Token expired for tc=%s; regenerating via bank.ready()", tc)
        try:
            b.created_at = timezone.now()
            b.save(update_fields=["created_at"])
        except Exception:
            b.created_at = timezone.now()
            b.save()
        bank._bank = b
        bank.ready()
        return bank.redirect_gateway()
    except AmountDoesNotSupport:
        log.exception("AmountDoesNotSupport tc=%s amount=%s", tc, getattr(b, "amount", None))
        raise


# ─────────────────── Create Intent / StartPayment / GatewayCallbackView ───────────────────
# ✅ ادامه فایل شما بدون تغییر (همان کدی که فرستادی) …


# ─────────────────── Create Intent ───────────────────

@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def create_intent(request):
    ser = InitiateSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data

    style = (data.get("style") or "kyorugi").lower()

    # ✅ amount از serializer باید ریال باشد
    base_amount = int(data["amount"])

    # 🔒 Guard ریال: مبالغ کمتر از 10,000 احتمالاً تومان هستند
    if base_amount < 10_000:
        raise ValidationError("amount باید به ریال ارسال شود (عدد خیلی کوچک است).")
    


    competition = None

    comp_id = data.get("competition_id")
    comp_public = data.get("competition_public_id") or data.get("competition") or ""

    # -------- پیدا کردن مسابقه بر اساس style --------
    if style == "kyorugi":
        if comp_id:
            competition = get_object_or_404(KyorugiCompetition, pk=comp_id)
        elif comp_public:
            competition = get_object_or_404(KyorugiCompetition, public_id=comp_public)
    elif style == "poomsae":
        if comp_id:
            competition = get_object_or_404(PoomsaeCompetition, pk=comp_id)
        elif comp_public:
            competition = get_object_or_404(PoomsaeCompetition, public_id=comp_public)
    else:
        competition = None

    # پیش‌فرض بدون تخفیف
    final_amount = base_amount
    dc_obj = None
    discount_amount = 0

    # اگر مسابقه و کد تخفیف داریم → تلاش برای اعمال تخفیف
    if data.get("discount_code"):
        try:
            log.info(
                "DISCOUNT_TRY comp=%s user=%s code=%s base=%s style=%s",
                getattr(competition, "id", None),
                getattr(request.user, "id", None),
                data.get("discount_code"),
                base_amount,
                style,
            )

            final_amount, dc_obj, discount_amount = apply_discount_for_competition(
                competition=competition,
                coach_user=request.user,
                base_amount=base_amount,  # ریال
                code_str=data.get("discount_code"),
            )
            
            # 🔒 sanity check + enforce ریال
            try:
                final_amount = int(final_amount)
                discount_amount = int(discount_amount)
            except (TypeError, ValueError):
                raise ValidationError("مقادیر تخفیف نامعتبر است (amount قابل تبدیل به عدد نیست).")
            
            # مبلغ نهایی نباید منفی شود
            if final_amount < 0:
                raise ValidationError("amount نهایی منفی شد (خطای محاسبه تخفیف).")
            
            # مبلغ تخفیف نباید منفی باشد
            if discount_amount < 0:
                raise ValidationError("discount_amount نامعتبر است.")
            
            # مبلغ نهایی نباید از مبلغ پایه بیشتر باشد
            if final_amount > base_amount:
                raise ValidationError("amount نهایی از مبلغ اولیه بیشتر شد (خطای تخفیف).")
            
            # 🔒 Guard واحد پول (ریال)
            # اگر مبلغ خیلی کوچک است، احتمالاً تومان ارسال شده
            if final_amount > 0 and final_amount < 10_000:
                raise ValidationError("amount نهایی باید به ریال باشد (عدد بسیار کوچک است).")


            log.info(
                "DISCOUNT_RESULT comp=%s user=%s code=%s final=%s disc=%s dc_id=%s",
                getattr(competition, "id", None),
                getattr(request.user, "id", None),
                data.get("discount_code"),
                final_amount,
                discount_amount,
                getattr(dc_obj, "id", None),
            )

        except ValidationError as e:
            log.warning(
                "DISCOUNT_INVALID comp=%s user=%s code=%s err=%s",
                getattr(competition, "id", None),
                getattr(request.user, "id", None),
                data.get("discount_code"),
                str(e),
            )
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            log.exception(
                "DISCOUNT_UNEXPECTED_ERROR comp=%s user=%s code=%s err=%s",
                getattr(competition, "id", None),
                getattr(request.user, "id", None),
                data.get("discount_code"),
                str(e),
            )
            return Response(
                {"detail": "internal discount error", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    intent = PaymentIntent.objects.create(
        user=request.user,
        # در حال حاضر فیلد competition فقط به KyorugiCompetition وصل است
        competition=competition if isinstance(competition, KyorugiCompetition) else None,
        amount=int(final_amount),
        original_amount=base_amount,
        discount_code=dc_obj,
        discount_amount=discount_amount,
        description=data.get("description", ""),
        callback_url=(data.get("callback_url") or _return_url()),

        gateway=_normalize_gateway_name(data.get("gateway")),
    )

    log.info(
        "NEW_INTENT pid=%s user=%s style=%s amount=%s orig=%s disc=%s code=%s gateway=%s",
        intent.public_id,
        getattr(request.user, "id", None),
        style,
        intent.amount,
        intent.original_amount,
        intent.discount_amount,
        intent.discount_code_id,
        intent.gateway,
    )

    return Response(
        {
            "public_id": intent.public_id,
            "amount": intent.amount,
            "original_amount": intent.original_amount,
            "discount_amount": intent.discount_amount,
            "discount_code": intent.discount_code.code if intent.discount_code else None,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def create_payment_link(request, public_id):
    intent = get_object_or_404(PaymentIntent, public_id=public_id, user=request.user)

    # اگر پرداخت شده بود، همان صفحه نتیجه را بده
    if intent.status == "paid":
        return_url = intent.callback_url or _return_url()
        sep = "&" if "?" in (return_url or "") else "?"
        return Response(
            {"already_paid": True,
             "payment_url": f"{return_url}{sep}ok=1&pid={intent.public_id}&ref={intent.ref_id or ''}"},
            status=200,
        )

    lt = intent.issue_payment_link(minutes=10)
    url = request.build_absolute_uri(f"/api/payments/start/{intent.public_id}/?lt={lt}")
    return Response({"payment_url": url}, status=200)


# ─────────────────── Start Payment ───────────────────

class StartPaymentView(APIView):
    # مهم: این endpoint نباید public باشد (خطر hijack و تغییر callback)
    permission_classes = [permissions.IsAuthenticated]

    def _pick_gateway(self, raw_from_req: Optional[str]) -> str:
        gw = _normalize_gateway_name(raw_from_req)
        if not settings.DEBUG and not _payments_dummy():
            return "sadad"
        return gw or "sadad"

    def _begin(self, request, public_id, gw_final, cb_from_client):
        if not _payments_enabled() and gw_final != "dummy":
            return None, Response({"detail": "payments disabled"}, status=403)

        intent = get_object_or_404(
            PaymentIntent.objects.select_for_update(),
            public_id=public_id,
            user=request.user,  # مالکیت
        )

        if intent.status == "paid":
            return_url = intent.callback_url or _return_url()
            sep = "&" if "?" in (return_url or "") else "?"
            redirect_url = f"{return_url}{sep}ok=1&pid={intent.public_id}&ref={intent.ref_id or ''}"
            return None, Response({"already_paid": True, "redirect_url": redirect_url})

        if intent.status == "redirected" and intent.token:
            continue_url = _continue_gateway_url(request, intent.token)
            return None, Response(
                {"already_redirected": True, "redirect_url": continue_url},
                status=409,
            )

        if intent.status not in ("initiated", "failed", "redirected"):
            return None, Response(
                {"detail": f"invalid status: {intent.status}"},
                status=409,
            )

        # callback_url از کلاینت (اختیاری) — validate کامل‌تر
        if cb_from_client:
            u = urlparse(cb_from_client)
            if u.scheme not in ("http", "https") or not u.netloc:
                return None, Response({"detail": "invalid callback_url"}, status=400)
            if not _callback_allowed(u.netloc):
                return None, Response({"detail": "callback_url not allowed"}, status=400)
            intent.callback_url = cb_from_client

        intent.initiator_ip = _client_ip(request)
        intent.user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:255]
        intent.gateway = gw_final
        intent.save(
            update_fields=[
                "callback_url",
                "initiator_ip",
                "user_agent",
                "gateway",
                "updated_at",
            ]
        )
        return intent, None

    def post(self, request, public_id):
        gw_final = self._pick_gateway(request.data.get("gateway"))
        cb_from_client = (request.data.get("callback_url") or "").strip()

        with transaction.atomic():
            intent, err = self._begin(request, public_id, gw_final, cb_from_client)
            if err:
                return err

        return self._dispatch_to_gateway(request, intent)

    def get(self, request, public_id):
        gw_final = self._pick_gateway(request.GET.get("gateway"))
        cb_from_client = (request.GET.get("callback_url") or "").strip()

        with transaction.atomic():
            intent, err = self._begin(request, public_id, gw_final, cb_from_client)
            if err:
                return err

        return self._dispatch_to_gateway(request, intent)

    # ───────── Dispatch Payment ─────────
    def _dispatch_to_gateway(self, request, intent: PaymentIntent):
        # رایگان
        if int(intent.amount or 0) <= 0:
            with transaction.atomic():
                intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
                intent.ref_id = intent.ref_id or "FREE-0-RIAL"

                intent.mark_paid(ref_id=intent.ref_id, card_pan="", extra={"free": True})

            return_url = intent.callback_url or _return_url()
            sep = "&" if "?" in (return_url or "") else "?"
            redirect_url = f"{return_url}{sep}ok=1&pid={intent.public_id}&ref={intent.ref_id}"

            return Response(
                {
                    "gateway": "free",
                    "redirect_url": redirect_url,
                    "public_id": intent.public_id,
                    "ref_id": intent.ref_id,
                }
            )

        # DUMMY
        if intent.gateway == "dummy":
            with transaction.atomic():
                intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
                intent.ref_id = intent.ref_id or "DUMMY-REF"
                intent.card_pan = intent.card_pan or "603799******0000"
                intent.mark_paid(
                    ref_id=intent.ref_id,
                    card_pan=intent.card_pan,
                    extra={"gateway": "dummy"},
                )

            return_url = intent.callback_url or _return_url()
            redirect_url = f"{return_url}?ok=1&pid={intent.public_id}&ref={intent.ref_id}"
            return Response(
                {
                    "gateway": "dummy",
                    "redirect_url": redirect_url,
                    "public_id": intent.public_id,
                    "ref_id": intent.ref_id,
                }
            )

        # ───────── SADAD (BMI) ─────────
        if intent.gateway in ("sadad", "bmi"):

            if not _sadad_creds_ok():
                return Response(
                    {"detail": "SADAD credentials not configured."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            # ✅ 1) ReturnUrl بانک: اینجا برمی‌گردد (بدون نیاز به tc در QueryString)
            bank_return_path = reverse("payments:bank_return", kwargs={"public_id": intent.public_id})
            bank_return_abs = request.build_absolute_uri(bank_return_path)

            # ✅ 2) مقصد نهایی بعد از verify: صفحه فرانت / کارت‌ها
            return_url = intent.callback_url or _return_url()
            if (return_url or "").startswith("/"):
                client_callback_abs = request.build_absolute_uri(return_url)
            else:
                client_callback_abs = return_url

            # مبلغ به ریال
            amount_riyal = int(intent.amount)

            # 🔒 Guard نهایی
            if amount_riyal < 10_000:
                log.error(
                    "AMOUNT_TOO_SMALL_FOR_BANK pid=%s amount=%s",
                    intent.public_id,
                    amount_riyal,
                )
                return Response(
                    {"detail": "invalid amount (must be rials)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # شماره موبایل کاربر (در صورت وجود)
            mobile = None
            if getattr(intent, "user", None):
                mobile = getattr(intent.user, "phone", None) or getattr(
                    intent.user, "phone_number", None
                )

            try:
                _bridge_bank_gateways_to_enum()

                factory = BankFactory()
                sadad_type = getattr(bank_models.BankType, "SADAD", None)
                bank_type = sadad_type or bank_models.BankType.BMI

                bank = factory.create(
                    bank_type=bank_type,
                    request=request,
                    amount=amount_riyal,
                    callback_url=bank_return_abs,  # ✅ کلید اصلی حل 404
                    mobile_number=mobile,
                )

                # ✅ کلید اصلی برای اینکه بعد از verify، کاربر به فرانت برگردد
                try:
                    bank.set_client_callback_url(client_callback_abs)
                except Exception:
                    try:
                        b_obj = getattr(bank, "_bank", None)
                        if b_obj is not None:
                            setattr(b_obj, "client_callback_url", client_callback_abs)
                            b_obj.save()
                    except Exception:
                        pass

                bank_record = bank.ready()

                # ✅ خروجی استاندارد برای ارسال مستقیم به بانک
                gateway = bank.get_gateway()  # dict شامل url/method/params
                try:
                    log.warning("SADAD_GATEWAY url=%s method=%s", gateway.get("url"), gateway.get("method"))
                    log.warning("SADAD_GATEWAY data=%s", gateway.get("data"))
                except Exception:
                    pass

                with transaction.atomic():
                    intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
                    intent.token = bank_record.tracking_code  # tc
                    intent.ref_id = intent.ref_id or str(bank_record.id)
                    intent.status = "redirected"
                    intent.save(update_fields=["token", "ref_id", "status", "updated_at"])

                return Response(
                    {
                        "gateway": "sadad",
                        "payment": gateway,
                        "token": intent.token,
                        "public_id": intent.public_id,
                    },
                    status=200,
                )

            except AZBankGatewaysException as e:
                log.exception("SADAD_INIT_FAILED pid=%s err=%s", intent.public_id, str(e))
                with transaction.atomic():
                    intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
                    intent.status = "failed"
                    intent.save(update_fields=["status", "updated_at"])
                return Response(
                    {"detail": "payment init failed", "error": str(e)},
                    status=502,
                )
            except Exception as e:
                log.exception("SADAD_UNEXPECTED_ERROR pid=%s err=%s", intent.public_id, str(e))
                with transaction.atomic():
                    intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
                    intent.status = "failed"
                    intent.save(update_fields=["status", "updated_at"])
                return Response(
                    {"detail": "unexpected error", "error": str(e)},
                    status=500,
                )

        # اگر به هیچ گیت‌وی‌ای نخورد
        return Response({"detail": "unsupported gateway"}, status=400)




# ─────────────────── Gateway Callback (اختیاری/فعلی شما) ───────────────────

@method_decorator(csrf_exempt, name="dispatch")
class GatewayCallbackView(APIView):
    permission_classes = [permissions.AllowAny]

    def _handle_sadad(self, request):
        tracking_param = gw_settings.TRACKING_CODE_QUERY_PARAM
        tracking = request.GET.get(tracking_param) or request.POST.get(tracking_param)
        pid = request.GET.get("pid") or request.POST.get("pid")

        if not tracking:
            return Response({"detail": "tracking code not found"}, status=400)

        # 1) رکورد بانک از روی tc
        try:
            bank_record = bank_models.Bank.objects.get(tracking_code=tracking)
        except bank_models.Bank.DoesNotExist:
            return Response({"detail": "bank record not found"}, status=404)

        intent = None

        # 2) اگر pid (public_id) همراه درخواست باشد
        if pid:
            intent = PaymentIntent.objects.filter(public_id=pid).first()

        # 3) از روی token = tracking_code
        if not intent:
            intent = PaymentIntent.objects.filter(token=tracking).first()

        # 4) از روی ref_id = id بانک
        if not intent:
            intent = PaymentIntent.objects.filter(ref_id=str(bank_record.id)).first()

        if not intent:
            return Response(
                {"detail": "intent not found", "pid": pid, "tc": tracking},
                status=404,
            )

        return_url = intent.callback_url or _return_url()

        if bank_record.is_success:
            info = bank_record.extra_information or {}
            masked_pan = None
            if isinstance(info, dict):
                masked_pan = (
                    info.get("card_pan")
                    or info.get("maskedPan")
                    or info.get("CardNoMasked")
                    or info.get("CardNumberMasked")
                    or info.get("cardNumberMasked")
                )

            ref_from_bank = (
                getattr(bank_record, "reference_number", None)
                or getattr(bank_record, "bank_track_id", None)
                or bank_record.tracking_code
            )

            with transaction.atomic():
                intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
                intent.ref_id = ref_from_bank or intent.ref_id
                if masked_pan:
                    intent.card_pan = masked_pan
                intent.extra = {
                    "bank": {
                        "status": getattr(bank_record, "status", None),
                        "ref": ref_from_bank,
                        "extra_information": bank_record.extra_information,
                    }
                }
                intent.mark_paid(ref_id=intent.ref_id, card_pan=intent.card_pan, extra=intent.extra)

            sep = "&" if "?" in (return_url or "") else "?"
            return HttpResponseRedirect(
                f"{return_url}{sep}ok=1&pid={intent.public_id}&ref={intent.ref_id or ''}"
            )

        # پرداخت ناموفق
        ref_from_bank = (
            getattr(bank_record, "reference_number", None)
            or getattr(bank_record, "bank_track_id", None)
            or bank_record.tracking_code
        )

        with transaction.atomic():
            intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
            intent.status = "failed"
            intent.extra = {
                "bank": {
                    "status": getattr(bank_record, "status", None),
                    "ref": ref_from_bank,
                    "extra_information": bank_record.extra_information,
                }
            }
            intent.save(update_fields=["status", "extra", "updated_at"])

        sep = "&" if "?" in (return_url or "") else "?"
        return HttpResponseRedirect(f"{return_url}{sep}ok=0&pid={intent.public_id}")

    def get(self, request, gateway_name="fake"):
        if gateway_name == "sadad":
            return self._handle_sadad(request)
        return Response({"detail": "unsupported callback"}, status=400)

    def post(self, request, gateway_name="fake"):
        if gateway_name == "sadad":
            return self._handle_sadad(request)
        return Response({"detail": "unsupported callback"}, status=400)



