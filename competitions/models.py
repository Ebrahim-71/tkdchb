# -*- coding: utf-8 -*-
from __future__ import annotations
from django.db import models, transaction, IntegrityError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from datetime import timedelta
import string, secrets, jdatetime, random
from django.db.models import Index, CheckConstraint, Q, F
from datetime import datetime, date
from django.contrib.auth import get_user_model

from django.utils import timezone
from django.db import models as djm
from typing import List, Optional


# competitions/models.py
from django.utils.translation import gettext_lazy as _

from accounts.models import UserProfile, TkdClub, TkdBoard
from django.conf import settings

from django.db import models
from django.utils import timezone
from django.db.models import Q

User = get_user_model()




# بهتر: فقط کنترل دستی + منطق محاسبه، بدون تاریخ‌ها
class RegistrationManualMixin(models.Model):
    registration_manual = models.BooleanField(
        "فعال بودن ثبت‌نام",
        null=True, blank=True, default=None,
        help_text="خالی=طبق تاریخ‌ها، تیک=اجباراً باز، بدون تیک=اجباراً بسته"
    )

    class Meta:
        abstract = True

    @property
    def registration_open_effective(self) -> bool:
        if self.registration_manual is True:
            return True
        if self.registration_manual is False:
            return False

        start = getattr(self, "registration_start", None)
        end = getattr(self, "registration_end", None)

        # اگر DateTime است: now بگیر و هر DateTime نا‌آگاه را آگاه کن
        if isinstance(start, datetime) or isinstance(end, datetime):
            current = timezone.now()
            if isinstance(start, datetime) and timezone.is_naive(start):
                start = timezone.make_aware(start)
            if isinstance(end, datetime) and timezone.is_naive(end):
                end = timezone.make_aware(end)
        else:
            # اگر DateField است: با date مقایسه کن
            current = timezone.localdate()

        if start and current < start:
            return False
        if end and current > end:
            return False
        return True

# =========================
def _gen_public_id(n: int = 10) -> str:
    """شناسه عمومی تصادفی حروف کوچک + رقم (برای URL عمومی)."""
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(n))

# =========================
# فرهنگ‌ها / قالب‌ها
# =========================
class AgeCategory(models.Model):
    name = models.CharField('عنوان رده سنی', max_length=100)
    from_date = models.DateField('از تاریخ تولد')
    to_date = models.DateField('تا تاریخ تولد')

    class Meta:
        verbose_name = 'رده سنی'
        verbose_name_plural = 'رده‌های سنی'

    def __str__(self):
        return self.name

class Belt(models.Model):
    name = models.CharField('نام کمربند', max_length=50)

    class Meta:
        verbose_name = 'کمربند'
        verbose_name_plural = 'کمربندها'

    def __str__(self):
        return self.name

class BeltGroup(models.Model):
    label = models.CharField('نام گروه کمربند', max_length=100)
    belts = models.ManyToManyField(Belt, verbose_name='کمربندها')

    class Meta:
        verbose_name = 'گروه کمربند'
        verbose_name_plural = 'گروه‌های کمربند'

    def __str__(self):
        return self.label

class TermsTemplate(models.Model):
    title = models.CharField("عنوان تعهدنامه", max_length=200)
    content = models.TextField("متن تعهدنامه")

    class Meta:
        verbose_name = "قالب تعهدنامه"
        verbose_name_plural = "قالب‌های تعهدنامه"

    def __str__(self):
        return self.title

class WeightCategory(models.Model):
    GENDER_CHOICES = [('male', 'مرد'), ('female', 'زن')]

    name = models.CharField('نام وزن', max_length=50)
    gender = models.CharField('جنسیت', max_length=6, choices=GENDER_CHOICES)
    min_weight = models.FloatField('حداقل وزن (kg)')
    max_weight = models.FloatField('حداکثر وزن (kg)')
    tolerance  = models.FloatField('میزان ارفاق وزنی (kg)', default=0.2)

    class Meta:
        verbose_name = 'رده وزنی'
        verbose_name_plural = 'رده‌های وزنی'

    def __str__(self):
        g = dict(self.GENDER_CHOICES).get(self.gender, self.gender)
        return f"{self.name} ({self.min_weight}–{self.max_weight} kg) - {g}"

    def includes_weight(self, weight: float) -> bool:
        return self.min_weight <= weight <= (self.max_weight + self.tolerance)

# =========================
# مسابقه کیوروگی
# =========================

class KyorugiCompetitionQuerySet(models.QuerySet):
    def registration_active(self):
        # همان active قبلی (یا اسمش را همین نگه دار)
        today = timezone.localdate()
        return self.filter(
            Q(registration_manual=True) |
            (Q(registration_manual__isnull=True) &
             Q(registration_start__lte=today) &
             Q(registration_end__gte=today))
        ).exclude(registration_manual=False)

    def not_finished(self):
        # معیار جدید: مسابقه هنوز تمام نشده
        today = timezone.localdate()
        return self.filter(
            Q(competition_date__isnull=True) | Q(competition_date__gte=today)
        )


class KyorugiCompetition(RegistrationManualMixin, models.Model):
    objects = KyorugiCompetitionQuerySet.as_manager()

    GENDER_CHOICES = [('male', 'آقایان'), ('female', 'بانوان')]
    BELT_LEVEL_CHOICES = [
        ('yellow_blue', 'زرد تا آبی'),
        ('red_black', 'قرمز و مشکی'),
        ('all', 'همه رده‌ها'),
    ]

    title = models.CharField('عنوان مسابقه', max_length=255)
    poster = models.ImageField('پوستر شاخص', upload_to='kyorugi_posters/', null=True, blank=True)
    entry_fee = models.PositiveIntegerField('مبلغ ورودی (ریال)', default=0, validators=[MinValueValidator(0)])


    age_category = models.ForeignKey(AgeCategory, verbose_name='رده سنی',
                                     on_delete=models.SET_NULL, null=True)
    belt_level = models.CharField('رده کمربندی', max_length=20, choices=BELT_LEVEL_CHOICES)
    belt_groups = models.ManyToManyField(BeltGroup, verbose_name='گروه‌های کمربندی', blank=True)
    gender = models.CharField('جنسیت', max_length=10, choices=GENDER_CHOICES)

    city = models.CharField('شهر محل برگزاری', max_length=100)
    address = models.TextField('آدرس محل برگزاری')

    registration_start = models.DateField(verbose_name='شروع ثبت‌نام')
    registration_end   = models.DateField(verbose_name='پایان ثبت‌نام')
    weigh_date         = models.DateField(verbose_name='تاریخ وزن‌کشی')
    draw_date          = models.DateField(verbose_name='تاریخ قرعه‌کشی')
    competition_date   = models.DateField(verbose_name='تاریخ برگزاری')
    bracket_published_at = models.DateTimeField(null=True, blank=True)
    bracket_published_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="published_kyorugi_brackets"
    )

    mat_count = models.PositiveIntegerField('تعداد زمین', default=1)

    terms_template = models.ForeignKey(
        TermsTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="قالب تعهدنامه",
        related_name='competitions'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    slug = models.SlugField(max_length=128, unique=True, null=True, blank=True)

    public_id = models.CharField(
        'شناسه عمومی',
        max_length=16,
        unique=True,
        db_index=True,
        editable=False,
        default=_gen_public_id,
    )

    class Meta:
        verbose_name = 'مسابقه کیوروگی'
        verbose_name_plural = 'مسابقات کیوروگی'
        constraints = [
            models.CheckConstraint(
                check=Q(registration_start__lte=F('registration_end')),
                name='reg_start_lte_reg_end'
            ),
            models.CheckConstraint(
                check=Q(weigh_date__lte=F('draw_date')),
                name='weigh_lte_draw'
            ),
            models.CheckConstraint(
                check=Q(draw_date__lte=F('competition_date')),
                name='draw_lte_comp'
            ),
        ]
        indexes = [
            models.Index(fields=['public_id']),
            models.Index(fields=['competition_date']),
        ]

    def __str__(self):
        return self.title

    @property
    def is_registration_open(self) -> bool:
        return self.registration_open_effective
    @property
    def style_display(self):
        return "کیوروگی"

    @property
    def is_bracket_published(self):
        return bool(self.bracket_published_at)
    def clean(self):
        # اگر کاربر در ادمین تاریخ شمسی وارد کرد (سال < 1700)، به میلادی تبدیل کن
        for f in ["registration_start", "registration_end", "weigh_date", "draw_date", "competition_date"]:
            d = getattr(self, f)
            if d and d.year < 1700:
                setattr(self, f, jdatetime.date(d.year, d.month, d.day).togregorian())
        super().clean()

    def save(self, *args, **kwargs):
        attempts = 5
        while attempts > 0:
            try:
                if not self.public_id:
                    self.public_id = _gen_public_id(10)
                return super().save(*args, **kwargs)
            except IntegrityError as e:
                if 'public_id' in str(e).lower():
                    self.public_id = _gen_public_id(10)
                    attempts -= 1
                    continue
                raise
        raise IntegrityError("عدم امکان ایجاد شناسهٔ عمومی یکتا برای مسابقه.")

    # اوزان مجاز این مسابقه از روی تخصیص زمین‌ها
    def allowed_weight_ids(self) -> set[int]:
        return set(
            self.mat_assignments.values_list('weights__id', flat=True)
        )

# =========================
# سایر موجودیت‌های مسابقه
# =========================
class MatAssignment(models.Model):
    competition = models.ForeignKey(
        KyorugiCompetition,
        verbose_name='مسابقه',
        on_delete=models.CASCADE,
        related_name='mat_assignments'
    )
    mat_number = models.PositiveIntegerField('شماره زمین')
    weights = models.ManyToManyField(WeightCategory, verbose_name='اوزان تخصیص‌یافته')

    class Meta:
        verbose_name = 'تخصیص زمین'
        verbose_name_plural = 'تخصیص اوزان به زمین‌ها'

    def __str__(self):
        return f'زمین {self.mat_number} - {self.competition.title}'

class CompetitionImage(models.Model):
    competition = models.ForeignKey(
        KyorugiCompetition,
        related_name='images',
        on_delete=models.CASCADE,
        verbose_name='مسابقه'
    )
    image = models.ImageField('تصویر پیوست', upload_to='kyorugi_images/')

    class Meta:
        verbose_name = 'تصویر مسابقه'
        verbose_name_plural = 'تصاویر مسابقه'

    def __str__(self):
        return f"تصویر - {self.competition.title}"

class CompetitionFile(models.Model):
    competition = models.ForeignKey(
        KyorugiCompetition,
        related_name='files',
        on_delete=models.CASCADE,
        verbose_name='مسابقه'
    )
    file = models.FileField('فایل PDF', upload_to='kyorugi_files/')

    class Meta:
        verbose_name = 'فایل مسابقه'
        verbose_name_plural = 'فایل‌های مسابقه'

    def __str__(self):
        return f"فایل - {self.competition.title}"

class CoachApproval(models.Model):
    competition = models.ForeignKey(
        'competitions.KyorugiCompetition',
        on_delete=models.CASCADE,
        related_name='coach_approvals',
        verbose_name='مسابقه'
    )
    coach = models.ForeignKey(
        'accounts.UserProfile',
        on_delete=models.CASCADE,
        limit_choices_to={'is_coach': True},
        related_name='competition_approvals',
        verbose_name='مربی'
    )
    code = models.CharField(
        'کد تأیید مربی',
        max_length=8,
        blank=True,
        null=True,
        db_index=True
    )
    terms_accepted = models.BooleanField('تعهدنامه پذیرفته شد', default=False)
    is_active = models.BooleanField('فعال', default=True)
    approved_at = models.DateTimeField('تاریخ تأیید', auto_now_add=True)

    class Meta:
        verbose_name = 'تأیید مربی برای مسابقه'
        verbose_name_plural = 'تأییدهای مربیان'
        constraints = [
            models.UniqueConstraint(
                fields=['competition', 'coach'],
                name='uniq_competition_coach'
            ),
            models.UniqueConstraint(
                fields=['competition', 'code'],
                condition=models.Q(code__isnull=False),
                name='uniq_competition_code'
            ),
        ]
        indexes = [
            models.Index(fields=['competition', 'is_active', 'terms_accepted']),
        ]

    def __str__(self):
        fn = getattr(self.coach, 'first_name', '') or ''
        ln = getattr(self.coach, 'last_name', '') or ''
        return f"{self.competition} - {fn} {ln}".strip()

    @staticmethod
    def _rand_code(length: int = 6) -> str:
        """تولید کد عددی با طول ثابت (پیش‌فرض: ۶ رقم)."""
        upper = 10**length - 1
        return f"{random.randint(0, upper):0{length}d}"

    @transaction.atomic
    def set_fresh_code(self, save: bool = True, force: bool = False) -> str:
        """
        اگر قبلاً کد دارد و force=False باشد، همان کد را برمی‌گرداند.
        اگر force=True باشد، «به‌اجبار» کد جدید و یکتا (در سطح همان مسابقه) می‌سازد.
        """
        if self.code and not force:
            return self.code

        current = CoachApproval.objects.select_for_update().get(pk=self.pk)

        if current.code and not force:
            return current.code

        for _ in range(25):
            c = self._rand_code(6)  # ۶ رقمی
            exists = CoachApproval.objects.filter(
                competition=self.competition, code=c
            ).exists()
            if not exists:
                current.code = c
                if save:
                    # اجازهٔ تغییر کد فقط از این مسیر
                    setattr(current, "_allow_code_change", True)
                    current.save(update_fields=['code'])
                    delattr(current, "_allow_code_change")
                return c

        raise ValueError("ساخت کد یکتا ممکن نشد، دوباره تلاش کنید.")

    def clean(self):
        """اعتبارسنجی اختیاری: اگر کد هست، فقط رقم و ۴ تا ۸ رقم."""
        import re as _re
        if self.code:
            if not _re.fullmatch(r"\d{4,8}", str(self.code)):
                raise ValidationError({"code": "کد باید عددی و بین ۴ تا ۸ رقم باشد."})
        super().clean()

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        # فقط اگر code واقعاً در حال ویرایش باشد، یا update_fields خالی/None باشد، حساسیت به تغییر کد را اعمال کن
        should_check_code = (not update_fields) or ("code" in update_fields)

        # 🔧 نکتهٔ اصلی: وقتی از مسیر داخلی set_fresh_code فراخوانی می‌شویم،
        # فلگ _allow_code_change=True می‌شود؛ در آن حالت بررسی تغییر کد را رد کن.
        if self.pk and should_check_code and not getattr(self, "_allow_code_change", False):
            orig = type(self).objects.only("code").get(pk=self.pk)
            if orig.code != self.code:
                raise ValidationError({"code": "تغییر کد مجاز نیست. فقط مدیر می‌تواند کد جدید تولید کند."})

        return super().save(*args, **kwargs)

    # هِلپر اختیاری برای ویو: تغییر وضعیت بدون برخورد به save() سفارشی
    def approve_terms(self):
        """
        تعهدنامه را می‌پذیرد و تایید را فعال می‌کند—با update مستقیم (بدون عبور از save()).
        """
        now = timezone.now()
        type(self).objects.filter(pk=self.pk).update(
            terms_accepted=True,
            is_active=True,
            approved_at=now,
        )
        self.refresh_from_db(fields=("terms_accepted", "is_active", "approved_at"))

# =========================
# ثبت‌نام بازیکن (Enrollment)
# =========================
class Enrollment(models.Model):
    MEDAL_CHOICES = [
        ("", "—"),
        ("gold", "طلا"),
        ("silver", "نقره"),
        ("bronze", "برنز"),
    ]

    STATUS_CHOICES = [
        ("pending_payment", "در انتظار پرداخت"),
        ("paid", "پرداخت‌شده"),
        ("confirmed", "تأیید نهایی"),
        ("accepted", "پذیرفته‌شده"),
        ("completed", "تکمیل‌شده"),
        ("canceled", "لغو شده"),
    ]

    competition = models.ForeignKey(
        "competitions.KyorugiCompetition",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    player = models.ForeignKey(
        UserProfile, on_delete=models.PROTECT, related_name="enrollments"
    )

    # مربی + اسنپ‌شات
    coach = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="coach_enrollments",
        limit_choices_to={"is_coach": True},
    )
    coach_name = models.CharField(max_length=150, blank=True, default="")
    coach_approval_code = models.CharField(max_length=8, blank=True, default="")

    # باشگاه/هیئت: FK + اسنپ‌شات نام
    club = models.ForeignKey(
        TkdClub, on_delete=models.SET_NULL, null=True, blank=True, related_name="club_enrollments"
    )
    club_name = models.CharField(max_length=150, blank=True, default="")
    board = models.ForeignKey(
        TkdBoard, on_delete=models.SET_NULL, null=True, blank=True, related_name="board_enrollments"
    )
    board_name = models.CharField(max_length=150, blank=True, default="")

    # گروه کمربندی/رده وزنی
    belt_group = models.ForeignKey(
        "competitions.BeltGroup", on_delete=models.SET_NULL, null=True, blank=True, related_name="enrollments"
    )
    weight_category = models.ForeignKey(
        "competitions.WeightCategory", on_delete=models.PROTECT, null=True, blank=True, related_name="enrollments"
    )

    # داده‌های فرم
    declared_weight = models.FloatField(validators=[MinValueValidator(0.0)])
    insurance_number = models.CharField(max_length=20)
    insurance_issue_date = models.DateField()

        # پرداخت
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending_payment")
    is_paid = models.BooleanField(default=False)
    paid_amount = models.PositiveIntegerField(default=0)  # ریال

    bank_ref_code = models.CharField(max_length=64, blank=True, default="")
    paid_at = models.DateTimeField(null=True, blank=True)
    medal = models.CharField(max_length=10, choices=MEDAL_CHOICES, blank=True, default="")

    # --- تخفیف ---
    discount_code = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    discount_amount = models.PositiveIntegerField(default=0)  # ریال
    payable_amount = models.PositiveIntegerField(default=0)   # ریال

    discount_redeemed = models.BooleanField(default=False)
    enrollments_created = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["competition", "status"]),
            models.Index(fields=["coach"]),
            models.Index(fields=["club"]),
            models.Index(fields=["board"]),
            models.Index(fields=["discount_code"]),
        ]



    def __str__(self):
        return f"{self.player} @ {self.competition} - {self.paid_amount}R - {self.status}"


    @transaction.atomic
    def mark_paid(self, amount: int = 0, ref_code: str = ""):
        current = type(self).objects.select_for_update().get(pk=self.pk)
        if current.is_paid:
            return
    
        current.is_paid = True
        current.paid_amount = int(amount or 0)
        if ref_code:
            current.bank_ref_code = ref_code
        current.paid_at = timezone.now()
    
        if current.status in ("pending_payment", "canceled", ""):
            current.status = "paid"
    
        current.save(update_fields=[
            "is_paid", "paid_amount", "bank_ref_code", "paid_at", "status"
        ])
    
        # ❗ امتیازدهی فقط اگر از مسیر PaymentIntent نیامده
        if not hasattr(current, "_paid_via_intent"):
            _award_points_after_payment(current)


class Draw(models.Model):
    """قرعهٔ یک گروه مشخص در یک مسابقه (جنسیت/رده سنی/گروه کمربندی/رده وزنی)."""
    competition = models.ForeignKey(
        "competitions.KyorugiCompetition",
        on_delete=models.CASCADE,
        related_name="draws",
        verbose_name="مسابقه",
    )
    gender = models.CharField("جنسیت", max_length=10)  # male / female
    age_category = models.ForeignKey(AgeCategory, on_delete=models.PROTECT, null=True, blank=True, related_name="draws")

    belt_group = models.ForeignKey(
        "competitions.BeltGroup",
        on_delete=models.PROTECT,
        verbose_name="گروه کمربندی",
    )
    weight_category = models.ForeignKey(
        "competitions.WeightCategory",
        on_delete=models.PROTECT,
        verbose_name="رده وزنی",
    )

    size = models.PositiveIntegerField("اندازه جدول (توان ۲)", help_text="مثل 8، 16، 32")
    club_threshold = models.PositiveIntegerField("آستانه هم‌باشگاهی", default=8)
    rng_seed = models.CharField("Seed تصادفی", max_length=32, blank=True, default="")
    is_locked = models.BooleanField("قفل شده؟", default=False)
    created_at = models.DateTimeField("ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "قرعه"
        verbose_name_plural = "قرعه‌ها"
        indexes = [
            models.Index(fields=["competition", "gender", "age_category", "belt_group", "weight_category"]),
            models.Index(fields=["competition", "weight_category"]),
        ]
        unique_together = (
            ("competition", "gender", "age_category", "belt_group", "weight_category"),
        )

    def __str__(self):
        return f"قرعه #{self.id} - {self.competition} [{self.gender}/{self.age_category}/{self.belt_group}/{self.weight_category}]"

class Match(models.Model):
    draw = models.ForeignKey(Draw, on_delete=models.CASCADE, related_name="matches", verbose_name="قرعه")
    round_no = models.PositiveIntegerField("دور", help_text="1 = دور اول")
    slot_a = models.PositiveIntegerField("اسلات A")
    slot_b = models.PositiveIntegerField("اسلات B")

    player_a = models.ForeignKey(
        "accounts.UserProfile", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="as_player_a", verbose_name="بازیکن A"
    )
    player_b = models.ForeignKey(
        "accounts.UserProfile", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="as_player_b", verbose_name="بازیکن B"
    )
    is_bye = models.BooleanField("BYE؟", default=False)

    winner = models.ForeignKey(
        "accounts.UserProfile", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="as_winner", verbose_name="برنده"
    )

    # زمینِ اندیشیده‌شده برای وزن (از MatAssignment درآورده می‌شود)
    mat_no = models.PositiveIntegerField("زمین", null=True, blank=True)

    # 🆕 شمارهٔ بازی روی زمین (از 1 شروع می‌شود و پیوسته است)
    match_number = models.PositiveIntegerField("شماره بازی", null=True, blank=True, db_index=True)

    scheduled_at = models.DateTimeField("زمان‌بندی", null=True, blank=True)
    created_at = models.DateTimeField("ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "مبارزه"
        verbose_name_plural = "مبارزات"
        indexes = [
            models.Index(fields=["draw", "round_no"]),
            models.Index(fields=["mat_no", "match_number"]),
        ]

    def __str__(self):
        return f"M{self.id} R{self.round_no} ({self.slot_a}-{self.slot_b})"

class DrawStart(Draw):
    class Meta:
        proxy = True
        verbose_name = "شروع قرعه‌کشی"
        verbose_name_plural = "شروع قرعه‌کشی"

class FirstRoundPairHistory(models.Model):
    player_a = models.ForeignKey("accounts.UserProfile", on_delete=models.CASCADE, related_name='+')
    player_b = models.ForeignKey("accounts.UserProfile", on_delete=models.CASCADE, related_name='+')

    gender = models.CharField(max_length=10)  # male / female
    age_category = models.ForeignKey("competitions.AgeCategory", on_delete=models.PROTECT)
    belt_group = models.ForeignKey("competitions.BeltGroup", on_delete=models.PROTECT)
    weight_category = models.ForeignKey("competitions.WeightCategory", on_delete=models.PROTECT)

    last_competition = models.ForeignKey("competitions.KyorugiCompetition", on_delete=models.SET_NULL, null=True, blank=True)
    last_met_at = models.DateTimeField(auto_now=True)  # آخرین به‌روزرسانی

    class Meta:
        unique_together = (
            "player_a", "player_b", "gender", "age_category", "belt_group", "weight_category"
        )

    def save(self, *args, **kwargs):
        # نرمال‌سازی ترتیب تا (a,b) و (b,a) تکراری نشوند
        if self.player_a_id and self.player_b_id and self.player_a_id > self.player_b_id:
            self.player_a_id, self.player_b_id = self.player_b_id, self.player_a_id
        super().save(*args, **kwargs)

class RankingAward(models.Model):
    enrollment = models.OneToOneField('Enrollment', on_delete=models.CASCADE, related_name='ranking_award')

    player = models.ForeignKey(UserProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name='awards_as_player')
    coach  = models.ForeignKey(UserProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name='awards_as_coach')
    club   = models.ForeignKey(TkdClub,  null=True, blank=True, on_delete=models.SET_NULL, related_name='awards_as_club')
    board  = models.ForeignKey(TkdBoard, null=True, blank=True, on_delete=models.SET_NULL, related_name='awards_as_board')

    player_name = models.CharField(max_length=255, blank=True)
    coach_name  = models.CharField(max_length=255, blank=True)
    club_name   = models.CharField(max_length=255, blank=True)
    board_name  = models.CharField(max_length=255, blank=True)

    points_player = models.FloatField(default=0.0)
    points_coach  = models.FloatField(default=0.0)
    points_club   = models.FloatField(default=0.0)
    points_board  = models.FloatField(default=0.0)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Award(enrollment={self.enrollment_id})"

def _award_points_after_payment(enrollment):
    player = enrollment.player

    coach = enrollment.coach or (player.coach if getattr(player, "coach_id", None) else None)
    club  = enrollment.club  or (player.club  if getattr(player, "club_id",  None) else None)
    board = (
        enrollment.board
        or (club.tkd_board if club and getattr(club, "tkd_board_id", None) else None)
        or (player.tkd_board if getattr(player, "tkd_board_id", None) else None)
    )

    defaults = dict(
        player=player, coach=coach, club=club, board=board,
        player_name=f"{getattr(player,'first_name','')} {getattr(player,'last_name','')}".strip(),
        coach_name=(f"{getattr(coach,'first_name','')} {getattr(coach,'last_name','')}".strip() if coach else ""),
        club_name=getattr(club, "club_name", "") or "",
        board_name=getattr(board, "name", "") or "",
        points_player=1.0,
        points_coach=0.75 if coach else 0.0,
        points_club=0.5  if club  else 0.0,
        points_board=0.5 if board else 0.0,
    )

    try:
        award, created = RankingAward.objects.get_or_create(
            enrollment=enrollment,
            defaults=defaults,
        )
    except IntegrityError:
        return  # یک درخواست همزمان دیگر ساخته

    if not created:
        return  # قبلاً ساخته شده؛ دوباره امتیاز نده

    # اعمال امتیازها (اتمیک با F)
    UserProfile.objects.filter(pk=player.pk).update(
        ranking_competition=F("ranking_competition") + award.points_player,
        ranking_total=F("ranking_total") + award.points_player,  # اگر total برای بازیکن هم می‌خواهی
    )
    if coach:
        UserProfile.objects.filter(pk=coach.pk).update(
            ranking_total=F("ranking_total") + award.points_coach
        )
    if club:
        TkdClub.objects.filter(pk=club.pk).update(
            ranking_total=F("ranking_total") + award.points_club
        )
    if board:
        TkdBoard.objects.filter(pk=board.pk).update(
            ranking_total=F("ranking_total") + award.points_board
        )



class KyorugiResult(models.Model):
    competition     = models.ForeignKey(
        "KyorugiCompetition",
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name="مسابقه",
    )
    weight_category = models.ForeignKey(
        "WeightCategory",
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name="رده وزنی",
    )

    gold_enrollment    = models.ForeignKey(
        "Enrollment",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="طلا (مقام اول)",
    )
    silver_enrollment  = models.ForeignKey(
        "Enrollment",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="نقره (مقام دوم)",
    )
    bronze1_enrollment = models.ForeignKey(
        "Enrollment",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="برنز (مقام سوم)",
    )
    bronze2_enrollment = models.ForeignKey(
        "Enrollment",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="برنز مشترک (سوم مشترک)",
    )

    notes = models.TextField(blank=True, default="", verbose_name="یادداشت")
    created_by = models.ForeignKey(
        "auth.User",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="ثبت‌کننده",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("competition", "weight_category")
        verbose_name = "نتیجه وزن"
        verbose_name_plural = "نتایج اوزان"
        indexes = [
            models.Index(fields=["competition", "weight_category"]),
        ]

    def __str__(self):
        return f"{self.competition.title} – {self.weight_category}"

    def clean(self):
        # 1) تکراری نبودن Enrollmentها در مقام‌ها
        chosen = [x for x in [self.gold_enrollment, self.silver_enrollment, self.bronze1_enrollment, self.bronze2_enrollment] if x]
        if len(chosen) != len(set(chosen)):
            raise ValidationError("یک ثبت‌نام نمی‌تواند همزمان در چند مقام ثبت شود.")

        # 2) هر Enrollment باید متعلق به همین مسابقه و همین وزن باشد
        for fld in ["gold_enrollment", "silver_enrollment", "bronze1_enrollment", "bronze2_enrollment"]:
            en = getattr(self, fld)
            if not en:
                continue
            if en.competition_id != self.competition_id:
                raise ValidationError({fld: "این ثبت‌نام متعلق به این مسابقه نیست."})
            if en.weight_category_id != self.weight_category_id:
                raise ValidationError({fld: "این ثبت‌نام متعلق به این رده وزنی نیست."})

        super().clean()

    @transaction.atomic
    def save(self, *args, **kwargs):
        # lock روی خود رکورد (اگر آپدیت است)
        if self.pk:
            type(self).objects.select_for_update().filter(pk=self.pk).exists()

        self.full_clean()
        super().save(*args, **kwargs)

        # idempotent: اول rollback، بعد اعمال جدید
        _rollback_result_points(self)
        _apply_result_points(self)


def _rollback_result_points(result: "KyorugiResult"):
    """
    تراکنش‌های قبلی همین result را از ranking_total کم می‌کند و حذف می‌کند.
    """
    txs = RankingTransaction.objects.filter(result=result)
    if not txs.exists():
        return

    for tx in txs:
        pts = float(tx.points or 0.0)
        if pts == 0:
            continue

        if tx.subject_type == RankingTransaction.SUBJECT_PLAYER:
            UserProfile.objects.filter(pk=tx.subject_id).update(
                ranking_competition=F("ranking_competition") - pts,
                ranking_total=F("ranking_total") - pts,
            )
        elif tx.subject_type == RankingTransaction.SUBJECT_COACH:
            UserProfile.objects.filter(pk=tx.subject_id).update(
                ranking_total=F("ranking_total") - pts
            )
        elif tx.subject_type == RankingTransaction.SUBJECT_CLUB:
            TkdClub.objects.filter(pk=tx.subject_id).update(
                ranking_total=F("ranking_total") - pts
            )
        elif tx.subject_type == RankingTransaction.SUBJECT_BOARD:
            TkdBoard.objects.filter(pk=tx.subject_id).update(
                ranking_total=F("ranking_total") - pts
            )

    txs.delete()


def _apply_result_points(result: "KyorugiResult"):
    """
    امتیازدهی مطابق نیاز:
    gold=3, silver=2, bronze=1, bronze2=1
    coach=30% of player points
    club=20% of player points
    board=20% of player points
    """
    medal_map = [
        ("gold",   result.gold_enrollment,   3.0),
        ("silver", result.silver_enrollment, 2.0),
        ("bronze", result.bronze1_enrollment, 1.0),
        ("bronze", result.bronze2_enrollment, 1.0),
    ]

    tx_bulk = []

    for medal, en, p_points in medal_map:
        if not en:
            continue

        player = en.player
        coach  = en.coach
        club   = en.club
        board  = en.board

        coach_points = round(p_points * 0.30, 2) if coach else 0.0
        club_points  = round(p_points * 0.20, 2) if club else 0.0
        board_points = round(p_points * 0.20, 2) if board else 0.0

        # دفتر امتیاز (ledger)
        tx_bulk.append(RankingTransaction(
            competition=result.competition,
            result=result,
            subject_type=RankingTransaction.SUBJECT_PLAYER,
            subject_id=player.pk,
            medal=medal,
            points=p_points,
        ))

        if coach and coach_points:
            tx_bulk.append(RankingTransaction(
                competition=result.competition,
                result=result,
                subject_type=RankingTransaction.SUBJECT_COACH,
                subject_id=coach.pk,
                medal=medal,
                points=coach_points,
            ))

        if club and club_points:
            tx_bulk.append(RankingTransaction(
                competition=result.competition,
                result=result,
                subject_type=RankingTransaction.SUBJECT_CLUB,
                subject_id=club.pk,
                medal=medal,
                points=club_points,
            ))

        if board and board_points:
            tx_bulk.append(RankingTransaction(
                competition=result.competition,
                result=result,
                subject_type=RankingTransaction.SUBJECT_BOARD,
                subject_id=board.pk,
                medal=medal,
                points=board_points,
            ))

        # اعمال به totals
        UserProfile.objects.filter(pk=player.pk).update(
            ranking_competition=F("ranking_competition") + p_points,
            ranking_total=F("ranking_total") + p_points,
        )
        if coach and coach_points:
            UserProfile.objects.filter(pk=coach.pk).update(
                ranking_total=F("ranking_total") + coach_points
            )
        if club and club_points:
            TkdClub.objects.filter(pk=club.pk).update(
                ranking_total=F("ranking_total") + club_points
            )
        if board and board_points:
            TkdBoard.objects.filter(pk=board.pk).update(
                ranking_total=F("ranking_total") + board_points
            )

    if tx_bulk:
        RankingTransaction.objects.bulk_create(tx_bulk)


    


# competitions/models.py (افزودنی)
class RankingTransaction(models.Model):
    SUBJECT_PLAYER = "player"
    SUBJECT_COACH  = "coach"
    SUBJECT_CLUB   = "club"
    SUBJECT_BOARD  = "board"
    SUBJECT_CHOICES = [
        (SUBJECT_PLAYER, "بازیکن"),
        (SUBJECT_COACH,  "مربی"),
        (SUBJECT_CLUB,   "باشگاه"),
        (SUBJECT_BOARD,  "هیئت"),
    ]

    competition  = models.ForeignKey("KyorugiCompetition", on_delete=models.CASCADE, related_name="ranking_transactions")
    result       = models.ForeignKey("KyorugiResult",      on_delete=models.CASCADE, related_name="transactions")
    subject_type = models.CharField(max_length=16, choices=SUBJECT_CHOICES)
    subject_id   = models.IntegerField()
    medal        = models.CharField(max_length=10, blank=True, default="")  # gold/silver/bronze
    points       = models.FloatField(default=0.0)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["competition", "subject_type", "subject_id"]),
            models.Index(fields=["result"]),
        ]

#-------------------------------------------------------------سمینار----------------------------------------------------------------------------
# -----------------------
# Helpers: public_id
# -----------------------
def _gen_seminar_public_id(n: int = 10) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(n))

def _unique_public_id_for_model(model_cls, field_name: str = "public_id", length: int = 10, attempts: int = 6) -> str:
    for _ in range(attempts):
        pid = _gen_seminar_public_id(length)
        if not model_cls.objects.filter(**{field_name: pid}).exists():
            return pid
    return _gen_seminar_public_id(length)

def _seminar_default_public_id() -> str:
    return _gen_seminar_public_id(10)

# -----------------------
# Seminar
# -----------------------
class SeminarQuerySet(models.QuerySet):
    def active(self):
        today = timezone.localdate()
        return self.filter(registration_start__lte=today, registration_end__gte=today)


class Seminar(models.Model):
    objects = SeminarQuerySet.as_manager()

    
    ROLE_PLAYER  = "player"
    ROLE_COACH   = "coach"
    ROLE_REFEREE = "referee"

    ROLE_CHOICES = [
        (ROLE_PLAYER,  "بازیکن"),
        (ROLE_COACH,   "مربی"),
        (ROLE_REFEREE, "داور"),
    ]
    ROLE_VALUES = [r[0] for r in ROLE_CHOICES]

    title       = models.CharField("عنوان", max_length=255)
    poster      = models.ImageField("پوستر", upload_to="seminars/posters/", blank=True, null=True)
    description = models.TextField("توضیحات", blank=True)

    registration_start = models.DateField("شروع ثبت‌نام")
    registration_end   = models.DateField("پایان ثبت‌نام")
    event_date         = models.DateField("تاریخ برگزاری")

    fee = models.PositiveIntegerField("هزینه (ریال)", default=0)

    location = models.CharField("مکان برگزاری", max_length=255, blank=True)

    allowed_roles = models.JSONField("نقش‌های مجاز", default=list, blank=True,
                                     help_text="مثلاً ['player','coach'] — خالی = همه نقش‌ها")

    created_at = models.DateTimeField("ایجاد شده در", auto_now_add=True)

    public_id = models.CharField(
        "شناسه عمومی",
        max_length=16,
        unique=True,
        db_index=True,
        editable=False,
        default=_seminar_default_public_id,
    )

    class Meta:
        verbose_name = "سمینار"
        verbose_name_plural = "سمینارها"
        indexes = [
            Index(fields=["public_id"]),
            Index(fields=["event_date"]),
        ]
        ordering = ["-event_date", "-created_at"]
        constraints = [
            CheckConstraint(check=Q(registration_start__lte=F("registration_end")),
                            name="seminar_reg_start_lte_reg_end"),
            CheckConstraint(check=Q(registration_end__lte=F("event_date")),
                            name="seminar_reg_end_lte_event_date"),
        ]

    def __str__(self) -> str:
        return self.title or f"سمینار #{self.pk}"

    # -------- Validation --------
    def clean(self):
        if self.registration_start and self.registration_end and self.registration_start > self.registration_end:
            raise ValidationError({"registration_start": "تاریخ شروع ثبت‌نام نباید بعد از تاریخ پایان ثبت‌نام باشد."})
        if self.registration_end and self.event_date and self.registration_end > self.event_date:
            raise ValidationError({"registration_end": "پایان ثبت‌نام نباید بعد از تاریخ برگزاری رویداد باشد."})

        if self.allowed_roles is None:
            self.allowed_roles = []
        elif not isinstance(self.allowed_roles, list):
            raise ValidationError({"allowed_roles": "allowed_roles باید یک لیست از مقادیر باشد."})
        else:
            invalid = [r for r in self.allowed_roles if r not in self.ROLE_VALUES]
            if invalid:
                raise ValidationError({"allowed_roles": f"مقادیر نامعتبر: {invalid}. مقادیر مجاز: {self.ROLE_VALUES}"})

        super().clean()

    # -------- Save with unique public_id --------
    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = _unique_public_id_for_model(type(self))
        for i in range(3):
            try:
                return super().save(*args, **kwargs)
            except IntegrityError as e:
                if "public_id" in str(e).lower() and i < 2:
                    self.public_id = _unique_public_id_for_model(type(self))
                    continue
                raise

    # -------- Helpers --------
    def can_register_role(self, role: Optional[str]) -> bool:
        allowed: List[str] = self.allowed_roles or []
        return True if not allowed else (bool(role) and role in allowed)

    @property
    def registration_open(self) -> bool:
        today = timezone.localdate()
        return self.registration_start <= today <= self.registration_end

    @staticmethod
    def _date_to_jalali_str(d) -> str:
        if not d:
            return ""
        try:
            j = jdatetime.date.fromgregorian(date=d)
            return f"{j.year:04d}/{j.month:02d}/{j.day:02d}"
        except Exception:
            return ""

    @property
    def registration_start_jalali(self) -> str: return self._date_to_jalali_str(self.registration_start)
    @property
    def registration_end_jalali(self)   -> str: return self._date_to_jalali_str(self.registration_end)
    @property
    def event_date_jalali(self)         -> str: return self._date_to_jalali_str(self.event_date)

    def allowed_roles_display(self) -> str:
        vals = self.allowed_roles or []
        if not vals:
            return "همه نقش‌ها"
        mapping = dict(self.ROLE_CHOICES)
        return "، ".join(mapping.get(v, v) for v in vals)

# -----------------------
# SeminarRegistration
# -----------------------
class SeminarRegistration(models.Model):
    seminar = models.ForeignKey(
        Seminar, verbose_name="سمینار",
        on_delete=models.CASCADE, related_name="registrations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="کاربر",
        on_delete=models.CASCADE, related_name="seminar_registrations"
    )

    roles = models.JSONField("نقش/نقش‌ها", default=list, blank=True, help_text="مثال: ['coach']")

    phone = models.CharField("تلفن تماس", max_length=40, blank=True)
    note  = models.TextField("یادداشت", blank=True)

    is_paid     = models.BooleanField("پرداخت شده", default=False)
    paid_amount = models.PositiveIntegerField("مبلغ پرداختی (ریال)", default=0)

    bank_ref_code = models.CharField("کد رهگیری بانک", max_length=64, blank=True, default="")
    paid_at     = models.DateTimeField("زمان پرداخت", null=True, blank=True)

    # --- تخفیف ---
    discount_code     = models.CharField("کد تخفیف", max_length=50, null=True, blank=True, db_index=True)
    
    discount_amount = models.PositiveIntegerField("مبلغ تخفیف (ریال)", default=0)

    
    payable_amount = models.PositiveIntegerField("مبلغ نهایی قابل پرداخت (ریال)", default=0)
    discount_redeemed = models.BooleanField("تخفیف مصرف‌شده؟", default=False)

    created_at = models.DateTimeField("ایجاد شده در", auto_now_add=True)

    class Meta:
        verbose_name = "ثبت‌نام سمینار"
        verbose_name_plural = "ثبت‌نام‌های سمینار"
        unique_together = ("seminar", "user")

    def __str__(self) -> str:
        return f"{self.user} → {self.seminar}"

    def clean(self):
        if self.roles is None:
            self.roles = []
        if not isinstance(self.roles, list):
            raise ValidationError({"roles": "roles باید یک لیست از نقش‌ها باشد."})

        invalid = [r for r in self.roles if r not in self.seminar.ROLE_VALUES]
        if invalid:
            raise ValidationError({"roles": f"نقش‌های نامعتبر: {invalid}"})
        if not self.roles:
            raise ValidationError({"roles": "باید حداقل یک نقش انتخاب شود."})
        super().clean()

    def mark_paid(self, amount: int = 0, ref_code: str = ""):
        if self.is_paid:
            return
        self.is_paid = True
        self.paid_amount = int(amount or 0)
        if ref_code:
            self.bank_ref_code = str(ref_code)
        self.paid_at = timezone.now()
        self.save(update_fields=["is_paid", "paid_amount", "bank_ref_code", "paid_at"])

# --- Proxy فقط برای ادمین: لیست شرکت‌کنندگان سمینارها ---
class SeminarParticipants(SeminarRegistration):
    class Meta:
        proxy = True
        verbose_name = "لیست شرکت‌کنندگان سمینارها"
        verbose_name_plural = "لیست شرکت‌کنندگان سمینارها"


#======================================================================poomseh==================================================================
# ====================== POOMSAE ======================
class PoomsaeCompetitionQuerySet(models.QuerySet):
    def active(self):
        today = timezone.localdate()
        return self.filter(
            Q(registration_manual=True) |
            (Q(registration_manual__isnull=True) &
             Q(registration_start__lte=today) &
             Q(registration_end__gte=today))
        ).exclude(registration_manual=False)
        
        
class PoomsaeCompetition(RegistrationManualMixin, models.Model):
    objects = PoomsaeCompetitionQuerySet.as_manager()

    class PoomsaeStyle(models.TextChoices):
        STANDARD = "standard", _("استاندارد")
        CREATIVE = "creative", _("ابداعی")

    # فهرست‌های کمکی برای فرم مثل کیوروگی
    GENDER_CHOICES = [('male', 'آقایان'), ('female', 'بانوان')]
    BELT_LEVEL_CHOICES = [
        ('yellow_blue', 'زرد تا آبی'),
        ('red_black', 'قرمز و مشکی'),
        ('all', 'همه رده‌ها'),
    ]

    public_id = models.SlugField(
        "شناسه عمومی", max_length=16, unique=True, db_index=True,
        editable=False, default=_gen_public_id,
    )

    # فیلدهای عمومی
    name = models.CharField(max_length=255, verbose_name="عنوان مسابقه")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    poster = models.ImageField('پوستر شاخص', upload_to='poomsae_posters/', null=True, blank=True)

    # انتخاب‌ها
    age_category = models.ForeignKey('AgeCategory', verbose_name='گروه سنی',
                                     on_delete=models.SET_NULL, null=True, blank=True)
    age_categories = models.ManyToManyField(AgeCategory, blank=True, related_name="poom_competitions")

    belt_level = models.CharField('رده کمربندی', max_length=20, choices=BELT_LEVEL_CHOICES, default='all', blank=True)
    belt_groups = models.ManyToManyField('BeltGroup', verbose_name='گروه‌های کمربندی', blank=True)
    gender = models.CharField('جنسیت', max_length=10, choices=GENDER_CHOICES, blank=True, default='')
    city = models.CharField('شهر محل برگزاری', max_length=100, blank=True, default='')
    address = models.TextField('آدرس محل برگزاری', blank=True, default='')

    terms_template = models.ForeignKey(
        TermsTemplate, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='poomsae_competitions', verbose_name='قالب تعهدنامه'
    )
 # تاریخ‌ها
    start_date = models.DateField(verbose_name="تاریخ شروع مسابقه")
    end_date   = models.DateField(verbose_name="تاریخ پایان مسابقه")

    # ⬅️ قبلش DateTimeField بود، الان می‌کنیم DateField
    registration_start = models.DateField(verbose_name="شروع ثبت‌نام")
    registration_end   = models.DateField(verbose_name="پایان ثبت‌نام")

    draw_date = models.DateField(verbose_name="تاریخ قرعه‌کشی", null=True, blank=True)
    competition_date = models.DateField(verbose_name="تاریخ برگزاری", null=True, blank=True)

    entry_fee = models.PositiveIntegerField(default=0, verbose_name="هزینه ورودی (ریال)")

    terms_text = models.TextField(blank=True, verbose_name="متن قوانین و مقررات")
    mat_count = models.PositiveIntegerField("تعداد زمین", default=1, validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "مسابقه پومسه"
        verbose_name_plural = "مسابقات پومسه"
        constraints = [
            CheckConstraint(check=Q(start_date__lte=F("end_date")), name="poomsae_start_lte_end"),
            CheckConstraint(check=Q(registration_start__lte=F("registration_end")), name="poomsae_reg_start_lte_end"),
            CheckConstraint(check=Q(registration_end__lte=F("start_date")), name="poomsae_reg_end_lte_start_date"),
        ]
        indexes = [
            Index(fields=["public_id"]),
            Index(fields=["start_date"]),
            Index(fields=["registration_start", "registration_end"]),
        ]
        ordering = ["-start_date", "-created_at"]

    def __str__(self):
        return self.name

    # alias برای استفادهٔ راحت در فرانت (comp.key)
    @property
    def key(self) -> str:
        return self.public_id

    @property
    def is_registration_open(self) -> bool:
        return self.registration_open_effective

    @property
    def style_display(self):
        return "پومسه"
    def allowed_belt_group_ids(self) -> set[int]:
        """
        اگر تخصیص زمین انجام شده باشد، فقط همین BeltGroup ها مجازند.
        اگر هیچ تخصیصی وجود نداشت، یعنی محدودیتی از سمت زمین‌ها نداریم.
        """
        qs = self.mat_assignments.values_list("belt_groups__id", flat=True)
        return set([x for x in qs if x])
    def resolve_belt_group_for(self, player: UserProfile) -> Optional['BeltGroup']:
        raw = getattr(player, "belt_grade", None)
        if not raw:
            return None
    
        t = str(raw).strip().lower().replace("ي", "ی").replace("ك", "ک")
    
        def _norm(v: str) -> Optional[str]:
            if not v:
                return None
            s = str(v).strip().lower().replace("ي", "ی").replace("ك", "ک")
            if "سفید" in s or "white" in s: return "white"
            if "زرد"  in s or "yellow" in s: return "yellow"
            if "سبز"  in s or "green" in s: return "green"
            if "آبی"  in s or "ابي" in s or "blue" in s: return "blue"
            if "قرمز" in s or "red" in s: return "red"
            if "مشکی" in s or "مشكى" in s or "black" in s: return "black"
            return None
    
        player_code = _norm(t)
        if not player_code:
            return None
    
        for g in self.belt_groups.all().prefetch_related("belts"):
            for b in g.belts.all():
                nm = getattr(b, "name", "") or getattr(b, "label", "")
                if _norm(nm) == player_code:
                    return g
        return None


    def _to_greg_if_jalali(self, d):
        if not d:
            return d
        # اگر date یا datetime با سال < 1700 است، به میلادی برگردان
        try:
            if isinstance(d, datetime):
                if d.year < 1700:
                    jdt = jdatetime.datetime(d.year, d.month, d.day, d.hour, d.minute, d.second)
                    return jdt.togregorian()
            elif isinstance(d, date):
                if d.year < 1700:
                    return jdatetime.date(d.year, d.month, d.day).togregorian()
        except Exception:
            pass
        return d

    def clean(self):
        self.start_date = self._to_greg_if_jalali(self.start_date)
        self.end_date = self._to_greg_if_jalali(self.end_date)
        self.draw_date = self._to_greg_if_jalali(self.draw_date)
        self.competition_date = self._to_greg_if_jalali(self.competition_date)
        self.registration_start = self._to_greg_if_jalali(self.registration_start)
        self.registration_end = self._to_greg_if_jalali(self.registration_end)
        super().clean()

    def save(self, *args, **kwargs):
        attempts = 4
        while attempts > 0:
            try:
                if not self.public_id:
                    self.public_id = _gen_public_id(10)
                return super().save(*args, **kwargs)
            except IntegrityError as e:
                if "public_id" in str(e).lower():
                    self.public_id = _gen_public_id(10)
                    attempts -= 1
                    continue
                raise
        raise IntegrityError("عدم امکان ایجاد شناسهٔ عمومی یکتا برای مسابقه پومسه.")

class PoomsaeMatAssignment(models.Model):
    """
    تخصیص زمین‌های پومسه به رده‌های کمربندی (BeltGroup)
    - هر زمین (mat_number) در یک مسابقه فقط یک رکورد دارد
    - belt_groups تعیین می‌کند این زمین کدام کمربندها را پوشش می‌دهد
    """
    competition = models.ForeignKey(
        PoomsaeCompetition,
        verbose_name="مسابقه پومسه",
        on_delete=models.CASCADE,
        related_name="mat_assignments",
    )
    mat_number = models.PositiveIntegerField("شماره زمین")
    belt_groups = models.ManyToManyField(
        BeltGroup,
        verbose_name="گروه‌های کمربندی تخصیص‌یافته",
        blank=True,
        related_name="poomsae_mat_assignments",
    )

    class Meta:
        verbose_name = "تخصیص زمین پومسه"
        verbose_name_plural = "تخصیص رده‌های کمربندی به زمین‌های پومسه"
        constraints = [
            models.UniqueConstraint(
                fields=["competition", "mat_number"],
                name="uniq_poomsae_mat_per_competition",
            ),
        ]
        indexes = [
            models.Index(fields=["competition", "mat_number"]),
        ]

    def __str__(self):
        return f"پومسه {self.competition} - زمین {self.mat_number}"

    def clean(self):
        super().clean()
        # اگر mat_count تنظیم شده، شماره زمین نباید بیشتر از آن باشد
        if self.competition_id and self.mat_number:
            mc = getattr(self.competition, "mat_count", None)
            if mc and self.mat_number > mc:
                raise ValidationError({"mat_number": f"شماره زمین نمی‌تواند بیشتر از تعداد زمین ({mc}) باشد."})
            if self.mat_number < 1:
                raise ValidationError({"mat_number": "شماره زمین باید >= 1 باشد."})


class PoomsaeDivision(models.Model):
    competition  = models.ForeignKey(PoomsaeCompetition, on_delete=models.CASCADE, related_name="divisions", verbose_name="مسابقه")
    age_category = models.ForeignKey("AgeCategory", on_delete=models.CASCADE, verbose_name="گروه سنی")
    belt_group   = models.ForeignKey("BeltGroup",   on_delete=models.CASCADE, verbose_name="رده کمربندی")
    style = models.CharField(
        max_length=20,
        choices=PoomsaeCompetition.PoomsaeStyle.choices,
        verbose_name="سبک مسابقه"
    )

    class Meta:
        verbose_name = "رده پومسه"
        verbose_name_plural = "رده‌های پومسه"
        unique_together = ("competition", "age_category", "belt_group", "style")
        indexes = [
            Index(fields=["competition", "age_category", "belt_group", "style"]),
        ]

    def __str__(self):
        return f"{self.competition.name} - {self.age_category} - {self.belt_group} - {self.get_style_display()}"

class PoomsaeCoachApproval(models.Model):
    """
    تأیید مربی برای شرکت بازیکنان در پومسه.
    - یکتایی مربی در هر مسابقه: (competition, coach)
    - یکتایی کد وقتی code نال نیست: (competition, code)
    - player می‌تواند تهی باشد؛ کد مربی هنگام ثبت‌نامِ بازیکن اعتبارسنجی می‌شود.
    """
    competition = models.ForeignKey(PoomsaeCompetition, on_delete=models.CASCADE,
                                    related_name="coach_approvals", verbose_name="مسابقه")
    player = models.ForeignKey("accounts.UserProfile", on_delete=models.CASCADE,
                               related_name="poomsae_approvals", verbose_name="بازیکن",
                               null=True, blank=True)
    coach  = models.ForeignKey("accounts.UserProfile", on_delete=models.CASCADE,
                               related_name="poomsae_coach_approvals",
                               limit_choices_to={"is_coach": True}, verbose_name="مربی")

    code = models.CharField("کد تأیید مربی", max_length=8, blank=True, null=True, db_index=True)
    approved = models.BooleanField("تأیید شده", default=False)
    is_active = models.BooleanField("فعال", default=True)
    created_at = models.DateTimeField("ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("به‌روزرسانی", auto_now=True)

    class Meta:
        verbose_name = "تأیید مربی پومسه"
        verbose_name_plural = "تأییدهای مربی پومسه"
        constraints = [
            models.UniqueConstraint(fields=["competition", "coach"],
                                    name="uniq_poomsae_competition_coach"),
            models.UniqueConstraint(fields=["competition", "code"],
                                    condition=Q(code__isnull=False),
                                    name="uniq_poomsae_competition_code"),
        ]
        indexes = [
            models.Index(fields=["competition", "is_active", "approved"]),
        ]

    def __str__(self):
        return f"{self.competition} - {self.player} - {self.coach}"

    @staticmethod
    def _rand_code(length: int = 6) -> str:
        upper = 10**length - 1
        return f"{random.randint(0, upper):0{length}d}"

    @transaction.atomic
    def set_fresh_code(self, save: bool = True, force: bool = False) -> str:
        if self.code and not force:
            return self.code
        current = type(self).objects.select_for_update().get(pk=self.pk)
        if current.code and not force:
            return current.code

        for _ in range(25):
            c = self._rand_code(6)
            if not type(self).objects.filter(competition=self.competition, code=c).exists():
                current.code = c
                if save:
                    setattr(current, "_allow_code_change", True)
                    current.save(update_fields=["code"])
                    delattr(current, "_allow_code_change")
                return c
        raise ValueError("ساخت کد یکتا ممکن نشد، دوباره تلاش کنید.")

    def clean(self):
        import re as _re
        if self.code and not _re.fullmatch(r"\d{4,8}", str(self.code)):
            raise ValidationError({"code": "کد باید عددی و بین ۴ تا ۸ رقم باشد."})
        super().clean()

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        should_check_code = (not update_fields) or ("code" in update_fields)
        if self.pk and should_check_code and not getattr(self, "_allow_code_change", False):
            orig = type(self).objects.only("code").get(pk=self.pk)
            if orig.code != self.code:
                raise ValidationError({"code": "تغییر کد مجاز نیست. فقط مسیر تولید کد مجاز است."})
        return super().save(*args, **kwargs)

# ====================== POOMSAE – Enrollment (مثل کیوروگی) ======================

class PoomsaeEnrollment(models.Model):
    POOMSAE_TYPE_CHOICES = [
        ("standard", "استاندارد"),
        ("creative", "ابداعی"),
    ]
    MODE_CHOICES = [
        ("single", "انفرادی"),
        ("team", "تیمی"),
    ]

    competition = models.ForeignKey(
        "competitions.PoomsaeCompetition",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    player = models.ForeignKey(
        UserProfile,
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="poomsae_enrollments",
    )

    coach = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="poomsae_coach_enrollments",
        limit_choices_to={"is_coach": True},
    )
    coach_name = models.CharField(max_length=150, blank=True, default="")
    coach_approval_code = models.CharField(max_length=8, blank=True, default="")

    club = models.ForeignKey(
        TkdClub, on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    club_name = models.CharField(max_length=150, blank=True, default="")

    board = models.ForeignKey(
        TkdBoard, on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    board_name = models.CharField(max_length=150, blank=True, default="")

    belt_group = models.ForeignKey(
        "competitions.BeltGroup",
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    age_category = models.ForeignKey(
        "competitions.AgeCategory",
        on_delete=models.PROTECT,
        null=True, blank=True,
    )

    poomsae_type = models.CharField(max_length=16, choices=POOMSAE_TYPE_CHOICES)
    mode = models.CharField(max_length=8, choices=MODE_CHOICES, default="single")

    insurance_number = models.CharField(max_length=20)
    insurance_issue_date = models.DateField()

    team = models.ForeignKey(
        "competitions.PoomsaeTeam",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="enrollments",
    )

    status = models.CharField(max_length=20, default="pending_payment")
    is_paid = models.BooleanField(default=False)
    paid_amount = models.PositiveIntegerField(default=0)  # ریال

    bank_ref_code = models.CharField(max_length=64, blank=True, default="")
    paid_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # 1) قانون انفرادی/تیمی: یکی از player یا team باید پر باشد، نه هر دو
            CheckConstraint(
                check=(
                    (Q(mode="single") & Q(player__isnull=False) & Q(team__isnull=True))
                    | (Q(mode="team") & Q(player__isnull=True) & Q(team__isnull=False))
                ),
                name="poomsae_enrollment_mode_requires_player_or_team",
            ),
    
            # 2) یکتایی انفرادی: هر بازیکن در هر مسابقه برای هر سبک فقط یکبار
            models.UniqueConstraint(
                fields=["competition", "player", "poomsae_type"],
                condition=Q(mode="single"),
                name="uniq_poomsae_single_per_style",
            ),
    
            # 3) یکتایی تیمی: هر تیم در هر مسابقه فقط یکبار ثبت‌نام (سبک از خود team می‌آید)
            models.UniqueConstraint(
                fields=["competition", "team"],
                condition=Q(mode="team"),
                name="uniq_poomsae_team_once",
            ),
        ]
        indexes = [
            models.Index(fields=["competition", "mode", "poomsae_type"]),
            models.Index(fields=["competition", "player"]),
            models.Index(fields=["competition", "team"]),
        ]


    # ---------------- helpers ----------------
    def _auto_fill_snapshots(self):
        # coach_name
        if self.coach_id and not (self.coach_name or "").strip():
            self.coach_name = f"{getattr(self.coach,'first_name','')} {getattr(self.coach,'last_name','')}".strip()

        # club + club_name
        if not self.club_id:
            self.club = getattr(self.player, "club", None)
        if self.club and not (self.club_name or "").strip():
            self.club_name = getattr(self.club, "club_name", "") or getattr(self.club, "name", "") or ""

        # board + board_name
        if not self.board_id:
            self.board = getattr(self.player, "tkd_board", None)
        if self.board and not (self.board_name or "").strip():
            self.board_name = getattr(self.board, "name", "") or ""

    # ---------------- validation ----------------
    def clean(self):
        errors = {}
    
        # --- mode enforcement (با nullable شدن player) ---
        if self.mode == "team":
            # تیمی: team اجباری، player باید خالی باشد
            if not self.team_id:
                errors["team"] = "در ثبت‌نام تیمی، انتخاب تیم الزامی است."
            if self.player_id:
                errors["player"] = "در ثبت‌نام تیمی نباید بازیکن (player) ست شود."
            if self.team_id:
                if self.team.competition_id != self.competition_id:
                    errors["team"] = "این تیم متعلق به این مسابقه نیست."
                # سبک enrollment باید با team یکی باشد
                if self.team.style != self.poomsae_type:
                    errors["poomsae_type"] = "نوع پومسه با سبک تیم مطابقت ندارد."
    
        elif self.mode == "single":
            # انفرادی: player اجباری، team باید خالی باشد
            if not self.player_id:
                errors["player"] = "در ثبت‌نام انفرادی، انتخاب بازیکن الزامی است."
            if self.team_id:
                errors["team"] = "در ثبت‌نام انفرادی نباید تیم انتخاب شود."
    
        # insurance date check (همان کد قبلی)
        if self.insurance_issue_date:
            comp_date = getattr(self.competition, "competition_date", None) or getattr(self.competition, "start_date", None)
            if comp_date:
                delta = comp_date - self.insurance_issue_date
                if delta.days < 3 or delta.days > 365:
                    errors["insurance_issue_date"] = "تاریخ بیمه باید بین ۳ روز تا ۱ سال قبل از مسابقه باشد."
    
        # فقط اگر player داریم snapshot های player محور را پر کنیم
        if self.player_id:
            self._auto_fill_snapshots()
    
        if errors:
            raise ValidationError(errors)
    
        super().clean()


    # ---------------- save ----------------
    def save(self, *args, **kwargs):
        # مهم: برای API هم clean اجرا شود
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        if self.mode == "team" and self.team_id:
            return f"TEAM:{self.team_id} - {self.competition} ({self.poomsae_type})"
        return f"{self.player} - {self.competition} ({self.poomsae_type})"




class PoomsaeImage(models.Model):
    competition = models.ForeignKey(
        PoomsaeCompetition, related_name='images',
        on_delete=models.CASCADE, verbose_name='مسابقه'
    )
    image = models.ImageField('تصویر پیوست', upload_to='poomsae_images/')

    class Meta:
        verbose_name = 'تصویر مسابقه پومسه'
        verbose_name_plural = 'تصاویر مسابقه پومسه'

class PoomsaeFile(models.Model):
    competition = models.ForeignKey(
        PoomsaeCompetition, related_name='files',
        on_delete=models.CASCADE, verbose_name='مسابقه'
    )
    file = models.FileField('فایل PDF', upload_to='poomsae_files/')

    class Meta:
        verbose_name = 'فایل مسابقه پومسه'
        verbose_name_plural = 'فایل‌های مسابقه پومسه'

# --- Backward-compat alias (to keep old imports working) ---
PoomsaeEntry = PoomsaeEnrollment






class PoomsaeTeam(models.Model):
    """
    تیم پومسه (برای مسابقهٔ پومسه، فقط مربی می‌سازد)
    - style همان standard/creative است (مثل poomsae_type)
    """
    STYLE_CHOICES = [
        ("standard", "استاندارد"),
        ("creative", "ابداعی"),
    ]

    competition = models.ForeignKey(
        PoomsaeCompetition,
        on_delete=models.CASCADE,
        related_name="teams",
        verbose_name="مسابقه پومسه",
    )
    coach = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="poomsae_teams",
        verbose_name="مربی",
        limit_choices_to={"is_coach": True},
    )
    name = models.CharField("نام تیم", max_length=100)
    style = models.CharField(
        "سبک تیم",
        max_length=16,
        choices=STYLE_CHOICES,  # standard / creative
    )
    created_at = models.DateTimeField("ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "تیم پومسه"
        verbose_name_plural = "تیم‌های پومسه"
        indexes = [
            models.Index(fields=["competition", "coach"]),
        ]
    def validate_members_counts(self, main_count: int, sub_count: int):
        """
        Standard: main=3 (اجباری), sub<=2
        Creative: main=2 (اجباری), sub<=1
        """
        if self.style == "standard":
            if main_count != 3:
                raise ValidationError("در تیم استاندارد باید دقیقاً ۳ عضو اصلی وجود داشته باشد.")
            if sub_count > 2:
                raise ValidationError("در تیم استاندارد حداکثر ۲ عضو ذخیره مجاز است.")
        elif self.style == "creative":
            if main_count != 2:
                raise ValidationError("در تیم ابداعی باید دقیقاً ۲ عضو اصلی وجود داشته باشد.")
            if sub_count > 1:
                raise ValidationError("در تیم ابداعی حداکثر ۱ عضو ذخیره مجاز است.")
    def __str__(self):
        return f"{self.name} – {self.get_style_display()}"


class PoomsaeTeamMember(models.Model):
    """
    عضو تیم پومسه (اصلی / ذخیره)
    """
    ROLE_MAIN = "main"
    ROLE_SUB  = "sub"
    ROLE_CHOICES = [
        (ROLE_MAIN, "اصلی"),
        (ROLE_SUB,  "ذخیره"),
    ]

    team = models.ForeignKey(
        PoomsaeTeam,
        on_delete=models.CASCADE,
        related_name="members",
        verbose_name="تیم",
    )
    player = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="poomsae_team_memberships",
        verbose_name="بازیکن",
    )
    role = models.CharField(
        "نقش در تیم",
        max_length=8,
        choices=ROLE_CHOICES,
        default=ROLE_MAIN,
    )
    order = models.PositiveSmallIntegerField(
        "ترتیب در تیم",
        default=1,
        help_text="برای مرتب‌کردن اعضا (۱، ۲، ۳، ...)",
    )

    class Meta:
        verbose_name = "عضو تیم پومسه"
        verbose_name_plural = "اعضای تیم‌های پومسه"
        unique_together = (("team", "player"),)
        indexes = [
            models.Index(fields=["team"]),
            models.Index(fields=["player"]),
        ]

    def __str__(self):
        return f"{self.player} @ {self.team} ({self.get_role_display()})"



class GroupRegistrationPayment(models.Model):
    coach = models.ForeignKey(
        "accounts.UserProfile",
        on_delete=models.CASCADE,
        related_name="group_payments"
    )
    competition = models.ForeignKey(
        "competitions.KyorugiCompetition",
        on_delete=models.CASCADE,
        related_name="group_payments"
    )

    payload = models.JSONField()  # اطلاعات شاگردها
    total_amount = models.PositiveIntegerField()  # ریال


    is_paid = models.BooleanField(default=False)
    bank_ref_code = models.CharField(max_length=64, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"GroupPayment #{self.id} - {self.coach_id}"



#==============================کد تخفیف======================================

class DiscountCodeType(models.TextChoices):
    COACH_GROUP = "COACH_GROUP", "تخفیف مربی (گروهی)"
    STUDENT = "STUDENT", "تخفیف هنرجو (تکی)"


class DiscountCode(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="کد تخفیف",
        help_text="مثلاً: CHB2025-ALICOACH"
    )

    # مربی
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="discount_codes",
        verbose_name="مربی",
    )

    type = models.CharField(
        max_length=20,
        choices=DiscountCodeType.choices,
        verbose_name="نوع کد",
    )

    percent = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        verbose_name="درصد تخفیف",
    )

    # هر کد برای یک مسابقه / پومسه / سمینار خاص
    competition = models.ForeignKey(
        "competitions.KyorugiCompetition",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="discount_codes",
        verbose_name="مسابقه کیوروگی",
    )

    poomsae_competition = models.ForeignKey(
        "competitions.PoomsaeCompetition",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="discount_codes_poomsae",
        verbose_name="مسابقه پومسه",
    )

    seminar = models.ForeignKey(
        "competitions.Seminar",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="discount_codes",
        verbose_name="سمینار",
    )

    max_uses = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="حداکثر تعداد استفاده (برای هنرجو)",
        help_text="فقط برای کد هنرجو. اگر خالی باشد یعنی نامحدود.",
    )
    used_count = models.PositiveIntegerField(
        default=0,
        verbose_name="تعداد استفاده‌شده",
    )

    active = models.BooleanField(default=True, verbose_name="فعال؟")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین تغییر")

    class Meta:
        verbose_name = "کد تخفیف"
        verbose_name_plural = "کدهای تخفیف"

    def __str__(self):
        return f"{self.code} - {self.coach} - {self.percent}%"

    @property
    def remaining_uses(self):
        if self.max_uses is None:
            return None
        return max(self.max_uses - self.used_count, 0)

    def clean(self):
        super().clean()
        targets = [
            bool(self.competition),
            bool(self.poomsae_competition),
            bool(self.seminar),
        ]
        # حداکثر یکی انتخاب شود
        if sum(targets) > 1:
            raise ValidationError(
                "هر کد تخفیف فقط باید برای یکی از «مسابقه کیوروگی» یا «مسابقه پومسه» یا «سمینار» تنظیم شود."
            )