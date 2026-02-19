from urllib.parse import unquote  # برای decode کردن object_id در delete_view

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.db import IntegrityError, transaction
from django.shortcuts import redirect
from django.urls import path, reverse
from typing import Optional
# ← ویجت شمسی
from common.widgets import PersianDateWidget
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core.serializers.json import DjangoJSONEncoder

import logging

import json
from django.utils.safestring import mark_safe

from .models import (
    ApprovedCoach, ApprovedPlayer, ApprovedReferee,
    PendingCoach, PendingPlayer, PendingReferee,
    PendingEditProfile, PendingClub, PendingUserProfile,
    TkdBoard, TkdClub, UserProfile
)
from django.template.response import TemplateResponse
from .utils.sms_utils import send_reject_signup_sms, send_approve_credentials_sms

UserModel = get_user_model()

# -------------------------------
# Helperها
# -------------------------------

logger = logging.getLogger(__name__)

def _safe_file_info(obj, field_name: str):
    f = getattr(obj, field_name, None)
    if not f:
        return None

    name = ""
    url = None
    size = None

    try:
        name = getattr(f, "name", "") or ""
    except Exception:
        name = ""

    try:
        url = f.url
    except Exception:
        url = None

    try:
        size = f.size
    except Exception:
        size = None

    if not name and not url:
        return None

    return {"url": url, "name": name, "size": size}

def _resolve_original_profile(pending_obj):
    """
    pending_obj.original_user ممکنه UserProfile یا auth.User باشه.
    خروجی: UserProfile یا None
    """
    o = getattr(pending_obj, "original_user", None)
    if o is None:
        return None

    # اگر خودش UserProfile است
    if isinstance(o, UserProfile):
        return o

    # اگر auth.User است و reverse relation دارد
    up = getattr(o, "userprofile", None)
    if isinstance(up, UserProfile):
        return up

    # اگر هیچکدوم نبود، تلاش با query
    try:
        return UserProfile.objects.filter(user=o).first()
    except Exception:
        return None







# اعداد فارسی→لاتین
def _fa2en(s: str) -> str:
    if not s:
        return s
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    return s.translate(table)

# تشخیص رشته تاریخ میلادی YYYY-MM-DD
def _looks_greg(s: str) -> bool:
    import re
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", _fa2en(s or "")))

# میلادی → شمسی (با jdatetime؛ در نبودش همون ورودی برمی‌گرده)
def _greg_to_jalali_str(greg: str) -> str:
    try:
        import datetime as _dt
        import jdatetime as _jd  # pip install jdatetime
        y, m, d = map(int, _fa2en(greg).split("-"))
        dt = _dt.date(y, m, d)
        j = _jd.date.fromgregorian(date=dt)
        return j.strftime("%Y/%m/%d")
    except Exception:
        return greg

# نرمال‌سازی ورودی کاربر: پذیرش ۱۴۰۳/۰۴/۱۰ یا 1993-01-30
def _normalize_birth_input(value: str) -> str:
    v = (_fa2en(value or "")).strip()
    # اگر میلادی بود، به شمسی تبدیل کن
    if _looks_greg(v):
        return _greg_to_jalali_str(v)
    # اگر کاربر شمسی زده (با / یا -)، یکدست کن به YYYY/MM/DD
    v = v.replace("-", "/")
    return v


def normalize_phone(raw: str) -> str:
    # تبدیل اعداد فارسی/عربی به لاتین و حذف غیرعددها
    import re
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    digits = re.sub(r"\D+", "", (raw or "").translate(table))
    if digits.startswith("98") and len(digits) == 12:
        return "0" + digits[2:]
    if len(digits) == 10 and digits.startswith("9"):
        return "0" + digits
    return digits[:11]


def get_or_create_auth_user_by_phone(phone: str, national_code: Optional[str] = None):
    """
    ایجاد/بازیابی User با یوزرنیم = شماره موبایل.
    اگر national_code داده شود، برای یوزر جدید (و یوزری که پسورد قابل‌استفاده ندارد)
    به عنوان پسورد تنظیم می‌شود.
    """
    phone = normalize_phone(phone)
    user, created = UserModel.objects.get_or_create(
        username=phone,
        defaults={'is_active': True}
    )

    # نرمال‌سازی کدملی (اعداد فارسی و …)
    if national_code:
        national_code = _fa2en(str(national_code)).strip()

    if created:
        # یوزر تازه ساخته شده
        if national_code:
            user.set_password(national_code)
        else:
            user.set_unusable_password()
        user.save()
    else:
        # یوزر قبلاً بوده؛ اگر پسورد ندارد، براش از روی کدملی بگذار
        if national_code and not user.has_usable_password():
            user.set_password(national_code)
            user.save(update_fields=["password"])

    return user


class PendingRejectWithSmsMixin:
    """
    هنگام حذف رکورد پندینگ:
      - یک فرم می‌گیرد برای علت رد
      - SMS می‌فرستد
      - رکورد را حذف می‌کند
    """
    reject_template = "admin/accounts/pendinguserprofile/reject_with_reason.html"

    def get_actions(self, request):
        actions = super().get_actions(request)
        # اکشن پیش‌فرض حذف گروهی رو بردار
        actions.pop('delete_selected', None)
        # اگر قبلاً اکشن ردِ قدیمی داشتی مثلاً 'reject_selected' می‌تونی اینو هم برداری:
        # actions.pop('reject_selected', None)
        return actions


    # ---------- حذف تکی (دلیت از صفحه جزئیات) ----------
    def delete_view(self, request, object_id, extra_context=None):
        obj = self.get_object(request, unquote(object_id))
        changelist_url = reverse(
            f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"
        )

        if obj is None:
            return redirect(changelist_url)

        # --- POST: بعد از ارسال علت رد ---
        if request.method == "POST":
            reason = (request.POST.get("reject_reason") or "").strip()

            if not reason:
                self.message_user(request, "لطفاً علت رد را وارد کنید.", level=messages.ERROR)
                context = {
                    "object": obj,
                    "original": obj,
                    "opts": self.model._meta,
                    "changelist_url": changelist_url,
                    **(extra_context or {}),
                }
                return TemplateResponse(request, self.reject_template, context)

            phone = getattr(obj, "phone", None) or getattr(obj, "founder_phone", None)

            if phone:
                try:
                    send_reject_signup_sms(phone, reason)
                except Exception as e:
                    self.message_user(
                        request,
                        f"خطا در ارسال پیامک رد درخواست: {e}",
                        level=messages.ERROR,
                    )

            try:
                obj.delete()
                self.message_user(request, "درخواست رد شد و پیامک ارسال گردید.", level=messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"خطا در حذف رکورد: {e}", level=messages.ERROR)

            return redirect(changelist_url)

        # --- GET: فرم علت رد ---
        context = {
            "object": obj,
            "original": obj,
            "opts": self.model._meta,
            "changelist_url": changelist_url,
            **(extra_context or {}),
        }
        return TemplateResponse(request, self.reject_template, context)

    # ---------- اکشن گروهی: رد + SMS ----------
    @admin.action(description="رد و حذف موارد انتخاب‌شده (با ارسال پیامک)")
    def reject_selected_with_sms(self, request, queryset):
        """
        اکشن منوی بازشونده:
        - بار اول فرم علت رد را نشان می‌دهد
        - بار دوم با علت، برای همه‌ی رکوردها SMS می‌فرستد و حذف می‌کند
        """
        changelist_url = reverse(
            f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"
        )

        # مرحله دوم: فرم ارسال شده
        if "confirm_reject" in request.POST:
            reason = (request.POST.get("reject_reason") or "").strip()

            if not reason:
                self.message_user(request, "لطفاً علت رد را وارد کنید.", level=messages.ERROR)
                context = {
                    "objects": queryset,
                    "opts": self.model._meta,
                    "changelist_url": changelist_url,
                    "action_checkbox_name": ACTION_CHECKBOX_NAME,
                    "action": "reject_selected_with_sms",
                }
                return TemplateResponse(request, self.reject_template, context)

            done = 0
            for obj in queryset:
                phone = getattr(obj, "phone", None) or getattr(obj, "founder_phone", None)

                if phone:
                    try:
                        send_reject_signup_sms(phone, reason)
                    except Exception as e:
                        self.message_user(
                            request,
                            f"خطا در ارسال پیامک برای «{obj}»: {e}",
                            level=messages.ERROR,
                        )
                try:
                    obj.delete()
                    done += 1
                except Exception as e:
                    self.message_user(
                        request,
                        f"خطا در حذف «{obj}»: {e}",
                        level=messages.ERROR,
                    )

            if done:
                self.message_user(
                    request,
                    f"{done} مورد رد شد و پیامک برای آن‌ها ارسال گردید.",
                    level=messages.SUCCESS,
                )
            return None  # برگرد به همان صفحه لیست

        # مرحله اول: فقط فرم را نمایش بده
        context = {
            "objects": queryset,
            "opts": self.model._meta,
            "changelist_url": changelist_url,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
            "action": "reject_selected_with_sms",
        }
        return TemplateResponse(request, self.reject_template, context)

# -------------------------------
# فرم‌ها (نمایش شمسی با PersianDateWidget)
# -------------------------------
import datetime as _dt
import jdatetime as _jd

def _date_to_jalali_str(val) -> str:
    """datetime/date میلادی → 'YYYY/MM/DD' شمسی"""
    if isinstance(val, _dt.datetime):
        val = val.date()
    if isinstance(val, _dt.date):
        try:
            return _jd.date.fromgregorian(date=val).strftime("%Y/%m/%d")
        except Exception:
            return ""
    return _normalize_birth_input(str(val or ""))

class UserProfileAdminFormWithJalali(forms.ModelForm):
    # فیلدها را صریح تعریف می‌کنیم تا ویجت شمسی بگیرد،
    # ولی همچنان رشته شمسی در مدل ذخیره می‌شود
    birth_date = forms.CharField(required=False, widget=PersianDateWidget)
    belt_certificate_date = forms.CharField(required=False, widget=PersianDateWidget)

    class Meta:
        model = UserProfile
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # مقدار اولیه را شمسی نشان بده
        if self.instance and self.instance.pk:
            bd = getattr(self.instance, "birth_date", "")
            if _looks_greg(bd):
                self.initial["birth_date"] = _greg_to_jalali_str(bd)
            cd = getattr(self.instance, "belt_certificate_date", "")
            if _looks_greg(cd):
                self.initial["belt_certificate_date"] = _greg_to_jalali_str(cd)

    def clean_birth_date(self):
        val = self.cleaned_data.get("birth_date")
        # اگر ویجت آبجکت تاریخ برگرداند
        if isinstance(val, (_dt.date, _dt.datetime)):
            return _date_to_jalali_str(val)
        return _normalize_birth_input(val)

    def clean_belt_certificate_date(self):
        val = self.cleaned_data.get("belt_certificate_date")
        if isinstance(val, (_dt.date, _dt.datetime)):
            return _date_to_jalali_str(val)
        return _normalize_birth_input(val)


class PendingUserProfileAdminFormWithJalali(forms.ModelForm):
    birth_date = forms.CharField(required=False, widget=PersianDateWidget)
    belt_certificate_date = forms.CharField(required=False, widget=PersianDateWidget)

    class Meta:
        model = PendingUserProfile
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            bd = getattr(self.instance, "birth_date", "")
            if _looks_greg(bd):
                self.initial["birth_date"] = _greg_to_jalali_str(bd)
            cd = getattr(self.instance, "belt_certificate_date", "")
            if _looks_greg(cd):
                self.initial["belt_certificate_date"] = _greg_to_jalali_str(cd)

    def clean_birth_date(self):
        val = self.cleaned_data.get("birth_date")
        if isinstance(val, (_dt.date, _dt.datetime)):
            return _date_to_jalali_str(val)
        return _normalize_birth_input(val)

    def clean_belt_certificate_date(self):
        val = self.cleaned_data.get("belt_certificate_date")
        if isinstance(val, (_dt.date, _dt.datetime)):
            return _date_to_jalali_str(val)
        return _normalize_birth_input(val)



@admin.action(description="حذف امن رکوردهای انتخاب‌شده")
def safe_delete_selected(modeladmin, request, queryset):
    try:
        with transaction.atomic():
            for obj in queryset:
                obj.delete()
        messages.success(request, "آیتم‌های انتخاب‌شده با موفقیت حذف شدند ✅")
    except Exception as e:
        messages.error(request, f"خطا در حذف: {str(e)} ❌")


def safe_delete_pending(admin_obj, request, pending):
    """حذف امن رکورد پِندینگ با مدیریت ProtectedError/IntegrityError."""
    try:
        pending.delete()
        return True
    except ProtectedError as e:
        admin_obj.message_user(
            request,
            f"حذف انجام نشد (ProtectedError): رکوردهای وابسته مانع حذف‌اند. تعداد وابسته‌ها: {len(e.protected_objects)}",
            level=messages.ERROR,
        )
        return False
    except IntegrityError as e:
        admin_obj.message_user(request, f"حذف انجام نشد (IntegrityError): {e}", level=messages.ERROR)
        return False


def create_profile_from_pending(pending, user_obj, role_flags: dict):
    """ساخت UserProfile از Pending با فلگ‌های نقش."""
    profile = UserProfile.objects.create(
        first_name=pending.first_name,
        last_name=pending.last_name,
        father_name=pending.father_name,
        national_code=pending.national_code,
        birth_date=pending.birth_date,
        phone=normalize_phone(pending.phone),
        gender=pending.gender,
        role=pending.role,
        province=pending.province,
        county=pending.county,
        city=pending.city,
        tkd_board=pending.tkd_board,
        tkd_board_name=pending.tkd_board.name if pending.tkd_board else '',
        address=pending.address,
        profile_image=pending.profile_image,
        belt_grade=pending.belt_grade,
        belt_certificate_number=pending.belt_certificate_number,
        belt_certificate_date=pending.belt_certificate_date,
        coach_level=getattr(pending, "coach_level", None),
        coach_level_International=getattr(pending, "coach_level_International", None),
        kyorogi=getattr(pending, "kyorogi", False),
        kyorogi_level=getattr(pending, "kyorogi_level", None),
        kyorogi_level_International=getattr(pending, "kyorogi_level_International", None),
        poomseh=getattr(pending, "poomseh", False),
        poomseh_level=getattr(pending, "poomseh_level", None),
        poomseh_level_International=getattr(pending, "poomseh_level_International", None),
        hanmadang=getattr(pending, "hanmadang", False),
        hanmadang_level=getattr(pending, "hanmadang_level", None),
        hanmadang_level_International=getattr(pending, "hanmadang_level_International", None),
        confirm_info=pending.confirm_info,
        club_names=pending.club_names,
        club=pending.club,
        coach=pending.coach,          # ← این خط را اضافه کن
        coach_name=pending.coach_name,
        user=user_obj,
        is_coach=role_flags.get('is_coach', False),
        is_referee=role_flags.get('is_referee', False),
    )
    if hasattr(profile, "coaching_clubs") and hasattr(pending, "coaching_clubs"):
        profile.coaching_clubs.set(pending.coaching_clubs.all())
    return profile


# -------------------------------
# Safe delete mixin
# -------------------------------
class SafeDeleteAdminMixin:
    actions = None

    def get_actions(self, request):
        """اکشن‌های پیش‌فرض را حذف می‌کند تا گزینه‌ی حذف گروهی نمایش داده نشود."""
        actions = super().get_actions(request)
        to_remove = [key for key in actions if "delete" in key.lower()]
        for key in to_remove:
            del actions[key]
        return actions

    def _changelist_url(self):
        opts = self.model._meta
        return f"/admin/{opts.app_label}/{opts.model_name}/"

    def delete_view(self, request, object_id, extra_context=None):
        """حذف تکی امن (بدون ارور 500 و با پیام مناسب)"""
        if request.method == "POST":
            obj = self.get_object(request, unquote(object_id))
            changelist = self._changelist_url()
            if obj is None:
                return redirect(changelist)
            try:
                obj.delete()
                self.message_user(request, "رکورد با موفقیت حذف شد ✅", level=messages.SUCCESS)
            except ProtectedError:
                self.message_user(request, "این رکورد به داده‌های دیگری وابسته است و حذف نشد ⚠️", level=messages.WARNING)
            except Exception as e:
                self.message_user(request, f"خطا در حذف: {e}", level=messages.ERROR)
            return redirect(changelist)
        return super().delete_view(request, object_id, extra_context=extra_context)


# -------------------------------
# میکسین: لینک «approve/» تکی در صفحهٔ جزئیات
# -------------------------------
class PendingSingleApproveMixin:
    change_form_template = "admin/accounts/pendinguserprofile/change_form.html"

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta
        custom = [
            path(
                "<int:pk>/approve/",
                self.admin_site.admin_view(self.approve_single),
                name=f"{info.app_label}_{info.model_name}_approve",
            ),
        ]
        return custom + urls

    def approve_single(self, request, pk, *args, **kwargs):
        self.approve(request, self.model.objects.filter(pk=pk))
        return redirect(reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"))

    def response_change(self, request, obj):
        if "_approve" in request.POST:
            try:
                self.approve(request, self.model.objects.filter(pk=obj.pk))
                self.message_user(request, "تأیید انجام شد و به کاربران اصلی منتقل گردید ✅")
            except Exception as e:
                self.message_user(request, f"⚠️ خطا در تأیید: {e}", level=messages.ERROR)
            return redirect(reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"))
        return super().response_change(request, obj)


# -------------------------------
# Pending Coach
# -------------------------------
class PendingCoachAdmin(PendingRejectWithSmsMixin, PendingSingleApproveMixin, admin.ModelAdmin):
    form = PendingUserProfileAdminFormWithJalali
    list_display = ['first_name', 'last_name', 'phone', 'submitted_at']
    search_fields = ('first_name', 'last_name', 'phone', 'national_code')
    list_filter = ('gender',)  # ✅ فیلتر جنسیت
    actions = ['approve', 'reject_selected_with_sms']
    change_form_template = "admin/accounts/pendinguserprofile/change_form.html"


    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(role__in=['coach', 'both'])

    def approve(self, request, queryset):
        success_count, delete_failed = 0, 0
        with transaction.atomic():
            qs = queryset.select_for_update()
            for pending in qs:
                # ایجاد/بازیابی User
                user_obj = get_or_create_auth_user_by_phone(pending.phone, pending.national_code)

                # شماره موبایل تمیز برای SMS
                phone_clean = normalize_phone(pending.phone)

                # کد ملی تمیز (اعداد لاتین، trim شده)
                national_code_clean = _fa2en(str(pending.national_code or "")).strip()

                # ساخت پروفایل اصلی
                create_profile_from_pending(
                    pending, user_obj,
                    role_flags={'is_coach': True, 'is_referee': pending.role in ['referee', 'both']}
                )

                # ارسال SMS تأیید
                ok = send_approve_credentials_sms(
                    phone_clean,          # {0}
                    national_code_clean,  # {1}
                )
                if not ok:
                    self.message_user(
                        request,
                        f"⚠️ ارسال پیامک تأیید برای «{pending}» موفق نبود. لاگ سرور را بررسی کنید.",
                        level=messages.ERROR,
                    )

                # حذف رکورد Pending
                if safe_delete_pending(self, request, pending):
                    success_count += 1
                else:
                    delete_failed += 1

        msg = f"{success_count} مربی با موفقیت تأیید شد."
        if delete_failed:
            msg += f" {delete_failed} رکورد حذف نشد."
        self.message_user(request, msg)


# -------------------------------
# Pending Referee
# -------------------------------
class PendingRefereeAdmin(PendingRejectWithSmsMixin, PendingSingleApproveMixin, admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'phone', 'submitted_at']
    search_fields = ('first_name', 'last_name', 'phone', 'national_code')
    list_filter = ('gender',)  # ✅ فیلتر جنسیت
    actions = ['approve', 'reject_selected_with_sms']
    change_form_template = "admin/accounts/pendinguserprofile/change_form.html"


    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(role__in=['referee', 'both'])

    def approve(self, request, queryset):
        success_count, delete_failed = 0, 0
        with transaction.atomic():
            qs = queryset.select_for_update()
            for pending in qs:
                # ایجاد/بازیابی User
                user_obj = get_or_create_auth_user_by_phone(pending.phone, pending.national_code)

                phone_clean = normalize_phone(pending.phone)
                national_code_clean = _fa2en(str(pending.national_code or "")).strip()

                # ساخت پروفایل اصلی
                create_profile_from_pending(
                    pending, user_obj,
                    role_flags={'is_coach': pending.role in ['coach', 'both'], 'is_referee': True}
                )

                # ارسال SMS تأیید
                ok = send_approve_credentials_sms(
                    phone_clean,
                    national_code_clean,
                )
                if not ok:
                    self.message_user(
                        request,
                        f"⚠️ ارسال پیامک تأیید برای «{pending}» موفق نبود. لاگ سرور را بررسی کنید.",
                        level=messages.ERROR,
                    )

                # حذف رکورد Pending
                if safe_delete_pending(self, request, pending):
                    success_count += 1
                else:
                    delete_failed += 1

        msg = f"{success_count} داور با موفقیت تأیید شد."
        if delete_failed:
            msg += f" {delete_failed} حذف نشدند."
        self.message_user(request, msg)

# -------------------------------
# Pending Player
# -------------------------------
class PendingPlayerAdmin(PendingRejectWithSmsMixin, PendingSingleApproveMixin, admin.ModelAdmin):
    form = PendingUserProfileAdminFormWithJalali
    list_display = ['first_name', 'last_name', 'coach_display', 'phone', 'submitted_at']
    search_fields = ('first_name', 'last_name', 'phone', 'national_code')
    list_filter = ('gender',)  # ✅ فیلتر جنسیت
    actions = ['approve', 'reject_selected_with_sms']
    change_form_template = "admin/accounts/pendinguserprofile/change_form.html"


    def get_queryset(self, request):
        return super().get_queryset(request).filter(role='player')

    def coach_display(self, obj):
        if getattr(obj, "coach", None):
            name = f"{obj.coach.first_name} {obj.coach.last_name}".strip()
            return name or obj.coach_name or "-"
        return obj.coach_name or "-"

    def approve(self, request, queryset):
        success_count, delete_failed = 0, 0
        with transaction.atomic():
            qs = queryset.select_for_update()
            for pending in qs:
                # ایجاد/بازیابی User
                user_obj = get_or_create_auth_user_by_phone(pending.phone, pending.national_code)

                phone_clean = normalize_phone(pending.phone)
                national_code_clean = _fa2en(str(pending.national_code or "")).strip()

                # ساخت پروفایل اصلی
                create_profile_from_pending(
                    pending, user_obj, role_flags={'is_coach': False, 'is_referee': False}
                )

                # ارسال SMS تأیید
                ok = send_approve_credentials_sms(
                    phone_clean,
                    national_code_clean,
                )
                if not ok:
                    self.message_user(
                        request,
                        f"⚠️ ارسال پیامک تأیید برای «{pending}» موفق نبود. لاگ سرور را بررسی کنید.",
                        level=messages.ERROR,
                    )

                # حذف رکورد Pending
                if safe_delete_pending(self, request, pending):
                    success_count += 1
                else:
                    delete_failed += 1

        msg = f"{success_count} بازیکن با موفقیت تأیید شد."
        if delete_failed:
            msg += f" {delete_failed} مورد حذف نشد."
        self.message_user(request, msg)



# ---- Approved (پروکسیِ UserProfile) ----
class ApprovedCoachAdmin(SafeDeleteAdminMixin, admin.ModelAdmin):
    form = UserProfileAdminFormWithJalali
    list_display = ['first_name', 'last_name', 'phone', 'national_code']
    search_fields = ('first_name', 'last_name', 'phone', 'national_code')
    list_filter = ('gender',)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_coach=True)


class ApprovedRefereeAdmin(SafeDeleteAdminMixin, admin.ModelAdmin):
    form = UserProfileAdminFormWithJalali
    list_display = ['first_name', 'last_name', 'phone', 'national_code']
    search_fields = ('first_name', 'last_name', 'phone', 'national_code')
    list_filter = ('gender',)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_referee=True)



class ApprovedPlayerAdmin(SafeDeleteAdminMixin, admin.ModelAdmin):
    form = UserProfileAdminFormWithJalali
    list_display = ['first_name', 'last_name','coach_display', 'phone', 'national_code']
    search_fields = ('first_name', 'last_name', 'phone', 'national_code')
    list_filter = ('gender',)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(role='player')


    def coach_display(self, obj):
        if getattr(obj, "coach", None):
            full_name = f"{getattr(obj.coach, 'first_name', '')} {getattr(obj.coach, 'last_name', '')}".strip()
            return full_name or getattr(obj.coach, "name", None) or obj.coach_name or "-"
        return getattr(obj, "coach_name", None) or "-"

    coach_display.short_description = "مربی"
    coach_display.admin_order_field = "coach_name"


# -------------------------------
# UserProfile Admin (با حذف امن)
# -------------------------------
class UserProfileAdmin(SafeDeleteAdminMixin, admin.ModelAdmin):
    form = UserProfileAdminFormWithJalali
    list_display = [
        'first_name', 'last_name', 'phone', 'role',
        'display_coach_level', 'display_coach_level_International'
    ]
    search_fields = ['first_name', 'last_name', 'phone', 'national_code']
    list_filter = ('gender', 'role')


    def display_coach_level(self, obj):
        return obj.get_coach_level_display() or '-'
    display_coach_level.short_description = 'درجه مربیگری'

    def display_coach_level_International(self, obj):
        return obj.get_coach_level_International_display() or '-'
    display_coach_level_International.short_description = 'درجه بین‌المللی مربیگری'


# -------------------------------
# TkdClub + PendingClub
# -------------------------------
class TkdClubAdmin(SafeDeleteAdminMixin, admin.ModelAdmin):
    list_display = ['club_name', 'founder_name', 'founder_phone', 'city']
    search_fields = ('club_name', 'founder_name', 'founder_phone', 'city')


# -------------------------------
# TkdClub + PendingClub
# -------------------------------
class PendingClubAdmin(PendingRejectWithSmsMixin, PendingSingleApproveMixin, admin.ModelAdmin):

    list_display = [
        'display_club_name',
        'display_founder_name',
        'display_founder_phone',
        'display_province',
        'display_submitted_at',
    ]
    actions = ['approve', 'reject_selected_with_sms']
    change_form_template = "admin/accounts/pendinguserprofile/approve_pending_club.html"
    empty_value_display = '-'

    # ---------- ستون‌های نمایشی لیست ----------
    def display_club_name(self, obj):
        return getattr(obj, 'club_name', None) or '-'
    display_club_name.short_description = 'نام باشگاه'
    display_club_name.admin_order_field = 'club_name'

    def display_founder_name(self, obj):
        return getattr(obj, 'founder_name', None) or '-'
    display_founder_name.short_description = 'بنیان‌گذار'
    display_founder_name.admin_order_field = 'founder_name'

    def display_founder_phone(self, obj):
        # اگر founder_phone نبود از phone استفاده کن
        return getattr(obj, 'founder_phone', None) or getattr(obj, 'phone', None) or '-'
    display_founder_phone.short_description = 'تلفن بنیان‌گذار'
    display_founder_phone.admin_order_field = 'founder_phone'

    def display_province(self, obj):
        return getattr(obj, 'province', None) or '-'
    display_province.short_description = 'استان'
    display_province.admin_order_field = 'province'

    def display_submitted_at(self, obj):
        # اگر فیلد submitted_at نداشتی، created_at رو امتحان کن
        return getattr(obj, 'submitted_at', None) or getattr(obj, 'created_at', None) or '-'
    display_submitted_at.short_description = 'تاریخ ارسال'
    display_submitted_at.admin_order_field = 'submitted_at'

    # ---------- اکشن تأیید باشگاه ----------
    @admin.action(description="تأیید و انتقال به لیست باشگاه‌ها")
    def approve(self, request, queryset):
        success_count = 0
        delete_failed = 0

        with transaction.atomic():
            qs = queryset.select_for_update()
            for pending in qs:
                try:
                    # 1) چک کردن موبایل موسس
                    raw_phone = getattr(pending, "founder_phone", None) or getattr(pending, "phone", None)
                    if not raw_phone:
                        self.message_user(
                            request,
                            f"برای «{pending}» تلفن موسس ثبت نشده، تأیید نشد.",
                            level=messages.ERROR,
                        )
                        delete_failed += 1
                        continue

                    phone_clean = normalize_phone(raw_phone)

                    # 2) ایجاد/بازیابی یوزر موسس (username = شماره موبایل)
                    founder_nc = getattr(pending, "founder_national_code", "") or ""
                    national_code_clean = _fa2en(str(founder_nc)).strip()

                    user_obj = get_or_create_auth_user_by_phone(
                        phone_clean,
                        founder_nc,
                    )

                    # 3) ساخت باشگاه اصلی
                    try:
                        TkdClub.objects.create(
                            club_name=getattr(pending, 'club_name', ''),
                            founder_name=getattr(pending, 'founder_name', ''),
                            founder_national_code=getattr(pending, 'founder_national_code', ''),
                            founder_phone=phone_clean,
                            club_type=getattr(pending, 'club_type', ''),
                            activity_description=getattr(pending, 'activity_description', ''),
                            province=getattr(pending, 'province', ''),
                            county=getattr(pending, 'county', ''),
                            city=getattr(pending, 'city', ''),
                            tkd_board=getattr(pending, 'tkd_board', None),
                            phone=getattr(pending, 'phone', ''),
                            address=getattr(pending, 'address', ''),
                            license_number=getattr(pending, 'license_number', ''),
                            federation_id=getattr(pending, 'federation_id', ''),
                            license_image=getattr(pending, 'license_image', None),
                            confirm_info=getattr(pending, 'confirm_info', ''),
                            user=user_obj,
                        )
                    except Exception as e:
                        self.message_user(
                            request,
                            f"خطا در ساخت باشگاه برای «{pending}»: {e}",
                            level=messages.ERROR,
                        )
                        delete_failed += 1
                        continue

                    # 4) ارسال SMS تأیید (اگر کد ملی موسس داریم)
                    if national_code_clean:
                        ok = send_approve_credentials_sms(
                            phone_clean,
                            national_code_clean,
                        )
                        if not ok:
                            self.message_user(
                                request,
                                f"⚠️ باشگاه «{pending}» تأیید شد، اما ارسال پیامک موفق نبود. لاگ سرور را ببینید.",
                                level=messages.WARNING,
                            )
                    else:
                        self.message_user(
                            request,
                            f"باشگاه «{pending}» تأیید شد، اما چون کد ملی موسس خالی است، SMS ارسال نشد.",
                            level=messages.WARNING,
                        )

                    # 5) حذف رکورد Pending
                    if safe_delete_pending(self, request, pending):
                        success_count += 1
                    else:
                        delete_failed += 1

                except Exception as e:
                    delete_failed += 1
                    self.message_user(
                        request,
                        f"خطای نامشخص هنگام تأیید «{pending}»: {e}",
                        level=messages.ERROR,
                    )

        msg = f"{success_count} باشگاه با موفقیت تأیید شد."
        if delete_failed:
            msg += f" {delete_failed} مورد به علت خطا یا وابستگی حذف/تأیید نشد."
        self.message_user(request, msg)




def _file_url(obj, field_name: str):
    f = getattr(obj, field_name, None)
    if not f:
        return None
    try:
        if getattr(f, "name", None):
            return f.url
    except Exception:
        return None
    return None


def _fa_bool(v):
    return "بله" if bool(v) else "خیر"


def _norm_text(v):
    if v is None:
        return ""
    return str(v).strip()


class PendingEditsAdmin(PendingSingleApproveMixin, admin.ModelAdmin):
    list_display = ("first_name", "last_name", "phone", "role")
    actions = ("approve",)
    change_form_template = "admin/accounts/pendinguserprofile/approve_edited_profile.html"

    DIFF_FIELDS = [
        "first_name", "last_name", "father_name",
        "birth_date", "gender",
        "province", "county", "city", "address",
        "role", "is_coach", "is_referee",
        "coach_level", "coach_level_International",
        "kyorogi", "kyorogi_level", "kyorogi_level_International",
        "poomseh", "poomseh_level", "poomseh_level_International",
        "hanmadang", "hanmadang_level", "hanmadang_level_International",
        "belt_grade", "belt_certificate_number", "belt_certificate_date",
        "tkd_board", "club", "coach",
        "profile_image",
    ]

    def _label(self, obj, field_name: str) -> str:
        try:
            f = obj._meta.get_field(field_name)
            return str(getattr(f, "verbose_name", field_name)) or field_name
        except Exception:
            return field_name

    def _pretty(self, obj, field_name: str, value):
        if field_name in ("is_coach", "is_referee", "kyorogi", "poomseh", "hanmadang"):
            return _fa_bool(value)

        disp = getattr(obj, f"get_{field_name}_display", None)
        if callable(disp):
            try:
                out = _norm_text(disp())
                return out if out else "ندارد"
            except Exception:
                pass

        if field_name in ("tkd_board", "club", "coach"):
            if not value:
                return "ندارد"
            try:
                return _norm_text(str(value)) or "ندارد"
            except Exception:
                return "ندارد"

        if field_name in ("birth_date", "belt_certificate_date"):
            return _norm_text(value) if _norm_text(value) else "ندارد"

        return _norm_text(value) if _norm_text(value) else "ندارد"

    def _build_diff(self, pending_obj):
        original = _resolve_original_profile(pending_obj)
        if not original:
            return [], {}

        changed_fields = []
        pairs = {}

        # --- m2m coaching_clubs ---
        try:
            if hasattr(original, "coaching_clubs") and hasattr(pending_obj, "coaching_clubs"):
                old_ids = list(original.coaching_clubs.all().values_list("id", flat=True))
                new_ids = list(pending_obj.coaching_clubs.all().values_list("id", flat=True))
                if sorted(old_ids) != sorted(new_ids):
                    changed_fields.append("coaching_clubs")
                    pairs["coaching_clubs"] = {
                        "label": "باشگاه‌های مربی",
                        "type": "text",
                        "old": "، ".join([str(x) for x in original.coaching_clubs.all()]) or "ندارد",
                        "new": "، ".join([str(x) for x in pending_obj.coaching_clubs.all()]) or "ندارد",
                    }
        except Exception as e:
            logger.exception("diff coaching_clubs failed: %s", e)

        # --- image profile_image ---
        try:
            old_img = _safe_file_info(original, "profile_image")
            new_img = _safe_file_info(pending_obj, "profile_image")
            
            old_sig = (
                (old_img or {}).get("name") or "",
                (old_img or {}).get("size"),
            )
            new_sig = (
                (new_img or {}).get("name") or "",
                (new_img or {}).get("size"),
            )
            
            if old_sig != new_sig:
                changed_fields.append("profile_image")
                pairs["profile_image"] = {
                    "label": self._label(pending_obj, "profile_image"),
                    "type": "image",
                    "old": old_img,
                    "new": new_img,
                }


        
        except Exception as e:
            logger.exception("diff profile_image failed: %s", e)

        # --- سایر فیلدها ---
        for field_name in self.DIFF_FIELDS:
            if field_name == "profile_image":
                continue

            if not hasattr(original, field_name) or not hasattr(pending_obj, field_name):
                continue

            try:
                old_val = getattr(original, field_name, None)
                new_val = getattr(pending_obj, field_name, None)

                old_pretty = self._pretty(original, field_name, old_val)
                new_pretty = self._pretty(pending_obj, field_name, new_val)

                if _norm_text(old_pretty) != _norm_text(new_pretty):
                    changed_fields.append(field_name)
                    pairs[field_name] = {
                        "label": self._label(pending_obj, field_name),
                        "type": "text",
                        "old": old_pretty,
                        "new": new_pretty,
                    }
            except Exception as e:
                logger.exception("diff field %s failed: %s", field_name, e)

        return changed_fields, pairs

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)

        changed_fields, pairs = ([], {})
        if obj:
            try:
                changed_fields, pairs = self._build_diff(obj)
            except Exception as e:
                logger.exception("build_diff crashed: %s", e)
                changed_fields, pairs = [], {}

        extra_context["tkd_changed_fields"] = changed_fields
        extra_context["tkd_pairs"] = pairs

        # مهم: برای json_script باید dict باشه
        extra_context["tkd_diff_json"] = {"changed_fields": changed_fields, "pairs": pairs}

        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    @admin.action(description="اعمال ویرایش موارد انتخاب‌شده")
    def approve(self, request, queryset):
        success, failed = 0, 0
        qs = queryset.select_related("original_user").prefetch_related("coaching_clubs")

        with transaction.atomic():
            for pending in qs:
                # ✅ حتماً پروفایل اصلی را resolve کن
                user_profile = _resolve_original_profile(pending)
                if not user_profile:
                    failed += 1
                    continue

                try:
                    for fname in self.DIFF_FIELDS:
                        if fname == "profile_image":
                            continue
                        if hasattr(pending, fname):
                            setattr(user_profile, fname, getattr(pending, fname))

                    if hasattr(user_profile, "coaching_clubs") and hasattr(pending, "coaching_clubs"):
                        user_profile.coaching_clubs.set(pending.coaching_clubs.all())

                    if getattr(pending, "profile_image", None):
                        user_profile.profile_image = pending.profile_image

                    user_profile.save()
                    pending.delete()
                    success += 1
                except Exception as e:
                    failed += 1
                    self.message_user(request, f"خطا در اعمال ویرایش برای «{pending}»: {e}", level=messages.ERROR)

        msg = f"{success} مورد اعمال شد."
        if failed:
            msg += f" {failed} مورد ناموفق بود."
        self.message_user(request, msg, level=messages.SUCCESS if success else messages.WARNING)
# -------------------------------
# TkdBoard (با فرم ساخت/ویرایش یوزر)
# -------------------------------
class TkdBoardAdminForm(forms.ModelForm):
    username = forms.CharField(label="یوزرنیم", required=False)
    password = forms.CharField(label="رمز عبور", required=False, widget=forms.PasswordInput)

    class Meta:
        model = TkdBoard
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user:
            self.fields['username'].initial = self.instance.user.username

    def save(self, commit=True):
        instance = super().save(commit=False)
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if instance.user:
            user = instance.user
            if username:
                user.username = username
            if password:
                user.set_password(password)
            user.save()
        elif username and password:
            user = UserModel.objects.create_user(username=username, password=password)
            instance.user = user

        if commit:
            instance.save()
        return instance


@admin.register(TkdBoard)
class TkdBoardAdmin(admin.ModelAdmin):
    form = TkdBoardAdminForm
    list_display = ['name', 'province', 'city', 'user']
    search_fields = ['name', 'province', 'city']


# -------------------------------
# Register
# -------------------------------
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(ApprovedPlayer, ApprovedPlayerAdmin)
admin.site.register(ApprovedCoach, ApprovedCoachAdmin)
admin.site.register(ApprovedReferee, ApprovedRefereeAdmin)
admin.site.register(TkdClub, TkdClubAdmin)
admin.site.register(PendingPlayer, PendingPlayerAdmin)
admin.site.register(PendingCoach, PendingCoachAdmin)
admin.site.register(PendingReferee, PendingRefereeAdmin)
admin.site.register(PendingClub, PendingClubAdmin)
admin.site.register(PendingEditProfile, PendingEditsAdmin)
