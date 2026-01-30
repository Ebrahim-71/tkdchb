from django.db import models
from accounts.models import UserProfile

# یک مدل پروکسی فقط برای داشتن آیتم منو در ادمین
class ReportCenter(UserProfile):
    class Meta:
        proxy = True
        verbose_name = "مرکز گزارش‌گیری"
        verbose_name_plural = "مرکز گزارش‌گیری"
