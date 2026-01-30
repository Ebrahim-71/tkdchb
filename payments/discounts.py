# payments/discounts.py
# -*- coding: utf-8 -*-
import logging
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from competitions.models import DiscountCode, KyorugiCompetition, PoomsaeCompetition

log = logging.getLogger("payments")


def apply_discount_for_competition(*, competition, coach_user, base_amount, code_str, commit: bool = False, commit_use=None):

    if commit_use is not None:
        commit = bool(commit_use)




    code_str = (code_str or "").strip()
    base_amount = int(base_amount)

    # 🔒 Guard واحد پول (ریال)
    if base_amount < 0:
        raise ValidationError("مبلغ پایه نامعتبر است.")
    
    # اگر مبلغ خیلی کوچک است، احتمالاً تومان ارسال شده
    if base_amount > 0 and base_amount < 10_000:
        raise ValidationError("مبلغ باید به ریال باشد (amount بسیار کوچک است).")


    # اگر هیچ کدی وارد نشده بود
    if not code_str:
        return base_amount, None, 0

    field_names = {f.name for f in DiscountCode._meta.get_fields()}

    qs = DiscountCode.objects.all()

    # --- فیلتر بر اساس خود کد (case-insensitive) ---
    if "code" in field_names:
        qs = qs.filter(code__iexact=code_str)
    else:
        raise ValidationError("کد تخفیف نامعتبر است.")

    # --- فیلتر مسابقه بر اساس نوع (کیوروگی / پومسه / عمومی) ---
    if competition is not None:
        cond = Q()

        # مدل جدید: فیلد جدا برای کیوروگی
        if isinstance(competition, KyorugiCompetition) and "kyorugi_competition" in field_names:
            cond |= Q(kyorugi_competition=competition) | Q(kyorugi_competition__isnull=True)

        # مدل جدید: فیلد جدا برای پومسه
        if isinstance(competition, PoomsaeCompetition) and "poomsae_competition" in field_names:
            cond |= Q(poomsae_competition=competition) | Q(poomsae_competition__isnull=True)

        # مدل قدیمی: فیلد عمومی competition که به KyorugiCompetition وصل است
        if "competition" in field_names:
            if isinstance(competition, KyorugiCompetition):
                # برای کیوروگی می‌توانیم خود مسابقه را هم ست کنیم
                cond |= Q(competition=competition) | Q(competition__isnull=True)
            else:
                # برای پومسه و بقیه، فقط کدهای عمومی (competition__isnull=True)
                cond |= Q(competition__isnull=True)

        if cond:
            qs = qs.filter(cond)

    # --- فقط کدهای فعال (اگر فیلد active / is_active / start/end داریم) ---
    if "active" in field_names:
        qs = qs.filter(active=True)
    if "is_active" in field_names:
        qs = qs.filter(is_active=True)

    now = timezone.now()
    if "start_at" in field_names:
        qs = qs.filter(Q(start_at__lte=now) | Q(start_at__isnull=True))
    if "end_at" in field_names:
        qs = qs.filter(Q(end_at__gte=now) | Q(end_at__isnull=True))

    dc = qs.first()

    if not dc:
        log.info(
            "DISCOUNT_NOT_FOUND code=%s comp=%s user=%s",
            code_str,
            getattr(competition, "id", None),
            getattr(coach_user, "id", None),
        )
        raise ValidationError("این کد تخفیف برای این مسابقه معتبر نیست.")

    # --- چک سقف استفاده ---
    max_uses = getattr(dc, "max_uses", None)
    used_count = getattr(dc, "used_count", 0) or 0
    if max_uses not in (None, 0) and used_count >= max_uses:
        raise ValidationError("سقف استفاده از این کد تخفیف تمام شده است.")

    # --- درصد تخفیف ---
    raw_percent = (
        getattr(dc, "percent", None)
        or getattr(dc, "discount_percent", None)
        or getattr(dc, "percentage", None)
    )
    percent = int(raw_percent or 0)

    # 🔒 sanity check درصد
    if percent < 0 or percent > 100:
        raise ValidationError("درصد تخفیف نامعتبر است.")


    if percent <= 0:
        log.info(
            "DISCOUNT_ZERO_PERCENT code=%s dc_id=%s base=%s",
            code_str,
            dc.pk,
            base_amount,
        )
        return base_amount, dc, 0

    discount_amount = (base_amount * percent) // 100
    final_amount = max(base_amount - discount_amount, 0)

    if commit and ("used_count" in field_names):
        DiscountCode.objects.filter(pk=dc.pk).update(used_count=used_count + 1)

    log.info(
        "DISCOUNT_APPLIED code=%s percent=%s base=%s final=%s disc=%s dc_id=%s",
        code_str,
        percent,
        base_amount,
        final_amount,
        discount_amount,
        dc.pk,
    )

    # 🔒 sanity check خروجی‌ها
    final_amount = int(final_amount)
    discount_amount = int(discount_amount)
    
    if final_amount < 0:
        raise ValidationError("amount نهایی منفی شد (خطای تخفیف).")
    
    if discount_amount < 0:
        raise ValidationError("discount_amount نامعتبر است.")
    
    if discount_amount > base_amount:
        raise ValidationError("discount_amount از مبلغ پایه بیشتر شد.")
    
    return final_amount, dc, discount_amount
    
