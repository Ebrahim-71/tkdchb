# --- stdlib
import logging
import json
import re
from collections import defaultdict
from typing import Optional  # ✅ سازگاری پایتون < 3.10
import base64  # optional اگر لازم شد

# زمان/تاریخ
from datetime import date as _date, datetime as _datetime, time as _time, timedelta

logger = logging.getLogger(__name__)

from typing import Set  # بالای فایل کنار typing ها اضافه کن

# بالای فایل کنار ایمپورت‌ها
from rest_framework.exceptions import ValidationError as DRFValidationError

import jdatetime

from django.db.models import Exists, OuterRef, Q

from decimal import Decimal
from uuid import UUID





# --- Django / DRF
from django.conf import settings
from django.core.exceptions import FieldError, ValidationError
from django.db import transaction, IntegrityError
from django.db import models as djm
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import views, generics, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

# --- Project models
from accounts.models import UserProfile, TkdClub, TkdBoard
from .models import (
    KyorugiCompetition, CoachApproval, Enrollment, Draw, Match,
    WeightCategory, BeltGroup, Belt, KyorugiResult, Seminar, SeminarRegistration, GroupRegistrationPayment,
    PoomsaeCompetition, PoomsaeCoachApproval, PoomsaeEnrollment,AgeCategory,

)

from payments.models import PaymentIntent


# --- Project permissions
from .permissions import IsCoach, IsPlayer

# --- Project serializers / helpers
from .serializers import (
     KyorugiCompetitionDetailSerializer,
     CompetitionRegistrationSerializer,
     EnrollmentCardSerializer,
     KyorugiBracketSerializer,
     EnrollmentLiteSerializer,DrawWithMatchesSerializer,
     _norm_belt, _player_belt_code_from_profile, _norm_gender, _allowed_belts,
     SeminarSerializer, SeminarRegistrationSerializer, SeminarCardSerializer,PoomsaeEnrollmentCardSerializer,
     DashboardAnyCompetitionSerializer, PoomsaeCompetitionDetailSerializer, PoomsaeRegistrationSerializer
)

CARD_READY_STATUSES = {"paid", "confirmed", "approved", "accepted", "completed"}

# ✅ کارت آماده نمایش؟
def _can_show_card(status: str, is_paid: bool = False) -> bool:
    s = (status or "").lower()
    return bool(is_paid or (s in CARD_READY_STATUSES))
# ------------------------------------------------------------------------------------
# Helpers (local)
# ------------------------------------------------------------------------------------

def jsonable(obj):
    # ✅ چون شما date/datetime را با alias ایمپورت کرده‌اید
    if isinstance(obj, (_datetime, _date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(x) for x in obj]
    return obj



def _birth_jalali_from_profile(p: UserProfile) -> str:
    g = _player_birthdate_to_gregorian(p)
    if not g:
        return ""
    try:
        return jdatetime.date.fromgregorian(date=g).strftime("%Y/%m/%d")
    except Exception:
        return ""

def _poomsae_user_eligible(user, comp):
    """صلاحیت بازیکن برای پومسه: جنسیت + بازه‌های سنی (M2M و FK) + کمربند."""
    prof = UserProfile.objects.filter(user=user, role__in=["player","both"])\
                              .only("gender","birth_date","belt_grade").first()
    if not prof:
        return False

    # جنسیت
    req_gender = _required_gender_for_comp(comp)
    gender_ok  = (req_gender in (None, "", "both")) or (_gender_norm(prof.gender) == req_gender)

    # سن
    wins = []
    try:
        wins += [(ac.from_date, ac.to_date) for ac in comp.age_categories.all()]
    except Exception:
        pass
    if not wins and getattr(comp, "age_category_id", None):
        ac = comp.age_category
        wins = [(ac.from_date, ac.to_date)]

    bd = _player_birthdate_to_gregorian(prof)
    age_ok = True if not wins else bool(bd and any(fr and to and fr <= bd <= to for fr, to in wins))

    # کمربند
    allowed_codes = set(_allowed_belts(comp))
    player_code   = _player_belt_code_from_profile(prof)
    belt_ok = True if not allowed_codes else bool(player_code and player_code in allowed_codes)

    return bool(gender_ok and age_ok and belt_ok)

def _age_groups_display_for(comp) -> str:
    names = []
    try:
        if hasattr(comp, "age_categories") and comp.age_categories.exists():
            names = list(comp.age_categories.values_list("name", flat=True))
    except Exception:
        pass
    if not names:
        ac = getattr(comp, "age_category", None)
        if ac:
            nm = getattr(ac, "name", None)
            if nm:
                names = [nm]
    return "، ".join([n for n in names if n]) if names else ""

def _uniq_preserve(seq):
    seen, out = set(), []
    for x in seq:
        s = (x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out

def _detect_role_and_profile(request):
    prof = UserProfile.objects.filter(user=request.user).first()
    if prof and prof.role:
        return (prof.role or "").lower(), prof
    if TkdClub.objects.filter(user=request.user).exists():
        return "club", None
    if request.user.groups.filter(name__iexact="heyat").exists():
        return "heyat", None
    if request.user.groups.filter(name__iexact="board").exists():
        return "board", None
    return "", prof

def registration_open_effective(obj):
    """
    True/False بر اساس:
    1) registration_manual
    2) در غیر این صورت، چک بازه زمانی (Date یا DateTime) با یکدست‌سازی آگاهی زمانی
    """
    try:
        manual = getattr(obj, "registration_manual", None)
        if manual is True:
            return True
        if manual is False:
            return False

        # تشخیص نوع فیلد
        try:
            f = obj._meta.get_field("registration_start")
            is_dt = isinstance(f, djm.DateTimeField)
        except Exception:
            is_dt = False

        rs = getattr(obj, "registration_start", None)
        re_ = getattr(obj, "registration_end", None)
        if not (rs and re_):
            return False

        if is_dt:
            nowv = timezone.now()
            # آگاه کردن datetime‌های نا‌آگاه
            if isinstance(rs, _datetime) and timezone.is_naive(rs):
                rs = timezone.make_aware(rs, timezone.get_current_timezone())
            if isinstance(re_, _datetime) and timezone.is_naive(re_):
                re_ = timezone.make_aware(re_, timezone.get_current_timezone())
        else:
            nowv = timezone.localdate()

        return bool(rs <= nowv <= re_)
    except Exception:
        return False

def _opened(qs, only_open: bool):
    if not only_open:
        return qs
    Model = qs.model
    fields = {f.name: f for f in Model._meta.get_fields() if hasattr(f, "attname")}
    needed = {"registration_manual", "registration_start", "registration_end"}
    if not needed.issubset(fields.keys()):
        return qs

    has_dt = isinstance(fields.get("registration_start"), djm.DateTimeField)
    if has_dt:
        nowdt = timezone.now()
        open_q = (
            Q(registration_manual=True) |
            (Q(registration_manual__isnull=True) &
             Q(registration_start__lte=nowdt) &
             Q(registration_end__gte=nowdt))
        )
    else:
        today = timezone.localdate()
        open_q = (
            Q(registration_manual=True) |
            (Q(registration_manual__isnull=True) &
             Q(registration_start__lte=today) &
             Q(registration_end__gte=today))
        )
    return qs.filter(open_q)

def _dashboard_base_qs(role, profile, only_open):
    ky_qs = KyorugiCompetition.objects.all()
    po_qs = PoomsaeCompetition.objects.all()

    if role == "player":
        if not (profile and profile.coach):
            return KyorugiCompetition.objects.none(), PoomsaeCompetition.objects.none()

        ky_qs = ky_qs.filter(
            coach_approvals__coach=profile.coach,
            coach_approvals__is_active=True,
            coach_approvals__terms_accepted=True,
        ).distinct()
        # پومسه: approved (نه terms_accepted)
        try:
            po_qs = po_qs.filter(
                coach_approvals__coach=profile.coach,
                coach_approvals__is_active=True,
                coach_approvals__approved=True,
            ).distinct()
        except FieldError:
            po_qs = po_qs.filter(
                coach_approvals__coach=profile.coach,
                coach_approvals__is_active=True,
            ).distinct()

        return _opened(ky_qs, only_open), _opened(po_qs, only_open)

    if role == "referee":
        return _opened(ky_qs, True), _opened(po_qs, True)

    return _opened(ky_qs, only_open), _opened(po_qs, only_open)

def _to_aware_dt(v):
    if v is None:
        return timezone.now()
    if isinstance(v, _date) and not isinstance(v, _datetime):
        v = _datetime.combine(v, _time.min)
    if timezone.is_naive(v):
        v = timezone.make_aware(v, timezone.get_current_timezone())
    return v

def _order_items(items):
    def _key(x):
        v = (getattr(x, "created_at", None)
             or getattr(x, "competition_date", None)
             or getattr(x, "event_date", None))
        v = _to_aware_dt(v)
        return v.timestamp()
    return sorted(items, key=_key, reverse=True)

def _get_comp_by_key(key):
    s = str(key).strip()
    qs = KyorugiCompetition.objects.all()
    if s.isdigit():
        obj = qs.filter(id=int(s)).first()
        if obj:
            return obj
    obj = qs.filter(public_id__iexact=s).first()
    if obj:
        return obj
    raise Http404("KyorugiCompetition not found")

def _get_comp_by_key_any(key):
    s = str(key).strip()
    try:
        return _get_comp_by_key(key)
    except Http404:
        pass
    if s.isdigit():
        obj = PoomsaeCompetition.objects.filter(id=int(s)).first()
        if obj:
            return obj
    obj = PoomsaeCompetition.objects.filter(public_id__iexact=s).first()
    if obj:
        return obj
    try:
        obj = PoomsaeCompetition.objects.filter(slug__iexact=s).first()
        if obj:
            return obj
    except Exception:
        pass
    raise Http404("Competition not found")

def _required_gender_for_comp(comp):
    g = getattr(comp, "gender", None)
    if not g:
        return None
    t = str(g).strip().lower().replace("‌", "").replace("-", "")
    mapping = {
        "m": "male", "male": "male", "man": "male", "آقا": "male", "اقا": "male", "مرد": "male", "آقایان": "male",
        "f": "female", "female": "female", "woman": "female", "زن": "female", "خانم": "female", "بانوان": "female",
        "both": "both", "mixed": "both", "مختلط": "both", "هر دو": "both", "هردو": "both",
    }
    return mapping.get(t, t)

def _gender_norm(val):
    m = {
        "male":"male","m":"male","man":"male","boy":"male","مرد":"male","آقا":"male",
        "female":"female","f":"female","woman":"female","girl":"female","زن":"female","خانم":"female",
        "both":"both","mix":"both", "":None, None:None
    }
    return m.get(str(val).strip().lower(), None)

def _parse_jalali_ymd(s: str) -> Optional[_date]:  # ✅ Optional
    if not s:
        return None
    t = re.sub(r"[\u200e\u200f\u200c\u202a-\u202e]", "", str(s))
    t = t.replace("-", "/")
    t = t.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩","01234567890123456789"))
    m = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", t)
    if not m: return None
    jy, jm, jd = map(int, m.groups())
    try:
        g = jdatetime.date(jy, jm, jd).togregorian()
        return _date(g.year, g.month, g.day)
    except Exception:
        return None

def _player_birthdate_to_gregorian(p: UserProfile):
    return _parse_jalali_ymd(p.birth_date)

def _allowed_belt_names_for_comp(comp: KyorugiCompetition):
    if comp.belt_groups.exists():
        belts = set()
        qs = BeltGroup.objects.filter(id__in=comp.belt_groups.values_list("id", flat=True)).prefetch_related("belts")
        for g in qs:
            belts.update(list(g.belts.values_list("name", flat=True)))
        return belts
    if comp.belt_level == "yellow_blue":
        return {"سفید", "زرد", "سبز", "آبی"}
    if comp.belt_level == "red_black":
        return {"قرمز"} | {f"مشکی دان {i}" for i in range(1, 11)}
    return {"سفید", "زرد", "سبز", "آبی", "قرمز"} | {f"مشکی دان {i}" for i in range(1, 11)}

def _age_ok_for_comp(p: UserProfile, comp: KyorugiCompetition):
    bd = _player_birthdate_to_gregorian(p)
    if not bd:
        return False
    cat = comp.age_category
    if not cat:
        return True
    return (cat.from_date <= bd <= cat.to_date)

def _find_weight_category_for(comp: KyorugiCompetition, gender: str, declared_weight: float):
    ids = comp.allowed_weight_ids()
    if not ids:
        return None
    qs = WeightCategory.objects.filter(id__in=ids, gender=gender).order_by("min_weight")
    for wc in qs:
        # اگر متد includes_weight در مدل داری، از اون استفاده کن؛ وگرنه این شرط را نگه دار:
        try:
            if hasattr(wc, "includes_weight") and callable(wc.includes_weight):
                if wc.includes_weight(float(declared_weight)):
                    return wc
            else:
                tol = getattr(wc, "tolerance", 0) or 0
                lo = (wc.min_weight or 0) - tol if wc.min_weight is not None else float("-inf")
                hi = (wc.max_weight or 0) + tol if wc.max_weight is not None else float("inf")
                if lo <= float(declared_weight) <= hi:
                    return wc
        except Exception:
            continue
    return None

def _coach_from_request(request):
    return UserProfile.objects.filter(user=request.user, role__in=["coach", "both"]).first()


def _allowed_belt_names(comp: KyorugiCompetition) -> "Set[str]":
    if comp.belt_groups.exists():
        return set(
            Belt.objects.filter(beltgroup__in=comp.belt_groups.all())
            .values_list("name", flat=True)
        )
    return set(Belt.objects.values_list("name", flat=True))


def _allowed_belt_names_for_any_comp(comp):
    names = set()
    try:
        if getattr(comp, "belt_groups", None) and comp.belt_groups.exists():
            names = set(
                Belt.objects.filter(beltgroup__in=comp.belt_groups.all())
                .values_list("name", flat=True)
            )
    except Exception:
        names = set()
    if not names:
        lvl = (getattr(comp, "belt_level", "") or "").lower()
        if lvl in ("yellow_blue", "yellow-to-blue"):
            names = {"سفید", "زرد", "سبز", "آبی"}
        elif lvl in ("red_black", "red-to-black"):
            names = {"قرمز"} | {f"مشکی دان {i}" for i in range(1, 11)}
    return names

def _enr_label(e):
    if not e:
        return None
    player_name = ""
    club_name = None
    try:
        player_name = f"{getattr(e.player,'first_name','') or ''} {getattr(e.player,'last_name','') or ''}".strip()
    except Exception:
        pass
    try:
        club_name = getattr(e.club, "club_name", None) or getattr(e.club, "name", None)
    except Exception:
        pass
    label = f"{player_name} — {club_name}" if player_name and club_name else (player_name or club_name or "—")
    return {
        "enrollment_id": e.id,
        "player_name": player_name or None,
        "club_name": club_name or None,
        "label": label,
    }

# ------------------------------------------------------------------------------------
# Views
# ------------------------------------------------------------------------------------
class CompetitionDetailAnyView(views.APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.AllowAny]

    def get(self, request, key):
        comp = _get_comp_by_key_any(key)

        # ----------------------- KYORUGI -----------------------
        if isinstance(comp, KyorugiCompetition):
            ser = KyorugiCompetitionDetailSerializer(comp, context={"request": request})
            data = dict(ser.data)
            data["kind"] = "kyorugi"

            if request.user and request.user.is_authenticated:
                player = UserProfile.objects.filter(user=request.user, role__in=["player", "both"]).first()
                if player:
                    enr = (Enrollment.objects
                           .only("id","status","player_id","competition_id")
                           .filter(competition=comp, player=player)
                           .order_by("-id")
                           .first())
                    if enr:
                        data["my_enrollment"] = {"id": enr.id, "status": enr.status}
                        data["card_ready"] = _can_show_card(enr.status, getattr(enr, "is_paid", False))
                    else:
                        data["my_enrollment"] = None
                        data["card_ready"] = False

                    # ✅ my_profile با کدملی و تاریخ تولد (جلالی)
                    birth_text = _birth_jalali_from_profile(player)
                    belt_val = getattr(player, "belt_grade", "") or getattr(player, "belt_name", "") or ""
                    data["my_profile"] = {
                        "gender": player.gender,
                        "belt": belt_val,
                        "national_code": getattr(player, "national_code", "") or "",
                        "birth_date": birth_text,
                        # camelCase
                        "nationalCode": getattr(player, "national_code", "") or "",
                        "birthDate": birth_text,
                    }

            return Response(data, status=status.HTTP_200_OK)

        # ----------------------- POOMSAE -----------------------
        ser = PoomsaeCompetitionDetailSerializer(comp, context={"request": request})
        data = dict(ser.data)
        data["kind"] = "poomsae"

        _age_txt = _age_groups_display_for(comp)
        _note = "ثبت نام تیم پومسه بر عهده مربی می‌باشد"
        data["age_groups_display"] = _age_txt
        data["ageGroupsDisplay"] = _age_txt
        data["age_category_name"] = _age_txt
        data["team_registration_by"] = "coach"
        data["teamRegistrationBy"] = "coach"
        data["team_registration_note"] = _note
        data["teamRegistrationNote"] = _note

        if request.user and request.user.is_authenticated:
            coach = UserProfile.objects.filter(user=request.user, role__in=["coach", "both"]).first()
            if coach:
                appr = PoomsaeCoachApproval.objects.filter(
                    competition=comp, coach=coach, is_active=True
                ).first()
                data["my_coach_approval"] = {
                    "approved": bool(appr and appr.approved),
                    "code": appr.code if appr and appr.is_active else None,
                }

            # ✅ my_profile پومسه: national_code + DOB جلالی
            player = UserProfile.objects.filter(user=request.user, role__in=["player", "both"]) \
                .only("gender", "belt_grade", "national_code", "birth_date").first()
            if player:
                birth_text = _birth_jalali_from_profile(player)
                belt_val = getattr(player, "belt_grade", "") or getattr(player, "belt_name", "") or ""
                data["my_profile"] = {
                    "gender": player.gender,
                    "belt": belt_val,
                    "national_code": getattr(player, "national_code", "") or "",
                    "birth_date": birth_text,
                    # camelCase
                    "nationalCode": getattr(player, "national_code", "") or "",
                    "birthDate": birth_text,
                }

            data["registration_open"] = bool(comp.registration_open_effective)
            data["user_eligible_self"] = _poomsae_user_eligible(request.user, comp)

        return Response(data, status=status.HTTP_200_OK)

# ---------- جزئیات مسابقه (کیوروگی) ----------
class KyorugiCompetitionDetailView(views.APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.AllowAny]

    def get(self, request, key):
        comp = _get_comp_by_key(key)
        ser = KyorugiCompetitionDetailSerializer(comp, context={"request": request})
        data = dict(ser.data)

        if request.user and request.user.is_authenticated:
            player = UserProfile.objects.filter(user=request.user, role__in=["player", "both"]).first()
            if player:
                enr = (Enrollment.objects
                       .only("id","status","player_id","competition_id")
                       .filter(competition=comp, player=player)
                       .order_by("-id")
                       .first())
                if enr:
                    data["my_enrollment"] = {"id": enr.id, "status": enr.status}
                    data["card_ready"] = _can_show_card(enr.status, getattr(enr, "is_paid", False))
                else:
                    data["my_enrollment"] = None
                    data["card_ready"] = False

                birth_text = _birth_jalali_from_profile(player)
                belt_val = getattr(player, "belt_grade", "") or getattr(player, "belt_name", "") or ""
                data["my_profile"] = {
                    "gender": player.gender,
                    "belt": belt_val,
                    "national_code": getattr(player, "national_code", "") or "",
                    "birth_date": birth_text,
                    "nationalCode": getattr(player, "national_code", "") or "",
                    "birthDate": birth_text,
                }

        return Response(data, status=status.HTTP_200_OK)

# ---------- ثبت‌نام خودِ بازیکن ----------
class RegisterSelfView(views.APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsPlayer]

    @transaction.atomic
    def post(self, request, key):
        comp = _get_comp_by_key(key)

        if not comp.registration_open_effective:
            return Response(
                {"detail": "ثبت‌نام این مسابقه فعال نیست."},
                status=status.HTTP_400_BAD_REQUEST
            )

        player = UserProfile.objects.filter(user=request.user, role__in=["player", "both"]).first()
        if not player:
            return Response({"detail": "پروفایل بازیکن یافت نشد."}, status=status.HTTP_404_NOT_FOUND)

        existing_qs = (
            Enrollment.objects
            .filter(competition=comp, player=player)
            .exclude(status="canceled")
        )
        if existing_qs.exists():
            exist = existing_qs.order_by("-id").first()
            return Response(
                {"detail": "شما قبلاً برای این مسابقه ثبت‌نام کرده‌اید.",
                 "enrollment_id": exist.id, "status": exist.status},
                status=status.HTTP_400_BAD_REQUEST
            )

        payload = {
            "coach_code": (request.data.get("coach_code") or "").strip(),
            "declared_weight": (request.data.get("declared_weight") or "").strip(),
            "insurance_number": (request.data.get("insurance_number") or "").strip(),
            "insurance_issue_date": (request.data.get("insurance_issue_date") or "").strip(),
        }

        ser = CompetitionRegistrationSerializer(
            data=payload,
            context={"request": request, "competition": comp}
        )
        ser.is_valid(raise_exception=True)
        enrollment = ser.save()

        entry_fee_irr = int(comp.entry_fee or 0)

        simulate_paid = (not getattr(settings, "PAYMENTS_ENABLED", False)) or (entry_fee_irr == 0)
        if simulate_paid:
            out = CompetitionRegistrationSerializer(enrollment, context={"request": request}).data
            return Response(
                {"detail": "ثبت‌نام انجام شد و پرداخت آزمایشی موفق بود.",
                 "data": out, "enrollment_id": enrollment.id, "status": enrollment.status},
                status=status.HTTP_201_CREATED
            )

        return Response(
            {
                "detail": "ثبت‌نام ایجاد شد؛ نیاز به پرداخت واقعی دارید.",
                "enrollment_id": enrollment.id,
                "amount": entry_fee_irr,          # ریال
                "amount_toman": entry_fee_irr // 10,
                "payment_required": True,
            },
            status=status.HTTP_201_CREATED
        )

# ---------- وضعیت/تأیید مربی ----------
class CoachApprovalStatusView(views.APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsCoach]

    def get(self, request, key):
        comp = _get_comp_by_key_any(key)
        coach = UserProfile.objects.filter(user=request.user, role__in=["coach", "both"]).first()
        if not coach:
            return Response({"detail": "پروفایل مربی یافت نشد."}, status=404)

        approval = None
        if isinstance(comp, PoomsaeCompetition):
            approval = None
        else:
            try:
                approval = CoachApproval.objects.filter(competition=comp, coach=coach).first()
            except (ValueError, ValidationError):
                approval = None

        coach_name = f"{coach.first_name} {coach.last_name}".strip()
        club_names = []
        if getattr(coach, "club", None) and getattr(coach.club, "club_name", None):
            club_names.append(coach.club.club_name)
        if hasattr(TkdClub, "coaches"):
            club_names += list(TkdClub.objects.filter(coaches=coach).values_list("club_name", flat=True))
        if isinstance(getattr(coach, "club_names", None), list):
            club_names += [c for c in coach.club_names if c]
        club_names = _uniq_preserve(club_names)

        approved = bool(approval and approval.is_active and (approval.terms_accepted or getattr(approval, "approved", False)))
        return Response({
            "competition": {"public_id": getattr(comp, "public_id", None), "title": getattr(comp, "title", None) or getattr(comp, "name", None)},
            "approved": approved,
            "terms_accepted": bool(approval and approval.terms_accepted),
            "is_active": bool(approval and approval.is_active),
            "code": approval.code if (approval and approval.is_active) else None,
            "coach_name": coach_name,
            "club_names": club_names,
        }, status=200)

class ApproveCompetitionView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsCoach]

    @transaction.atomic
    def post(self, request, key):
        comp = _get_comp_by_key_any(key)
        if isinstance(comp, PoomsaeCompetition):
            return Response({"detail": "تأیید مربی برای پومسه هنوز به مدل جدا/جنریک وصل نشده است."}, status=400)

        coach = UserProfile.objects.filter(user=request.user, role__in=["coach", "both"]).first()
        if not coach:
            return Response({"detail": "پروفایل مربی یافت نشد."}, status=404)

        approval, _ = CoachApproval.objects.select_for_update().get_or_create(
            competition=comp, coach=coach,
            defaults={"terms_accepted": True, "is_active": True, "approved_at": timezone.now()}
        )
        changed = []
        if not approval.terms_accepted: approval.terms_accepted = True; changed.append("terms_accepted")
        if hasattr(approval, "approved") and not getattr(approval, "approved"): approval.approved = True; changed.append("approved")
        if not approval.is_active: approval.is_active = True; changed.append("is_active")
        if not approval.approved_at: approval.approved_at = timezone.now(); changed.append("approved_at")
        if changed: approval.save(update_fields=changed)

        if not approval.code:
            approval.set_fresh_code(save=True, force=True)

        return Response({"ok": True, "code": approval.code}, status=200)

class CompetitionTermsView(views.APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = [JWTAuthentication]

    def get(self, request, key):
        comp = _get_comp_by_key_any(key)
        title = getattr(getattr(comp, "terms_template", None), "title", "") or "تعهدنامه مربی"
        content = getattr(getattr(comp, "terms_template", None), "content", "") or "با ثبت تأیید، مسئولیت‌های مربی را می‌پذیرم."
        return Response({"title": title, "content": content}, status=status.HTTP_200_OK)

class PlayerCompetitionsList(views.APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsPlayer]

    def get(self, request):
        player = UserProfile.objects.filter(user=request.user, role__in=["player", "both"]).first()
        if not player or not player.coach:
            return Response([], status=200)

        base = KyorugiCompetition.objects.filter(
            coach_approvals__coach=player.coach,
            coach_approvals__is_active=True,
            coach_approvals__terms_accepted=True,
        ).distinct()

        qs = _opened(base, only_open=True)
        out = [{"public_id": c.public_id, "title": c.title, "style": "kyorugi"} for c in qs]
        return Response(out, status=200)

class RefereeCompetitionsList(views.APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        referee = UserProfile.objects.filter(user=request.user, role='referee').first()
        if not referee:
            return Response([], status=200)

        qs = _opened(KyorugiCompetition.objects.all(), only_open=True)
        return Response([{"public_id": c.public_id, "title": c.title} for c in qs], status=200)

class DashboardAllCompetitionsView(views.APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        role, profile = _detect_role_and_profile(request)
        only_open = str(request.query_params.get("only_open", "")).lower() in {"1", "true", "yes"}

        ky_qs, po_qs = _dashboard_base_qs(role, profile, only_open)
        items = _order_items([*ky_qs, *po_qs])
        ser = DashboardAnyCompetitionSerializer(items, many=True, context={"request": request})
        return Response(ser.data, status=status.HTTP_200_OK)

class DashboardKyorugiListView(views.APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        role, profile = _detect_role_and_profile(request)
        only_open = str(request.query_params.get("only_open", "")).lower() in {"1","true","yes"}

        ky_qs, _ = _dashboard_base_qs(role, profile, only_open)
        items = _order_items(list(ky_qs))

        ser = DashboardAnyCompetitionSerializer(items, many=True, context={"request": request})
        return Response(ser.data, status=status.HTTP_200_OK)

class RegisterSelfPrefillView(views.APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, key):
        comp = _get_comp_by_key(key)
        prof = UserProfile.objects.filter(user=request.user).first()
        if not prof:
            return Response(
                {"can_register": False, "detail": "پروفایل کاربر یافت نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        def _strip_phone(s: str) -> str:
            if not s:
                return ""
            t = str(s)
            t = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\u200c]", "", t)
            trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
            t_norm = t.translate(trans)
            t_norm = re.sub(r"[\s\-–—:|،]*[+(\[]?\d[\d\s\-\(\)]{6,}$", "", t_norm).strip()
            return t_norm if len(t_norm) < len(t) else t.strip()

        def _coach_name_only(p: UserProfile) -> str:
            if getattr(p, "coach", None):
                fn = getattr(p.coach, "first_name", "") or ""
                ln = getattr(p.coach, "last_name", "") or ""
                return f"{fn} {ln}".strip()
            return _strip_phone(getattr(p, "coach_name", "") or "")

        def _belt_display(p: UserProfile) -> str:
            if getattr(p, "belt_grade", None):
                return str(p.belt_grade)
            b = getattr(p, "belt", None)
            if b:
                for attr in ("name", "label", "title"):
                    v = getattr(b, attr, None)
                    if v:
                        return str(v)
                if isinstance(b, str):
                    return b
            for name in ("belt_name", "belt_label", "belt_title"):
                v = getattr(p, name, None)
                if v:
                    return str(v)
            return ""

        def _parse_birthdate_to_date(val):
            if not val:
                return None
            t = str(val).strip()
            if "T" in t:
                t = t[:10]
            t = t.replace("-", "/")
            t = t.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
            m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", t)
            if not m:
                return None
            y, m_, d = map(int, m.groups())
            try:
                if y < 1700:
                    g = jdatetime.date(y, m_, d).togregorian()
                    return _date(g.year, g.month, g.day)
                return _date(y, m_, d)
            except Exception:
                return None

        def _birth_display(p: UserProfile) -> str:
            raw = getattr(p, "birth_date", None) or getattr(p, "birthDate", None)
            if not raw:
                return ""
            g = _parse_birthdate_to_date(raw)
            if g:
                return jdatetime.date.fromgregorian(date=g).strftime("%Y/%m/%d")
            return ""

        can_register = comp.registration_open_effective
        coach_name = _coach_name_only(prof)

        club_name = ""
        if getattr(prof, "club", None):
            club_name = getattr(prof.club, "club_name", "") or getattr(prof.club, "name", "") or ""
        elif isinstance(getattr(prof, "club_names", None), list) and prof.club_names:
            club_name = "، ".join([c for c in prof.club_names if c])

        national = (
            getattr(prof, "national_code", "")
            or getattr(prof, "melli_code", "")
            or getattr(prof, "code_melli", "")
            or getattr(prof, "national_id", "")
        )

        birth_text = _birth_display(prof)
        belt_text = _belt_display(prof)

        data = {
            "competition": {
                "public_id": comp.public_id,
                "title": comp.title,
                "registration_open_effective": bool(can_register),
            },
            "can_register": bool(can_register),
            "locked": {
                "first_name": prof.first_name or getattr(request.user, "first_name", ""),
                "last_name":  prof.last_name  or getattr(request.user, "last_name",  ""),
                "national_code": national,
                "national_id":   national,
                "birth_date":    birth_text,
                "belt":          belt_text,
                "club":          club_name,
                "coach":         coach_name,

                "firstName":  prof.first_name or getattr(request.user, "first_name", ""),
                "lastName":   prof.last_name  or getattr(request.user, "last_name",  ""),
                "nationalCode": national,
                "nationalId":   national,
                "birthDate":    birth_text,
                "beltName":     belt_text,
                "coachName":    coach_name,
            },
            "suggested": {
                "weight": getattr(prof, "weight", None),
                "insurance_number": getattr(prof, "insurance_number", "") or "",
                "insurance_issue_date": getattr(prof, "insurance_issue_date", "") or "",
            },
            "need_coach_code": True,
        }
        return Response(data, status=status.HTTP_200_OK)



# یک هلسپر کوچک (جلالی)
def _to_jalali_str(d):
    if not d:
        return ""
    try:
        # اگر datetime است، به timezone محلی برگردان و فقط تاریخ را بردار
        if isinstance(d, _datetime):
            if timezone.is_naive(d):
                d = timezone.make_aware(d, timezone.get_current_timezone())
            d = timezone.localtime(d).date()
        return jdatetime.date.fromgregorian(date=d).strftime("%Y/%m/%d")
    except Exception:
        return ""

def _profile_belt_display(p):
    # اولویت با grade / سپس نام کمربند
    for name in ("belt_grade", "belt_name", "belt_label", "belt_title"):
        v = getattr(p, name, None)
        if v:
            return str(v)
    b = getattr(p, "belt", None)
    if not b:
        return ""
    # اگر فیلد رابطه‌ای بود
    for attr in ("name", "label", "title"):
        v = getattr(b, attr, None)
        if v:
            return str(v)
    # اگر رشته بود
    if isinstance(b, str):
        return b
    return ""

def _belt_group_for_player_in_comp(player, comp):
    """
    گروه کمربندی مناسبِ همین مسابقه را بر اساس کمربند بازیکن برمی‌گرداند.
    تطبیق با نرمال‌سازی (white/yellow/green/blue/red/black و «مشکی دان n»).
    """
    code = _player_belt_code_from_profile(player)  # از serializers ایمپورت شده
    if not code or not getattr(comp, "belt_groups", None):
        return None

    for g in comp.belt_groups.all().prefetch_related("belts"):
        for b in g.belts.all():
            nm = getattr(b, "name", "") or getattr(b, "label", "")
            if _norm_belt(nm) == code:  # _norm_belt از serializers
                return g
    return None

class EnrollmentCardView(views.APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _photo_url(self, request, prof):
        img = getattr(prof, "profile_image", None)
        if not img:
            return None
        url = getattr(img, "url", None) or (str(img) if img else None)
        if not url:
            return None
        if not re.match(r"^https?://", str(url)):
            try:
                url = request.build_absolute_uri(url)
            except Exception:
                pass
        return url

    def _to_jalali_str(self, d):
        if not d:
            return ""
        try:
            return jdatetime.date.fromgregorian(date=d).strftime("%Y/%m/%d")
        except Exception:
            return ""

    def _profile_belt_display(self, p):
        for name in ("belt_grade", "belt_name", "belt_label", "belt_title"):
            v = getattr(p, name, None)
            if v:
                return str(v)
        b = getattr(p, "belt", None)
        if not b:
            return ""
        for attr in ("name", "label", "title"):
            v = getattr(b, attr, None)
            if v:
                return str(v)
        return b if isinstance(b, str) else ""

    def get(self, request, enrollment_id: int):
        eid = int(enrollment_id)

        # 1) هر دو مدل را با این id امتحان کن
        candidates = []
        try:
            sr = ["player","club","board","competition","weight_category","belt_group"]
            k = Enrollment.objects.select_related(*sr).get(id=eid)
            candidates.append(("kyorugi", k))
        except Enrollment.DoesNotExist:
            pass
        try:
            sr = ["player","club","board","competition","age_category","belt_group"]
            p = PoomsaeEnrollment.objects.select_related(*sr).get(id=eid)
            candidates.append(("poomsae", p))
        except PoomsaeEnrollment.DoesNotExist:
            pass

        if not candidates:
            return Response({"detail": "No Enrollment matches the given query."},
                            status=status.HTTP_404_NOT_FOUND)

        # 2) فقط اگر خودِ بازیکن است اجازه بده
        prof  = UserProfile.objects.filter(user=request.user).first()
        club  = TkdClub.objects.filter(user=request.user).first()
        board = TkdBoard.objects.filter(user=request.user).first()

        def _allowed_for_enrollment(e) -> bool:
            # بازیکن خودش
            if getattr(e.player, "user_id", None) == request.user.id:
                return True

            # مربی (پروفایل نقش coach/both) و مالک این ثبت‌نام
            if prof:
                role = (str(getattr(prof, "role", "")) or "").lower()
                is_coachish = role in {"coach", "both"} or bool(getattr(prof, "is_coach", False))
                if is_coachish and getattr(e, "coach_id", None) == getattr(prof, "id", None):
                    return True

            # کلاب / هیئت
            if club and getattr(e, "club_id", None) == club.id:
                return True

            # بورد
            if board and getattr(e, "board_id", None) == board.id:
                return True

            return False

        chosen = None
        for kind, e in candidates:
            if _allowed_for_enrollment(e):
                chosen = (kind, e)
                break

        if not chosen:
            return Response({"detail": "اجازه دسترسی ندارید."}, status=status.HTTP_403_FORBIDDEN)


        kind, e = chosen

        # 3) کارت فقط برای وضعیت‌های آماده
        if not _can_show_card(e.status, getattr(e, "is_paid", False)):
            return Response({"detail": "هنوز پرداخت/تأیید نهایی نشده است."},
                            status=status.HTTP_403_FORBIDDEN)

        # 4) استفاده از سریالایزر مناسب
        if kind == "kyorugi":
            data = EnrollmentCardSerializer(e, context={"request": request}).data
            data["kind"] = "kyorugi"          # برای یکدست‌سازی با پومسه
            data["enrollment_id"] = e.id
            return Response(data, status=status.HTTP_200_OK)
        else:
            data = PoomsaeEnrollmentCardSerializer(e, context={"request": request}).data
            # این سریالایزر خودش فیلد kind را "poomsae" برمی‌گرداند
            data["enrollment_id"] = e.id
            return Response(data, status=status.HTTP_200_OK)


class MyEnrollmentView(views.APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, key):
        comp = _get_comp_by_key(key)

        player = UserProfile.objects.filter(user=request.user, role__in=["player", "both"]).first()
        if not player:
            return Response({"enrollment_id": None}, status=status.HTTP_200_OK)

        qs = Enrollment.objects.filter(competition=comp, player=player)

        model_field_names = {f.name for f in Enrollment._meta.get_fields()}
        sr = []
        if "division" in model_field_names:
            sr.append("division")
        if "division_weight" in model_field_names:
            sr.append("division_weight")
        if "weight_category" in model_field_names:
            sr.append("weight_category")
        if "belt_group" in model_field_names:
            sr.append("belt_group")
        if sr:
            qs = qs.select_related(*sr)

        e = qs.first()
        if not e:
            return Response({"enrollment_id": None}, status=status.HTTP_200_OK)

        can_show_card = _can_show_card(e.status, getattr(e, "is_paid", False))
        return Response(
            {"enrollment_id": e.id, "status": e.status, "can_show_card": can_show_card},
            status=status.HTTP_200_OK
        )

class KyorugiBracketView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, key):
        comp = _get_comp_by_key(key)

        # شرط انتشار (property یا فیلد تاریخی)
        is_published = bool(
            getattr(comp, "is_bracket_published", None)
            or getattr(comp, "bracket_published_at", None)
        )
        if not is_published:
            return Response({"detail": "bracket_not_ready"}, status=status.HTTP_404_NOT_FOUND)

        # فقط براکت‌هایی که هیچ مسابقهٔ واقعیِ بدون شماره ندارند
        unsafe = Match.objects.filter(
            draw=OuterRef("pk"),
            is_bye=False,
            match_number__isnull=True,
        )
        has_any_draw = comp.draws.exists()
        draws_qs = (
            Draw.objects.filter(competition=comp)
            .annotate(_has_unumbered=Exists(unsafe))
            .filter(_has_unumbered=False)
            .order_by("weight_category__min_weight", "id")
        )

        if (not has_any_draw) or (not draws_qs.exists()):
            return Response({"detail": "bracket_not_ready"}, status=status.HTTP_404_NOT_FOUND)

        # اگر از سریالایزر کلی استفاده می‌کنی:
        ser = DrawWithMatchesSerializer(draws_qs, many=True, context={"request": request})
        return Response({
            "competition": {
                "title": comp.title,
                "public_id": comp.public_id,
            },
            "draws": ser.data
        }, status=200)


# ───────── GET: لیست شاگردها با پیش‌تیک ثبت‌نام‌شده‌ها ─────────
class CoachStudentsEligibleListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsCoach]

    def get(self, request, key):
        comp = _get_comp_by_key(key)
        coach = _coach_from_request(request)
        if not coach:
            return Response({"detail": "پروفایل مربی یافت نشد."}, status=status.HTTP_404_NOT_FOUND)

        allowed_belts = _allowed_belt_names_for_comp(comp)
        req_gender = _required_gender_for_comp(comp)

        students_qs = (
            UserProfile.objects
            .filter(coach=coach, role__in=["player", "both"])
            .select_related("club", "tkd_board")
            .only(
                "id","first_name","last_name","national_code","birth_date",
                "belt_grade","gender","club","tkd_board"
            )
        )
        if req_gender in ("male","female"):
            students_qs = students_qs.filter(gender=req_gender)

        ids = list(students_qs.values_list("id", flat=True))
        existing_map = dict(
            Enrollment.objects
            .filter(competition=comp, player_id__in=ids)
            .exclude(status="canceled")
            .values_list("player_id", "status")
        )

        items = []
        for s in students_qs:
            if s.belt_grade not in allowed_belts:
                continue
            if not _age_ok_for_comp(s, comp):
                continue
            items.append({
                "id": s.id,
                "first_name": s.first_name,
                "last_name": s.last_name,
                "national_code": s.national_code,
                "birth_date": s.birth_date,
                "belt_grade": s.belt_grade,
                "belt": s.belt_grade,
                "club_name": getattr(s.club, "club_name", "") if s.club_id else "",
                "board_name": getattr(s.tkd_board, "name", "") if s.tkd_board_id else "",
                "already_enrolled": s.id in existing_map,
                "enrollment_status": existing_map.get(s.id),
            })

        belt_groups = list(comp.belt_groups.values_list("label", flat=True))

        entry_fee_irr = int(comp.entry_fee or 0)

        return Response({
            "competition": {
                "public_id": comp.public_id,
                "title": comp.title,
        
                # ✅ استانداردهای پیشنهادی برای فرانت (ریال)
                "entry_fee": entry_fee_irr,
                "entry_fee_rial": entry_fee_irr,
        
                # ✅ کلیدهای قبلی‌ات را هم نگه دار برای سازگاری عقب‌رو
                "entry_fee_irr": entry_fee_irr,
                "entry_fee_toman": entry_fee_irr // 10,
        
                "gender": comp.gender,
                "gender_display": comp.get_gender_display(),
                "age_category_name": getattr(comp.age_category, "name", None),
                "belt_groups_display": "، ".join([b for b in belt_groups if b]),
            },
            "students": items,
            "prechecked_ids": list(existing_map.keys()),
        }, status=status.HTTP_200_OK)


# ───────── POST: ثبت‌نام گروهی ─────────
class CoachRegisterStudentsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsCoach]

    # --------------------------
    # Helpers (local)
    # --------------------------
    def _split_amounts(self, total, n):
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
    def _finalize_free_or_test(self, comp, coach, payload, ref_code):
        from datetime import date as _date

        items = payload.get("items") or []
        if not items:
            return {"enrollment_ids": [], "enrollments": []}

        payable_amount = int(payload.get("payable_amount") or 0)
        per_person_paid = self._split_amounts(payable_amount, len(items))

        enrollments_out = []
        created_ids = []

        for idx, it in enumerate(items):
            pid = int(it["player_id"])
            player = UserProfile.objects.select_for_update().get(id=pid)

            declared_weight = float(it["declared_weight"])

            ins_date = it.get("insurance_issue_date")
            if isinstance(ins_date, str) and ins_date:
                ins_date = _date.fromisoformat(ins_date)

            belt_group_id = it.get("belt_group_id") or None
            weight_cat_id = it.get("weight_category_id") or None

            board_id = it.get("board_id") or None
            club_id = it.get("club_id") or None

            coach_name = f"{coach.first_name} {coach.last_name}".strip()

            e = Enrollment.objects.create(
                competition=comp,
                player=player,
                coach=coach,
                coach_name=coach_name,

                club_id=club_id,
                club_name=str(it.get("club_name") or ""),

                board_id=board_id,
                board_name=str(it.get("board_name") or ""),

                belt_group_id=belt_group_id,
                weight_category_id=weight_cat_id,

                declared_weight=declared_weight,
                insurance_number=str(it.get("insurance_number") or ""),
                insurance_issue_date=ins_date,

                discount_code=payload.get("discount_code") or None,
                discount_amount=0,
                payable_amount=int(per_person_paid[idx] if idx < len(per_person_paid) else 0),

                status="pending_payment",
                is_paid=False,
                paid_amount=0,
                bank_ref_code="",
            )

            e.mark_paid(
                amount=int(per_person_paid[idx] if idx < len(per_person_paid) else 0),
                ref_code=ref_code,
            )

            created_ids.append(e.id)
            enrollments_out.append({
                "enrollment_id": e.id,
                "status": e.status,
                "player": {"id": e.player_id, "name": f"{player.first_name} {player.last_name}".strip()},
            })

        return {"enrollment_ids": created_ids, "enrollments": enrollments_out}

    # --------------------------
    # Main endpoint
    # --------------------------
    @transaction.atomic
    def post(self, request, key):
        import re as _re
        from datetime import date as _date

        comp = _get_comp_by_key(key)
        coach = _coach_from_request(request)
        if not coach:
            return Response({"detail": "پروفایل مربی یافت نشد."}, status=404)

        if not comp.registration_open_effective:
            return Response({"detail": "ثبت‌نام این مسابقه فعال نیست."}, status=400)

        items = request.data.get("students") or []
        if not isinstance(items, list) or not items:
            return Response({"detail": "لیست شاگردان خالی است."}, status=400)

        # ---- flags / inputs ----
        preview = str(request.data.get("preview", "")).lower() in {"1", "true", "yes"}
        gateway = (request.data.get("gateway") or "sadad").strip().lower()
        discount_code_in = (request.data.get("discount_code") or "").strip()
        discount_code_in = discount_code_in or None

        # --- جلوگیری از ثبت‌نام تکراری ---
        player_ids = []
        for i in items:
            if i.get("player_id"):
                try:
                    player_ids.append(int(i.get("player_id")))
                except Exception:
                    pass

        already = set(
            Enrollment.objects.filter(competition=comp, player_id__in=player_ids)
            .exclude(status="canceled")
            .values_list("player_id", flat=True)
        )

        # --- پارس تاریخ بیمه ---
        def _parse_insurance_date(v):
            if v is None:
                return None
            t = str(v).strip()
            if "T" in t:
                t = t.split("T", 1)[0]
            t = _re.sub(r"[\u200e\u200f\u200c\u202a-\u202e]", "", t)
            t = t.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
            t = t.replace("-", "/")
            m = _re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", t)
            if not m:
                return None
            y, m_, d = map(int, m.groups())
            try:
                if y < 1700:
                    g = jdatetime.date(y, m_, d).togregorian()
                    return _date(g.year, g.month, g.day)
                return _date(y, m_, d)
            except Exception:
                return None

        created_items = []
        skipped_already = []
        errors = {}

        req_gender = _required_gender_for_comp(comp)

        for it in items:
            pid = it.get("player_id")
            if not pid:
                continue
            try:
                pid = int(pid)
            except Exception:
                continue

            if pid in already:
                skipped_already.append(pid)
                continue

            player = UserProfile.objects.filter(id=pid, role__in=["player", "both"]).first()
            if not player:
                errors[str(pid)] = "پروفایل بازیکن یافت نشد."
                continue

            if req_gender in ("male", "female") and _gender_norm(player.gender) != req_gender:
                errors[str(pid)] = "جنسیت بازیکن با مسابقه سازگار نیست."
                continue

            ins_date = _parse_insurance_date(it.get("insurance_issue_date"))
            if not ins_date:
                errors[str(pid)] = "تاریخ صدور بیمه نامعتبر است."
                continue

            if comp.competition_date and ins_date > (comp.competition_date - timedelta(days=3)):
                errors[str(pid)] = "تاریخ صدور بیمه باید حداقل ۷۲ ساعت قبل از مسابقه باشد."
                continue

            try:
                declared_weight = float(str(it.get("declared_weight")).replace(",", "."))
            except Exception:
                declared_weight = 0.0
            if declared_weight <= 0:
                errors[str(pid)] = "وزن اعلامی نامعتبر است."
                continue

            belt_group = _belt_group_for_player_in_comp(player, comp)
            if comp.belt_groups.exists() and not belt_group:
                errors[str(pid)] = "گروه کمربندی متناسب با کمربند بازیکن در این مسابقه یافت نشد."
                continue

            gender_for_wc = req_gender or _gender_norm(player.gender)
            weight_cat = _find_weight_category_for(comp, gender_for_wc, declared_weight)
            if not weight_cat:
                errors[str(pid)] = "رده وزنی مناسب با وزن اعلامی در این مسابقه یافت نشد."
                continue

            board_obj = getattr(player, "tkd_board", None)
            club_obj = getattr(player, "club", None)

            created_items.append({
                "player_id": pid,
                "declared_weight": declared_weight,
                "insurance_number": str(it.get("insurance_number") or ""),
                "insurance_issue_date": ins_date.isoformat(),  # JSON-safe

                "belt_group_id": belt_group.id if belt_group else None,
                "weight_category_id": weight_cat.id if weight_cat else None,

                "club_id": club_obj.id if club_obj else None,
                "club_name": getattr(club_obj, "club_name", "") if club_obj else "",

                "board_id": board_obj.id if board_obj else None,
                "board_name": getattr(board_obj, "name", "") if board_obj else "",
            })

        if not created_items and (not errors) and skipped_already:
            return Response({
                "detail": "همه شاگردها قبلاً ثبت‌نام شده‌اند.",
                "skipped_already_enrolled": skipped_already,
                "errors": errors,
            }, status=status.HTTP_200_OK)

        if not created_items:
            return Response({
                "detail": "هیچ ثبت‌نامی ساخته نشد.",
                "skipped_already_enrolled": skipped_already,
                "errors": errors,
            }, status=status.HTTP_400_BAD_REQUEST)

        # --- مبلغ (ریال) ---
        entry_fee_irr = int(comp.entry_fee or 0)

        # Guard ریال (اگر هنوز جایی تومان مانده باشد سریع لو می‌رود)
        # (عدد آستانه را اگر لازم داری تغییر بده)
        if entry_fee_irr > 0 and entry_fee_irr < 10_000:
            return Response(
                {"detail": "مبلغ ثبت‌نام مسابقه باید به ریال باشد (entry_fee خیلی کوچک است)."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        raw_total_irr = entry_fee_irr * len(created_items)

        # --- تخفیف واقعی + اعتبارسنجی ---
        discount_amount_irr = 0
        dc_obj = None
        if discount_code_in:
            try:
                # از payments/discounts.py استفاده می‌کنیم تا قوانین (فعال/منقضی/سقف مصرف/مربی/مسابقه) اعمال شود
                from payments.discounts import apply_discount_for_competition
                final_amount, dc_obj, discount_amount_irr = apply_discount_for_competition(
                    competition=comp,
                    coach_user=request.user,
                    base_amount=int(raw_total_irr),
                    code_str=discount_code_in,
                    commit=False,   # ⚠️ preview یا مرحله ساخت intent نباید مصرف تخفیف را ثبت کند
                    commit_use=None,
                )
                # apply_discount_for_competition ممکن است final_amount را برگرداند
                payable_amount_irr = int(final_amount)
            except Exception:
                # اگر دوست داری پیام دقیق‌تر بدهیم، باید Exceptionهای دقیق همان فایل discounts.py را اینجا هندل کنیم
                raise DRFValidationError({"discount_code": ["کد تخفیف نامعتبر یا غیرقابل استفاده است."]})
        else:
            payable_amount_irr = int(raw_total_irr)

        payable_amount_irr = max(0, int(payable_amount_irr))
        discount_amount_irr = max(0, int(discount_amount_irr))

        # --- مقادیر تومانی برای UI ---
        raw_total_toman = raw_total_irr // 10
        discount_amount_toman = discount_amount_irr // 10
        payable_amount_toman = payable_amount_irr // 10

        safe_items = created_items  # JSON-safe

        # ✅ PREVIEW: هیچ رکوردی نساز، فقط محاسبه و اعتبارسنجی کن
        if preview:
            return Response({
                "detail": "پیش‌نمایش محاسبه شد.",
                "preview": True,
                "payment_required": bool(payable_amount_irr > 0),

                "raw_total_irr": int(raw_total_irr),
                "discount_amount_irr": int(discount_amount_irr),
                "amount_irr": int(payable_amount_irr),

                "raw_total_toman": int(raw_total_toman),
                "discount_amount_toman": int(discount_amount_toman),
                "amount_toman": int(payable_amount_toman),

                "discount_code": (dc_obj.code if dc_obj else None),
                "gateway": gateway,
                "count": len(created_items),

                "skipped_already_enrolled": skipped_already,
                "errors": errors,
            }, status=200)

        # --- ساخت GroupRegistrationPayment ---
        gp = GroupRegistrationPayment.objects.create(
            coach=coach,
            competition=comp,
            payload={
                "items": safe_items,

                # تومان (UI)
                "raw_total_toman": int(raw_total_toman),
                "discount_amount_toman": int(discount_amount_toman),
                "payable_amount_toman": int(payable_amount_toman),

                # ریال (بانک)
                "raw_total": int(raw_total_irr),
                "discount_amount": int(discount_amount_irr),
                "payable_amount": int(payable_amount_irr),

                "discount_code": (dc_obj.code if dc_obj else None),
                "created_at": timezone.now().isoformat(),
            },
            total_amount=int(payable_amount_irr),  # ریال
            is_paid=False,
            bank_ref_code=None,
        )

        simulate_paid = (not getattr(settings, "PAYMENTS_ENABLED", False)) or (int(payable_amount_irr) == 0)
        if simulate_paid:
            ref = "FREE" if int(payable_amount_irr) == 0 else f"TEST-COACH-GP-{gp.id:06d}"

            result = self._finalize_free_or_test(
                comp=comp,
                coach=coach,
                payload=gp.payload,
                ref_code=ref,
            )

            gp.is_paid = True
            gp.bank_ref_code = ref
            gp.payload["enrollment_ids"] = result["enrollment_ids"]
            gp.save(update_fields=["is_paid", "bank_ref_code", "payload"])

            # ✅ اگر تخفیف داشت و این پرداخت واقعاً نهایی شد، اینجا می‌توانی مصرف را ثبت کنی (اختیاری)
            # من پیشفرض «ثبت مصرف» را خاموش گذاشتم چون باید دقیقاً با قواعد شما هماهنگ شود.
            # اگر می‌خواهی فعالش کنیم، می‌گم دقیقاً کجا و با چه شرطی انجام بدهی.

            return Response({
                "detail": "ثبت‌نام انجام و پرداخت (رایگان/آزمایشی) تأیید شد.",
                "group_payment_id": gp.id,
                "payment_required": False,

                "amount_toman": int(payable_amount_toman),
                "amount_irr": int(payable_amount_irr),

                "enrollment_ids": result["enrollment_ids"],
                "enrollments": result["enrollments"],
                "skipped_already_enrolled": skipped_already,
                "errors": errors,
            }, status=status.HTTP_201_CREATED)

        # --- پرداخت واقعی ---
        intent = PaymentIntent.objects.create(
            user=request.user,
            amount=int(payable_amount_irr),
            original_amount=int(raw_total_irr),
            description=f"Group registration GP#{gp.id}",  # ✅ کلید پیدا کردن gp در callback
            gateway=gateway,  # ✅ از ورودی
            callback_url=getattr(settings, "PAYMENTS_CALLBACK_URL", "") or "",
        )

        # اگر مدل PaymentIntent شما FK به competitions.DiscountCode دارد و می‌خواهی ذخیره شود:
        # (فقط اگر چنین فیلدی دارید؛ در کدهای قبلی‌تان ظاهراً دارید)
        try:
            if dc_obj:
                intent.discount_code = dc_obj
                intent.discount_amount = int(discount_amount_irr)
                intent.save(update_fields=["discount_code", "discount_amount"])
        except Exception:
            pass

        return Response({
            "detail": "ثبت‌نام ایجاد شد. پرداخت لازم است.",
            "payment_required": True,

            "amount_toman": int(payable_amount_toman),
            "amount_irr": int(payable_amount_irr),

            "payment_intent_public_id": intent.public_id,
            "group_payment_id": gp.id,

            "skipped_already_enrolled": skipped_already,
            "errors": errors,
        }, status=status.HTTP_201_CREATED)
            
        
                        
        



class EnrollmentCardsBulkView(views.APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ids = request.data.get("ids") or request.data.get("enrollment_ids") or []
        if not isinstance(ids, (list, tuple)):
            return Response({"detail": "ids باید آرایه باشد."}, status=400)
        ids = [int(i) for i in ids if str(i).isdigit()]

        # هر دو مدل
        kyo = {e.id: e for e in Enrollment.objects.filter(id__in=ids)}
        poo = {e.id: e for e in PoomsaeEnrollment.objects.filter(id__in=ids)}
        all_map = {**kyo, **poo}

        prof  = UserProfile.objects.filter(user=request.user).first()
        club  = TkdClub.objects.filter(user=request.user).first()
        board = TkdBoard.objects.filter(user=request.user).first()

        out_by_id = {}
        for eid, e in all_map.items():
            # مجوز
            allowed = (
                getattr(e.player, "user_id", None) == request.user.id
                or (prof and (str(getattr(prof, "role", "")).lower() in {"coach","both"} or getattr(prof,"is_coach",False)) and getattr(e,"coach_id",None) == getattr(prof,"id",None))
                or (club and getattr(e,"club_id",None) == club.id)
                or (board and getattr(e,"board_id",None) == board.id)
            )
            if not allowed:
                out_by_id[eid] = {"enrollment_id": eid, "error": "forbidden"}
                continue

            # آماده نمایش؟
            if not _can_show_card(getattr(e, "status", ""), getattr(e, "is_paid", False)):
                out_by_id[eid] = {"enrollment_id": eid, "error": "not_ready"}
                continue

            # سریالایزر مناسب
            if isinstance(e, Enrollment):
                data = EnrollmentCardSerializer(e, context={"request": request}).data
            else:
                data = PoomsaeEnrollmentCardSerializer(e, context={"request": request}).data

            data["enrollment_id"] = eid
            out_by_id[eid] = data

        # حفظ ترتیب
        out_sorted = [out_by_id[i] for i in ids if i in out_by_id]
        return Response(out_sorted, status=200)

# ------------------------------ نتایج کیوروگی ------------------------------
class KyorugiResultsView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, key):
        comp = _get_comp_by_key(key)
        qs = (
            KyorugiResult.objects
            .filter(competition=comp)
            .select_related(
                "weight_category",
                "gold_enrollment__player", "gold_enrollment__club",
                "silver_enrollment__player", "silver_enrollment__club",
                "bronze1_enrollment__player", "bronze2_enrollment__player",
                "bronze1_enrollment__club",  "bronze2_enrollment__club",
            )
            .order_by("weight_category__gender", "weight_category__min_weight", "weight_category__name")
        )

        out = []
        for r in qs:
            out.append({
                "weight": getattr(r.weight_category, "name", None) or "—",
                "gold":   _enr_label(getattr(r, "gold_enrollment", None)),
                "silver": _enr_label(getattr(r, "silver_enrollment", None)),
                "bronze1": _enr_label(getattr(r, "bronze1_enrollment", None)),
                "bronze2": _enr_label(getattr(r, "bronze2_enrollment", None)),
            })
        return Response({"results": out, "count": len(out)}, status=status.HTTP_200_OK)



def public_bracket_view(request, public_id):
    comp = KyorugiCompetition.objects.filter(public_id=public_id).first()
    if not comp:
        return Response({"detail":"not_found"}, status=404)

    # شرط انتشار
    if not comp.is_bracket_published:
        return Response({"detail":"bracket_not_ready"}, status=404)

    # فقط براکت‌های «کاملاً شماره‌گذاری‌شده»
    unsafe = Match.objects.filter(
        draw=OuterRef("pk"),
        is_bye=False,
        match_number__isnull=True,
    )
    draws_qs = (
        Draw.objects.filter(competition=comp)
        .annotate(_has_unumbered=Exists(unsafe))
        .filter(_has_unumbered=False)
        .order_by("weight_category__min_weight", "id")
    )

    data = {
        "board_logo_url": _logo_url(),
        "draws": DrawWithMatchesSerializer(draws_qs, many=True).data,  # از سریالایزر فعلی‌ات استفاده کن
    }
    return Response(data, status=200)




# ------------------------------------------------------------- سمینار -------------------------------------------------------------
class DefaultPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 100

class SeminarListView(generics.ListAPIView):
    serializer_class = SeminarSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = DefaultPagination

    def get_queryset(self):
        qs = Seminar.objects.all()

        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q) |
                Q(location__icontains=q)
            )

        role = (self.request.query_params.get("role") or "").strip().lower()
        if role and role not in ("club", "heyat"):
            if role == "both":
                wanted = {"coach", "referee"}
                ids = [
                    s.id for s in qs.only("id", "allowed_roles")
                    if not (s.allowed_roles or []) or (wanted & set(s.allowed_roles or []))
                ]
            else:
                ids = [
                    s.id for s in qs.only("id", "allowed_roles")
                    if not (s.allowed_roles or []) or (role in (s.allowed_roles or []))
                ]
            qs = qs.filter(id__in=ids)

        date_from = (self.request.query_params.get("date_from") or "").strip()
        date_to   = (self.request.query_params.get("date_to") or "").strip()
        if date_from:
            qs = qs.filter(event_date__gte=date_from)
        if date_to:
            qs = qs.filter(event_date__lte=date_to)

        open_only = self.request.query_params.get("open")
        if open_only in ("1", "true", "True"):
            today = timezone.localdate()
            qs = qs.filter(registration_start__lte=today, registration_end__gte=today)

        upcoming = self.request.query_params.get("upcoming")
        past     = self.request.query_params.get("past")
        today = timezone.localdate()
        if upcoming in ("1", "true", "True"):
            qs = qs.filter(event_date__gte=today)
        if past in ("1", "true", "True"):
            qs = qs.filter(event_date__lt=today)

        ordering = self.request.query_params.get("ordering") or "event_date"
        allowed = {"event_date", "-event_date", "created_at", "-created_at", "title", "-title"}
        if ordering not in allowed:
            ordering = "event_date"
        return qs.order_by(ordering, "id")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

class SeminarDetailView(generics.RetrieveAPIView):
    queryset = Seminar.objects.all()
    serializer_class = SeminarSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "key"
    permission_classes = [permissions.AllowAny]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

class SeminarRegisterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, key):
        seminar = get_object_or_404(Seminar, public_id=key)
        roles = request.data.get("roles") or []

        allowed = seminar.allowed_roles or []
        if allowed and not any(r in allowed for r in roles):
            return Response({"detail": "نقش شما مجاز به ثبت‌نام نیست."}, status=400)

        try:
            with transaction.atomic():
                reg, created = SeminarRegistration.objects.get_or_create(
                    seminar=seminar, user=request.user,
                    defaults={"roles": roles or [], "is_paid": False, "paid_amount": 0, "paid_at": None}
                )
        except IntegrityError:
            reg = SeminarRegistration.objects.filter(seminar=seminar, user=request.user).first()
            created = False

        return Response({
            "status": "ok",
            "created": bool(created),
            "registration_id": getattr(reg, "id", None),
            "payment_required": False,
        }, status=200)

class MySeminarRegistrationsView(generics.ListAPIView):
    serializer_class = SeminarRegistrationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = DefaultPagination

    def get_queryset(self):
        qs = SeminarRegistration.objects.select_related("seminar").filter(user=self.request.user)

        paid = self.request.query_params.get("paid")
        if paid in ("1", "true", "True"):
            qs = qs.filter(is_paid=True)
        elif paid in ("0", "false", "False"):
            qs = qs.filter(is_paid=False)

        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(seminar__title__icontains=q) |
                Q(seminar__location__icontains=q)
            )

        return qs.order_by("-created_at", "-id")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

ROLE_ALL = {"player", "coach", "referee"}

@api_view(["GET"])
@permission_classes([AllowAny])
def sidebar_seminars(request):
    role  = (request.query_params.get("role") or "player").lower()
    limit = int(request.query_params.get("limit", 6))
    show  = request.query_params.get("show", "upcoming")

    today = timezone.localdate()
    qs = Seminar.objects.all()

    if show == "open":
        qs = qs.filter(registration_start__lte=today, registration_end__gte=today).order_by("event_date", "-created_at")
    elif show == "upcoming":
        qs = qs.filter(event_date__gte=today).order_by("event_date", "-created_at")
    elif show == "past":
        qs = qs.filter(event_date__lt=today).order_by("-event_date", "-created_at")
    else:
        qs = qs.order_by("event_date", "-created_at")

    if role not in ("club", "heyat"):
        superset = list(qs[:200])

        def role_ok(s):
            allowed = (s.allowed_roles or [])
            if not allowed:
                return True
            if role == "both":
                return ("coach" in allowed) or ("referee" in allowed)
            return role in allowed

        filtered = [s for s in superset if role_ok(s)]
        qs = filtered[:limit]
        data = SeminarCardSerializer(qs, many=True, context={"request": request}).data
        return Response(data)

    qs = qs[:limit]
    data = SeminarCardSerializer(qs, many=True, context={"request": request}).data
    return Response(data)

# =============================== Poomsae specific ===============================
# =============================== Poomsae specific ===============================

# یک میکسین کوچک برای سازگاری هر دو نام پارامتر (public_id / key)
class PoomsaeKwargMixin:
    def get_public_id_from_kwargs(self, **kwargs):
        return kwargs.get("public_id") or kwargs.get("key")

class PoomsaeCoachApprovalStatusView(PoomsaeKwargMixin, APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        public_id = self.get_public_id_from_kwargs(**kwargs)
        comp = get_object_or_404(PoomsaeCompetition, public_id=public_id)

        coach = UserProfile.objects.filter(user=request.user, role__in=["coach", "both"]).first()
        if not coach:
            return Response({"detail": "پروفایل مربی یافت نشد."}, status=404)

        appr = PoomsaeCoachApproval.objects.filter(competition=comp, coach=coach, is_active=True).first()

        coach_name = f"{coach.first_name} {coach.last_name}".strip()
        club_names = []
        if getattr(coach, "club", None) and getattr(coach.club, "club_name", None):
            club_names.append(coach.club.club_name)
        if hasattr(TkdClub, "coaches"):
            club_names += list(TkdClub.objects.filter(coaches=coach).values_list("club_name", flat=True))
        if isinstance(getattr(coach, "club_names", None), list):
            club_names += [c for c in coach.club_names if c]
        club_names = _uniq_preserve(club_names)

        return Response({
            "competition": {"public_id": comp.public_id, "title": comp.name},
            "approved": bool(appr and appr.approved and appr.is_active),
            "is_active": bool(appr and appr.is_active),
            "code": appr.code if appr and appr.is_active else None,
            "coach_name": coach_name,
            "club_names": club_names,
        }, status=200)

class PoomsaeCoachApprovalApproveView(PoomsaeKwargMixin, APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsCoach]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        public_id = self.get_public_id_from_kwargs(**kwargs)
        comp = get_object_or_404(PoomsaeCompetition, public_id=public_id)

        coach = UserProfile.objects.filter(user=request.user, role__in=["coach", "both"]).first()
        if not coach:
            return Response({"detail": "پروفایل مربی یافت نشد."}, status=404)

        if not comp.registration_open_effective:
            return Response({"detail": "ثبت‌نام این مسابقه فعال نیست."}, status=400)

        appr, _ = PoomsaeCoachApproval.objects.select_for_update().get_or_create(
            competition=comp, coach=coach,
            defaults={"approved": True, "is_active": True}
        )

        changed = []
        if not appr.approved:
            appr.approved = True; changed.append("approved")
        if not appr.is_active:
            appr.is_active = True; changed.append("is_active")
        if changed:
            appr.save(update_fields=changed)

        if not appr.code:
            appr.set_fresh_code(save=True, force=True)

        return Response({"ok": True, "code": appr.code}, status=200)

class PoomsaeCompetitionDetailView(views.APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.AllowAny]

    def get(self, request, key):
        base_qs = (
            PoomsaeCompetition.objects
            .select_related("age_category")
            .prefetch_related("images", "files")
        )

        s = str(key).strip()
        if s.isdigit():
            comp = get_object_or_404(base_qs, id=int(s))
        else:
            comp = base_qs.filter(public_id__iexact=s).first() or base_qs.filter(slug__iexact=s).first()
            if not comp:
                raise Http404("PoomsaeCompetition not found")

        reg_open_effective = comp.registration_open_effective

        ser = PoomsaeCompetitionDetailSerializer(comp, context={"request": request})
        data = dict(ser.data)
        data["kind"] = "poomsae"
        data["registration_open_effective"] = bool(reg_open_effective)
        data["can_register"] = bool(reg_open_effective)

        _age_txt = _age_groups_display_for(comp)
        _note = "ثبت‌نام تیم پومسه بر عهده مربی می‌باشد"

        data.update({
            "age_groups_display": _age_txt,
            "ageGroupsDisplay": _age_txt,
            "age_category_name": _age_txt,
            "team_registration_by": "coach",
            "teamRegistrationBy": "coach",
            "team_registration_note": _note,
            "teamRegistrationNote": _note,
        })

        if request.user and request.user.is_authenticated:
            coach = UserProfile.objects.filter(user=request.user, role__in=["coach", "both"]).first()
            if coach:
                appr = PoomsaeCoachApproval.objects.filter(
                    competition=comp, coach=coach, is_active=True
                ).first()
                data["my_coach_approval"] = {
                    "approved": bool(appr and appr.approved),
                    "code": appr.code if appr and appr.is_active else None,
                }

            player = UserProfile.objects.filter(user=request.user, role__in=["player", "both"])\
                                        .only("gender","belt_grade","national_code","birth_date").first()
            if player:
                birth_text = _birth_jalali_from_profile(player)
                belt_val = getattr(player, "belt_grade", "") or getattr(player, "belt_name", "") or ""
                data["my_profile"] = {
                    "gender": player.gender,
                    "belt": belt_val,
                    "national_code": getattr(player, "national_code", "") or "",
                    "birth_date": birth_text,
                    "nationalCode": getattr(player, "national_code", "") or "",
                    "birthDate": birth_text,
                }

            data["registration_open"] = bool(reg_open_effective)
            data["user_eligible_self"] = _poomsae_user_eligible(request.user, comp)

        return Response(data, status=status.HTTP_200_OK)


# --- PoomsaeRegisterSelfView (fixed) ---
class PoomsaeRegisterSelfView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _get_first(self, data, *keys, default=""):
        for k in keys:
            if k in data:
                v = data.get(k)
                if v not in (None, ""):
                    return str(v).strip()
        return default

    def _clean_poomsae_type(self, v: str) -> str:
        t = (v or "").strip().lower().replace("ي","ی").replace("ك","ک")
        mapping = {
            "std": "standard", "standard": "standard", "استاندارد": "standard",
            "creative": "creative", "cre": "creative", "ابداعی": "creative", "ابداعي": "creative",
        }
        return mapping.get(t, t)

    def _to_iso_from_jalali_or_iso(self, s: str) -> str:
        """
        ورودی می‌تواند:
          - 'YYYY/MM/DD' (جلالی یا گریگوریان)
          - 'YYYY-MM-DD'
          - ISO datetime مثل 'YYYY-MM-DDTHH:mm:ssZ'
        خروجی: 'YYYY-MM-DD' گریگوریان (بدون جابه‌جایی روز).
        """
        if not s:
            return ""
        import re as _re
        t = str(s).strip()
        # اگر ISO datetime است، فقط تاریخ را بردار
        if "T" in t:
            t = t.split("T", 1)[0]
        # پاک‌سازی و یکسان‌سازی
        t = _re.sub(r"[\u200e\u200f\u200c\u202a-\u202e]", "", t)
        t = t.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).replace("-", "/")

        m = _re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", t)
        if not m:
            return ""

        y, m_, d = map(int, m.groups())
        try:
            if y < 1700:
                # جلالی→گریگوریان: با ساعت 12 ظهر تا هیچ DST/Timezone شِفتی اتفاق نیفتد
                jdt = jdatetime.datetime(y, m_, d, 12, 0, 0)
                g = jdt.togregorian().date()
            else:
                g = _date(y, m_, d)
            return f"{g.year:04d}-{g.month:02d}-{g.day:02d}"
        except Exception:
            return ""

    def _as_plain_dict(self, data):
        out = {}
        try:
            items = data.lists() if hasattr(data, "lists") else data.items()
            for k, v in items:
                out[k] = (v[0] if isinstance(v, (list, tuple)) else v)
        except Exception:
            try:
                out = dict(data)
            except Exception:
                out = {"__raw__": str(data)}
        return out

    def _get_comp_by_key(self, key):
        s = str(key).strip()
        base = PoomsaeCompetition.objects.all()
        if s.isdigit():
            obj = base.filter(id=int(s)).first()
            if obj: return obj
        obj = base.filter(public_id__iexact=s).first() or base.filter(slug__iexact=s).first()
        if obj: return obj
        raise Http404("PoomsaeCompetition not found")

    def _to_greg_date(self, val):
        if not val:
            return None
        if isinstance(val, _date):
            return val
        t = str(val).strip().replace("-", "/")
        t = t.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩","01234567890123456789"))
        try:
            y, m, d = map(int, t.split("/")[:3])
            if y < 1700:
                g = jdatetime.date(y, m, d).togregorian()
                return _date(g.year, g.month, g.day)
            return _date(y, m, d)
        except Exception:
            return None

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        key = kwargs.get("key") or kwargs.get("public_id")
        comp = self._get_comp_by_key(key)

        if not comp.registration_open_effective:
            return Response({"detail": "ثبت‌نام این مسابقه فعال نیست."}, status=status.HTTP_400_BAD_REQUEST)

        player = UserProfile.objects.filter(user=request.user, role__in=["player", "both"])\
                                    .select_related("club","tkd_board").first()
        if not player:
            return Response({"detail": "پروفایل بازیکن یافت نشد."}, status=status.HTTP_404_NOT_FOUND)

        data = self._as_plain_dict(request.data or {})
        coach_code = self._get_first(data, "coach_code", "code", "coachApprovalCode", "coach_approval_code")
        poomsae_type = self._clean_poomsae_type(self._get_first(data, "poomsae_type", "type", "poomsaeType"))
        insurance_number = self._get_first(data, "insurance_number", "insuranceNumber")
        ins_raw = self._get_first(data, "insurance_issue_date", "insurance_issue_date_jalali", "insuranceIssueDate", "insuranceIssueDateJalali")
        insurance_issue_date_iso = self._to_iso_from_jalali_or_iso(ins_raw)

        errors = {}
        if poomsae_type not in {"standard", "creative"}:
            errors["poomsae_type"] = ["مقدار نامعتبر است (standard/creative)."]
        if not insurance_number:
            errors["insurance_number"] = ["شمارهٔ بیمه الزامی است."]
        if not insurance_issue_date_iso:
            errors["insurance_issue_date"] = ["تاریخ صدور بیمه نامعتبر است."]
        else:
            try:
                iid = _date.fromisoformat(insurance_issue_date_iso)
                comp_date = comp.competition_date or comp.start_date
                delta = (comp_date - iid)
                if delta.days < 3 or delta.days > 365:
                    errors["insurance_issue_date"] = ["تاریخ بیمه باید حداقل ۳ روز و حداکثر ۱ سال قبل از مسابقه باشد."]
            except Exception:
                errors["insurance_issue_date"] = ["تاریخ صدور بیمه نامعتبر است."]

        coach = None
        coach_name = ""
        if coach_code:
            appr = PoomsaeCoachApproval.objects.filter(
                competition=comp, code=str(coach_code).strip(),
                is_active=True, approved=True
            ).select_related("coach").first()
            if not appr:
                errors["coach_code"] = ["کد مربی نامعتبر یا غیرفعال است."]
            else:
                coach = appr.coach
                coach_name = f"{coach.first_name or ''} {coach.last_name or ''}".strip()
        else:
            errors["coach_code"] = ["کد مربی الزامی است."]

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        if PoomsaeEnrollment.objects.filter(competition=comp, player=player, poomsae_type=poomsae_type).exists():
            return Response({"detail": "برای این مسابقه پومسه قبلاً ثبت‌نام شده‌اید."}, status=status.HTTP_409_CONFLICT)

        # ردهٔ سنی از DOB و رده‌های خود مسابقه
        bd = self._to_greg_date(getattr(player, "birth_date", None))
        age_obj = None
        if bd:
            if getattr(comp, "age_categories", None) and comp.age_categories.exists():
                age_obj = AgeCategory.objects.filter(
                    id__in=comp.age_categories.values_list("id", flat=True),
                    from_date__lte=bd, to_date__gte=bd
                ).first()
            if not age_obj:
                age_obj = AgeCategory.objects.filter(from_date__lte=bd, to_date__gte=bd).first()

        # گروه کمربندی فقط از بین گروه‌های مسابقه
        belt_name = (
            getattr(player, "belt_grade", None)
            or getattr(player, "belt_name", None)
            or getattr(player, "belt", None)
        )
        # گروه کمربندی فقط از گروه‌های همین مسابقه و با نرمال‌سازی؛ بدون هیچ fallback
        bg_obj = _belt_group_for_player_in_comp(player, comp)

        # اگر مسابقه گروه کمربندی دارد ولی مچ پیدا نشد، خطا بدهیم
        if comp.belt_groups.exists() and not bg_obj:
            return Response(
                {"belt_group": ["گروه کمربندی متناسب با کمربند شما در این مسابقه یافت نشد."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        enrollment = PoomsaeEnrollment.objects.create(
            competition=comp,
            player=player,
            coach=coach,
            coach_name=coach_name,
            coach_approval_code=str(coach_code).strip(),
            club=player.club if getattr(player, "club_id", None) else None,
            club_name=(getattr(player.club, "club_name", "") if getattr(player, "club_id", None) else ""),
            board=(player.club.tkd_board if getattr(player, "club_id", None) and getattr(player.club, "tkd_board_id", None) else getattr(player, "tkd_board", None)),
            board_name=(getattr(player.club.tkd_board, "name", "") if getattr(player, "club_id", None) and getattr(player.club, "tkd_board_id", None) else (getattr(player.tkd_board, "name", "") if getattr(player, "tkd_board_id", None) else "")),
            belt_group=bg_obj,
            age_category=age_obj,
            poomsae_type=poomsae_type,
            insurance_number=insurance_number,
            insurance_issue_date=_date.fromisoformat(insurance_issue_date_iso),  # ← تاریخ دقیق روز
            status="pending_payment",
            is_paid=False,
            paid_amount=0,
        )

        # پرداخت آزمایشی
        entry_fee_irr = int(comp.entry_fee or 0)
        simulate_paid = (not getattr(settings, "PAYMENTS_ENABLED", False)) or (entry_fee_irr == 0)
        
        if simulate_paid:
            enrollment.mark_paid(amount=entry_fee_irr, ref_code=f"TEST-POOM-{enrollment.id:06d}")


        return Response({
            "detail": "ثبت‌نام پومسه با موفقیت ذخیره شد.",
            "enrollment_id": enrollment.id,
            "status": enrollment.status,
            "is_paid": enrollment.is_paid,
            "paid_amount": enrollment.paid_amount,
            "bank_ref_code": enrollment.bank_ref_code,
            "paid_at": enrollment.paid_at,
            "poomsae_type": enrollment.poomsae_type,
            "insurance_number": enrollment.insurance_number,
            "insurance_issue_date": str(enrollment.insurance_issue_date),
            "coach_name": enrollment.coach_name or None,
            "coach_approval_code": enrollment.coach_approval_code or None,
            "age_category_id": enrollment.age_category_id,
            "belt_group_id": enrollment.belt_group_id,
        }, status=status.HTTP_201_CREATED)

# Mixin
class CompetitionLookupMixin:
    model = None
    def get_competition_by_key(self, key):
        qs = self.model.objects.all()
        if str(key).isdigit():
            return get_object_or_404(qs, id=int(key))
        obj = qs.filter(public_id__iexact=key).first()
        if obj:
            return obj
        obj = qs.filter(slug__iexact=key).first()
        if obj:
            return obj
        return get_object_or_404(qs, public_id__iexact=key)


class MyPoomsaeEnrollmentsView(views.APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, key):
        # پیداکردن مسابقه پومسه با public_id/slug/id
        s = str(key).strip()
        base_qs = PoomsaeCompetition.objects.all()
        if s.isdigit():
            comp = get_object_or_404(base_qs, id=int(s))
        else:
            comp = base_qs.filter(public_id__iexact=s).first() or base_qs.filter(slug__iexact=s).first()
            if not comp:
                raise Http404("PoomsaeCompetition not found")

        player = UserProfile.objects.filter(user=request.user, role__in=["player", "both"]).first()
        if not player:
            return Response({"standard": None, "creative": None}, status=200)

        qs = (PoomsaeEnrollment.objects
              .filter(competition=comp, player=player)
              .only("id", "status", "poomsae_type"))
        std = qs.filter(poomsae_type="standard").first()
        cre = qs.filter(poomsae_type="creative").first()

        def pack(e):
            if not e: return None
            return {
                "enrollment_id": e.id,
                "status": e.status,
                "can_show_card": _can_show_card(e.status, getattr(e, "is_paid", False))
            }

        return Response({"standard": pack(std), "creative": pack(cre)}, status=200)
