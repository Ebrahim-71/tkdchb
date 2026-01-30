from django.db import models
 
TARGET_CHOICES = (
    ("competition","competition"),
    ("seminar","seminar"),
)


class DiscountCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    amount = models.PositiveIntegerField(help_text="مبلغ تخفیف به تومان")
    capacity = models.PositiveIntegerField(default=1, help_text="تعداد مجاز استفاده از این کد")
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    target_type = models.CharField(max_length=20, choices=TARGET_CHOICES, null=True, blank=True, db_index=True)
    target_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.amount} تومان"

    @property
    def remaining_capacity(self):
        return max(0, self.capacity - self.used_count)

# --- Scope fields (optional) ---
TARGET_CHOICES = (
    ('competition','competition'),
    ('seminar','seminar'),
)

# این فیلدها رو به بالای کلاس DiscountCode اضافه نکردیم چون قبلاً migrate شده؛
# پس یک مدل پروکسی نمی‌خوایم — برویم با یک مایگریشن بعدی اضافه‌شان کنیم:
