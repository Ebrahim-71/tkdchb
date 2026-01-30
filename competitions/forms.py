# competitions/forms.py
# -*- coding: utf-8 -*-
from django import forms
from datetime import date as gdate
import jdatetime
import django_jalali.admin as jadmin

from .models import AgeCategory, KyorugiCompetition


# --- Helpers ---
def _fa2en(s: str) -> str:
    if not isinstance(s, str):
        return s
    return (s
        .replace("۰","0").replace("۱","1").replace("۲","2").replace("۳","3").replace("۴","4")
        .replace("۵","5").replace("۶","6").replace("۷","7").replace("۸","8").replace("۹","9")
    )

def _to_gregorian(value):
    """
    مقدار ورودی (str/jdatetime.date/datetime.date) را به datetime.date میلادی تبدیل می‌کند.
    """
    if value in (None, "",):
        return None

    # اگر خود jdatetime.date باشد
    if isinstance(value, jdatetime.date):
        return value.togregorian()

    # اگر datetime.date میلادی باشد (ولی سالِ کوچک ⇒ احتمالاً شمسی خام)
    if isinstance(value, gdate):
        if value.year < 1700:
            return jdatetime.date(value.year, value.month, value.day).togregorian()
        return value

    # اگر رشته باشد (۱۴۰۳/۰۵/۲۳ یا 1403-05-23 و …)
    if isinstance(value, str):
        s = _fa2en(value.strip()).replace("-", "/")
        try:
            y, m, d = [int(p) for p in s.split("/")[:3]]
            return jdatetime.date(y, m, d).togregorian()
        except Exception:
            raise forms.ValidationError("فرمت تاریخ نامعتبر است. مثال: 1403/12/29")

    # هر حالت دیگری
    raise forms.ValidationError("فرمت تاریخ نامعتبر است.")


def _set_initial_jalali(field, instance_date):
    """
    مقدار میلادی ذخیره‌شده را به شمسی برای نمایش اولیه در فرم تبدیل می‌کند.
    """
    if instance_date:
        j = jdatetime.date.fromgregorian(date=instance_date)
        field.initial = j.strftime("%Y/%m/%d")


# ---------------- AgeCategory ----------------
class AgeCategoryForm(forms.ModelForm):
    class Meta:
        model = AgeCategory
        fields = "__all__"
        # می‌تونی همین ویجت رو نگه داری؛ مهم تبدیل در clean_* است
        widgets = {
            "from_date": jadmin.widgets.AdminjDateWidget,
            "to_date": jadmin.widgets.AdminjDateWidget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = getattr(self, "instance", None)
        if inst and inst.pk:
            _set_initial_jalali(self.fields["from_date"], inst.from_date)
            _set_initial_jalali(self.fields["to_date"], inst.to_date)

    def clean_from_date(self):
        return _to_gregorian(self.cleaned_data.get("from_date"))

    def clean_to_date(self):
        return _to_gregorian(self.cleaned_data.get("to_date"))


# ---------------- KyorugiCompetition ----------------
class KyorugiCompetitionForm(forms.ModelForm):
    class Meta:
        model = KyorugiCompetition
        fields = "__all__"
        widgets = {
            "registration_start": jadmin.widgets.AdminjDateWidget,
            "registration_end":   jadmin.widgets.AdminjDateWidget,
            "weigh_date":         jadmin.widgets.AdminjDateWidget,
            "draw_date":          jadmin.widgets.AdminjDateWidget,
            "competition_date":   jadmin.widgets.AdminjDateWidget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = getattr(self, "instance", None)
        if inst and inst.pk:
            for f in ["registration_start", "registration_end", "weigh_date", "draw_date", "competition_date"]:
                _set_initial_jalali(self.fields[f], getattr(inst, f))

    # تبدیل همهٔ فیلدهای تاریخ به میلادی قبل از ذخیره
    def clean(self):
        cleaned = super().clean()
        for f in ["registration_start", "registration_end", "weigh_date", "draw_date", "competition_date"]:
            cleaned[f] = _to_gregorian(cleaned.get(f))
        return cleaned
