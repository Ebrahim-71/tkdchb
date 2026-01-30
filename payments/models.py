from __future__ import annotations

import secrets
import string
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError

from django.db import models, transaction
from django.utils import timezone
from django.db.models import Q
User = get_user_model()


def _gen_public_id(n: int = 12) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


class PaymentIntent(models.Model):
    GATEWAY_CHOICES = [
    ("sadad", "سداد (بانک ملّی)"),
    ("bmi",   "سداد/BMI (azbankgateways)"),
    ("fake",  "درگاه آزمایشی"),
    ("dummy", "درگاه نمایشی (تست)"),
]
    STATUS_CHOICES = [
        ("initiated", "ایجاد شده"),
        ("redirected", "ارسال به درگاه"),
        ("paid", "پرداخت موفق"),
        ("failed", "ناموفق/لغو"),
    ]

    # شناسه‌ی عمومی (برای URL/Frontend)
    public_id = models.CharField(
        max_length=16,
        unique=True,
        db_index=True,
        default=_gen_public_id,
        editable=False,
    )

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_intents",
    )

    gateway = models.CharField(
        max_length=20, choices=GATEWAY_CHOICES, default="sadad"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="initiated"
    )

    # هدف پرداخت (سازگاری قدیمی: مسابقه‌ی کیوروگی)
    # نگه می‌داریم؛ ولی برای نهایی‌سازی بهتر است به Enrollmentها وصل شویم (پایین اضافه شده)
    competition = models.ForeignKey(
        "competitions.KyorugiCompetition",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_intents",
    )

    # مبلغ (تومان) — اجازه‌ی 0 برای رویداد رایگان/معاف
   # مبلغ (ریال) — اجازه‌ی 0 برای رویداد رایگان/معاف
    amount = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    
    # مبلغ اصلی و تخفیف (ریال)
    original_amount = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    discount_amount = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    discount_code = models.ForeignKey(
        "competitions.DiscountCode",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_intents",
    )

    description = models.CharField(max_length=255, blank=True, default="")


    # بازگشت به فرانت (صفحه‌ی نتیجه). اگر خالی باشد از settings.PAYMENTS["RETURN_URL"] استفاده می‌شود.
    callback_url = models.URLField(blank=True, default="")

    # داده‌های درگاه
    token = models.CharField(
        max_length=128, blank=True, default=""
    )  # tracking_code
    ref_id = models.CharField(
        max_length=64, blank=True, default=""
    )  # bank_track_id / reference
    card_pan = models.CharField(
        max_length=64, blank=True, default=""
    )  # ماسک کارت
    extra = models.JSONField(default=dict, blank=True)

    # ردیابی درخواست
    initiator_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, default="")
    payment_link_token = models.CharField(max_length=128, blank=True, default="", db_index=True)
    payment_link_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    kyorugi_enrollments = models.ManyToManyField(
        "competitions.Enrollment",
        related_name="bulk_payment_intents",
        blank=True,
    )
    # اتصال مستقیم به ثبت‌نام‌ها برای نهایی‌سازی اتوماتیک
    kyorugi_enrollment = models.ForeignKey(
        "competitions.Enrollment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_intents",
    )
    poomsae_enrollment = models.ForeignKey(
        "competitions.PoomsaeEnrollment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_intents",
    )
    seminar_registration = models.ForeignKey(
        "competitions.SeminarRegistration",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_intents",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "تراکنش/Intent"
        verbose_name_plural = "تراکنش‌ها"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["token"]),
            models.Index(fields=["created_at"]),
        ]
        # حداکثر یکی از FKهای هدف باید مقدار داشته باشد (at most one non-null)
        constraints = [
            models.CheckConstraint(
                name="payments_at_most_one_target_fk",
                check=(
                    # 0 target
                    (Q(kyorugi_enrollment__isnull=True) & Q(poomsae_enrollment__isnull=True) & Q(seminar_registration__isnull=True))
                    # exactly 1 target
                    | (Q(kyorugi_enrollment__isnull=False) & Q(poomsae_enrollment__isnull=True) & Q(seminar_registration__isnull=True))
                    | (Q(kyorugi_enrollment__isnull=True) & Q(poomsae_enrollment__isnull=False) & Q(seminar_registration__isnull=True))
                    | (Q(kyorugi_enrollment__isnull=True) & Q(poomsae_enrollment__isnull=True) & Q(seminar_registration__isnull=False))
                ),
            )
        ]


    def clean(self):
        super().clean()

        # اگر bulk انتخاب شده باشد، نباید FK هدف‌ها پر باشند
        if self.pk and self.kyorugi_enrollments.exists():
            if self.kyorugi_enrollment_id or self.poomsae_enrollment_id or self.seminar_registration_id:
                raise ValidationError(
                    "Bulk kyorugi_enrollments cannot be combined with single target FK fields."
                )

        # اگر FK های هدف پر هستند، bulk باید خالی باشد
        if (self.kyorugi_enrollment_id or self.poomsae_enrollment_id or self.seminar_registration_id):
            if self.pk and self.kyorugi_enrollments.exists():
                raise ValidationError(
                    "Single target FK cannot be combined with bulk kyorugi_enrollments."
                )

    def __str__(self):
        return f"{self.public_id} - {self.amount_rial} R ({self.amount_toman} T) - {self.status}"

    


    # ───────────── Properties ─────────────
    @property
    def is_paid(self) -> bool:
        return self.status == "paid"

    @property
    def needs_redirect(self) -> bool:
        return self.status in ("initiated", "failed") and self.gateway in ("sadad", "bmi", "fake")


    @property
    def can_retry(self) -> bool:
        return self.status in ("failed",)

    @property
    def amount_rial(self) -> int:
        """مبلغ به ریال (واحد ذخیره در DB و واحد مورد نیاز درگاه)."""
        return int(self.amount or 0)
    
    @property
    def amount_toman(self) -> int:
        """مبلغ به تومان (برای نمایش)."""
        return int(self.amount or 0) // 10



    # ───────────── Helpers ─────────────
    def default_return_url(self) -> str:
        from django.conf import settings as _s

        try:
            return (getattr(_s, "PAYMENTS", {}) or {}).get("RETURN_URL") or "/"
        except Exception:
            return "/"
    def issue_payment_link(self, minutes=10) -> str:
        """
        یک توکن یکبارمصرف/کوتاه‌عمر برای شروع پرداخت تولید می‌کند.
        برای flow ای که فرانت باید با window.location برود (بدون Authorization header).
        """
        # token جدید بساز
        self.payment_link_token = secrets.token_urlsafe(32)
        self.payment_link_expires_at = timezone.now() + timezone.timedelta(minutes=minutes)
        self.save(update_fields=["payment_link_token", "payment_link_expires_at", "updated_at"])
        return self.payment_link_token

    @transaction.atomic
    def mark_paid(self, ref_id=None, card_pan=None, extra=None):
        """
        قطعی‌سازی پرداخت و اعمال به رکورد هدف (enrollment/registration).
        idempotent: اگر قبلاً paid شده، دوباره اعمال نکن.
        """
        if self.status == "paid":
            # اگر لازم داری فقط ref_id/card_pan را تکمیل کنی، اینجا می‌تونی guard نرم‌تر بذاری.
            return
    
        if ref_id:
            self.ref_id = ref_id
        if card_pan:
            self.card_pan = card_pan
        if extra:
            self.extra = extra if isinstance(extra, dict) else {"extra": extra}
    
        self.status = "paid"
        self.save(update_fields=["status", "ref_id", "card_pan", "extra", "updated_at"])
    
        # ۱) اعمال نتیجه روی ثبت‌نام‌ها
        self._apply_success_to_targets()
    
        # ۲) اگر کد تخفیف داشتیم، شمارنده‌اش را آپدیت کنیم (فقط یک‌بار چون بالا idempotent شد)
        if self.discount_code_id:
            dc = self.discount_code
            if dc:
                dc.used_count = (dc.used_count or 0) + 1
    
                max_uses = getattr(dc, "max_uses", None)
                if max_uses not in (None, 0) and dc.used_count >= max_uses:
                    dc.active = False
                    dc.save(update_fields=["used_count", "active"])
                else:
                    dc.save(update_fields=["used_count"])




    def _apply_success_to_targets(self):
        

        def _mark_enrollment_paid(e, set_paid_amount: bool = True):
            changed = False
    
            if getattr(e, "is_paid", False) is False:
                e.is_paid = True
                changed = True
    
            # ⛔️ برای Bulk می‌خوایم false کنیم تا مبلغ کل روی تک‌تک‌ها ننشیند
            if set_paid_amount and not getattr(e, "paid_amount", None):
                e.paid_amount = int(self.amount or 0)  # ریال
                changed = True
    
            if getattr(e, "status", "") != "paid":
                e.status = "paid"
                changed = True
    
            if not getattr(e, "bank_ref_code", None):
                e.bank_ref_code = self.ref_id or ""
                changed = True
    
            if changed:
                e.save()
    
        # ✅ 0) Bulk kyorugi enrollments (بدون set_paid_amount)
        qs = self.kyorugi_enrollments.all()
        if qs.exists():
            for e in qs:
                _mark_enrollment_paid(e, set_paid_amount=False)

    
        # 1) پرداخت تکی کیوروگی (اینجا set_paid_amount=True می‌مونه)
        if self.kyorugi_enrollment_id:
            _mark_enrollment_paid(self.kyorugi_enrollment, set_paid_amount=True)



        # 2) پرداخت تکی پومسه
        if self.poomsae_enrollment_id:
            pe = self.poomsae_enrollment
            changed = False
            if getattr(pe, "is_paid", False) is False:
                pe.is_paid = True
                changed = True
            if not getattr(pe, "paid_amount", None):
                pe.paid_amount = int(self.amount or 0)
                changed = True
            if getattr(pe, "status", "") != "paid":
                pe.status = "paid"
                changed = True
            if not getattr(pe, "bank_ref_code", None):
                pe.bank_ref_code = self.ref_id or ""
                changed = True
            if changed:
                pe.save()

        # 3) سمینار
        if self.seminar_registration_id:
            sr = self.seminar_registration
            if hasattr(sr, "mark_paid") and callable(getattr(sr, "mark_paid")):
                try:
                    sr.mark_paid(amount=int(self.amount or 0), ref_code=(self.ref_id or ""))

                    return
                except Exception:
                    pass
            sr.is_paid = True
            sr.paid_amount = int(self.amount or 0)
            sr.paid_at = timezone.now()
            sr.save(update_fields=["is_paid", "paid_amount", "paid_at"])
