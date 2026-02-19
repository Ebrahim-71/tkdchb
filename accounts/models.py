from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from accounts.utils.file_utils import clean_filename

User = get_user_model()



from django.db.models.signals import post_save
from django.dispatch import receiver


def club_license_upload(instance, filename):
    filename = clean_filename(filename)
    return f"club_licenses/{filename}"

def pending_photo_upload(instance, filename):
    filename = clean_filename(filename)
    return f"pending_photos/{filename}"

def player_photo_upload(instance, filename):
    filename = clean_filename(filename)
    return f"player_photos/{filename}"

# -----------------------------
# ۱) هیئت
# -----------------------------
class TkdBoard(models.Model):
    name = models.CharField("نام هیئت", max_length=100)
    province = models.CharField("استان", max_length=100)
    city = models.CharField("شهر", max_length=100)
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, null=True, blank=True, verbose_name="کاربر مرتبط"
    )
    ranking_total = models.FloatField("امتیاز کل", default=0)

    def __str__(self):
        return (self.name or "").strip() or f"هیئت #{self.pk}"

    class Meta:
        verbose_name = "هیئت"
        verbose_name_plural = "\u200b\u200c\u200c\u200cهیئت‌ها"


# -----------------------------
# ۲) باشگاه
# -----------------------------
class TkdClub(models.Model):
    club_name = models.CharField("نام باشگاه", max_length=100)
    founder_name = models.CharField("نام مؤسس", max_length=100)
    founder_national_code = models.CharField("کد ملی مؤسس", max_length=10)
    founder_phone = models.CharField(
        "شماره موبایل مؤسس", max_length=11, db_index=True
    )

    province = models.CharField("استان", max_length=100)
    county = models.CharField("شهرستان", max_length=100)
    city = models.CharField("شهر", max_length=100)

    tkd_board = models.ForeignKey(
        TkdBoard, on_delete=models.SET_NULL, null=True, related_name="clubs", verbose_name="هیئت"
    )

    license_number = models.CharField("شماره مجوز", max_length=100)
    federation_id = models.CharField("شناسه فدراسیون", max_length=100)

    CLUB_TYPE_CHOICES = [
        ("private", "خصوصی"),
        ("governmental", "دولتی"),
        ("other", "سایر"),
    ]
    club_type = models.CharField("نوع باشگاه", max_length=20, choices=CLUB_TYPE_CHOICES)

    phone = models.CharField("تلفن باشگاه", max_length=11)
    address = models.TextField("آدرس")
    activity_description = models.TextField("توضیحات فعالیت", blank=True, null=True)
    license_image = models.ImageField("تصویر مجوز", upload_to=club_license_upload)

    confirm_info = models.BooleanField("اطلاعات تأیید شده", default=False)

    coach_count = models.PositiveIntegerField("تعداد مربیان", default=0)
    student_count = models.PositiveIntegerField("تعداد ورزشکاران", default=0)
    matches_participated = models.PositiveIntegerField("تعداد حضور در مسابقات", default=0)

    gold_medals = models.PositiveIntegerField("مدال‌های طلا", default=0)
    silver_medals = models.PositiveIntegerField("مدال‌های نقره", default=0)
    bronze_medals = models.PositiveIntegerField("مدال‌های برنز", default=0)

    ranking_competition = models.FloatField("امتیاز مسابقات", default=0)
    ranking_total = models.FloatField("امتیاز کل", default=0)

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, null=True, blank=True, verbose_name="کاربر مرتبط"
    )

    def __str__(self):
        name = (self.club_name or "").strip()
        return name or f"باشگاه #{self.pk}"

    class Meta:
        verbose_name = "باشگاه"
        verbose_name_plural = "\u200b\u200b\u200cباشگاه‌ها"
        constraints = [
            models.UniqueConstraint(
                fields=["club_name", "city"],
                name="uniq_club_name_city",
            ),
        ]

class PendingClub(models.Model):
    club_name = models.CharField("نام باشگاه", max_length=100)
    founder_name = models.CharField("نام مؤسس", max_length=100)
    founder_national_code = models.CharField("کد ملی مؤسس", max_length=10)
    founder_phone = models.CharField("شماره موبایل مؤسس", max_length=11)

    club_type = models.CharField(
        "نوع باشگاه",
        max_length=20,
        choices=[("private", "خصوصی"), ("governmental", "دولتی"), ("other", "سایر")],
    )
    activity_description = models.TextField("توضیحات فعالیت", blank=True, null=True)

    province = models.CharField("استان", max_length=100)
    county = models.CharField("شهرستان", max_length=100)
    city = models.CharField("شهر", max_length=100)

    tkd_board = models.ForeignKey(
        TkdBoard, on_delete=models.SET_NULL, null=True,
        related_name="pending_clubs", verbose_name="هیئت"
    )
    tkd_board_name = models.CharField("نام هیئت (متنی)", max_length=100, blank=True)

    phone = models.CharField("تلفن باشگاه", max_length=11)
    address = models.TextField("آدرس")

    license_number = models.CharField("شماره مجوز", max_length=100)
    federation_id = models.CharField("شناسه فدراسیون", max_length=100)
    license_image = models.ImageField("تصویر مجوز", upload_to=club_license_upload)


    confirm_info = models.BooleanField("اطلاعات تأیید شده", default=False)
    submitted_at = models.DateTimeField("تاریخ ارسال", auto_now_add=True)

    def __str__(self):
        name = (self.club_name or "").strip()
        return f"در انتظار تأیید: {name or f'باشگاه #{self.pk}'}"

    class Meta:
        verbose_name = "تأیید باشگاه"
        verbose_name_plural = "\u200c\u200c\u200c\u200cتأیید باشگاه‌ها"
        constraints = [
            models.UniqueConstraint(
                fields=["club_name", "city"],
                name="uniq_pending_club_name_city",
            ),
        ]


# -----------------------------
# ۳) پروفایل کاربر تأیید‌شده
# -----------------------------
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("player", "بازیکن"),
        ("coach", "مربی"),
        ("referee", "داور"),
        ("both", "مربی و داور"),
    ]
    GENDER_CHOICES = [("male", "مرد"), ("female", "زن")]
    BELT_CHOICES = [
        ("سفید", "سفید"),
        ("زرد", "زرد"),
        ("سبز", "سبز"),
        ("آبی", "آبی"),
        ("قرمز", "قرمز"),
        *[(f"مشکی دان {i}", f"مشکی دان {i}") for i in range(1, 11)],
    ]
    DEGREE_CHOICES = [
        ("درجه یک", "درجه یک"),
        ("درجه دو", "درجه دو"),
        ("درجه سه", "درجه سه"),
        ("ممتاز", "ممتاز"),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile",
        null=True, blank=True, verbose_name="کاربر مرتبط"
    )
    first_name = models.CharField("نام", max_length=50)
    last_name = models.CharField("نام خانوادگی", max_length=50)
    father_name = models.CharField("نام پدر", max_length=50)
    national_code = models.CharField("کد ملی", max_length=10, unique=True)
    birth_date = models.CharField("تاریخ تولد", max_length=10, help_text="فرمت: ۱۴۰۳/۰۴/۱۰")
    gender = models.CharField("جنسیت", max_length=10, choices=GENDER_CHOICES)
    phone = models.CharField("شماره موبایل", max_length=11, unique=True, db_index=True)
    role = models.CharField("نقش", max_length=10, choices=ROLE_CHOICES, default="player")
    profile_image = models.ImageField("عکس پرسنلی", upload_to=player_photo_upload)

    address = models.TextField("آدرس")
    province = models.CharField("استان", max_length=50)
    county = models.CharField("شهرستان", max_length=50)
    city = models.CharField("شهر", max_length=50)

    tkd_board = models.ForeignKey(TkdBoard, on_delete=models.SET_NULL, null=True, verbose_name="هیئت")
    tkd_board_name = models.CharField("نام هیئت (متنی)", max_length=255, blank=True)

    coach = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"is_coach": True},
        related_name="students",
        verbose_name="مربی"
    )

    coach_name = models.CharField("نام مربی (متنی)", max_length=255, blank=True)
    club = models.ForeignKey(
        TkdClub, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="members", verbose_name="باشگاه"
    )

    club_names = models.JSONField("نام باشگاه‌ها (متنی)", default=list, blank=True)
    coaching_clubs = models.ManyToManyField(
        TkdClub, blank=True, related_name="coaches", verbose_name="باشگاه‌های تحت مربیگری"
    )

    belt_grade = models.CharField("درجه کمربند", max_length=20, choices=BELT_CHOICES)
    belt_certificate_number = models.CharField("شماره گواهی کمربند", max_length=50)
    belt_certificate_date = models.CharField(
        "تاریخ گواهی کمربند", max_length=10, help_text="فرمت: ۱۴۰۳/۰۴/۱۰"
    )

    is_coach = models.BooleanField("مربی است؟", default=False)
    coach_level = models.CharField("درجه مربیگری", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)
    coach_level_International = models.CharField("درجه مربیگری بین‌المللی", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)

    is_referee = models.BooleanField("داور است؟", default=False)
    kyorogi = models.BooleanField("کیوروگی", default=False)
    kyorogi_level = models.CharField("درجه کیوروگی", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)
    kyorogi_level_International = models.CharField("درجه بین‌المللی کیوروگی", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)
    poomseh = models.BooleanField("پومسه", default=False)
    poomseh_level = models.CharField("درجه پومسه", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)
    poomseh_level_International = models.CharField("درجه بین‌المللی پومسه", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)
    hanmadang = models.BooleanField("هان مادانگ", default=False)
    hanmadang_level = models.CharField("درجه هان مادانگ", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)
    hanmadang_level_International = models.CharField("درجه بین‌المللی هان مادانگ", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)

    match_count = models.PositiveIntegerField("تعداد مسابقات", default=0)
    seminar_count = models.PositiveIntegerField("تعداد سمینارها", default=0)
    gold_medals = models.PositiveIntegerField("مدال طلا", default=0)
    silver_medals = models.PositiveIntegerField("مدال نقره", default=0)
    bronze_medals = models.PositiveIntegerField("مدال برنز", default=0)

    gold_medals_country = models.PositiveIntegerField("مدال طلا (کشوری)", default=0)
    silver_medals_country = models.PositiveIntegerField("مدال نقره (کشوری)", default=0)
    bronze_medals_country = models.PositiveIntegerField("مدال برنز (کشوری)", default=0)

    gold_medals_int = models.PositiveIntegerField("مدال طلا (بین‌المللی)", default=0)
    silver_medals_int = models.PositiveIntegerField("مدال نقره (بین‌المللی)", default=0)
    bronze_medals_int = models.PositiveIntegerField("مدال برنز (بین‌المللی)", default=0)

    ranking_competition = models.FloatField("امتیاز مسابقات", default=0)
    ranking_total = models.FloatField("امتیاز کل", default=0)

    confirm_info = models.BooleanField("اطلاعات تأیید شده", default=False)
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)

    def __str__(self):
        full = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return full or (self.phone or f"کاربر #{self.pk}")

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = " کاربران"


# -----------------------------
# ۴) ثبت‌نام در انتظار تأیید
# -----------------------------
class PendingUserProfile(models.Model):
    ROLE_CHOICES = UserProfile.ROLE_CHOICES
    GENDER_CHOICES = UserProfile.GENDER_CHOICES

    first_name = models.CharField("نام", max_length=50)
    last_name = models.CharField("نام خانوادگی", max_length=50)
    father_name = models.CharField("نام پدر", max_length=50)
    national_code = models.CharField("کد ملی", max_length=10, unique=True)
    birth_date = models.CharField("تاریخ تولد", max_length=10, help_text="فرمت: ۱۴۰۳/۰۴/۱۰")
    phone = models.CharField("شماره موبایل", max_length=11, unique=True)
    role = models.CharField("نقش", max_length=10, choices=ROLE_CHOICES, default="player")
    gender = models.CharField("جنسیت", max_length=10, choices=GENDER_CHOICES)
    address = models.TextField("آدرس")
    province = models.CharField("استان", max_length=50)
    county = models.CharField("شهرستان", max_length=50)
    city = models.CharField("شهر", max_length=50)
    tkd_board = models.ForeignKey(TkdBoard, on_delete=models.SET_NULL, null=True, verbose_name="هیئت")
    tkd_board_name = models.CharField("نام هیئت (متنی)", max_length=255, blank=True)

    profile_image = models.ImageField(
    "عکس پرسنلی (در انتظار تأیید)",
    upload_to=pending_photo_upload,
)



    belt_grade = models.CharField("درجه کمربند", max_length=20, choices=UserProfile.BELT_CHOICES)
    belt_certificate_number = models.CharField("شماره گواهی کمربند", max_length=50)
    belt_certificate_date = models.CharField("تاریخ گواهی کمربند", max_length=10, help_text="فرمت: ۱۴۰۳/۰۴/۱۰")
    coach_name = models.CharField("نام مربی (متنی)", max_length=255, blank=True)
    club_names = models.JSONField("نام باشگاه‌ها (متنی)", default=list, blank=True)

    is_coach = models.BooleanField("مربی است؟", default=False)
    coach_level = models.CharField("درجه مربیگری", max_length=20, choices=UserProfile.DEGREE_CHOICES, null=True, blank=True)
    coach_level_International = models.CharField("درجه مربیگری بین‌المللی", max_length=20, choices=UserProfile.DEGREE_CHOICES, null=True, blank=True)

    is_referee = models.BooleanField("داور است؟", default=False)
    kyorogi = models.BooleanField("کیوروگی", default=False)
    poomseh = models.BooleanField("پومسه", default=False)
    hanmadang = models.BooleanField("هان مادانگ", default=False)

    kyorogi_level = models.CharField("درجه کیوروگی", max_length=20, choices=UserProfile.DEGREE_CHOICES, null=True, blank=True)
    kyorogi_level_International = models.CharField("درجه بین‌المللی کیوروگی", max_length=20, choices=UserProfile.DEGREE_CHOICES, null=True, blank=True)

    poomseh_level = models.CharField("درجه پومسه", max_length=20, choices=UserProfile.DEGREE_CHOICES, null=True, blank=True)
    poomseh_level_International = models.CharField("درجه بین‌المللی پومسه", max_length=20, choices=UserProfile.DEGREE_CHOICES, null=True, blank=True)

    hanmadang_level = models.CharField("درجه هان مادانگ", max_length=20, choices=UserProfile.DEGREE_CHOICES, null=True, blank=True)
    hanmadang_level_International = models.CharField("درجه بین‌المللی هان مادانگ", max_length=20, choices=UserProfile.DEGREE_CHOICES, null=True, blank=True)

    coaching_clubs = models.ManyToManyField(
        TkdClub, blank=True, related_name="pending_coaches", verbose_name="باشگاه‌های تحت مربیگری"
    )

    confirm_info = models.BooleanField("اطلاعات تأیید شده", default=False)

    coach = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pending_students",
        limit_choices_to={"is_coach": True},
        verbose_name="مربی"
    )
    club = models.ForeignKey(
        TkdClub, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pending_members", verbose_name="باشگاه"
    )

    submitted_at = models.DateTimeField("تاریخ ارسال", auto_now_add=True)

    def __str__(self):
        full = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return f"{full or f'کاربر #{self.pk}'} (در انتظار تأیید)"


# -----------------------------
# ۵) درخواست ویرایش پروفایل
# -----------------------------
class PendingEditProfile(models.Model):
    ROLE_CHOICES = UserProfile.ROLE_CHOICES
    GENDER_CHOICES = UserProfile.GENDER_CHOICES
    DEGREE_CHOICES = UserProfile.DEGREE_CHOICES
    BELT_CHOICES = UserProfile.BELT_CHOICES

    original_user = models.OneToOneField(
        UserProfile, on_delete=models.CASCADE, related_name="edit_request", verbose_name="کاربر اصلی"
    )

    # فیلدهای قابل ویرایش
    first_name = models.CharField("نام", max_length=50)
    last_name = models.CharField("نام خانوادگی", max_length=50)
    father_name = models.CharField("نام پدر", max_length=50)
    national_code = models.CharField("کد ملی", max_length=10, unique=True)
    birth_date = models.CharField("تاریخ تولد", max_length=10, help_text="فرمت: ۱۴۰۳/۰۴/۱۰")
    phone = models.CharField("شماره موبایل", max_length=11, unique=True)
    role = models.CharField("نقش", max_length=10, choices=ROLE_CHOICES, default="player")
    gender = models.CharField("جنسیت", max_length=10, choices=GENDER_CHOICES)
    address = models.TextField("آدرس")
    province = models.CharField("استان", max_length=50)
    county = models.CharField("شهرستان", max_length=50)
    city = models.CharField("شهر", max_length=50)
    tkd_board = models.ForeignKey(TkdBoard, on_delete=models.SET_NULL, null=True, verbose_name="هیئت")
    tkd_board_name = models.CharField("نام هیئت (متنی)", max_length=255, blank=True)
    profile_image = models.ImageField(
        "عکس پروفایل (در انتظار تأیید)",
        upload_to=pending_photo_upload,
        blank=True,
        null=True,
    )


    belt_grade = models.CharField("درجه کمربند", max_length=20, choices=BELT_CHOICES)
    belt_certificate_number = models.CharField("شماره گواهی کمربند", max_length=50)
    belt_certificate_date = models.CharField("تاریخ گواهی کمربند", max_length=10, help_text="فرمت: ۱۴۰۳/۰۴/۱۰")
    coach_name = models.CharField("نام مربی (متنی)", max_length=255, blank=True)
    club_names = models.JSONField("نام باشگاه‌ها (متنی)", default=list, blank=True)

    is_coach = models.BooleanField("مربی است؟", default=False)
    coach_level = models.CharField("درجه مربیگری", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)
    coach_level_International = models.CharField("درجه مربیگری بین‌المللی", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)

    is_referee = models.BooleanField("داور است؟", default=False)
    kyorogi = models.BooleanField("کیوروگی", default=False)
    poomseh = models.BooleanField("پومسه", default=False)
    hanmadang = models.BooleanField("هان مادانگ", default=False)

    kyorogi_level = models.CharField("درجه کیوروگی", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)
    kyorogi_level_International = models.CharField("درجه بین‌المللی کیوروگی", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)
    poomseh_level = models.CharField("درجه پومسه", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)
    poomseh_level_International = models.CharField("درجه بین‌المللی پومسه", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)
    hanmadang_level = models.CharField("درجه هان مادانگ", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)
    hanmadang_level_International = models.CharField("درجه بین‌المللی هان مادانگ", max_length=20, choices=DEGREE_CHOICES, null=True, blank=True)

    confirm_info = models.BooleanField("اطلاعات تأیید شده", default=False)

    coach = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pending_edit_students",
        limit_choices_to={"is_coach": True},
        verbose_name="مربی"
    )
    club = models.ForeignKey(
        TkdClub, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pending_edit_members", verbose_name="باشگاه"
    )
    coaching_clubs = models.ManyToManyField(
        TkdClub, blank=True, related_name="pending_edit_coaches", verbose_name="باشگاه‌های تحت مربیگری"
    )

    submitted_at = models.DateTimeField("تاریخ ارسال", auto_now_add=True)

    def __str__(self):
        try:
            base = str(self.original_user) if self.original_user_id else ""
        except Exception:
            base = ""
        uid = self.original_user_id or "?"
        fallback = f"کاربر #{uid}"
        label = base or fallback
        return f"ویرایش {label} - در انتظار تأیید"

    class Meta:
        verbose_name = "درخواست ویرایش"
        verbose_name_plural = "\u200c\u200c\u200c\u200c\u200c درخواست‌های ویرایش"



class ProfileChangeHistory(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    field_name = models.CharField("نام فیلد تغییر یافته", max_length=100)
    old_value = models.TextField("مقدار قدیمی")
    new_value = models.TextField("مقدار جدید")
    changed_at = models.DateTimeField("زمان تغییر", auto_now_add=True)

    def __str__(self):
        return f"تغییر {self.field_name} برای {self.user_profile}"

    class Meta:
        verbose_name = "تاریخچه تغییرات پروفایل"
        verbose_name_plural = "تاریخچه تغییرات پروفایل‌ها"


@receiver(post_save, sender=PendingEditProfile)
def save_change_history(sender, instance, **kwargs):
    # مقایسه فیلدهای قدیمی و جدید و ذخیره تغییرات
    for field in instance._meta.get_fields():
        if field.name in ["original_user", "id"]:  # اجتناب از فیلدهایی که نیاز به تغییر ندارند
            continue
        
        old_value = getattr(instance, f"original_{field.name}", None)
        new_value = getattr(instance, field.name)
        if old_value != new_value:
            ProfileChangeHistory.objects.create(
                user_profile=instance.original_user,
                field_name=field.name,
                old_value=str(old_value) if old_value else 'ندارد',
                new_value=str(new_value),
            )


# -----------------------------
# ۵-الف) پروکسی‌های ادمین
# -----------------------------
class ApprovedPlayer(UserProfile):
    class Meta:
        proxy = True
        verbose_name = "بازیکن"
        verbose_name_plural = "بازیکنان"


class ApprovedCoach(UserProfile):
    class Meta:
        proxy = True
        verbose_name = "مربی"
        verbose_name_plural = "\u200bمربی‌ها"


class ApprovedReferee(UserProfile):
    class Meta:
        proxy = True
        verbose_name = "داور"
        verbose_name_plural = "\u200b\u200bداوران"


class PendingPlayer(PendingUserProfile):
    class Meta:
        proxy = True
        verbose_name = "تأیید بازیکن"
        verbose_name_plural = "\u200cتأیید بازیکنان"


class PendingCoach(PendingUserProfile):
    class Meta:
        proxy = True
        verbose_name = "تأیید مربی"
        verbose_name_plural = "\u200c\u200cتأیید مربی‌ها"


class PendingReferee(PendingUserProfile):
    class Meta:
        proxy = True
        verbose_name = "تأیید داور"
        verbose_name_plural = "\u200c\u200c\u200cتأیید داوران"


# -----------------------------
# ۶) تایید پیامک
# -----------------------------
class SMSVerification(models.Model):
    phone = models.CharField("شماره موبایل", max_length=11)
    code = models.CharField("کد", max_length=4)
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)

    def is_expired(self):
        return (timezone.now() - self.created_at).seconds > 300  # 5 دقیقه

    class Meta:
        verbose_name = "کد تأیید پیامکی"
        verbose_name_plural = "کدهای تأیید پیامکی"


# -----------------------------
# ۷) درخواست ارتباط مربی-باشگاه
# -----------------------------
class CoachClubRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "در انتظار"),
        ("accepted", "تأیید شده"),
        ("rejected", "رد شده"),
    ]
    REQUEST_TYPE_CHOICES = [
        ("add", "افزودن"),
        ("remove", "حذف"),
    ]

    coach = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="club_requests", verbose_name="مربی"
    )
    club = models.ForeignKey(TkdClub, on_delete=models.CASCADE, verbose_name="باشگاه")
    request_type = models.CharField("نوع درخواست", max_length=10, choices=REQUEST_TYPE_CHOICES)
    status = models.CharField("وضعیت", max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)

    def __str__(self):
        try:
            coach = str(self.coach) if self.coach_id else "?"
        except Exception:
            coach = "?"
        try:
            club = str(self.club) if self.club_id else "?"
        except Exception:
            club = "?"
        return f"[{self.get_request_type_display()}] {coach} ↔ {club}"

    class Meta:
        verbose_name = "درخواست ارتباط مربی-باشگاه"
        verbose_name_plural = "درخواست‌های ارتباط مربی-باشگاه"
        unique_together = ("coach", "club", "request_type")
