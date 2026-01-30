# common/widgets.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime
from typing import Any

import jdatetime
from django import forms
from django.utils.safestring import mark_safe


def _to_jalali_str(value: Any) -> str:
    """
    تبدیل تاریخ میلادی به رشته شمسی برای نمایش در اینپوت.
    خروجی همیشه به فرمت YYYY/MM/DD است.
    """
    if not value:
        return ""

    # اگر خودش رشته شمسی بود (مثلاً 1403/01/10) همون رو برگردون
    if isinstance(value, str):
        v = value.strip()
        if "/" in v and "-" not in v:
            return v
        try:
            value = datetime.date.fromisoformat(v)
        except Exception:
            return v

    # اگر datetime بود، فقط قسمت date مهمه
    if isinstance(value, datetime.datetime):
        value = value.date()

    try:
        j = jdatetime.date.fromgregorian(date=value)
        return j.strftime("%Y/%m/%d")
    except Exception:
        return ""


def _to_gregorian_date(value: str):
    """
    تبدیل رشته شمسی (YYYY/MM/DD) به تاریخ میلادی (datetime.date)
    اگر خالی یا نامعتبر باشد، None برمی‌گرداند.
    """
    if not value:
        return None
    v = value.strip().replace("-", "/")
    try:
        y, m, d = [int(x) for x in v.split("/")]
        return jdatetime.date(y, m, d).togregorian()
    except Exception:
        # اگر نشد، شاید فرمت ISO میلادی باشد
        try:
            return datetime.date.fromisoformat(v)
        except Exception:
            return None


class _BasePersianWidget(forms.TextInput):
    """
    پایهٔ مشترک برای ویجت تاریخ و تاریخ/زمان شمسی.
    روی TextInput می‌نشیند و جاوااسکریپت persian-datepicker را روی input فعال می‌کند.
    """
    input_type = "text"

    def __init__(
        self,
        attrs=None,
        *,
        date_format: str = "YYYY/MM/DD",
        jalali_format: str = "YYYY/MM/DD",
    ):
        attrs = attrs or {}
        # فرمت شمسی‌ای که به پلاگین می‌دهیم را نگه می‌داریم
        self._pd_format = jalali_format

        base = {
            "dir": "ltr",
            "autocomplete": "off",
            "class": (attrs.get("class", "") + " vTextField pdate").strip(),
            "data-pformat": jalali_format,
            "data-gformat": date_format,
        }
        base.update(attrs)
        super().__init__(base)

    @property
    def media(self):
        """
        استایل و اسکریپت‌های لازم برای تقویم شمسی
        (از CDN، تا مشکل 404 و MIME نداشته باشیم)
        """
        return forms.Media(
            css={
                "all": [
                    "https://cdn.jsdelivr.net/npm/persian-datepicker@1.2.0/dist/css/persian-datepicker.min.css",
                ]
            },
            js=[
                # jQuery برای پلاگین
                "https://cdn.jsdelivr.net/npm/jquery@3.6.4/dist/jquery.min.js",
                # persian-date برای تاریخ شمسی
                "https://cdn.jsdelivr.net/npm/persian-date@1.1.0/dist/persian-date.js",
                # خود پلاگین persian-datepicker
                "https://cdn.jsdelivr.net/npm/persian-datepicker@1.2.0/dist/js/persian-datepicker.min.js",
            ],
        )

    def format_value(self, value):
        # مقدار اولیه را به شمسی برای نمایش در input تبدیل می‌کنیم
        return _to_jalali_str(value)

    def render(self, name, value, attrs=None, renderer=None):
        """
        رندر input + اسکریپت اینیشالایز persianDatepicker
        """
        html = super().render(name, value, attrs, renderer)
        input_id = (attrs or {}).get("id") or f"id_{name}"

        script = f"""
        <script>
        (function() {{
          var el = document.getElementById('{input_id}');
          if (!el || el._hasPD) return;
          el._hasPD = true;

          function boot() {{
            var $ = null;

            // ترجیحاً از django.jQuery استفاده می‌کنیم اگر پلاگین روی آن نصب شده باشد
            if (window.django && django.jQuery && django.jQuery.fn && django.jQuery.fn.persianDatepicker) {{
              $ = django.jQuery;
            }} else if (window.jQuery && window.jQuery.fn && window.jQuery.fn.persianDatepicker) {{
              // در غیر این صورت از jQuery سراسری
              $ = window.jQuery;
            }}

            if (!($ && $.fn && $.fn.persianDatepicker)) {{
              // هنوز پلاگین نیامده، دوباره تلاش کن
              return setTimeout(boot, 100);
            }}

            $(el).persianDatepicker({{
              format: '{self._pd_format}',
              initialValueType: 'persian',
              initialValue: false,
              autoClose: true,
              calendar: {{
                persian: {{
                  locale: 'fa',
                  leapYearMode: 'astronomical'
                }}
              }},
              navigator: {{
                scroll: {{
                  enabled: false
                }}
              }},
              toolbox: {{
                calendarSwitch: {{
                  enabled: true
                }},
                todayButton: {{
                  enabled: true,
                  text: 'امروز'
                }},
                submitButton: {{
                  enabled: false
                }}
              }},
              onShow: function () {{
                if (!el.value) {{
                  try {{
                    $(el).data('datepicker').setDate(new persianDate());
                  }} catch (e) {{}}
                }}
              }}
            }});
          }}

          boot();
        }})();
        </script>
        """

        return mark_safe(html + script)


class PersianDateWidget(_BasePersianWidget):
    """
    ویجت انتخاب تاریخ شمسی برای DateField
    دیتا را از فرم گرفته و به تاریخ میلادی (date) تبدیل می‌کند.
    """

    def value_from_datadict(self, data, files, name):
        return _to_gregorian_date(data.get(name, ""))


class PersianDateTimeWidget(_BasePersianWidget):
    """
    ویجت انتخاب تاریخ/زمان شمسی برای DateTimeField
    """

    def __init__(self, attrs=None):
        super().__init__(
            attrs=attrs,
            date_format="YYYY/MM/DD HH:mm",
            jalali_format="YYYY/MM/DD HH:mm",
        )

    def value_from_datadict(self, data, files, name):
        raw = (data.get(name, "") or "").strip().replace("-", "/")
        if not raw:
            return None

        # انتظار فرمت: 1403/01/10 14:30
        try:
            date_part, time_part = raw.split()
            y, m, d = [int(x) for x in date_part.split("/")]
            hh, mm = [int(x) for x in time_part.split(":")[:2]]
            jdt = jdatetime.datetime(y, m, d, hh, mm, 0)
            return jdt.togregorian()
        except Exception:
            # اگر نشد، شاید ISO میلادی باشد
            try:
                return datetime.datetime.fromisoformat(raw)
            except Exception:
                return None
