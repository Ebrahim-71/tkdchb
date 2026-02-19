# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime as _dt
import datetime
import json
import os
import unicodedata
import uuid
from collections import OrderedDict
from typing import Optional, Union  # ✅ اضافه شود
from django.db.models import DateField, DateTimeField  # ✅ بالای فایل اضافه شود

from django.contrib.admin.views.decorators import staff_member_required
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction, models as dj_models
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.template.response import TemplateResponse
from django.templatetags.static import static
from django.urls import path, reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.html import format_html
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.db.models import Q
from django.contrib.admin.utils import construct_change_message as _dj_construct_change_message


from django.contrib.auth import get_user_model

User = get_user_model()


import jdatetime

# ویجت جدید ما (بدون دردسر)
from common.widgets import PersianDateWidget, PersianDateTimeWidget

# ============================ مدل‌ها ============================
from .models import (
    AgeCategory, Belt, BeltGroup, WeightCategory,
    KyorugiCompetition, CompetitionImage, CompetitionFile, MatAssignment,
    CoachApproval, TermsTemplate, Enrollment, Draw, Match, DrawStart, KyorugiResult,
    Seminar, SeminarRegistration,
    # --- پومسه ---
    PoomsaeCompetition, PoomsaeDivision, PoomsaeCoachApproval, PoomsaeEntry,
    PoomsaeMatAssignment,  # ✅ جدید
    DiscountCode, 
)


# سرویس‌ها
from .services.draw_service import create_draw_for_group
from .services.results_service import apply_results_and_points
from competitions.services.numbering_service import (
    number_matches_for_competition,
    clear_match_numbers_for_competition,
)

ELIGIBLE_STATUSES = ("paid", "confirmed", "accepted", "completed")
class KyorugiResultEntryForm(forms.Form):
    gender = forms.ChoiceField(
        choices=(("", "همه"), ("male", "آقایان"), ("female", "بانوان")),
        required=False,
        label="جنسیت",
    )
    only_upcoming = forms.BooleanField(required=False, initial=False, label="فقط مسابقات آینده")


    competition = forms.ModelChoiceField(
        queryset=KyorugiCompetition.objects.none(),
        required=False,
        label="مسابقه",
    )
    weight_category = forms.ModelChoiceField(
        queryset=WeightCategory.objects.none(),
        required=False,
        label="رده وزنی",
    )

    gold = forms.ModelChoiceField(queryset=Enrollment.objects.none(), required=False, label="نفر اول")
    silver = forms.ModelChoiceField(queryset=Enrollment.objects.none(), required=False, label="نفر دوم")
    bronze1 = forms.ModelChoiceField(queryset=Enrollment.objects.none(), required=False, label="نفر سوم")
    bronze2 = forms.ModelChoiceField(queryset=Enrollment.objects.none(), required=False, label="نفر سوم مشترک")

    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}), label="یادداشت")

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        data = self.data if self.is_bound else (self.request.GET if self.request else {})

        gender = data.get("gender")
        only_upcoming = data.get("only_upcoming") in ("on", "1", "true", True)

        qs = KyorugiCompetition.objects.all().order_by("-competition_date", "-id")
        if gender:
            qs = qs.filter(gender=gender)
        if only_upcoming:
            qs = qs.filter(competition_date__gte=timezone.localdate())

        self.fields["competition"].queryset = qs

        comp = qs.filter(id=data.get("competition")).first()
        wc_qs = WeightCategory.objects.none()

        if comp:
            allowed_ids = comp.mat_assignments.values_list("weights__id", flat=True).distinct()

            wc_qs = WeightCategory.objects.filter(id__in=allowed_ids, gender=comp.gender)

        self.fields["weight_category"].queryset = wc_qs

        wc = wc_qs.filter(id=data.get("weight_category")).first()

        eq = Enrollment.objects.none()
        if comp and wc:
            eq = Enrollment.objects.filter(
                competition=comp,
                weight_category=wc,
                status__in=ELIGIBLE_STATUSES,
            ).select_related("player")

        def _enroll_label(e: Enrollment) -> str:
            p = getattr(e, "player", None)
            if not p:
                return f"Enrollment #{e.id}"
            return (
                getattr(p, "full_name", None)
                or (f"{getattr(p,'first_name','')} {getattr(p,'last_name','')}".strip())
                or getattr(p, "username", None)
                or str(p)
            )
        
        for f in ("gold", "silver", "bronze1", "bronze2"):
            self.fields[f].queryset = eq
            self.fields[f].label_from_instance = _enroll_label
    
    
    def clean(self):
        cleaned = super().clean()
        picks = [
            cleaned.get("gold"),
            cleaned.get("silver"),
            cleaned.get("bronze1"),
            cleaned.get("bronze2"),
        ]
        picks = [p for p in picks if p]
        if len(picks) != len(set(picks)):
            raise forms.ValidationError("یک نفر نمی‌تواند در چند مقام همزمان ثبت شود.")
        return cleaned

# ---------------------- ابزارهای تاریخ/زمان (یکپارچه) ----------------------



def _tz():
    """منطقه‌ی زمانی فعلی جنگو."""
    return timezone.get_current_timezone()

def _localdate(dt_or_date: Optional[Union[datetime.date, datetime.datetime]]) -> Optional[datetime.date]:
    """
    هر ورودی تاریخ/زمان را به تاریخ «محلی» تبدیل می‌کند.
    - datetime آگاه => localtime => date
    - datetime ناآگاه => فرض محلی => date
    - date => همان
    """
    if not dt_or_date:
        return None
    if isinstance(dt_or_date, datetime.datetime):
        if timezone.is_aware(dt_or_date):
            return timezone.localtime(dt_or_date).date()
        return dt_or_date.date()
    if isinstance(dt_or_date, datetime.date):
        return dt_or_date
    return None


def _to_greg(v):
    """jdatetime.date|datetime -> معادل میلادی؛ یا همان ورودی اگر لازم نبود."""
    if isinstance(v, jdatetime.datetime):
        return v.togregorian()
    if isinstance(v, jdatetime.date):
        return v.togregorian()
    return v

def _to_jalali_str(value):
    """گرگوری(تاریخ/زمان/رشته) → رشتهٔ شمسی YYYY/MM/DD (نمایش امن بدون اختلاف روز)."""
    if not value:
        return "-"
    try:
        # رشته‌ها هم پشتیبانی شوند
        if isinstance(value, str):
            dt = parse_datetime(value) or parse_date(value)
        else:
            dt = value
        d = _localdate(dt)
        if not d:
            return "-"
        j = jdatetime.date.fromgregorian(date=d)
        return j.strftime("%Y/%m/%d")
    except Exception:
        return "-"

def _to_jalali_dt_str(val):
    """گرگوری → رشتهٔ شمسی YYYY/MM/DD HH:MM (برای نمایش تاریخ-زمان به‌صورت محلی)."""
    if not val:
        return "—"
    try:
        if isinstance(val, (datetime.datetime, datetime.date)):
            base_dt = val if isinstance(val, datetime.datetime) else datetime.datetime.combine(val, datetime.time(0, 0))
        else:
            parsed = parse_datetime(str(val)) or parse_date(str(val))
            if not parsed:
                return "—"
            base_dt = parsed if isinstance(parsed, datetime.datetime) else datetime.datetime.combine(parsed, datetime.time(0, 0))
        if timezone.is_aware(base_dt):
            base_dt = timezone.localtime(base_dt)
        jdt = jdatetime.datetime.fromgregorian(datetime=base_dt)
        return jdt.strftime("%Y/%m/%d %H:%M")
    except Exception:
        return "—"

def _full_name(u):
    if not u:
        return None
    for a in ("full_name", "name"):
        v = getattr(u, a, None)
        if v:
            return v
    fn = (getattr(u, "first_name", "") or "").strip()
    ln = (getattr(u, "last_name", "") or "").strip()
    return (fn + " " + ln).strip() or getattr(u, "username", None)

def _logo_url():
    url = getattr(settings, "BOARD_LOGO_URL", None)
    return url or static("img/board-logo.png")

# ---------------------- ایمن‌سازی نام فایل‌های آپلودی ----------------------

def _today_local() -> datetime.date:
    # Django 4+: timezone.localdate() مطمئن‌ترین است
    try:
        return timezone.localdate()
    except Exception:
        return timezone.localtime(timezone.now()).date()



def _safe_filename(full_name: str) -> str:
    """
    نام فایل را به ASCII ایمن تبدیل می‌کند، در حالی که مسیر (دایرکتوری) را نگه می‌دارد.
    فقط basename امن می‌شود.
    """
    if not full_name:
        return full_name

    # جدا کردن مسیر و نام فایل
    dir_name, filename = os.path.split(full_name)
    base, ext = os.path.splitext(filename)

    # نرمال‌سازی و حذف نویسه‌های غیر ASCII
    safe_base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii").strip()
    # جایگزینی فاصله و کاراکترهای مشکل‌ساز
    safe_base = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in safe_base)
    safe_base = safe_base.strip("-_") or uuid.uuid4().hex

    # محدود کردن طول
    if len(safe_base) > 120:
        safe_base = safe_base[:120]

    safe_name = f"{safe_base}{ext or ''}"

    # مسیر قبلی را نگه می‌داریم
    return os.path.join(dir_name, safe_name) if dir_name else safe_name



def _sanitize_upload_field(file_field):
    """
    اگر فایلی روی فیلد هست، نام آن را امن می‌کند تا خطای UnicodeEncodeError رخ ندهد.
    """
    try:
        f = file_field
        if f and getattr(f, "name", None):
            f.name = _safe_filename(f.name)
    except Exception:
        # در بدترین حالت، بگذار جنگو رفتار پیش‌فرض را انجام دهد
        pass

# ============================ Kyorugi ============================

class KyorugiCompetitionAdminForm(forms.ModelForm):
    registration_start = forms.DateField(widget=PersianDateWidget())
    registration_end   = forms.DateField(widget=PersianDateWidget())
    weigh_date         = forms.DateField(required=False, widget=PersianDateWidget())
    draw_date          = forms.DateField(required=False, widget=PersianDateWidget())
    competition_date   = forms.DateField(widget=PersianDateWidget())


    class Meta:
        model = KyorugiCompetition
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "registration_manual" in self.fields:
            current = getattr(self.instance, "registration_manual", None)
            # سه‌حالتی
            self.fields["registration_manual"] = TriStateChoiceField(label="فعال بودن ثبت‌نام")
            if not self.is_bound:
                self.initial["registration_manual"] = (
                    "" if current is None else ("1" if current is True else "0")
                )
            self.fields["registration_manual"].help_text = "خالی=طبق تاریخ‌ها، بله=اجباراً باز، خیر=اجباراً بسته"

    # اگر لازم بود، تبدیل خاص نداریم؛ PersianDateWidget مقدار میلادی استاندارد برمی‌گرداند.
    def clean_registration_start(self): return self.cleaned_data.get("registration_start")
    def clean_registration_end(self):   return self.cleaned_data.get("registration_end")
    def clean_weigh_date(self):         return self.cleaned_data.get("weigh_date")
    def clean_draw_date(self):          return self.cleaned_data.get("draw_date")
    def clean_competition_date(self):   return self.cleaned_data.get("competition_date")

class TriStateChoiceField(forms.TypedChoiceField):
    def __init__(self, *args, **kwargs):
        super().__init__(
            choices=(
                ("",  "طبق تاریخ‌ها"),  # None
                ("1", "اجباراً باز"),   # True
                ("0", "اجباراً بسته"),  # False
            ),
            coerce=lambda v: True if v == "1" else (False if v == "0" else None),
            required=False,
            *args, **kwargs
        )

class MatAssignmentInline(admin.TabularInline):
    model = MatAssignment
    extra = 0
    filter_horizontal = ("weights",)
    fields = ("mat_number", "weights")
    verbose_name = "زمین"
    verbose_name_plural = "زمین‌ها و اوزان"

class CompetitionImageInline(admin.TabularInline):
    model = CompetitionImage
    extra = 0
    verbose_name = "تصویر"
    verbose_name_plural = "تصاویر پیوست"

class CompetitionFileInline(admin.TabularInline):
    model = CompetitionFile
    extra = 0
    verbose_name = "فایل PDF"
    verbose_name_plural = "فایل‌های پیوست"

class CoachApprovalInline(admin.TabularInline):
    model = CoachApproval
    extra = 0
    fields = ("coach", "code", "terms_accepted", "is_active", "get_jalali_approved_at")
    readonly_fields = ("code", "get_jalali_approved_at")
    raw_id_fields = ("coach",)

    @admin.display(description="تاریخ تأیید (شمسی)")
    def get_jalali_approved_at(self, obj):
        if obj.approved_at:
            return _to_jalali_dt_str(obj.approved_at)
        return "-"

@admin.display(description="تاریخ برگزاری (شمسی)")
def _comp_date_jalali(obj):
    return _to_jalali_str(getattr(obj, "competition_date", None))

@admin.display(boolean=True, description="جدول منتشر؟")
def _is_bracket_published(obj):
    return bool(getattr(obj, "bracket_published_at", None))

@admin.display(description="سبک")
def _style_col(obj):
    return getattr(obj, "style_display", "—")

@admin.display(boolean=True, description="ثبت‌نام باز؟")
def _registration_open_col(obj):
    return bool(getattr(obj, "registration_open_effective", False))


@admin.register(KyorugiCompetition)
class KyorugiCompetitionAdmin(admin.ModelAdmin):
    form = KyorugiCompetitionAdminForm

    list_display = (
        "title", _style_col, "age_category", "gender",
        _comp_date_jalali, _registration_open_col, "registration_manual",
        "entry_fee", _is_bracket_published,
    )
    search_fields = ("title", "public_id", "city", "address")
    filter_horizontal = ("belt_groups",)
    list_filter = (
        "gender", "age_category", "belt_level",
        "registration_manual",
        ("competition_date", admin.DateFieldListFilter),
        ("registration_start", admin.DateFieldListFilter),
        ("registration_end", admin.DateFieldListFilter),
    )
    actions = []
    inlines = [MatAssignmentInline, CompetitionImageInline, CompetitionFileInline, CoachApprovalInline]
    readonly_fields = ("public_id",)
    ordering = ("-competition_date", "-id")
    fieldsets = (
        ("اطلاعات کلی", {
            "fields": ("title", "poster", "entry_fee", "age_category", "belt_level", "belt_groups", "gender")
        }),
        ("محل برگزاری", {"fields": ("city", "address")}),
        ("تاریخ‌ها", {"fields": ("registration_start", "registration_end", "weigh_date", "draw_date", "competition_date")}),
        ("ثبت‌نام", {"fields": ("mat_count", "registration_manual"),
                     "description": "خالی=طبق تاریخ‌ها، بله=اجباراً باز، خیر=اجباراً بسته"}),
        ("تعهدنامه مربی", {"fields": ("terms_template",), "classes": ("collapse",)}),
        ("شناسه عمومی", {"fields": ("public_id",), "classes": ("collapse",)}),
    )

    # پیام تغییر/افزودن سازگار با فرم‌ست‌های سفارشی
    def construct_change_message(self, request, form, formsets, add=False):
        safe_formsets = [
            fs for fs in (formsets or [])
            if all(hasattr(fs, attr) for attr in ("new_objects", "changed_objects", "deleted_objects"))
        ]
        try:
            return _dj_construct_change_message(form, safe_formsets, add)
        except Exception:
            return "added" if add else "changed"

    def save_formset(self, request, form, formset, change):
        """
        ذخیره‌ی ایمن اینلاین‌ها، و **ایمن‌سازی نام فایل‌های آپلودی** برای جلوگیری از UnicodeEncodeError.
        """
        from django.core.exceptions import ValidationError
        from .models import MatAssignment

        try:
            # اگر فرم‌ست سفارشیِ غیـرمدلی برای زمین‌ها باشد:
            if formset.__class__.__name__ == "MatAssignmentFormFormSet" and not (
                hasattr(formset, "model")
                and isinstance(getattr(formset, "model", None), type)
                and issubclass(formset.model, dj_models.Model)
            ):
                MatAssignment.objects.filter(competition=form.instance).delete()
                for f in formset.forms:
                    if not f.is_valid() or not f.has_changed():
                        continue
                    cd = getattr(f, "cleaned_data", {}) or {}
                    if cd.get("DELETE"):
                        continue
                    mat_no  = cd.get("mat_number")
                    weights = cd.get("weights")
                    if not mat_no or not weights:
                        continue
                    ma = MatAssignment.objects.create(
                        competition=form.instance,
                        mat_number=mat_no,
                    )
                    try:
                        ma.weights.set(weights)
                    except Exception:
                        ma.weights.set(list(weights or []))
                return

            # فرم‌ست مدل‌دار استاندارد
            model_name = getattr(formset.model, "__name__", "") if hasattr(formset, "model") else ""

            for f in formset.forms:
                if not f.is_valid():
                    continue

                cd = getattr(f, "cleaned_data", {}) or {}

                if cd.get("DELETE"):
                    inst = getattr(f, "instance", None)
                    if inst and getattr(inst, "pk", None):
                        inst.delete()
                    continue

                # رد کردن فرم‌های خالی
                if model_name == "CompetitionImage" and not cd.get("image"):
                    continue
                if model_name == "CompetitionFile" and not cd.get("file"):
                    continue
                if model_name == "MatAssignment" and not (cd.get("mat_number") or cd.get("weights")):
                    continue

                obj = f.save(commit=False)

                # ایمن‌سازی نام فایل‌ها قبل از save()
                if model_name == "CompetitionImage" and hasattr(obj, "image"):
                    _sanitize_upload_field(obj.image)
                if model_name == "CompetitionFile" and hasattr(obj, "file"):
                    _sanitize_upload_field(obj.file)

                # ست FK والد در اینلاین‌ها
                if hasattr(formset, "fk") and formset.fk and hasattr(obj, formset.fk.name):
                    setattr(obj, formset.fk.name, form.instance)

                obj.save()
                if hasattr(f, "save_m2m"):
                    f.save_m2m()

            # حذف‌های فرم‌ست
            for obj in getattr(formset, "deleted_objects", []):
                obj.delete()

            if hasattr(formset, "save_m2m"):
                formset.save_m2m()

        except (ValidationError, IntegrityError) as e:
            messages.error(
                request,
                "خطا در ذخیره‌ی آیتم‌های زیرمجموعه (زمین/اوزان یا فایل/تصویر). لطفاً مقادیر را بررسی کن. جزئیات: {}".format(e)
            )

    def save_model(self, request, obj, form, change):
        if "poster" in getattr(form, "changed_data", []) and getattr(obj, "poster", None):
            _sanitize_upload_field(obj.poster)
        super().save_model(request, obj, form, change)
        transaction.on_commit(lambda: None)


# ============================ سن/کمربند/وزن ============================

@admin.register(AgeCategory)
class AgeCategoryAdmin(admin.ModelAdmin):
    class _Form(forms.ModelForm):
        from_date = forms.DateField(widget=PersianDateWidget)
        to_date   = forms.DateField(required=False, widget=PersianDateWidget)

        class Meta:
            model = AgeCategory
            fields = "__all__"

        def clean_from_date(self): return self.cleaned_data.get("from_date")
        def clean_to_date(self):   return self.cleaned_data.get("to_date")

    form = _Form
    list_display = ("name", "get_jalali_from_date", "get_jalali_to_date")
    search_fields = ("name",)
    ordering = ("from_date",)
    list_filter = (("from_date", admin.DateFieldListFilter), ("to_date", admin.DateFieldListFilter))

    @admin.display(description="از تاریخ تولد (شمسی)")
    def get_jalali_from_date(self, obj):
        return _to_jalali_str(obj.from_date)

    @admin.display(description="تا تاریخ تولد (شمسی)")
    def get_jalali_to_date(self, obj):
        return _to_jalali_str(obj.to_date)

@admin.register(Belt)
class BeltAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)

@admin.register(BeltGroup)
class BeltGroupAdmin(admin.ModelAdmin):
    list_display = ("label",)
    search_fields = ("label",)
    filter_horizontal = ("belts",)

@admin.register(WeightCategory)
class WeightCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "gender", "min_weight", "max_weight", "tolerance")
    list_filter = ("gender",)
    search_fields = ("name",)
    ordering = ("gender", "min_weight")

# ============================ تعهدنامه/تأیید مربی (Kyorugi) ============================

@admin.register(TermsTemplate)
class TermsTemplateAdmin(admin.ModelAdmin):
    list_display = ("title",)
    search_fields = ("title",)

# ============================ گزارش شرکت‌کنندگان (Kyorugi) ============================

class KyorugiCompetitionParticipantsReport(KyorugiCompetition):
    class Meta:
        proxy = True
        verbose_name = "لیست شرکت‌کنندگان مسابقات"
        verbose_name_plural = "لیست شرکت‌کنندگان مسابقات"

@admin.register(KyorugiCompetitionParticipantsReport)
class ParticipantsReportAdmin(admin.ModelAdmin):
    change_list_template = "admin/competitions/participants_report.html"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    def changelist_view(self, request, extra_context=None):
        # اگر درخواست حذف گروهی بود
        if request.method == "POST" and request.POST.get("delete_selected") == "1":
            ids = request.POST.getlist("selected_enrollments")
            comp_id = request.POST.get("competition")  # برای برگشت به همان مسابقه

            if ids:
                qs = Enrollment.objects.filter(id__in=ids)
                count = qs.count()
                qs.delete()
                self.message_user(request, f"{count} شرکت‌کننده حذف شد.", level=messages.SUCCESS)
            else:
                self.message_user(request, "هیچ شرکت‌کننده‌ای انتخاب نشده است.", level=messages.WARNING)

            changelist_url = reverse(
                f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"
            )
            if comp_id:
                changelist_url += f"?competition={comp_id}"
            return HttpResponseRedirect(changelist_url)

        # حالت عادی (نمایش گزارش)
        form = ParticipantsReportForm(request.GET or None)

        selected_competition = None
        groups = []

        if form.is_valid():
            selected_competition = form.cleaned_data["competition"]
            qs = (
                Enrollment.objects
                .filter(competition=selected_competition)
                .select_related("player", "club", "coach", "belt_group", "weight_category")
                .order_by("belt_group__label", "weight_category__min_weight",
                          "player__last_name", "player__first_name")
            )

            grouped = OrderedDict()
            for e in qs:
                coach = e.coach
                e.coach_name = (
                    getattr(coach, "full_name", None)
                    or f"{(getattr(coach, 'first_name', '') or '').strip()} {(getattr(coach, 'last_name','') or '').strip()}".strip()
                    or ""
                )
            
                club = getattr(e, "club", None)
                e.club_name = (
                    getattr(club, "club_name", None)   # نام باشگاه طبق مدل TkdClub
                    or getattr(club, "name", None)     # اگر جایی مدل دیگه‌ای اسمش name بود
                    or ""
                )
                belt_label = getattr(e.belt_group, "label", "—")
                weight_label = getattr(e.weight_category, "name", "—")

                g = grouped.setdefault(belt_label, OrderedDict())
                g.setdefault(weight_label, []).append(e)

            groups = [(belt_label, list(weights.items())) for belt_label, weights in grouped.items()]

        ctx = dict(self.admin_site.each_context(request))
        ctx.update({
            "title": "لیست شرکت‌کنندگان مسابقات",
            "form": form,
            "selected_competition": selected_competition,
            "groups": groups,
        })
        if extra_context:
            ctx.update(extra_context)

        return TemplateResponse(request, self.change_list_template, ctx)


class ParticipantsReportForm(forms.Form):
    competition = forms.ModelChoiceField(
        queryset=KyorugiCompetition.objects.none(),  # ✅ در __init__ ست می‌کنیم
        label="مسابقه",
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        today = _today_local()

        # نوع فیلد را تشخیص می‌دهیم (DateField یا DateTimeField)
        try:
            field = KyorugiCompetition._meta.get_field("competition_date")
        except Exception:
            field = None

        qs = KyorugiCompetition.objects.all()

        if isinstance(field, DateTimeField):
            start_today = timezone.make_aware(
                datetime.datetime.combine(today, datetime.time(0, 0, 0)),
                _tz()
            )
            qs = qs.filter(competition_date__gte=start_today)
        else:
            # پیش‌فرض: DateField
            qs = qs.filter(competition_date__gte=today)

        self.fields["competition"].queryset = qs.order_by("-competition_date", "-id")

# ============================ شروع قرعه‌کشی (Kyorugi) ============================

class DrawStartForm(forms.Form):
    competition = forms.ModelChoiceField(
        label="مسابقه", queryset=KyorugiCompetition.objects.order_by("-competition_date", "-id")
    )
    belt_group = forms.ModelChoiceField(
        label="گروه کمربندی", queryset=BeltGroup.objects.none(), required=False
    )
    weight_category = forms.ModelChoiceField(
        label="رده وزنی", queryset=WeightCategory.objects.none(), required=False
    )

    auto_count = forms.IntegerField(label="شرکت‌کننده‌ها", required=False, disabled=True)
    auto_size  = forms.IntegerField(label="اندازهٔ پیشنهادی جدول", required=False, disabled=True)

    manual = forms.BooleanField(label="تنظیمات دستی", required=False)
    size_override = forms.IntegerField(
        label="اندازهٔ جدول (توان ۲)", required=False,
        help_text="خالی = خودکار. توان‌های ۲ مانند 2, 4, 8, 16, 32, 64…"
    )
    club_threshold = forms.IntegerField(
        label="آستانه هم‌باشگاهی", initial=8, required=False,
        help_text="اگر تعداد ≥ این مقدار باشد قانون هم‌باشگاهی در دور اول اعمال می‌شود."
    )
    seed = forms.CharField(label="Seed (اختیاری)", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        comp = self.data.get("competition") or self.initial.get("competition")
        if comp:
            try:
                comp = KyorugiCompetition.objects.get(pk=comp)
            except KyorugiCompetition.DoesNotExist:
                comp = None

        if comp:
            self.fields["belt_group"].queryset = comp.belt_groups.all()
        else:
            self.fields["belt_group"].queryset = BeltGroup.objects.none()

        wc_qs = WeightCategory.objects.none()
        if comp:
            allowed_ids = list(comp.mat_assignments.values_list("weights__id", flat=True))
            wc_qs = WeightCategory.objects.filter(id__in=allowed_ids, gender=comp.gender).order_by("min_weight")
        self.fields["weight_category"].queryset = wc_qs

        bg = self.data.get("belt_group") or self.initial.get("belt_group")
        wc = self.data.get("weight_category") or self.initial.get("weight_category")
        auto_count = 0
        auto_size = 1
        if comp and bg and wc:
            qs = Enrollment.objects.filter(
                competition=comp, belt_group_id=bg, weight_category_id=wc, status__in=ELIGIBLE_STATUSES
            )
            auto_count = qs.count()
            s = 1
            while s < max(auto_count, 1):
                s <<= 1
            auto_size = s
        self.fields["auto_count"].initial = auto_count
        self.fields["auto_size"].initial  = auto_size



@admin.register(DrawStart)
class DrawStartAdmin(admin.ModelAdmin):
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request): return False

    def changelist_view(self, request, extra_context=None):
        form = DrawStartForm(request.POST or request.GET or None)

        auto: dict = {"count": 0, "size": 1}
        comp = bg = wc = None
        draw = None
        use_draw = None
        matches_data = []

        if form.is_valid():
            comp = form.cleaned_data["competition"]
            bg   = form.cleaned_data.get("belt_group")
            wc   = form.cleaned_data.get("weight_category")
            seed = form.cleaned_data.get("seed") or ""

            count = (Enrollment.objects
                     .filter(competition=comp, belt_group=bg, weight_category=wc,
                             status__in=ELIGIBLE_STATUSES)
                     .count())
            size = 1
            while size < max(count, 1):
                size <<= 1
            auto = {"count": count, "size": size}

            if (request.GET.get("start") == "1") or (request.POST.get("start") == "1"):
                manual        = form.cleaned_data.get("manual") or False
                size_override = form.cleaned_data.get("size_override")
                ct_manual     = form.cleaned_data.get("club_threshold")

                final_size = (size_override if (manual and size_override) else size)
                final_th   = (ct_manual if (manual and ct_manual) else (8 if count >= 8 else 9999))

                if count < 1:
                    messages.error(request, "حداقل یک شرکت‌کننده لازم است.")
                else:
                    try:
                        draw = create_draw_for_group(
                            competition_id=comp.id,
                            age_category_id=comp.age_category_id,
                            belt_group_id=bg.id,
                            weight_category_id=wc.id,
                            club_threshold=int(final_th),
                            seed=seed,
                            size_override=final_size,
                        )
                        messages.success(request, "قرعه‌کشی انجام شد.")
                    except Exception as e:
                        messages.error(request, f"خطا در قرعه‌کشی: {e}")

        use_draw = draw or (
            (Draw.objects
             .filter(competition=comp,
                     gender=getattr(comp, "gender", None),
                     age_category=getattr(comp, "age_category", None),
                     belt_group=bg, weight_category=wc)
             .order_by("-created_at")
             .first()) if (comp and bg and wc) else None
        )

        if use_draw:
            qs = (Match.objects
                  .filter(draw=use_draw)
                  .select_related("player_a", "player_b")
                  .order_by("round_no", "slot_a"))
            for m in qs:
                matches_data.append({
                    "id": m.id,
                    "round_no": m.round_no,
                    "slot_a": m.slot_a,
                    "slot_b": m.slot_b,
                    "is_bye": bool(m.is_bye),
                    "player_a": _full_name(m.player_a),
                    "player_b": _full_name(m.player_b),
                })

        ctx = dict(self.admin_site.each_context(request))
        ctx.update({
            "title": "شروع قرعه‌کشی",
            "form": form,
            "auto": auto,
            "has_draw": bool(use_draw),
            "draw_size": (use_draw.size if use_draw else None),
            "show_bracket_now": bool(draw),
            "matches_json": json.dumps(matches_data, ensure_ascii=False),
        })
        if extra_context:
            ctx.update(extra_context)
        return TemplateResponse(request, "admin/competitions/draw_start.html", ctx)


@admin.site.admin_view
@transaction.atomic
def kyorugi_results_view(request):
    if request.method == "POST":
        form = KyorugiResultEntryForm(request.POST, request=request)
        if form.is_valid():
            comp = form.cleaned_data["competition"]
            wc = form.cleaned_data["weight_category"]

            result, _ = KyorugiResult.objects.get_or_create(
                competition=comp,
                weight_category=wc,
                defaults={"created_by": request.user},
            )

            result.gold_enrollment = form.cleaned_data["gold"]
            result.silver_enrollment = form.cleaned_data["silver"]
            result.bronze1_enrollment = form.cleaned_data["bronze1"]
            result.bronze2_enrollment = form.cleaned_data["bronze2"]
            result.notes = form.cleaned_data["notes"]
            result.save()

            apply_results_and_points(result.id)

            messages.success(request, "نتیجه ذخیره شد.")
            qs = request.META.get("QUERY_STRING", "")
            return redirect(request.path + (("?" + qs) if qs else ""))

    else:
        form = KyorugiResultEntryForm(request.GET, request=request)

    return TemplateResponse(
        request,
        "admin/competitions/results_entry.html",
        {
            **admin.site.each_context(request),
            "title": "ثبت نتایج کیوروگی",
            "form": form,
        },
    )

# ---------- شماره‌گذاری بازی‌ها ----------

class MatchNumberingForm(forms.Form):
    competition = forms.ModelChoiceField(
        label="مسابقه",
        queryset=KyorugiCompetition.objects.order_by("-competition_date", "-id"),
        required=True,
    )
    weights = forms.ModelMultipleChoiceField(
        label="اوزانی که قرعه‌کشی شده‌اند",
        queryset=WeightCategory.objects.none(),
        required=True,
        help_text="فقط اوزانی را انتخاب کن که برایشان قرعه ساخته‌ای."
    )
    reset_old = forms.BooleanField(label="پاک کردن شماره‌های قبلی", required=False, initial=True)
    do_apply  = forms.BooleanField(label="اعمال شماره‌گذاری", required=False, initial=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        comp = None
        comp_id = self.data.get("competition") or self.initial.get("competition")
        if comp_id:
            try:
                comp = KyorugiCompetition.objects.get(pk=comp_id)
            except KyorugiCompetition.DoesNotExist:
                comp = None

        wc_qs = WeightCategory.objects.none()
        if comp:
            allowed_ids = list(comp.mat_assignments.values_list("weights__id", flat=True))
            wc_qs = WeightCategory.objects.filter(id__in=allowed_ids, gender=comp.gender).order_by("min_weight")
        self.fields["weights"].queryset = wc_qs

def numbering_view(request):
    form = MatchNumberingForm(request.POST or request.GET or None)

    ctx = {**admin.site.each_context(request)}
    ctx.update({"title": "شماره‌گذاری بازی‌ها", "form": form, "mats_map": None, "brackets": [], "is_bracket_published": False})

    selected_competition_id = None
    raw_comp = (request.POST.get("competition") or request.GET.get("competition") or "").strip()
    if raw_comp.isdigit():
        selected_competition_id = int(raw_comp)

    is_published = False
    if selected_competition_id:
        comp_pub = KyorugiCompetition.objects.filter(pk=selected_competition_id)\
                                             .only("bracket_published_at").first()
        is_published = bool(getattr(comp_pub, "bracket_published_at", None))

    if not form.is_valid():
        ctx["selected_competition_id"] = selected_competition_id
        ctx["is_bracket_published"] = is_published
        return TemplateResponse(request, "admin/competitions/match_numbering.html", ctx)

    comp: KyorugiCompetition = form.cleaned_data["competition"]
    ctx["selected_competition_id"] = comp.id
    ctx["is_bracket_published"] = bool(getattr(comp, "bracket_published_at", None))

    weights_qs = form.cleaned_data["weights"]
    weight_ids = list(weights_qs.values_list("id", flat=True))
    reset_old = bool(form.cleaned_data.get("reset_old"))
    do_apply  = bool(form.cleaned_data.get("do_apply"))

    if reset_old and not do_apply:
        clear_match_numbers_for_competition(comp.id, weight_ids)
        messages.warning(request, "شماره‌های قبلی پاک شد.")

    if do_apply:
        try:
            number_matches_for_competition(comp.id, weight_ids, clear_prev=reset_old)
            messages.success(request, "شماره‌گذاری با موفقیت انجام شد.")
        except Exception as e:
            messages.error(request, f"خطا در شماره‌گذاری: {e}")

    mat_assignments = list(comp.mat_assignments.all().prefetch_related("weights"))

    mats_map = []
    for ma in mat_assignments:
        ws = [w.name for w in ma.weights.filter(id__in=weight_ids).order_by("min_weight")]
        if ws:
            mats_map.append((ma.mat_number, ws))
    ctx["mats_map"] = mats_map



    draws = (Draw.objects.filter(competition=comp, weight_category_id__in=weight_ids)
             .select_related("belt_group", "weight_category")
             .order_by("weight_category__min_weight", "id"))

    brackets = []
    for dr in draws:
        ms = (Match.objects.filter(draw=dr)
              .select_related("player_a", "player_b")
              .order_by("round_no", "slot_a", "id"))
    
        matches_json = []
        for m in ms:
            matches_json.append({
                "id": m.id,
                "round_no": m.round_no,
                "slot_a": m.slot_a,
                "slot_b": m.slot_b,
                "is_bye": bool(m.is_bye),
                "player_a": (getattr(m.player_a, "full_name", None)
                             or f"{getattr(m.player_a,'first_name','')} {getattr(m.player_a,'last_name','')}".strip()
                             or ""),
                "player_b": (getattr(m.player_b, "full_name", None)
                             or f"{getattr(m.player_b,'first_name','')} {getattr(m.player_b,'last_name','')}".strip()
                             or ""),
                "match_number": m.match_number,
            })
    
        mat_no = None
        for ma in mat_assignments:
            if ma.weights.filter(id=dr.weight_category_id).exists():
                mat_no = ma.mat_number
                break

    
        brackets.append({
            "title": comp.title,
            "belt": getattr(dr.belt_group, "label", "—"),
            "weight": getattr(dr.weight_category, "name", "—"),
            "mat_no": mat_no,
            "date_j": _to_jalali_str(comp.competition_date),
            "size": getattr(dr, "size", 0) or 0,
            "matches_json": json.dumps(matches_json, ensure_ascii=False),
        })



    ctx["brackets"] = brackets
    ctx["board_logo_url"] = getattr(settings, "BOARD_LOGO_URL", None)
    return TemplateResponse(request, "admin/competitions/match_numbering.html", ctx)

@staff_member_required
@transaction.atomic
def numbering_publish_view(request):
    comp_id = (request.POST.get("competition") or "").strip()
    if not comp_id.isdigit():
        messages.error(request, "مسابقه انتخاب نشده است.")
        return redirect("/admin/competitions/numbering/")

    comp = KyorugiCompetition.objects.filter(pk=int(comp_id)).first()
    if not comp:
        messages.error(request, "مسابقه یافت نشد.")
        return redirect("/admin/competitions/numbering/")

    unpublish = request.GET.get("unpublish") in ("1", "true", "True")

    if unpublish:
        if getattr(comp, "bracket_published_at", None):
            comp.bracket_published_at = None
            comp.save(update_fields=["bracket_published_at"])
        messages.info(request, "جدول از پنل کاربر پنهان شد.")
    else:
        has_unnumbered = (
            Match.objects
            .filter(draw__competition=comp, is_bye=False, match_number__isnull=True)
            .filter(player_a__isnull=False, player_b__isnull=False)
            .exists()
        )
        if has_unnumbered:
            messages.error(request, "برخی مسابقات شماره‌گذاری نشده‌اند. ابتدا شماره‌گذاری را کامل کنید.")
            return redirect(f"/admin/competitions/numbering/?competition={comp.id}")

        if not getattr(comp, "bracket_published_at", None):
            comp.bracket_published_at = timezone.now()
            comp.save(update_fields=["bracket_published_at"])
        messages.success(request, "جدول منتشر شد و در پنل کاربر قابل مشاهده است.")

    return redirect(f"/admin/competitions/numbering/?competition={comp.id}")

def _inject_competitions_admin_urls(get_urls_fn):
    def wrapper():
        urls = get_urls_fn()
        extra = [
            path(
                "competitions/kyorugi-results/",
                admin.site.admin_view(kyorugi_results_view),
                name="competitions_kyorugi_results",
            ),
            path(
                "competitions/numbering/",
                admin.site.admin_view(numbering_view),
                name="competitions_match_numbering",
            ),
            path(
                "competitions/numbering/publish/",
                admin.site.admin_view(numbering_publish_view),
                name="competitions_match_numbering_publish",
            ),
        ]
        return extra + urls
    return wrapper

admin.site.get_urls = _inject_competitions_admin_urls(admin.site.get_urls)

class NumberingEntry(KyorugiCompetition):
    class Meta:
        proxy = True
        verbose_name = "شماره‌گذاری بازی‌ها"
        verbose_name_plural = "شماره‌گذاری بازی‌ها"

@admin.register(NumberingEntry)
class NumberingEntryAdmin(admin.ModelAdmin):
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request): return False

    def changelist_view(self, request, extra_context=None):
        return HttpResponseRedirect(reverse("admin:competitions_match_numbering"))

# ============================ سمینار ============================

def _greg_to_jalali_str(val):
    """نمایش تاریخ گرگوری به شمسی (با لحاظ محلی)."""
    return _to_jalali_str(val)

class SeminarAdminForm(forms.ModelForm):
    registration_start = forms.DateField(label="شروع ثبت‌نام", widget=PersianDateWidget)
    registration_end   = forms.DateField(label="پایان ثبت‌نام", widget=PersianDateWidget)
    event_date         = forms.DateField(label="تاریخ برگزاری", widget=PersianDateWidget)

    allowed_roles = forms.MultipleChoiceField(
        label="نقش‌های مجاز",
        choices=Seminar.ROLE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="خالی = همه نقش‌ها",
    )

    class Meta:
        model = Seminar
        fields = [
            "title", "poster", "description", "fee", "location",
            "registration_start", "registration_end", "event_date",
            "allowed_roles",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst: Optional[Seminar] = getattr(self, "instance", None)  # ✅ سازگار با 3.9
        if not self.is_bound and inst and inst.pk:
            for name in ("registration_start", "registration_end", "event_date"):
                d = _localdate(getattr(inst, name, None))
                if d:
                    self.initial[name] = d
            self.initial["allowed_roles"] = inst.allowed_roles or []

    def clean_registration_start(self):
        d = self.cleaned_data.get("registration_start")
        if not d: return None
        dt = datetime.datetime.combine(d, datetime.time(0, 0, 0))
        return timezone.make_aware(dt, _tz())

    def clean_registration_end(self):
        d = self.cleaned_data.get("registration_end")
        if not d: return None
        dt = datetime.datetime.combine(d, datetime.time(23, 59, 59))
        return timezone.make_aware(dt, _tz())

    
    def clean_event_date(self):
        d = self.cleaned_data.get("event_date")
        if not d:
            return None
    
        field = Seminar._meta.get_field("event_date")
    
        # ✅ اگر مدل واقعاً DateField است همان date را برگردان
        if isinstance(field, DateField) and not isinstance(field, DateTimeField):
            return d
    
        # ✅ اگر DateTimeField است
        dt = datetime.datetime.combine(d, datetime.time(0, 0, 0))
        return timezone.make_aware(dt, _tz())

    def clean(self):
        cleaned = super().clean()
        rs = cleaned.get("registration_start")
        re = cleaned.get("registration_end")
        cd = cleaned.get("event_date")

        if rs and re and rs > re:
            self.add_error("registration_start", "شروع ثبت‌نام نباید بعد از پایان ثبت‌نام باشد.")
        if cd and re:
            left = re.date() if isinstance(re, datetime.datetime) else re
            right = cd.date() if isinstance(cd, datetime.datetime) else cd
            if left > right:
                self.add_error("registration_end", "پایان ثبت‌نام باید قبل یا در همان روز برگزاری باشد.")
        return cleaned

    def save(self, commit=True):
        inst: Seminar = super().save(commit=False)
        # ایمن‌سازی نام فایل پوستر
        if getattr(inst, "poster", None):
            _sanitize_upload_field(inst.poster)
        inst.allowed_roles = self.cleaned_data.get("allowed_roles") or []
        if commit:
            inst.save()
        return inst

class SeminarAdmin(admin.ModelAdmin):
    """مدیریت سمینارها + نمای سفارشی لیست شرکت‌کنندگان"""
    form = SeminarAdminForm

    list_display = (
        "title",
        "registration_start_shamsi",
        "registration_end_shamsi",
        "event_date_shamsi",
        "fee",
        "allowed_roles_disp",
        "registrations_count_link",
    )
    list_display_links = ("title",)
    list_per_page = 25
    search_fields = ("title", "location")
    list_filter = (
        ("event_date", admin.DateFieldListFilter),
        ("registration_start", admin.DateFieldListFilter),
        ("registration_end", admin.DateFieldListFilter),
    )
    readonly_fields = ("created_at",)
    fieldsets = (
        ("اطلاعات اصلی", {"fields": ("title", "poster", "description", "fee", "location")}),
        ("زمان‌بندی (شمسی)", {"fields": ("registration_start", "registration_end", "event_date")}),
        ("دسترسی", {"fields": ("allowed_roles",)}),
        ("سیستمی", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    @admin.display(description="تاریخ برگزاری (شمسی)", ordering="event_date")
    def event_date_shamsi(self, obj: Seminar):
        return _greg_to_jalali_str(obj.event_date)

    @admin.display(description="شروع ثبت‌نام (شمسی)", ordering="registration_start")
    def registration_start_shamsi(self, obj: Seminar):
        return _greg_to_jalali_str(obj.registration_start)

    @admin.display(description="پایان ثبت‌نام (شمسی)", ordering="registration_end")
    def registration_end_shamsi(self, obj: Seminar):
        return _greg_to_jalali_str(obj.registration_end)

    def allowed_roles_disp(self, obj: Seminar):
        return obj.allowed_roles_display()
    allowed_roles_disp.short_description = "نقش‌های مجاز"

    @admin.display(description="تعداد ثبت‌نام")
    def registrations_count_link(self, obj: Seminar):
        url = reverse("admin:competitions_seminar_participants")
        url = f"{url}?seminar={obj.pk}"
        count = obj.registrations.count()
        return format_html('<a class="button" href="{}">{}</a>', url, count)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "participants/",
                self.admin_site.admin_view(self.participants_view),
                name="competitions_seminar_participants",
            ),
        ]
        return custom + urls

    def participants_view(self, request):
        seminars = Seminar.objects.order_by("-event_date", "-id")
        sel = request.GET.get("seminar")
        rows, selected = [], None

        if sel:
            try:
                selected = seminars.get(pk=int(sel))
            except Exception:
                selected = None

        if selected:
            qs = (
                SeminarRegistration.objects
                .filter(seminar=selected)
                .select_related("user", "user__profile")
                .order_by("id")
            )
            mapping = dict(Seminar.ROLE_CHOICES)

            for i, r in enumerate(qs, 1):
                prof = getattr(r.user, "profile", None)
                full_name = (
                    ((getattr(prof, "first_name", "") + " " + getattr(prof, "last_name", "")).strip())
                    or (getattr(r.user, "get_full_name", lambda: "")() or str(r.user))
                )
                nid   = (getattr(prof, "national_code", "") or "").strip()
                belt  = (getattr(prof, "belt_grade", "") or "").strip()
                mobile = (r.phone or getattr(prof, "phone", "") or "").strip() or "—"
                roles_fa = "، ".join(mapping.get(x, x) for x in (r.roles or [])) or "—"

                rows.append({
                    "idx": i,
                    "full_name": full_name or "—",
                    "nid": nid or "—",
                    "belt": belt or "—",
                    "roles_fa": roles_fa,
                    "mobile": mobile,
                    "paid": "بله" if r.is_paid else "خیر",
                    "amount": r.paid_amount or 0,
                })

        ctx = {
            **self.admin_site.each_context(request),
            "title": "لیست شرکت‌کنندگان سمینارها",
            "seminars": seminars,
            "selected": selected,
            "rows": rows,
        }
        return render(request, "admin/competitions/seminar/participants_changelist.html", ctx)

admin.site.register(Seminar, SeminarAdmin)

class SeminarAttendee(SeminarRegistration):
    class Meta:
        proxy = True
        verbose_name = "لیست شرکت‌کنندگان سمینارها"
        verbose_name_plural = "لیست شرکت‌کنندگان سمینارها"

@admin.action(description="خروجی CSV")
def export_csv(modeladmin, request, queryset):
    import csv
    from django.http import HttpResponse

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="seminar_attendees.csv"'
    w = csv.writer(resp)
    w.writerow([
        "Seminar", "User", "Full name", "National code",
        "Belt", "Phone", "Roles", "Paid", "Amount", "Paid At", "Created At"
    ])
    mapping = dict(Seminar.ROLE_CHOICES)

    qs = queryset.select_related("seminar", "user", "user__profile")
    for r in qs:
        p = getattr(r.user, "profile", None)
        full_name = (f"{getattr(p, 'first_name', '')} {getattr(p, 'last_name', '')}".strip()
                     if p else (getattr(r.user, "get_full_name", lambda: str(r.user))()))
        nid = getattr(p, "national_code", "") if p else ""
        belt = getattr(p, "belt_grade", "") if p else ""
        roles = "، ".join(mapping.get(x, x) for x in (r.roles or []))
        w.writerow([
            str(r.seminar), str(r.user), full_name, nid, belt, r.phone or "",
            "Yes" if r.is_paid else "No", r.paid_amount, r.paid_at or "", r.created_at
        ])
    return resp

@admin.register(SeminarAttendee)
class SeminarAttendeeAdmin(admin.ModelAdmin):
    change_list_template = "admin/competitions/seminar/participants_changelist.html"
    actions = [export_csv]

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request): return False

    def changelist_view(self, request, extra_context=None):
        seminars = Seminar.objects.all().order_by("-event_date", "-created_at")
        selected = request.GET.get("seminar") or ""
        regs = []
        selected_obj = None
        if selected:
            regs = (SeminarRegistration.objects
                    .select_related("seminar", "user", "user__profile")
                    .filter(seminar_id=selected)
                    .order_by("-created_at"))
            selected_obj = Seminar.objects.filter(id=selected).first()

        ctx = {
            **self.admin_site.each_context(request),
            "title": "لیست شرکت‌کنندگان سمینارها",
            "seminars": seminars,
            "selected_id": int(selected) if str(selected).isdigit() else "",
            "selected_seminar": selected_obj,
            "registrations": regs,
            "role_map": dict(Seminar.ROLE_CHOICES),
        }
        if extra_context:
            ctx.update(extra_context)
        return TemplateResponse(request, self.change_list_template, ctx)
# ============================ پومسه ============================

try:
    POOM_FIELDS = {f.name for f in PoomsaeCompetition._meta.get_fields()}
except Exception:
    POOM_FIELDS = set()

_HAS_AGE_CATEGORY   = "age_category"   in POOM_FIELDS
_HAS_AGE_CATEGORIES = "age_categories" in POOM_FIELDS

PoomsaeImageInline = None
PoomsaeFileInline  = None

try:
    from .models import PoomsaeImage

    class PoomsaeImageInline(admin.TabularInline):
        model = PoomsaeImage
        extra = 0
        verbose_name = "تصویر"
        verbose_name_plural = "تصاویر پیوست"
except Exception:
    pass

try:
    from .models import PoomsaeFile

    class PoomsaeFileInline(admin.TabularInline):
        model = PoomsaeFile
        extra = 0
        verbose_name = "فایل PDF"
        verbose_name_plural = "فایل‌های پیوست"
except Exception:
    pass

class PoomsaeMatAssignmentInline(admin.TabularInline):
    model = PoomsaeMatAssignment
    extra = 0
    filter_horizontal = ("belt_groups",)
    fields = ("mat_number", "belt_groups")
    verbose_name = "زمین"
    verbose_name_plural = "زمین‌ها و رده‌های کمربندی"

class PoomsaeCoachApprovalInline(admin.TabularInline):
    model = PoomsaeCoachApproval
    extra = 0
    fields = ("player", "coach", "code", "approved", "is_active", "created_at", "updated_at")
    readonly_fields = ("code", "created_at", "updated_at")
    autocomplete_fields = ("player", "coach")


class PoomsaeCompetitionAdminForm(forms.ModelForm):
    """
    فرم ادمین پومسه با ویجت تاریخ شمسی.
    """
    registration_start = forms.DateField(
        widget=PersianDateWidget(),   # ✅ شیء، نه کلاس
        label="شروع ثبت‌نام",
    )
    registration_end = forms.DateField(
        widget=PersianDateWidget(),   # ✅
        label="پایان ثبت‌نام",
    )
    draw_date = forms.DateField(
        required=False,
        widget=PersianDateWidget(),   # ✅
        label="تاریخ قرعه‌کشی",
    )
    competition_date = forms.DateField(
        widget=PersianDateWidget(),   # ✅
        label="تاریخ برگزاری",
    )

    class Meta:
        model = PoomsaeCompetition
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # سه‌حالتی کردن registration_manual (مثل کیوروگی)
        if "registration_manual" in self.fields:
            current = getattr(self.instance, "registration_manual", None)
            self.fields["registration_manual"] = TriStateChoiceField(label="فعال بودن ثبت‌نام")
            if not self.is_bound:
                self.initial["registration_manual"] = (
                    "" if current is None else ("1" if current is True else "0")
                )
            self.fields["registration_manual"].help_text = "خالی=طبق تاریخ‌ها، بله=اجباراً باز، خیر=اجباراً بسته"

    # PersianDateWidget خودش تاریخ میلادی برمی‌گرداند؛ فقط همان را پاس می‌دهیم.
    def clean_registration_start(self):
        return self.cleaned_data.get("registration_start")

    def clean_registration_end(self):
        return self.cleaned_data.get("registration_end")

    def clean_draw_date(self):
        return self.cleaned_data.get("draw_date")

    def clean_competition_date(self):
        return self.cleaned_data.get("competition_date")


@admin.register(PoomsaeCompetition)
class PoomsaeCompetitionAdmin(admin.ModelAdmin):
    form = PoomsaeCompetitionAdminForm

    # فیلتر افقی داینامیک (بسته به وجود فیلد در مدل)
    _fh = []
    if "belt_groups" in POOM_FIELDS:
        _fh.append("belt_groups")
    if _HAS_AGE_CATEGORIES:
        _fh.append("age_categories")
    if _fh:
        filter_horizontal = tuple(_fh)
    
    # اینلاین‌ها
    _inlines = [PoomsaeMatAssignmentInline]  # ✅ تمیزتر
    
    if PoomsaeImageInline:
        _inlines.append(PoomsaeImageInline)
    if PoomsaeFileInline:
        _inlines.append(PoomsaeFileInline)
    
    _inlines.append(PoomsaeCoachApprovalInline)
    inlines = _inlines



    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if "belt_groups" in POOM_FIELDS:
            qs = qs.prefetch_related("belt_groups")
        return qs

    list_display = (
        "name",
        "belt_groups_col",
        "gender",
        "competition_date_shamsi",
        "registration_open_col",
        "registration_manual",
        "mat_count",
        "entry_fee",
    )
    list_display_links = ("name",)

    search_fields = tuple(
        x
        for x in ("name", "public_id", "description", "city", "address")
        if (x in POOM_FIELDS) or x in ("name", "description")
    )
    list_filter = tuple(
        f
        for f in (
            ("registration_start", admin.DateFieldListFilter)
            if "registration_start" in POOM_FIELDS
            else None,
            ("registration_end", admin.DateFieldListFilter)
            if "registration_end" in POOM_FIELDS
            else None,
            ("draw_date", admin.DateFieldListFilter)
            if "draw_date" in POOM_FIELDS
            else None,
            ("competition_date", admin.DateFieldListFilter)
            if "competition_date" in POOM_FIELDS
            else None,
            "registration_manual",
            ("gender" if "gender" in POOM_FIELDS else None),
        )
        if f
    )

    actions = []
    readonly_fields = tuple(
        f for f in ("public_id", "created_at", "updated_at") if f in POOM_FIELDS
    )
    ordering = ("-competition_date", "-id")

    def get_fieldsets(self, request, obj=None):
        # ✅ هرگز اینجا get_form/get_fields صدا نزن؛ باعث recursion می‌شود.
        present = set(POOM_FIELDS) | set(self.readonly_fields or ())
    
        def keep(*names):
            out = []
            for n in names:
                if not n:
                    continue
                if isinstance(n, (list, tuple)):
                    out.extend([x for x in n if x and x in present])
                else:
                    if n in present:
                        out.append(n)
            return tuple(out)
    
        info = keep(
            "name",
            "poster",
            "description",
            "entry_fee",
            ("age_categories" if _HAS_AGE_CATEGORIES else ("age_category" if _HAS_AGE_CATEGORY else None)),
            "belt_level",
            "belt_groups",
            "gender",
        )
    
        place = keep("city", "address")
    
        dates = keep(
            "mat_count",
            "registration_manual",
            "registration_start",
            "registration_end",
            "draw_date",
            "competition_date",
        )
    
        terms = keep("terms_template")
        system = keep("public_id", "created_at", "updated_at")
    
        fs = [("اطلاعات کلی", {"fields": info})]
        if place:
            fs.append(("محل برگزاری", {"fields": place}))
        if dates:
            fs.append(("ثبت‌نام و تاریخ‌ها (شمسی)", {"fields": dates}))
        if terms:
            fs.append(("تعهدنامه مربی", {"fields": terms}))
        if system:
            fs.append(("سیستمی", {"fields": system, "classes": ("collapse",)}))
    
        return tuple(fs)


    def construct_change_message(self, request, form, formsets, add=False):
        """
        جلوگیری از خطای new_objects/deleted_objects برای فرم‌ست‌های سفارشی
        مثل PoomsaeImageFormFormSet که این اتربیوت‌ها رو ندارن.
        """
        safe_formsets = [
            fs
            for fs in (formsets or [])
            if all(
                hasattr(fs, attr)
                for attr in ("new_objects", "changed_objects", "deleted_objects")
            )
        ]
        try:
            return _dj_construct_change_message(form, safe_formsets, add)
        except Exception:
            return "added" if add else "changed"

    def save_formset(self, request, form, formset, change):
        """
        ذخیرهٔ امن اینلاین‌های پومسه + امن‌سازی نام فایل‌ها
        و جلوگیری از باگ‌های فرم‌ست‌های سفارشی.
        """
        try:
            # اگر فرم‌ست مدل‌دار استاندارد است (اینلاین معمولی)
            if (
                hasattr(formset, "model")
                and isinstance(getattr(formset, "model", None), type)
                and issubclass(formset.model, dj_models.Model)
            ):
                model_name = getattr(formset.model, "__name__", "")

                for f in formset.forms:
                    if not f.is_valid():
                        continue

                    cd = getattr(f, "cleaned_data", {}) or {}

                    # حذف
                    if cd.get("DELETE"):
                        inst = getattr(f, "instance", None)
                        if inst and getattr(inst, "pk", None):
                            inst.delete()
                        continue

                   
                    # فرم خالی را برای فایل/تصویر رد کن
                    if model_name == "PoomsaeImage" and not cd.get("image"):
                        continue
                    if model_name == "PoomsaeFile" and not cd.get("file"):
                        continue
                    
                    # ✅ فرم خالی زمین پومسه را رد کن (چک خواناتر)
                    if model_name == "PoomsaeMatAssignment":
                        bg = cd.get("belt_groups")
                        if not cd.get("mat_number") and not bg:
                            continue



                    obj = f.save(commit=False)

                    # امن کردن نام فایل‌ها
                    if model_name == "PoomsaeImage" and hasattr(obj, "image"):
                        _sanitize_upload_field(obj.image)
                    if model_name == "PoomsaeFile" and hasattr(obj, "file"):
                        _sanitize_upload_field(obj.file)

                    # ست کردن FK والد
                    if (
                        hasattr(formset, "fk")
                        and formset.fk
                        and hasattr(obj, formset.fk.name)
                    ):
                        setattr(obj, formset.fk.name, form.instance)

                    obj.save()
                    if hasattr(f, "save_m2m"):
                        f.save_m2m()

                # حذف‌هایی که فرم‌ست مدل‌دار پشتیبانی می‌کند
                for obj in getattr(formset, "deleted_objects", []):
                    obj.delete()

                if hasattr(formset, "save_m2m"):
                    formset.save_m2m()
            else:
                # اگر فرم‌ست غیرمدلی/سفارشی باشد، بده به والد
                super().save_formset(request, form, formset, change)

        except (ValidationError, IntegrityError) as e:
            messages.error(
                request,
                "خطا در ذخیره‌ی آیتم‌های زیرمجموعه پومسه (فایل/تصویر/تأیید مربی). "
                f"لطفاً مقادیر را بررسی کن. جزئیات: {e}"
            )

    @admin.display(description="گروه‌های کمربندی")
    def belt_groups_col(self, obj):
        if not hasattr(obj, "belt_groups"):
            return "—"
        labels = list(obj.belt_groups.values_list("label", flat=True))
        if not labels:
            return "—"
        shown = "، ".join(labels[:3])
        extra = len(labels) - 3
        return f"{shown} …(+{extra})" if extra > 0 else shown

    @admin.display(description="برگزاری (شمسی)", ordering="competition_date")
    def competition_date_shamsi(self, obj):
        return _to_jalali_str(getattr(obj, "competition_date", None))

    @admin.display(description="شروع ثبت‌نام (شمسی)")
    def registration_start_shamsi(self, obj):
        return _greg_to_jalali_str(getattr(obj, "registration_start", None))

    @admin.display(description="پایان ثبت‌نام (شمسی)")
    def registration_end_shamsi(self, obj):
        return _greg_to_jalali_str(getattr(obj, "registration_end", None))

    @admin.display(boolean=True, description="ثبت‌نام باز؟")
    def registration_open_col(self, obj):
        return getattr(obj, "registration_open_effective", False)

    def save_model(self, request, obj, form, change):
        """
        موقع ذخیرهٔ مسابقه پومسه، علاوه بر امن‌سازی نام پوستر،
        فیلدهای قدیمی (start_date/end_date) را از فیلدهای جدید
        پر می‌کنیم تا هم NOT NULL رعایت شود هم کانسترینت‌های قدیمی.
        """
        cd = getattr(form, "cleaned_data", {}) or {}
    
        rs = cd.get("registration_start")
        re = cd.get("registration_end")
        comp = cd.get("competition_date")
    
        # ✅ start_date = تاریخ شروع واقعی مسابقه (competition_date)
        if hasattr(obj, "start_date"):
            if comp:
                obj.start_date = comp
            elif rs:
                obj.start_date = rs
            elif re:
                obj.start_date = re
    
        # اگر end_date هم اجباری است، مقدار معقول بگذار (مثلاً تا خود روز مسابقه)
        if hasattr(obj, "end_date"):
            if comp:
                obj.end_date = comp
            elif re:
                obj.end_date = re
            elif rs:
                obj.end_date = rs
    
        # ⭐ امن‌سازی نام پوستر فقط وقتی واقعاً تغییر کرده
        if "poster" in getattr(form, "changed_data", []) and getattr(obj, "poster", None):
            _sanitize_upload_field(obj.poster)
    
        super().save_model(request, obj, form, change)

# ======================= تأیید مربیان (یکپارچه) =======================

try:
    admin.site.unregister(CoachApproval)
except admin.sites.NotRegistered:
    pass
try:
    admin.site.unregister(PoomsaeCoachApproval)
except admin.sites.NotRegistered:
    pass

class CoachApprovalsEntry(KyorugiCompetition):
    class Meta():
        proxy = True
        verbose_name = "تأیید مربیان"
        verbose_name_plural = "تأیید مربیان"

@admin.register(CoachApprovalsEntry)
class CoachApprovalsAdmin(admin.ModelAdmin):
    change_list_template = "admin/competitions/approvals_unified.html"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "detail/<str:kind>/<int:comp_id>/",
                self.admin_site.admin_view(self.detail_view),
                name="competitions_approvals_detail",
            ),
        ]
        return custom + urls

    def changelist_view(self, request, extra_context=None):
        k_qs = (CoachApproval.objects
                .filter(terms_accepted=True, is_active=True)
                .select_related("competition")
                .order_by("-approved_at"))

        p_qs = (PoomsaeCoachApproval.objects
                .filter(approved=True, is_active=True)
                .select_related("competition")
                .order_by("-updated_at", "-created_at"))

        rows = []
        bundle = {}
        last_dt = {}

        for a in k_qs:
            key = ("ky", a.competition_id)
            b = bundle.setdefault(key, {
                "title": getattr(a.competition, "title", f"#{a.competition_id}"),
                "style": "کیوروگی", "count": 0
            })
            b["count"] += 1
            last_dt[key] = max(last_dt.get(key, a.approved_at), a.approved_at)

        for a in p_qs:
            key = ("pm", a.competition_id)
            b = bundle.setdefault(key, {
                "title": getattr(a.competition, "name", f"#{a.competition_id}"),
                "style": "پومسه", "count": 0
            })
            b["count"] += 1
            dt = a.updated_at or a.created_at
            last_dt[key] = max(last_dt.get(key, dt), dt)

        for (kind, cid), info in bundle.items():
            rows.append({
                "title": info["title"],
                "style": info["style"],
                "count": info["count"],
                "last": last_dt.get((kind, cid)),
                "detail_url": reverse("admin:competitions_approvals_detail", args=[kind, cid]),
            })

        rows.sort(key=lambda r: (r["last"] or datetime.datetime.min), reverse=True)
        for r in rows:
            r["last_j"] = _to_jalali_dt_str(r["last"])

        ctx = dict(self.admin_site.each_context(request))
        ctx.update({"title": "تأیید مربیان", "mode": "list", "rows": rows})
        if extra_context: ctx.update(extra_context)
        return TemplateResponse(request, "admin/competitions/approvals_unified.html", ctx)

    def detail_view(self, request, kind: str, comp_id: int):
        if request.method == "POST":
            del_id = request.POST.get("del_id")
            if del_id and del_id.isdigit():
                if kind == "ky":
                    CoachApproval.objects.filter(pk=int(del_id)).delete()
                else:
                    PoomsaeCoachApproval.objects.filter(pk=int(del_id)).delete()
                self.message_user(request, "حذف شد.", level=messages.SUCCESS)
                return redirect(request.path)

        rows = []
        if kind == "ky":
            comp = KyorugiCompetition.objects.filter(pk=comp_id).first()
            comp_title = getattr(comp, "title", f"# {comp_id}")
            qs = (CoachApproval.objects
                  .filter(competition_id=comp_id, terms_accepted=True, is_active=True)
                  .select_related("coach")
                  .order_by("-approved_at", "-id"))
            for a in qs:
                rows.append({
                    "id": a.id,
                    "coach": _full_name(a.coach) or "—",
                    "code": a.code or "—",
                    "date_j": _to_jalali_dt_str(a.approved_at),
                })
            style = "کیوروگی"
        else:
            comp = PoomsaeCompetition.objects.filter(pk=comp_id).first()
            comp_title = getattr(comp, "name", f"# {comp_id}")
            qs = (PoomsaeCoachApproval.objects
                  .filter(competition_id=comp_id, approved=True, is_active=True)
                  .select_related("coach")
                  .order_by("-updated_at", "-id"))
            for a in qs:
                rows.append({
                    "id": a.id,
                    "coach": _full_name(a.coach) or "—",
                    "code": a.code or "—",
                    "date_j": _to_jalali_dt_str(a.updated_at or a.created_at),
                })
            style = "پومسه"

        ctx = dict(self.admin_site.each_context(request))
        ctx.update({
            "title": f"تأیید مربیان – {comp_title}",
            "mode": "detail",
            "style": style,
            "comp_title": comp_title,
            "rows": rows,
            "back_url": reverse("admin:competitions_coachapprovalsentry_changelist"),
        })
        return TemplateResponse(request, "admin/competitions/approvals_unified.html", ctx)


#=================================================================

class DiscountCodeAdminForm(forms.ModelForm):
    class Meta:
        model = DiscountCode
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        coach_field = self.fields.get("coach")
        if coach_field is not None:
            coach_field.queryset = (
                User.objects
                .filter(profile__is_coach=True)
                .select_related("profile")
            )

            def _label(u):
                prof = getattr(u, "profile", None)
                if prof:
                    full = f"{prof.first_name} {prof.last_name}".strip()
                    if full:
                        return full
                # اگر به هر دلیل پروفایل یا اسم نداشت
                username = (getattr(u, "username", "") or "").strip()
                return username or str(u)

            coach_field.label_from_instance = _label



@admin.register(DiscountCode)
class DiscountCodeAdmin(admin.ModelAdmin):
    form = DiscountCodeAdminForm
    list_display = (
        "code",
        "coach",
        "type",
        "percent",
        "competition",
        "seminar",
        "max_uses",
        "used_count",
        "active",
        "created_at",
    )
    list_filter = ("type", "active", "competition", "seminar")
    search_fields = (
    "code",
    "coach__first_name",
    "coach__last_name",
    "coach__username",
)


class KyorugiResultAdminForm(forms.ModelForm):
    class Meta:
        model = KyorugiResult
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        # ✅ اگر فرم bind نشده (صفحه add)، از GET بخون
        data = self.data if self.is_bound else (getattr(self.request, "GET", {}) if self.request else {})

        comp_id = data.get("competition") or getattr(self.instance, "competition_id", None)
        w_id    = data.get("weight_category") or getattr(self.instance, "weight_category_id", None)

        # وزن‌ها بر اساس مسابقه
        if comp_id:
            try:
                comp = KyorugiCompetition.objects.get(pk=comp_id)
                allowed_ids = comp.mat_assignments.values_list("weights__id", flat=True).distinct()
                self.fields["weight_category"].queryset = WeightCategory.objects.filter(id__in=list(allowed_ids))
            except KyorugiCompetition.DoesNotExist:
                self.fields["weight_category"].queryset = WeightCategory.objects.none()
        else:
            self.fields["weight_category"].queryset = WeightCategory.objects.none()

        # enrollments بر اساس comp + weight
        medal_fields = ["gold_enrollment", "silver_enrollment", "bronze1_enrollment", "bronze2_enrollment"]
        if comp_id and w_id:
            qs = Enrollment.objects.filter(
                competition_id=comp_id,
                weight_category_id=w_id,
                status__in=ELIGIBLE_STATUSES,
            )
            for f in medal_fields:
                if f in self.fields:
                    self.fields[f].queryset = qs
        else:
            for f in medal_fields:
                if f in self.fields:
                    self.fields[f].queryset = Enrollment.objects.none()


@admin.register(KyorugiResult)
class KyorugiResultAdmin(admin.ModelAdmin):
    form = KyorugiResultAdminForm

    def get_form(self, request, obj=None, **kwargs):
        BaseForm = super().get_form(request, obj, **kwargs)

        class FormWithRequest(BaseForm):
            def __init__(self2, *args, **kw):
                kw["request"] = request
                super().__init__(*args, **kw)

        return FormWithRequest

    class Media:
        js = ("admin/competitions/kyorugiresult_deps.js",)
