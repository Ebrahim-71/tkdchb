# -*- coding: utf-8 -*-
import re
import jdatetime
from datetime import date, datetime
from django import template

register = template.Library()

_EN_TO_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

@register.filter
def to_fa(value):
    """تبدیل همه ارقام به فارسی (هر نوعی)."""
    if value is None:
        return ""
    return str(value).translate(_EN_TO_FA)

@register.filter
def to_jalali(value):
    """
    تاریخ میلادی → شمسی (YYYY/MM/DD).
    اگر مقدار رشتهٔ شمسی باشد همان را برمی‌گرداند.
    """
    if not value:
        return ""

    # اگر رشتهٔ شمسی/میلادی باشد
    if isinstance(value, str):
        s = value.strip().replace("-", "/")
        # اگر شبیه 13xx/.. باشد، خودش شمسی است
        m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", s)
        if m:
            year = int(m.group(1))
            # سال کمتر از 1700 را شمسی فرض می‌کنیم
            if year < 1700:
                return f"{int(m.group(1)):04d}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
            # میلادی رشته‌ای → تبدیل
            try:
                g = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                jd = jdatetime.date.fromgregorian(date=g)
                return jd.strftime("%Y/%m/%d")
            except Exception:
                return s
        return value  # رشته‌های دیگر را دست نمی‌زنیم

    # اگر datetime/date باشد
    try:
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            jd = jdatetime.date.fromgregorian(date=value)
            return jd.strftime("%Y/%m/%d")
    except Exception:
        pass
    return value
