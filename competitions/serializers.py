# -*- coding: utf-8 -*-
from __future__ import annotations
from rest_framework import serializers
from django.utils import timezone
from datetime import date as _date, datetime as _datetime, timedelta
import jdatetime
from django.core.files.storage import default_storage
import re
from django.db.models import Q
from django.db import transaction
from django.conf import settings
from django.db.models import Exists, OuterRef
from typing import Optional

from django.shortcuts import get_object_or_404


from accounts.models import UserProfile, TkdClub, TkdBoard
from math import inf

from .models import (
    KyorugiCompetition, CompetitionImage, MatAssignment, Belt, Draw, Match, BeltGroup,
    CompetitionFile, CoachApproval, WeightCategory, Enrollment, Seminar, SeminarRegistration,
    PoomsaeCompetition, AgeCategory, PoomsaeImage, PoomsaeFile, PoomsaeDivision, PoomsaeEnrollment,
    PoomsaeCoachApproval,
)

BELT_FA = {"white":"سفید","yellow":"زرد","green":"سبز","blue":"آبی","red":"قرمز","black":"مشکی"}

# پرداخت (اختیاری)
try:
    from payments.models import Payment  # اگر پروژهٔ پرداخت داری
except Exception:
    Payment = None

# وضعیت‌هایی که «کارت» آماده نمایش است
CARD_READY_STATUSES = {"paid", "confirmed", "approved", "accepted", "completed"}

# ✅ کارت آماده نمایش؟
def _can_show_card(status: str, is_paid: bool = False) -> bool:
    s = (status or "").lower()
    return bool(is_paid or (s in CARD_READY_STATUSES))
# -------------------------------------------------
# Helpers: تاریخ
# -------------------------------------------------

def _get_player_like_profile(user: "UserProfile"):
    """
    پروفایلی برگردان که برای ثبت‌نام به عنوان بازیکن قابل استفاده باشد.
    اولویت: role=player
    اگر وجود نداشت: role=coach (یا هر پروفایل موجود)
    """
    if not user:
        return None

    prof = getattr(user, "profile", None)
    if prof and getattr(prof, "role", None) in ("player", "coach"):
        return prof

    # اولویت با player
    p = UserProfile.objects.filter(user=user, role="player").first()
    if p:
        return p

    # fallback: اگر فقط coach است
    c = UserProfile.objects.filter(user=user, role="coach").first()
    if c:
        return c

    # آخرین fallback: هر پروفایل
    return UserProfile.objects.filter(user=user).first()



def _full_name(u):
    if not u:
        return None
    # تلاش برای full_name یا name
    for a in ("full_name", "name"):
        v = getattr(u, a, None)
        if v:
            return v
    fn = (getattr(u, "first_name", "") or "").strip()
    ln = (getattr(u, "last_name", "") or "").strip()
    return (fn + " " + ln).strip() or getattr(u, "username", None)

class MatchPublicSerializer(serializers.ModelSerializer):
    player_a = serializers.SerializerMethodField()
    player_b = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = (
            "id",
            "round_no",
            "slot_a",
            "slot_b",
            "is_bye",
            "match_number",   # شماره بازی که در شماره‌گذاری ست می‌شود
            "player_a",
            "player_b",
        )

    def get_player_a(self, obj): return _full_name(getattr(obj, "player_a", None)) or ""
    def get_player_b(self, obj): return _full_name(getattr(obj, "player_b", None)) or ""

class DrawWithMatchesSerializer(serializers.ModelSerializer):
    belt_group = serializers.CharField(source="belt_group.label", allow_null=True)
    weight_category = serializers.CharField(source="weight_category.name", allow_null=True)
    matches = serializers.SerializerMethodField()

    class Meta:
        model = Draw
        fields = ("id", "size", "belt_group", "weight_category", "matches")

    def get_matches(self, obj: Draw):
        # اگر related_name روی مدل Match ندارید، از match_set استفاده می‌شود
        qs = (getattr(obj, "matches", None) or obj.match_set)\
                .select_related("player_a", "player_b")\
                .order_by("round_no", "slot_a", "id")
        return MatchPublicSerializer(qs, many=True).data



def _as_local_date(v):
    if not v:
        return None
    if isinstance(v, _datetime):
        v = timezone.localtime(v) if timezone.is_aware(v) else v
        return v.date()
    if isinstance(v, _date):
        return v
    return None

def _g2j(d):
    if not d:
        return None
    if isinstance(d, _datetime):
        d = d.date()
    return jdatetime.date.fromgregorian(date=d)

def _j2str(jd):
    return f"{jd.year:04d}/{jd.month:02d}/{jd.day:02d}" if jd else None

# helpers (بالای فایل)


def _to_jalali_date_str(d):
    """Gregorian date/datetime -> 'YYYY/MM/DD' jalali (safe)."""
    if not d:
        return None
    # اگر datetime است، قبل از تبدیل صرفاً تاریخ را بگیر
    if isinstance(d, _datetime):
        # اگر آگاه به تایم‌زون است، به لوکال تبدیل کن بعد date() بگیر
        d = timezone.localtime(d).date() if timezone.is_aware(d) else d.date()
    try:
        jd = jdatetime.date.fromgregorian(date=d)
        return f"{jd.year:04d}/{jd.month:02d}/{jd.day:02d}"
    except Exception:
        return None

def _to_jalali_date_str_safe(d):
    # الان با _to_jalali_date_str یکی شد؛ نگهش داریم برای سازگاری
    return _to_jalali_date_str(d)

def _to_greg_from_str_jalali(s: str):
    """
    ورودی: 'YYYY/MM/DD' یا 'YYYY-MM-DD' (جلالی یا میلادی).
    خروجی: datetime.date گریگوریان. سال >=1700 میلادی فرض می‌شود.
    """
    if not s:
        return None
    # حذف ZWNJ/RTL/… و یکدست‌سازی ارقام و جداکننده
    t = str(s)
    t = re.sub(r"[\u200e\u200f\u200c\u202a-\u202e]", "", t)
    t = _to_en_digits(t).strip().replace("-", "/")
    try:
        y, m, d = [int(x) for x in t.split("/")[:3]]
    except Exception:
        return None
    try:
        if y >= 1700:
            return _date(y, m, d)
        # جلالی → گریگوریان (date، نه datetime)
        return jdatetime.date(y, m, d).togregorian()
    except Exception:
        return None


def _parse_jalali_str(s):
    if not s:
        return None
    if isinstance(s, (_date, _datetime)):
        g = s.date() if isinstance(s, _datetime) else s
        return jdatetime.date.fromgregorian(date=g)
    t = _to_en_digits(str(s)).strip().strip('"').strip("'").replace("-", "/")
    parts = t.split("/")[:3]
    try:
        y, m, d = [int(x) for x in parts]
    except Exception:
        return None
    try:
        if y >= 1700:  # Gregorian
            g = _date(y, m, d)
            return jdatetime.date.fromgregorian(date=g)
        return jdatetime.date(y, m, d)
    except Exception:
        return None

def _eligible_real_matches_qs(comp):
    """
    بازی‌های «واقعی» یعنی:
      - BYE نیستند (is_bye=False)
      - هر دو طرف مشخص است (player_* یا slot_* برای A و B)
    """
    base = Match.objects.filter(draw__competition=comp)
    eligible = base.filter(is_bye=False).filter(
        (Q(player_a__isnull=False) | Q(slot_a__isnull=False)) &
        (Q(player_b__isnull=False) | Q(slot_b__isnull=False))
    )
    return base, eligible

# -------------------------------------------------
# Helpers: جنسیت، ارقام، کمربند، باشگاه
# -------------------------------------------------
_GENDER_MAP = {
    "male": "male", "m": "male", "man": "male",
    "آقا": "male", "اقا": "male", "مرد": "male",
    "آقایان": "male", "آقايان": "male", "اقایان": "male",
    "both": "both", "mixed": "both", "مختلط": "both", "هردو": "both", "هر دو": "both",
    "female": "female", "f": "female", "woman": "female",
    "زن": "female", "خانم": "female", "بانو": "female",
    "بانوان": "female", "خانم‌ها": "female", "خانمها": "female",
}
def _norm_gender(v):
    if v is None:
        return None
    t = str(v).strip().lower().replace("ي", "ی").replace("ك", "ک").replace("‌", "").replace("-", "")
    return _GENDER_MAP.get(t, t)

_DIGIT_MAP = {ord(p): str(i) for i, p in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_DIGIT_MAP.update({ord(a): str(i) for i, a in enumerate("٠١٢٣٤٥٦٧٨٩")})

def _to_en_digits(s):
    return str(s).translate(_DIGIT_MAP) if s is not None else s

BELT_BASE = {
    "white": "white", "سفید": "white",
    "yellow": "yellow", "زرد": "yellow",
    "green": "green", "سبز": "green",
    "blue": "blue", "آبی": "blue", "ابي": "blue", "ابی": "blue",
    "red": "red", "قرمز": "red",
    "black": "black", "مشکی": "black", "مشكى": "black",
}
_DAN_RE = re.compile(r"(مشکی|مشكى)\s*دان\s*(\d{1,2})", re.IGNORECASE)

def _norm_belt(s):
    """نام کمربند را به کُد یکتا نگاشت می‌کند؛ «مشکی دان n» → black."""
    if not s:
        return None
    t = _to_en_digits(str(s)).strip().lower().replace("ي", "ی").replace("ك", "ک")
    m = _DAN_RE.search(t)
    if m:
        try:
            dan = int(_to_en_digits(m.group(2)))
            if 1 <= dan <= 10:
                return "black"
        except Exception:
            pass
    for k, v in BELT_BASE.items():
        if k in t:
            return v
    if t in {"white", "yellow", "green", "blue", "red", "black"}:
        return t
    return None

def _player_belt_code_from_profile(prof: UserProfile):
    """
    🔧 با مدل فعلی شما فقط belt_grade (CharField) معتبر است.
    """
    raw = getattr(prof, "belt_grade", None)
    code = _norm_belt(raw)
    if code:
        return code
    # آینده‌نگر: اگر بعدها فیلدی اضافه شد:
    raw2 = (
        getattr(prof, "belt_name", None)
        or getattr(prof, "belt_level", None)
        or getattr(prof, "belt_code", None)
    )
    return _norm_belt(raw2)

def _find_belt_group_obj(comp, player_belt_code: str):
    if not comp or not player_belt_code:
        return None
    for g in comp.belt_groups.all().prefetch_related("belts"):
        for b in g.belts.all():
            nm = getattr(b, "name", "") or getattr(b, "label", "")
            if _norm_belt(nm) == player_belt_code:
                return g
    return None

def _find_belt_group_label(comp, player_belt_code: str)-> Optional[str]:
    for g in comp.belt_groups.all().prefetch_related("belts"):
        codes = set()
        for b in g.belts.all():
            nm = getattr(b, "name", "") or getattr(b, "label", "")
            code = _norm_belt(nm)
            if code:
                codes.add(code)
        if player_belt_code in codes:
            return getattr(g, "label", None) or getattr(g, "name", None)
    return None

def _collect_comp_weights(comp):
    """WeightCategoryهایی که برای مسابقه روی زمین‌ها ست شده‌اند."""
    ws = set()
    for ma in comp.mat_assignments.all().prefetch_related("weights"):
        for w in ma.weights.all():
            ws.add(w)
    return list(ws)

def _wc_includes(wc, val: float) -> bool:
    tol = getattr(wc, "tolerance", 0) or 0
    mn  = getattr(wc, "min_weight", None)
    mx  = getattr(wc, "max_weight", None)
    lo  = -inf if mn is None else (mn - tol)
    hi  =  inf if mx is None else (mx + tol)
    return (val >= lo) and (val <= hi)

def _gender_ok_for_wc(comp, wc_gender):
    rg = _norm_gender(getattr(comp, "gender", None))
    wg = _norm_gender(wc_gender)
    if rg in (None, "", "both"):
        return True
    if wg in (None, "",):
        return True
    return wg == rg

def _extract_club_profile_and_name(player: UserProfile):
    """خروجی: (club_profile_for_fk, club_name_snapshot) — مطابق مدل‌های شما"""
    club_profile = None
    club_name = ""
    raw = getattr(player, "club", None)  # FK به TkdClub
    if isinstance(raw, TkdClub):
        club_name = getattr(raw, "club_name", "") or ""
    if not club_name and isinstance(getattr(player, "club_names", None), list):
        club_name = "، ".join([c for c in player.club_names if c])
    return raw, club_name

def _parse_weight_to_float(raw):
    t = _to_en_digits(raw or "")
    for ch in "/٫,،":
        t = t.replace(ch, ".")
    t = "".join(ch for ch in t if (ch.isdigit() or ch == "."))
    if t.count(".") > 1:
        first = t.find(".")
        t = t[:first + 1] + t[first + 1:].replace(".", "")
    return float(t)

# -------------------------------------------------
# Poomsae helpers
# -------------------------------------------------
def _name_like(obj):
    if not obj:
        return None
    for a in ("label", "name", "title"):
        v = getattr(obj, a, None)
        if v:
            return str(v)
    return None

def _poomsae_age_group_display(obj):
    try:
        ags = getattr(obj, "age_categories", None)
        if ags is not None:
            names = [_name_like(x) for x in ags.all()]
            names = [n for n in names if n]
            if names:
                return "، ".join(names)
    except Exception:
        pass
    ac = getattr(obj, "age_category", None)
    if ac:
        n = _name_like(ac)
        if n:
            return n
    return None

def _poomsae_age_windows(obj):
    """
    بازه‌های سنی معتبر برای پومسه را برمی‌گرداند: [(from_j, to_j), ...]
    ابتدا M2M age_categories و اگر خالی بود از FK age_category.
    """
    wins = []
    try:
        ags = getattr(obj, "age_categories", None)
        if ags is not None:
            for ac in ags.all():
                fr = _g2j(getattr(ac, "from_date", None))
                to = _g2j(getattr(ac, "to_date", None))
                wins.append((fr, to))
    except Exception:
        pass
    if not wins and getattr(obj, "age_category", None):
        ac = obj.age_category
        wins.append((_g2j(getattr(ac, "from_date", None)),
                     _g2j(getattr(ac, "to_date", None))))
    return wins

# -------------------------------------------------
# --- Locked profile helpers (for FE prefill) ---
def _profile_locked_dict(prof: UserProfile):
    if not prof:
        return None
    # تاریخ تولد را به شمسی/استرینگ بدهیم تا FE راحت نمایش دهد
    def _birth_fa(p):
        bd = getattr(p, "birth_date", None)
        if not bd:
            return None
        if isinstance(bd, (_datetime, _date)):
            return _to_jalali_date_str(bd)
        jd = _parse_jalali_str(bd)
        if jd:
            return _j2str(jd)
        g = _to_greg_from_str_jalali(bd)
        return _to_jalali_date_str(g) if g else str(bd)

    club_name = ""
    coach_name = ""
    club_obj = getattr(prof, "club", None)
    if isinstance(club_obj, TkdClub):
        club_name = getattr(club_obj, "club_name", "") or ""
    if getattr(prof, "coach", None):
        coach_name = f"{getattr(prof.coach, 'first_name', '')} {getattr(prof.coach, 'last_name', '')}".strip()

    # کمربند را هم متن هم کُدش را بدهیم (برای نمایش/بررسی)
    belt_raw = getattr(prof, "belt_grade", None)
    belt_code = _norm_belt(belt_raw)
    belt_display = BELT_FA.get(belt_code, belt_raw or None)

    return {
        "first_name":  getattr(prof, "first_name", "") or getattr(prof.user, "first_name", ""),
        "last_name":   getattr(prof, "last_name", "")  or getattr(prof.user, "last_name", ""),
        "national_id": getattr(prof, "national_id", "") or getattr(prof, "nationalCode", "") or "",
        "birth_date":  _birth_fa(prof),                 # "YYYY/MM/DD" شمسی
        "birth_date_jalali": _birth_fa(prof),           # هم‌نام رایج
        "belt":        belt_display,                    # برای نمایش
        "belt_code":   belt_code,                       # برای منطق
        "club":        club_name,
        "coach":       coach_name,

    }

# -------------------------------------------------
class WeightCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = WeightCategory
        fields = ("id", "name", "gender", "min_weight", "max_weight", "tolerance")

class MatAssignmentSerializer(serializers.ModelSerializer):
    weights = WeightCategorySerializer(many=True, read_only=True)
    class Meta:
        model = MatAssignment
        fields = ("id", "mat_number", "weights")

class CompetitionImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompetitionImage
        fields = ("id", "image")

class CompetitionFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompetitionFile
        fields = ("id", "file")

# -------------------------------------------------
# Competition detail – KYORUGI  (fixed)
# -------------------------------------------------
class KyorugiCompetitionDetailSerializer(serializers.ModelSerializer):
    # نام‌های نمایشی
    age_category_name  = serializers.CharField(source="age_category.name", read_only=True)
    gender_display     = serializers.CharField(source="get_gender_display", read_only=True)
    belt_level_display = serializers.CharField(source="get_belt_level_display", read_only=True)
    style_display      = serializers.CharField(read_only=True)

    # تعهدنامه
    terms_title   = serializers.SerializerMethodField()
    terms_content = serializers.SerializerMethodField()

    # تاریخ‌ها (شمسی)
    registration_start_jalali = serializers.SerializerMethodField()
    registration_end_jalali   = serializers.SerializerMethodField()
    weigh_date_jalali         = serializers.SerializerMethodField()
    draw_date_jalali          = serializers.SerializerMethodField()
    lottery_date_jalali       = serializers.SerializerMethodField()
    competition_date_jalali   = serializers.SerializerMethodField()

    # alias‌ها برای سازگاری فرانت
    weigh_in_date        = serializers.SerializerMethodField()
    weigh_in_date_jalali = serializers.SerializerMethodField()

    # سایر نماها/منطق
    belt_groups_display = serializers.SerializerMethodField()

    # ✅ وضعیت ثبت‌نام
    registration_open_effective = serializers.SerializerMethodField()
    registration_open           = serializers.SerializerMethodField()
    can_register                = serializers.SerializerMethodField()

    # صلاحیت
    user_eligible_self  = serializers.SerializerMethodField()
    allowed_belts       = serializers.SerializerMethodField()
    age_from            = serializers.SerializerMethodField()
    age_to              = serializers.SerializerMethodField()
    eligibility_debug   = serializers.SerializerMethodField()

    # پیوست‌ها و زمین‌ها
    images          = CompetitionImageSerializer(many=True, read_only=True)
    files           = CompetitionFileSerializer(many=True, read_only=True)
    mat_assignments = MatAssignmentSerializer(many=True, read_only=True)

    # براکت
    bracket_ready   = serializers.SerializerMethodField()
    bracket_stats   = serializers.SerializerMethodField()

    # ✅ پروفایل قفل‌شدهٔ کاربر برای نمایش در فرم ثبت‌نام
    me_locked  = serializers.SerializerMethodField()
    my_profile = serializers.SerializerMethodField()  # alias برای سازگاری

    class Meta:
        model = KyorugiCompetition
        fields = [
            "id", "public_id",
            "title", "poster", "entry_fee",
            "age_category_name", "gender_display", "belt_level_display",
            "style_display",
            "city", "address",

            # فیلدهای خام تاریخ
            "registration_start", "registration_end",
            "weigh_date", "draw_date", "competition_date",

            # تاریخ‌های شمسی
            "registration_start_jalali", "registration_end_jalali",
            "weigh_date_jalali", "draw_date_jalali", "lottery_date_jalali", "competition_date_jalali",

            # alias‌ها
            "weigh_in_date", "weigh_in_date_jalali",

            # وضعیت ثبت‌نام
            "registration_manual",
            "registration_open_effective",
            "registration_open",
            "can_register",

            # کمربند/زمین/پیوست
            "belt_groups_display",
            "mat_count",
            "mat_assignments",
            "images", "files",

            # صلاحیت
            "user_eligible_self",
            "allowed_belts",
            "age_from", "age_to",
            "eligibility_debug",

            # تعهدنامه
            "terms_title", "terms_content",

            # براکت
            "bracket_ready", "bracket_stats",

            # 🔹 پروفایل قفل‌شدهٔ کاربر
            "me_locked", "my_profile",
        ]

    # ---------------- Locked profile helpers ----------------
    def _locked_profile_dict(self, prof: UserProfile):
        """پروفایل بازیکن را به ساختار یکنواخت برای فرانت تبدیل می‌کند."""
        if not prof:
            return None

        # تاریخ تولد شمسی
        def _birth_fa(p):
            bd = getattr(p, "birth_date", None)
            if not bd:
                return None
            if isinstance(bd, (_datetime, _date)):
                return _to_jalali_date_str(bd)
            jd = _parse_jalali_str(bd)
            if jd:
                return _j2str(jd)
            g = _to_greg_from_str_jalali(bd)
            return _to_jalali_date_str(g) if g else str(bd)

        # باشگاه
        club_name = ""
        club_obj = getattr(prof, "club", None)
        if isinstance(club_obj, TkdClub):
            club_name = getattr(club_obj, "club_name", "") or ""
        if not club_name and isinstance(getattr(prof, "club_names", None), list):
            club_name = "، ".join([c for c in prof.club_names if c])

        # مربی
        coach_obj = getattr(prof, "coach", None)
        coach_name = ""
        if coach_obj:
            coach_name = f"{getattr(coach_obj, 'first_name', '')} {getattr(coach_obj, 'last_name', '')}".strip()

        # کمربند
        belt_raw  = getattr(prof, "belt_grade", None)
        belt_code = _norm_belt(belt_raw)
        belt_disp = BELT_FA.get(belt_code, belt_raw or None)

        return {
            "first_name":  getattr(prof, "first_name", "") or getattr(getattr(prof, "user", None), "first_name", ""),
            "last_name":   getattr(prof, "last_name", "")  or getattr(getattr(prof, "user", None), "last_name", ""),
            "national_id": getattr(prof, "national_id", "") or getattr(prof, "nationalCode", "") or "",
            "birth_date":  _birth_fa(prof),              # "YYYY/MM/DD"
            "birth_date_jalali": _birth_fa(prof),        # alias رایج
            "belt":        belt_disp,                    # برای نمایش
            "belt_code":   belt_code,                    # برای منطق
            "club":        club_name,
            "coach":       coach_name,
        }

    def _current_player_profile(self):
        req = self.context.get("request")
        user = getattr(req, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None
        prof = getattr(user, "profile", None)
        if prof and getattr(prof, "role", None) == "player":
            return prof
        return UserProfile.objects.filter(user=user, role="player").first()

    def get_me_locked(self, obj):
        return self._locked_profile_dict(self._current_player_profile())

    def get_my_profile(self, obj):
        # alias برای سازگاری با فرانت‌های قدیمی
        return self.get_me_locked(obj)

    # ---------- Terms ----------
    def get_terms_title(self, obj):
        tmpl = getattr(obj, "terms_template", None)
        return tmpl.title if tmpl else None

    def get_terms_content(self, obj):
        tmpl = getattr(obj, "terms_template", None)
        return tmpl.content if tmpl else None

    # ---------- Dates (Jalali) ----------
    def get_registration_start_jalali(self, obj):
        return _to_jalali_date_str(getattr(obj, "registration_start", None))

    def get_registration_end_jalali(self, obj):
        return _to_jalali_date_str(getattr(obj, "registration_end", None))

    def get_weigh_date_jalali(self, obj):
        return _to_jalali_date_str(getattr(obj, "weigh_date", None))

    def get_draw_date_jalali(self, obj):
        return _to_jalali_date_str(getattr(obj, "draw_date", None))

    def get_lottery_date_jalali(self, obj):
        d = getattr(obj, "lottery_date", None) or getattr(obj, "draw_date", None)
        return _to_jalali_date_str(d)

    def get_competition_date_jalali(self, obj):
        return _to_jalali_date_str(getattr(obj, "competition_date", None))

    # ---------- Aliases ----------
    def get_weigh_in_date(self, obj):
        d = getattr(obj, "weigh_date", None) or getattr(obj, "weigh_in_date", None)
        return str(d or "")[:10] if d else None

    def get_weigh_in_date_jalali(self, obj):
        d = getattr(obj, "weigh_date", None) or getattr(obj, "weigh_in_date", None)
        return _to_jalali_date_str(d)

    # ---------- Registration state ----------
    def _compute_effective_open(self, obj):
        manual = getattr(obj, "registration_manual", None)
        if manual is True:
            return True
        if manual is False:
            return False
        today = timezone.localdate()
        rs = _as_local_date(getattr(obj, "registration_start", None))
        re_ = _as_local_date(getattr(obj, "registration_end", None))
        if rs and re_:
            return rs <= today <= re_
        val = getattr(obj, "registration_open_effective", None)
        if isinstance(val, bool):
            return val
        raw2 = getattr(obj, "registration_open", None)
        return bool(raw2)

    def get_registration_open_effective(self, obj):
        val = getattr(obj, "registration_open_effective", None)
        if isinstance(val, bool):
            return val
        return self._compute_effective_open(obj)

    def get_registration_open(self, obj):
        return self.get_registration_open_effective(obj)

    def get_belt_groups_display(self, obj):
        names = list(obj.belt_groups.values_list("label", flat=True))
        return "، ".join([n for n in names if n]) if names else ""

    def get_can_register(self, obj):
        if not self.get_registration_open_effective(obj):
            return False
        today = timezone.localdate()
        rs = _as_local_date(getattr(obj, "registration_start", None))
        re_ = _as_local_date(getattr(obj, "registration_end", None))
        return (rs <= today <= re_) if (rs and re_) else True

    # ---------- Eligibility ----------
    def _get_profile(self, user):
        prof = getattr(user, "profile", None)
        if prof and getattr(prof, "role", None) == "player":
            return prof
        return (
            UserProfile.objects.filter(user=user, role="player").first()
            or UserProfile.objects.filter(user=user).first()
        )

    def _get_player_belt(self, prof):
        return _player_belt_code_from_profile(prof)

    def get_user_eligible_self(self, obj):
        req = self.context.get("request")
        user = getattr(req, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        prof = self._get_profile(user)
        if not prof:
            return False

        rg = _norm_gender(getattr(obj, "gender", None))
        pg = _norm_gender(getattr(prof, "gender", None))
        if rg in (None, "", "both"):
            gender_ok = True
        elif pg:
            gender_ok = (rg == pg)
        else:
            gender_ok = False

        dob_j = _parse_jalali_str(getattr(prof, "birth_date", None))
        from_j = _g2j(getattr(obj.age_category, "from_date", None)) if obj.age_category else None
        to_j   = _g2j(getattr(obj.age_category, "to_date", None)) if obj.age_category else None
        age_ok = True if not (from_j and to_j) else bool(dob_j and (from_j <= dob_j <= to_j))

        allowed = set(_allowed_belts(obj))
        player_belt = self._get_player_belt(prof)
        belt_ok = True if not allowed else bool(player_belt and player_belt in allowed)

        return bool(gender_ok and age_ok and belt_ok)

    def get_allowed_belts(self, obj):
        return _allowed_belts(obj)

    def get_age_from(self, obj):
        return _j2str(_g2j(getattr(obj.age_category, "from_date", None))) if obj.age_category else None

    def get_age_to(self, obj):
        return _j2str(_g2j(getattr(obj.age_category, "to_date", None))) if obj.age_category else None

    def get_eligibility_debug(self, obj):
        req = self.context.get("request")
        user = getattr(req, "user", None)
        today = timezone.localdate()
        in_reg_window = True
        if getattr(obj, "registration_start", None) and getattr(obj, "registration_end", None):
            in_reg_window = obj.registration_start <= today <= obj.registration_end

        data = {
            "registration_open": bool(self.get_registration_open_effective(obj)),
            "in_reg_window": bool(in_reg_window),
            "required_gender": _norm_gender(getattr(obj, "gender", None)),
            "player_gender": None,
            "gender_ok": None,
            "age_from": self.get_age_from(obj),
            "age_to": self.get_age_to(obj),
            "player_dob": None,
            "age_ok": None,
            "allowed_belts": _allowed_belts(obj),
            "player_belt": None,
            "belt_ok": None,
            "profile_role": None,
        }

        if not user or not getattr(user, "is_authenticated", False):
            return data

        prof = self._get_profile(user)
        if not prof:
            return data

        data["profile_role"] = getattr(prof, "role", None)
        data["player_gender"] = _norm_gender(getattr(prof, "gender", None))
        rg, pg = data["required_gender"], data["player_gender"]
        data["gender_ok"] = True if rg in (None, "", "both") else (pg and rg == pg)

        dob_j = _parse_jalali_str(getattr(prof, "birth_date", None))
        data["player_dob"] = _j2str(dob_j) if dob_j else None
        from_j = _g2j(getattr(obj.age_category, "from_date", None)) if obj.age_category else None
        to_j   = _g2j(getattr(obj.age_category, "to_date", None)) if obj.age_category else None
        data["age_ok"] = bool(dob_j and from_j and to_j and (from_j <= dob_j <= to_j)) if (from_j and to_j) else True

        data["player_belt"] = self._get_player_belt(prof)
        allowed = set(data["allowed_belts"])
        data["belt_ok"] = True if not allowed else bool(data["player_belt"] and data["player_belt"] in allowed)
        return data

    # ---------- Bracket ----------
    def get_bracket_ready(self, obj):
        return obj.draws.exists()

    def get_bracket_stats(self, obj):
        base, eligible = _eligible_real_matches_qs(obj)
        return {
            "draws": obj.draws.count(),
            "matches_total": base.count(),  # کل مچ‌ها (اطلاعاتی)
            "real_total": eligible.count(),  # فقط واقعی‌ها
            "real_numbered": eligible.filter(match_number__isnull=False).count(),  # شماره‌دارهای واقعی
        }


# -------------------------------------------------
# Register-self – KYORUGI (بدون Division)
# -------------------------------------------------
def _allowed_belts(obj):
    """از belt_groups یا belt_level قدیمی می‌خوانیم (بدون Division)."""
    allowed = set()
    if obj.belt_groups.exists():
        for g in obj.belt_groups.all().prefetch_related("belts"):
            for b in g.belts.all():
                code = _norm_belt(getattr(b, "name", "") or getattr(b, "label", ""))
                if code:
                    allowed.add(code)
    else:
        if obj.belt_level == "yellow_blue":
            allowed.update({"yellow", "green", "blue"})
        elif obj.belt_level == "red_black":
            allowed.update({"red", "black"})
        else:
            allowed.update({"white", "yellow", "green", "blue", "red", "black"})
    return sorted(list(allowed))

# -------------------------------------------------
# Register-self – KYORUGI  (اجباری شدن coach_code)
# -------------------------------------------------
class CompetitionRegistrationSerializer(serializers.Serializer):
    # ⬅️ coach_code اجباری شد
    coach_code = serializers.CharField(allow_blank=False, required=True)
    declared_weight = serializers.CharField()
    insurance_number = serializers.CharField()
    insurance_issue_date = serializers.CharField()  # YYYY/MM/DD شمسی

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._competition = self.context.get("competition")
        self._request = self.context.get("request")
        self._player = None
        self._coach = None
        self._coach_code = ""
        self._belt_group = None
        self._weight_category = None
        self._issue_date_greg = None
        self._declared_weight_float = None

    def _player_belt_code(self, prof: UserProfile):
        return _player_belt_code_from_profile(prof)

    def validate(self, attrs):
        comp = self._competition
        req = self._request
        if not comp:
            raise serializers.ValidationError({"__all__": "مسابقه یافت نشد."})

        # بازهٔ ثبت‌نام (Date)

        today = timezone.localdate()
        rs = _as_local_date(getattr(comp, "registration_start", None))
        re_ = _as_local_date(getattr(comp, "registration_end", None))
        if rs and today < rs:
            raise serializers.ValidationError({"__all__": "ثبت‌نام هنوز شروع نشده است."})
        if re_ and today > re_:
            raise serializers.ValidationError({"__all__": "مهلت ثبت‌نام به پایان رسیده است."})

        # کاربر/پروفایل بازیکن
        user = getattr(req, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            raise serializers.ValidationError({"__all__": "برای ثبت‌نام باید وارد شوید."})
        # کاربر/پروفایل بازیکن (قبلاً فقط player را می‌گرفت)
        user = getattr(req, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            raise serializers.ValidationError({"__all__": "برای ثبت‌نام باید وارد شوید."})
        
        player = _get_player_like_profile(user)
        if not player:
            raise serializers.ValidationError({"__all__": "پروفایل بازیکن پیدا نشد."})
        
        self._player = player


        # جلوگیری از ثبت‌نام تکراری
        if Enrollment.objects.filter(competition=comp, player=player).exclude(status="canceled").exists():
            raise serializers.ValidationError({"__all__": "برای این مسابقه قبلاً ثبت‌نام کرده‌اید."})

        # تاریخ بیمه (≥ ۷۲ ساعت قبل از برگزاری)
        issue_g = _to_greg_from_str_jalali(attrs.get("insurance_issue_date"))
        if not issue_g:
            raise serializers.ValidationError({"insurance_issue_date": "تاریخ صدور نامعتبر است (مثلاً ۱۴۰۳/۰۵/۲۰)."})
        cd = _as_local_date(getattr(comp, "competition_date", None))
        if cd and issue_g > (cd - timedelta(days=3)):
            raise serializers.ValidationError({"insurance_issue_date": "تاریخ صدور باید حداقل ۷۲ ساعت قبل از برگزاری باشد."})
        self._issue_date_greg = issue_g

        # وزن
        try:
            w = _parse_weight_to_float(attrs.get("declared_weight") or "")
        except Exception:
            raise serializers.ValidationError({"declared_weight": "وزن نامعتبر است."})
        self._declared_weight_float = w

        # ⬅️ کُد مربی: همیشه اجباری + اعتبارسنجی CoachApproval
        coach_code = (attrs.get("coach_code") or "").strip()
        if not coach_code:
            raise serializers.ValidationError({"coach_code": "کد تأیید مربی الزامی است."})
        appr = CoachApproval.objects.filter(
            competition=comp, code=coach_code, is_active=True, terms_accepted=True
        ).select_related("coach").first()
        if not appr:
            raise serializers.ValidationError({"coach_code": "کد مربی معتبر نیست یا فعال نیست."})
        self._coach = appr.coach
        self._coach_code = appr.code

        # گروه کمربندی سازگار — فقط از belt_grade بازیکن
        belt_group = None
        code = self._player_belt_code(player)
        if code:
            belt_group = _find_belt_group_obj(comp, code)
        if comp.belt_groups.exists() and not belt_group:
            raise serializers.ValidationError({"belt_group": "کمربند شما با گروه‌های مسابقه سازگار نیست."})
        self._belt_group = belt_group

        # انتخاب رده وزنی
        chosen = None
        for wc in _collect_comp_weights(comp):
            if _gender_ok_for_wc(comp, getattr(wc, "gender", None)) and _wc_includes(wc, w):
                chosen = wc
                break
        if not chosen:
            raise serializers.ValidationError({"declared_weight": "هیچ رده وزنی متناسب با این وزن در مسابقه یافت نشد."})
        self._weight_category = chosen

        # شماره بیمه
        if not (attrs.get("insurance_number") or "").strip():
            raise serializers.ValidationError({"insurance_number": "شماره بیمه الزامی است."})

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        comp = self._competition
        player = self._player
        coach = self._coach
    
        req = self.context.get("request")
        user = getattr(req, "user", None)
    
        coach_name = f"{getattr(coach, 'first_name', '')} {getattr(coach, 'last_name', '')}".strip() if coach else ""
        club_obj, club_name = _extract_club_profile_and_name(player)
        board_obj = getattr(player, "tkd_board", None)
        board_name = getattr(board_obj, "name", "") or ""
        amount = int(getattr(comp, "entry_fee", 0) or 0)
        
        # 🔒 Guard ریال (entry_fee باید ریالی باشد)
        if amount > 0 and amount < 10_000:
            raise serializers.ValidationError(
                {"entry_fee": "مبلغ ثبت‌نام باید به ریال باشد (entry_fee خیلی کوچک است)."}
            )

    
        # ✅ ایجاد ثبت‌نام «در انتظار پرداخت»
        e = Enrollment.objects.create(
            competition=comp,
            player=player,
            coach=coach,
            created_by=user if (user and getattr(user, "is_authenticated", False)) else None,  # ✅ مهم برای permission
            kind="kyorugi",  # ✅ مهم: جلوگیری از kind=None
    
            coach_name=coach_name,
            coach_approval_code=self._coach_code,
    
            club=club_obj, club_name=club_name,
            board=board_obj, board_name=board_name,
    
            belt_group=self._belt_group,
            weight_category=self._weight_category,
            declared_weight=self._declared_weight_float,
    
            insurance_number=validated_data.get("insurance_number"),
            insurance_issue_date=self._issue_date_greg,
    
            status="pending",     # ✅ دیگر paid نیست
            is_paid=False,
            paid_amount=0,        # یا اگر مدل شما expects amount_due دارد، آن را جدا نگه دارید
            bank_ref_code=None,
        )
    
        # فعلاً لینک پرداخت را اینجا نمی‌سازیم (در view/payment flow)
        self._payment_url = None
        return e


    def to_representation(self, instance: Enrollment):
        return {
            "enrollment_id": instance.id,
            "status": instance.status,
            "paid": instance.is_paid,
            "paid_amount": instance.paid_amount,
            "bank_ref_code": instance.bank_ref_code,
        }


# -------------------------------------------------
# Dashboard – KYORUGI list item
# -------------------------------------------------
class DashboardKyorugiCompetitionSerializer(serializers.ModelSerializer):
    # شناسه برای اسلاگ/URL
    slug = serializers.CharField(source="public_id", read_only=True)

    # نمایش‌های متنی
    age_category_name  = serializers.CharField(source="age_category.name", read_only=True)
    gender_display     = serializers.CharField(source="get_gender_display", read_only=True)
    belt_level_display = serializers.CharField(source="get_belt_level_display", read_only=True)
    style_display      = serializers.CharField(read_only=True)

    # تاریخ‌های شمسی
    registration_start_jalali = serializers.SerializerMethodField()
    registration_end_jalali   = serializers.SerializerMethodField()
    weigh_date_jalali         = serializers.SerializerMethodField()
    draw_date_jalali          = serializers.SerializerMethodField()
    lottery_date_jalali       = serializers.SerializerMethodField()
    competition_date_jalali   = serializers.SerializerMethodField()

    # alias وزن‌کشی
    weigh_in_date        = serializers.SerializerMethodField()
    weigh_in_date_jalali = serializers.SerializerMethodField()

    # وضعیت ثبت‌نام و وضعیت کلی کارت
    registration_open = serializers.SerializerMethodField()
    can_register      = serializers.SerializerMethodField()
    status            = serializers.SerializerMethodField()

    class Meta:
        model = KyorugiCompetition
        fields = [
            "id", "public_id",
            "title", "poster", "entry_fee",
            "age_category_name", "gender_display", "belt_level_display",
            "style_display",
            "city", "slug",

            # وضعیت ثبت‌نام (محاسبه‌شده با override دستی)
            "registration_open",

            # تاریخ‌های میلادی خام (برای سازگاری فرانت)
            "registration_start", "registration_end",
            "weigh_date", "draw_date", "competition_date",

            # تاریخ‌های شمسی
            "registration_start_jalali", "registration_end_jalali",
            "weigh_date_jalali", "draw_date_jalali", "lottery_date_jalali", "competition_date_jalali",

            # alias‌های وزن‌کشی
            "weigh_in_date", "weigh_in_date_jalali",

            # وضعیت کارت
            "can_register", "status",
        ]

    # --- جلالی‌ها ---
    def get_registration_start_jalali(self, obj):
        return _to_jalali_date_str(obj.registration_start)

    def get_registration_end_jalali(self, obj):
        return _to_jalali_date_str(obj.registration_end)

    def get_weigh_date_jalali(self, obj):
        return _to_jalali_date_str(getattr(obj, "weigh_date", None))

    def get_draw_date_jalali(self, obj):
        d = getattr(obj, "draw_date", None) or getattr(obj, "lottery_date", None)
        return _to_jalali_date_str(d)

    def get_lottery_date_jalali(self, obj):
        d = getattr(obj, "lottery_date", None) or getattr(obj, "draw_date", None)
        return _to_jalali_date_str(d)

    def get_competition_date_jalali(self, obj):
        return _to_jalali_date_str(obj.competition_date)

    # --- alias وزن‌کشی برای فرانت ---
    def get_weigh_in_date(self, obj):
        d = getattr(obj, "weigh_in_date", None) or getattr(obj, "weigh_date", None)
        return str(d or "")[:10] if d else None

    def get_weigh_in_date_jalali(self, obj):
        d = getattr(obj, "weigh_in_date", None) or getattr(obj, "weigh_date", None)
        return _to_jalali_date_str(d)

    # --- ثبت‌نام ---
    def get_registration_open(self, obj):
        # به‌جای اتکا به فیلد قدیمی، از مقدار موثر مدل استفاده کن
        return bool(getattr(obj, "registration_open_effective", False))

    def get_can_register(self, obj):
        if not self.get_registration_open(obj):
            return False
        today = timezone.localdate()
        rs = _as_local_date(getattr(obj, "registration_start", None))
        re_ = _as_local_date(getattr(obj, "registration_end", None))
        return (rs <= today <= re_) if (rs and re_) else True

    # --- وضعیت کلی مسابقه برای کارت ---
    def get_status(self, obj):
        cd = getattr(obj, "competition_date", None)
        if not cd:
            return "unknown"
        today = timezone.localdate()
        if today < cd:
            return "upcoming"
        if today == cd:
            return "today"
        return "finished"

# -------------------------------------------------
# Enrollment card
# -------------------------------------------------

def _abs_media(request, f):
    try:
        if not f:
            return None
        url = getattr(f, "url", None) or str(f)
        if not url:
            return None
        return request.build_absolute_uri(url) if request else url
    except Exception:
        return None

class EnrollmentCardSerializer(serializers.ModelSerializer):
    competition_title = serializers.CharField(source="competition.title", read_only=True)
    competition_date_jalali = serializers.SerializerMethodField()

    first_name = serializers.CharField(source="player.first_name", read_only=True)
    last_name  = serializers.CharField(source="player.last_name", read_only=True)
    birth_date = serializers.SerializerMethodField()
    photo      = serializers.SerializerMethodField()

    declared_weight = serializers.FloatField(read_only=True)

    weight_name  = serializers.SerializerMethodField()
    belt       = serializers.SerializerMethodField()
    belt_group = serializers.SerializerMethodField()

    insurance_number = serializers.CharField(read_only=True)
    insurance_issue_date_jalali = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment
        fields = [
            "competition_title", "competition_date_jalali",
            "first_name", "last_name", "birth_date", "photo",
            "declared_weight",
            "weight_name",
            "belt", "belt_group",
            "insurance_number", "insurance_issue_date_jalali",
            "coach_name", "club_name",
        ]

    def get_competition_date_jalali(self, obj):
        d = getattr(obj.competition, "competition_date", None) or getattr(obj.competition, "start_date", None)
        return _to_jalali_date_str(d)

    def get_birth_date(self, obj):
        bd = getattr(obj.player, "birth_date", None)
        if not bd:
            return None
        if isinstance(bd, (_datetime, _date)):
            return _to_jalali_date_str(bd)
        jd = _parse_jalali_str(bd)
        if jd:
            return _j2str(jd)
        g = _to_greg_from_str_jalali(bd)
        return _to_jalali_date_str(g) if g else str(bd)

    def get_photo(self, obj):
        request = self.context.get("request")
        prof = obj.player
        cand = getattr(prof, "profile_image", None)
        if not cand or (hasattr(cand, "name") and not getattr(cand, "name", "")):
            for alt in ("avatar", "photo", "image"):
                v = getattr(prof, alt, None)
                if v and (not hasattr(v, "name") or getattr(v, "name", "")):
                    cand = v
                    break
        return _abs_media(request, cand)

    def _pick_wc(self, obj):
        if getattr(obj, "weight_category", None):
            return obj.weight_category
        declared = getattr(obj, "declared_weight", None)
        if not declared:
            return None
        for wc in _collect_comp_weights(obj.competition):
            if _gender_ok_for_wc(obj.competition, getattr(wc, "gender", None)) and _wc_includes(wc, declared):
                return wc
        return None

    def get_weight_name(self, obj):
        wc = self._pick_wc(obj)
        return getattr(wc, "name", None) if wc else None

    def get_belt(self, obj):
        raw = getattr(obj.player, "belt_grade", None)
        code = _norm_belt(raw)
        return BELT_FA.get(code, raw or None)

    def get_belt_group(self, obj):
        if getattr(obj, "belt_group", None):
            return getattr(obj.belt_group, "label", None)
        code = _norm_belt(getattr(obj.player, "belt_grade", None))
        return _find_belt_group_label(obj.competition, code)

    def get_insurance_issue_date_jalali(self, obj):
        return _to_jalali_date_str(obj.insurance_issue_date)


class MyEnrollmentStatusSerializer(serializers.Serializer):
    enrollment_id = serializers.IntegerField()
    status = serializers.CharField()
    can_show_card = serializers.SerializerMethodField()

    def get_can_show_card(self, obj: Enrollment):
        return _can_show_card(getattr(obj, "status", ""), getattr(obj, "is_paid", False))

    def to_representation(self, obj: Enrollment):
        return {
            "enrollment_id": obj.id,
            "status": obj.status,
            "can_show_card": self.get_can_show_card(obj),
        }

# -------------------------------------------------
# Bracket API
# -------------------------------------------------
class MatchSlimSerializer(serializers.ModelSerializer):
    player_a_name = serializers.SerializerMethodField()
    player_b_name = serializers.SerializerMethodField()
    winner_name   = serializers.SerializerMethodField()
    class Meta:
        model = Match
        fields = ("id","round_no","slot_a","slot_b","is_bye","mat_no","match_number",
                  "player_a_name","player_b_name","winner_name")
    def _nm(self, u): return f"{getattr(u,'first_name','')} {getattr(u,'last_name','')}".strip() if u else None
    def get_player_a_name(self, obj): return self._nm(obj.player_a)
    def get_player_b_name(self, obj): return self._nm(obj.player_b)
    def get_winner_name(self, obj):   return self._nm(obj.winner)

class DrawWithMatchesSerializer(serializers.ModelSerializer):
    age_category_name = serializers.CharField(source="age_category.name", read_only=True)
    belt_group_label  = serializers.CharField(source="belt_group.label", read_only=True)
    weight_name       = serializers.CharField(source="weight_category.name", read_only=True)
    gender_display    = serializers.SerializerMethodField()
    matches           = MatchSlimSerializer(many=True, read_only=True)
    class Meta:
        model = Draw
        fields = ("id","gender","gender_display","age_category_name","belt_group_label",
                  "weight_name","size","matches")
    def get_gender_display(self, obj):
        return "آقایان" if obj.gender=="male" else ("بانوان" if obj.gender=="female" else obj.gender)

def _bracket_ready_for(comp):
    return bool(getattr(comp, "is_bracket_published", True)) and comp.draws.exists()


def _bracket_stats_for(comp):
    base, eligible = _eligible_real_matches_qs(comp)
    return {
        "draws": comp.draws.count(),
        "matches_total": base.count(),
        "real_total": eligible.count(),
        "real_numbered": eligible.filter(match_number__isnull=False).count(),
    }

class KyorugiBracketSerializer(serializers.Serializer):
    def to_representation(self, comp):
        from .models import Match, Draw

        draws_qs = (Draw.objects.filter(competition=comp).select_related("age_category", "belt_group", "weight_category")
                   .prefetch_related("matches", "matches__player_a", "matches__player_b", "matches__winner")
                     .order_by("weight_category__min_weight", "id"))

        draws = DrawWithMatchesSerializer(draws_qs, many=True, context=self.context).data

        by_mat = []
        mat_count = comp.mat_count or 1
        for m in range(1, mat_count + 1):
            qs = (
                Match.objects.filter(draw__competition=comp, mat_no=m)
                .order_by("match_number", "id")
                .select_related("player_a", "player_b", "winner")
            )
            by_mat.append({
                "mat_no": m,
                "count": qs.count(),
                "matches": MatchSlimSerializer(qs, many=True, context=self.context).data,
            })

        return {
            "competition": {
                "id": comp.id,
                "public_id": comp.public_id,
                "title": comp.title,
                "mat_count": mat_count,
                "bracket_ready": _bracket_ready_for(comp),
                "bracket_stats": _bracket_stats_for(comp),
            },
            "draws": draws,
            "by_mat": by_mat,
        }

# -------------------------------------------------
# Seminars
# -------------------------------------------------
def _to_jalali_str(d):
    if not d:
        return None
    if isinstance(d, _datetime):
        d = d.date()
    try:
        jd = jdatetime.date.fromgregorian(date=d)
        return jd.strftime("%Y/%m/%d")
    except Exception:
        return None

def _abs_url(request, url_or_field):
    if not url_or_field:
        return None
    try:
        return request.build_absolute_uri(url_or_field.url if hasattr(url_or_field, "url") else url_or_field)
    except Exception:
        return None

def _normalize_iran_mobile(s: str):
    if not s:
        return s
    digits = "".join(ch for ch in s if ch.isdigit())
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98"):
        digits = digits[2:]
    elif digits.startswith("+98"):
        digits = digits[3:]
    if len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits
    return digits

class SeminarSerializer(serializers.ModelSerializer):
    registration_start_jalali = serializers.SerializerMethodField(read_only=True)
    registration_end_jalali   = serializers.SerializerMethodField(read_only=True)
    event_date_jalali         = serializers.SerializerMethodField(read_only=True)
    poster_url                = serializers.SerializerMethodField(read_only=True)
    is_open_for_registration  = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Seminar
        fields = [
            'id','public_id','title','poster','poster_url','description',
            'registration_start','registration_start_jalali',
            'registration_end','registration_end_jalali',
            'event_date','event_date_jalali',
            'location','fee','allowed_roles','is_open_for_registration','created_at'
        ]
        read_only_fields = ['id','public_id','created_at',
                            'registration_start_jalali','registration_end_jalali',
                            'event_date_jalali','poster_url','is_open_for_registration']

    def get_registration_start_jalali(self, obj): return _to_jalali_str(obj.registration_start)
    def get_registration_end_jalali(self, obj):   return _to_jalali_str(obj.registration_end)
    def get_event_date_jalali(self, obj):         return _to_jalali_str(obj.event_date)
    def get_poster_url(self, obj):
        req = self.context.get('request')
        return _abs_url(req, obj.poster) if req else (obj.poster.url if getattr(obj.poster, "url", None) else None)
    def get_is_open_for_registration(self, obj):
        # مدل شما property دارد:
        return obj.registration_open

class SeminarRegistrationSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    seminar_public_id = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = SeminarRegistration
        fields = [
            'id','seminar','seminar_public_id','user','roles','phone','note',
            'is_paid','paid_amount','paid_at','created_at'
        ]
        read_only_fields = ['id','is_paid','paid_amount','paid_at','created_at']

    def _resolve_seminar(self, attrs):
        seminar = attrs.get('seminar')
        if seminar:
            return seminar
        public_id = self.initial_data.get('seminar_public_id') or attrs.get('seminar_public_id')
        if public_id:
            try:
                return Seminar.objects.get(public_id=public_id)
            except Seminar.DoesNotExist:
                raise serializers.ValidationError({"seminar_public_id": "سمینار با این شناسه یافت نشد."})
        raise serializers.ValidationError({"seminar": "سمینار مشخص نشده است."})

    def validate(self, attrs):
        request = self.context.get('request')
        user = attrs.get('user') or (request.user if request and getattr(request, "user", None) and request.user.is_authenticated else None)
        if not user or not user.is_authenticated:
            raise serializers.ValidationError({"user": "برای ثبت‌نام باید وارد حساب شوید."})

        seminar = self._resolve_seminar(attrs)
        attrs['seminar'] = seminar

        today = timezone.localdate()
        if not (seminar.registration_start <= today <= seminar.registration_end):
            raise serializers.ValidationError({"seminar": "ثبت‌نام این سمینار فعال نیست یا خارج از بازه است."})

        roles = attrs.get('roles') or []
        if not isinstance(roles, (list, tuple)):
            raise serializers.ValidationError({"roles": "فرمت roles باید آرایه باشد."})
        roles = list(roles)

        allowed = seminar.allowed_roles or []
        if allowed:
            if not roles:
                raise serializers.ValidationError({"roles": "برای این سمینار انتخاب نقش الزامی است."})
            if not set(roles).issubset(set(allowed)):
                raise serializers.ValidationError({"roles": "یک یا چند نقش انتخاب‌شده مجاز نیستند."})

        attrs['roles'] = roles

        phone = attrs.get('phone')
        if not phone:
            prof = getattr(user, "profile", None)
            phone = getattr(prof, "phone", None) if prof else None

        phone_norm = _normalize_iran_mobile(phone) if phone else None
        if not phone_norm:
            raise serializers.ValidationError({"phone": "شماره موبایل الزامی است."})
        if not (len(phone_norm) == 11 and phone_norm.startswith("09")):
            raise serializers.ValidationError({"phone": "شماره موبایل نامعتبر است. نمونه صحیح: 09123456789"})
        attrs['phone'] = phone_norm

        exists = SeminarRegistration.objects.filter(seminar=seminar, user=user).exists()
        if exists:
            raise serializers.ValidationError({"seminar": "شما قبلاً در این سمینار ثبت‌نام کرده‌اید."})

        return attrs

    def create(self, validated_data):
        reg = super().create(validated_data)
        try:
            fee = int(getattr(reg.seminar, "fee", 0) or 0)

            # 🔒 Guard ریال
            if fee > 0 and fee < 10_000:
                raise serializers.ValidationError(
                    {"fee": "مبلغ سمینار باید به ریال باشد (fee خیلی کوچک است)."}
                )

            # بدون درگاه: هر مبلغی بود، paid کن
            if fee >= 0:
                if hasattr(reg, "mark_paid"):
                    reg.mark_paid(amount=fee)
                else:
                    reg.is_paid = True
                    reg.paid_amount = fee
                    reg.paid_at = timezone.now()
                    reg.save(update_fields=["is_paid", "paid_amount", "paid_at"])
        except AttributeError:
            pass
        return reg

class SeminarCardSerializer(serializers.ModelSerializer):
    poster_url = serializers.SerializerMethodField()
    event_date_jalali = serializers.ReadOnlyField()
    registration_start_jalali = serializers.ReadOnlyField()
    registration_end_jalali = serializers.ReadOnlyField()
    registration_open = serializers.SerializerMethodField()
    visible_for_role = serializers.SerializerMethodField()

    class Meta:
        model = Seminar
        fields = [
            "public_id", "title", "location", "fee",
            "event_date", "event_date_jalali",
            "registration_start_jalali", "registration_end_jalali",
            "poster_url", "allowed_roles",
            "registration_open", "visible_for_role",
        ]

    def get_poster_url(self, obj: Seminar):
        if not obj.poster:
            return None
        try:
            url = obj.poster.url
        except Exception:
            url = default_storage.url(obj.poster.name)
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    def get_registration_open(self, obj: Seminar):
        return obj.registration_open

    def get_visible_for_role(self, obj: Seminar):
        role = (self.context.get("role") or "").strip()
        if role in ("club", "heyat"):
            return True
        if not obj.allowed_roles:
            return True
        return role in obj.allowed_roles

# -------------------------------------------------
# Enrollment (لیست سبک)
# -------------------------------------------------
class EnrollmentLiteSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source="player.first_name", read_only=True)
    last_name  = serializers.CharField(source="player.last_name", read_only=True)
    belt_group_label = serializers.CharField(source="belt_group.label", read_only=True)
    age_category_name = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment
        fields = ["id","first_name","last_name","belt_group_label","age_category_name","is_paid","paid_amount"]

    def get_age_category_name(self, obj):
        comp = obj.competition
        return getattr(getattr(comp, "age_category", None), "name", None)

# -------------------------------------------------
# Dashboard – Any competition (MatchCard)
# -------------------------------------------------
class DashboardAnyCompetitionSerializer(serializers.Serializer):
    public_id = serializers.CharField()
    title = serializers.CharField()
    style_display = serializers.CharField()
    poster = serializers.SerializerMethodField()
    gender_display = serializers.CharField(allow_null=True)

    # قبلی‌ها
    age_category_name = serializers.CharField(allow_null=True)
    belt_level_display = serializers.CharField(allow_null=True)
    registration_start = serializers.CharField(allow_null=True)
    registration_end = serializers.CharField(allow_null=True)
    competition_date = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()

    # کارت: مبلغ و شهر (آدرس عمداً None)
    entry_fee = serializers.IntegerField(required=False)
    city = serializers.CharField(required=False, allow_null=True)
    address = serializers.CharField(required=False, allow_null=True)

    # تاریخ‌های شمسی
    registration_start_jalali = serializers.SerializerMethodField()
    registration_end_jalali   = serializers.SerializerMethodField()
    competition_date_jalali   = serializers.SerializerMethodField()

    # فقط کیوروگی
    weigh_date = serializers.CharField(required=False, allow_null=True)
    weigh_date_jalali = serializers.SerializerMethodField()
    weigh_in_date = serializers.CharField(required=False, allow_null=True)
    weigh_in_date_jalali = serializers.SerializerMethodField()

    # فقط پومسه
    age_group_display = serializers.CharField(required=False, allow_null=True)
    age_categories_display = serializers.SerializerMethodField()
    registration_open = serializers.SerializerMethodField()

    def get_registration_open(self, obj):
        return bool(getattr(obj, "registration_open_effective", False))

    # ------------ helpers ------------
    def _abs_url(self, f):
        try:
            if not f:
                return None
            url = getattr(f, "url", None) or (str(f) if isinstance(f, str) else None)
            req = self.context.get("request")
            if not url:
                return None
            return req.build_absolute_uri(url) if (req and not str(url).startswith("http")) else url
        except Exception:
            return None

    def get_poster(self, obj):
        return self._abs_url(getattr(obj, "poster", None))

    def get_registration_start_jalali(self, obj):
        return _to_jalali_date_str_safe(getattr(obj, "registration_start", None))

    def get_registration_end_jalali(self, obj):
        return _to_jalali_date_str_safe(getattr(obj, "registration_end", None))

    def get_competition_date_jalali(self, obj):
        d = getattr(obj, "competition_date", None) or getattr(obj, "start_date", None)
        return _to_jalali_date_str_safe(d)

    def get_weigh_date_jalali(self, obj):
        d = getattr(obj, "weigh_date", None) or getattr(obj, "weigh_in_date", None)
        return _to_jalali_date_str_safe(d)

    def get_weigh_in_date_jalali(self, obj):
        d = getattr(obj, "weigh_in_date", None) or getattr(obj, "weigh_date", None)
        return _to_jalali_date_str_safe(d)

    def get_age_categories_display(self, obj):
        try:
            ags = getattr(obj, "age_categories", None)
            if ags is not None:
                names = [_name_like(x) for x in ags.all()]
                names = [n for n in names if n]
                if names:
                    return "، ".join(names)
        except Exception:
            pass
        ac = getattr(obj, "age_category", None)
        return _name_like(ac) if ac else None

    # ------------ main ------------
    def to_representation(self, obj):
        is_ky = isinstance(obj, KyorugiCompetition)
        is_po = isinstance(obj, PoomsaeCompetition)

        # مشترک
        data = {
            "public_id": getattr(obj, "public_id", None),
            "style_display": getattr(obj, "style_display", None),
            "poster": self.get_poster(obj),
            "gender_display": None,
            "created_at": getattr(obj, "created_at", None),

            "entry_fee": getattr(obj, "entry_fee", None),
            "city": getattr(obj, "city", None) or getattr(obj, "location_city", None),
            "address": None,  # فقط شهر

            "registration_start": None,
            "registration_end": None,
            "competition_date": None,

            "registration_start_jalali": self.get_registration_start_jalali(obj),
            "registration_end_jalali":   self.get_registration_end_jalali(obj),
            "competition_date_jalali":   self.get_competition_date_jalali(obj),
        }

        try:
            data["gender_display"] = obj.get_gender_display() or None
        except Exception:
            pass

        if is_ky:
            rs = getattr(obj, "registration_start", None)
            re = getattr(obj, "registration_end", None)
            cd = getattr(obj, "competition_date", None)
            wd = getattr(obj, "weigh_date", None) or getattr(obj, "weigh_in_date", None)

            data.update({
                "title": getattr(obj, "title", None),
                "age_category_name": getattr(getattr(obj, "age_category", None), "name", None),
                "belt_level_display": getattr(obj, "get_belt_level_display", lambda: None)(),

                "registration_start": str(rs or "")[:10],
                "registration_end":   str(re or "")[:10],
                "competition_date":   str(cd or "")[:10],

                "weigh_date":           str(wd or "")[:10] if wd else None,
                "weigh_date_jalali":    self.get_weigh_date_jalali(obj),
                "weigh_in_date":        str(wd or "")[:10] if wd else None,
                "weigh_in_date_jalali": self.get_weigh_in_date_jalali(obj),

                "age_group_display": None,
                "age_categories_display": None,
            })
            return data

        if is_po:
            rs = getattr(obj, "registration_start", None)
            re = getattr(obj, "registration_end", None)
            cd = getattr(obj, "competition_date", None) or getattr(obj, "start_date", None)

            ag_disp = _poomsae_age_group_display(obj)

            data.update({
                "title": getattr(obj, "name", None) or getattr(obj, "title", None),

                "age_category_name": getattr(getattr(obj, "age_category", None), "name", None),
                "age_categories_display": self.get_age_categories_display(obj),
                "age_group_display": ag_disp,

                "belt_level_display": getattr(obj, "get_belt_level_display", lambda: None)(),

                "registration_start": str(rs or "")[:10] if rs else None,
                "registration_end":   str(re or "")[:10] if re else None,
                "competition_date":   str(cd or "")[:10] if cd else None,

                "weigh_date": None,
                "weigh_date_jalali": None,
                "weigh_in_date": None,
                "weigh_in_date_jalali": None,
            })
            return data

        # fallback
        data["title"] = getattr(obj, "title", None) or getattr(obj, "name", None) or "—"
        return data

# -------------------------------------------------
# PoomsaeCompetition – detail
# -------------------------------------------------
class PoomsaeImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PoomsaeImage
        fields = ["image"]  # UI به key=image نگاه می‌کند

class PoomsaeFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = PoomsaeFile
        fields = ["file"]   # UI به key=file نگاه می‌کند


class PoomsaeCompetitionDetailSerializer(serializers.ModelSerializer):
    # هماهنگ با کیوروگی
    title = serializers.CharField(source="name")
    gender_display = serializers.CharField(source="get_gender_display", read_only=True)

    registration_open = serializers.SerializerMethodField()
    registration_open_effective = serializers.SerializerMethodField()  # ← اضافه
    team_registration_open = serializers.SerializerMethodField()  # ←
    registration_start = serializers.DateField(read_only=True, required=False, allow_null=True)
    registration_end = serializers.DateField(read_only=True, required=False, allow_null=True)


    # تاریخ‌های جلالی
    registration_start_jalali = serializers.SerializerMethodField()
    registration_end_jalali   = serializers.SerializerMethodField()
    competition_date_jalali   = serializers.SerializerMethodField()

    belt_groups_display = serializers.SerializerMethodField()
    age_category_name   = serializers.SerializerMethodField()

    # فیلدهای صلاحیت
    can_register       = serializers.SerializerMethodField()
    allowed_belts      = serializers.SerializerMethodField()
    user_eligible_self = serializers.SerializerMethodField()
    age_from           = serializers.SerializerMethodField()
    age_to             = serializers.SerializerMethodField()
    eligibility_debug  = serializers.SerializerMethodField()

    # پیوست‌ها
    images    = serializers.SerializerMethodField()
    files     = serializers.SerializerMethodField()
    gallery   = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    # ✅ پروفایل قفل‌شدهٔ کاربر برای نمایش در فرم (هماهنگ با فرانت)
    me_locked  = serializers.SerializerMethodField()
    my_profile = serializers.SerializerMethodField()  # alias

    class Meta:
        model = PoomsaeCompetition
        fields = [
            "public_id", "title", "poster", "entry_fee",
            "gender", "gender_display", "city", "address",
            "registration_open", "registration_open_effective",
            "registration_start", "registration_end",
            "registration_start_jalali", "registration_end_jalali",
            "draw_date", "competition_date", "competition_date_jalali",
            "belt_level", "belt_groups_display", "age_category_name",
            "terms_text","team_registration_open",

            "can_register", "allowed_belts", "user_eligible_self",
            "age_from", "age_to", "eligibility_debug",

            # پیوست‌ها
            "images", "files", "gallery", "documents",

            # 🔹 پروفایل قفل‌شدهٔ کاربر
            "me_locked", "my_profile",
        ]

    # ---------------- Locked profile helpers ----------------
    def _locked_profile_dict(self, prof: UserProfile):
        """پروفایل بازیکن را به ساختار یکنواخت برای فرانت تبدیل می‌کند."""
        if not prof:
            return None

        # تاریخ تولد شمسی
        def _birth_fa(p):
            bd = getattr(p, "birth_date", None)
            if not bd:
                return None
            if isinstance(bd, (_datetime, _date)):
                return _to_jalali_date_str(bd)
            jd = _parse_jalali_str(bd)
            if jd:
                return _j2str(jd)
            g = _to_greg_from_str_jalali(bd)
            return _to_jalali_date_str(g) if g else str(bd)

        # باشگاه
        club_name = ""
        club_obj = getattr(prof, "club", None)
        if isinstance(club_obj, TkdClub):
            club_name = getattr(club_obj, "club_name", "") or ""
        if not club_name and isinstance(getattr(prof, "club_names", None), list):
            club_name = "، ".join([c for c in prof.club_names if c])

        # مربی
        coach_obj = getattr(prof, "coach", None)
        coach_name = ""
        if coach_obj:
            coach_name = f"{getattr(coach_obj, 'first_name', '')} {getattr(coach_obj, 'last_name', '')}".strip()

        # کمربند
        belt_raw  = getattr(prof, "belt_grade", None)
        belt_code = _player_belt_code_from_profile(prof)  # از هلسپر بالاسری‌ات
        belt_disp = BELT_FA.get(belt_code, belt_raw or None)

        return {
            "first_name":  getattr(prof, "first_name", "") or getattr(getattr(prof, "user", None), "first_name", ""),
            "last_name":   getattr(prof, "last_name", "")  or getattr(getattr(prof, "user", None), "last_name", ""),
            "national_id": (
                 getattr(prof, "national_id", "")
                 or getattr(prof, "nationalID", "")
                 or getattr(prof, "national_code", "")
                 or getattr(prof, "nationalCode", "")
                 or getattr(prof, "code_melli", "")
                 or getattr(prof, "melli_code", "")
             ),
            "birth_date":  _birth_fa(prof),
            "birth_date_jalali": _birth_fa(prof),  # alias
            "belt":        belt_disp,
            "belt_code":   belt_code,
            "club":        club_name,
            "coach":       coach_name,
        }

    def _current_player_profile(self):
        req = self.context.get("request")
        user = getattr(req, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None
        prof = getattr(user, "profile", None)
        if prof and getattr(prof, "role", None) == "player":
            return prof
        return UserProfile.objects.filter(user=user, role="player").first()

    def get_me_locked(self, obj):
        return self._locked_profile_dict(self._current_player_profile())

    def get_my_profile(self, obj):
        # alias برای سازگاری
        return self.get_me_locked(obj)

    # ---------- گالری/فایل‌ها ----------
    def get_gallery(self, obj):
        return PoomsaeImageSerializer(obj.images.all(), many=True, context=self.context).data

    def get_documents(self, obj):
        return PoomsaeFileSerializer(obj.files.all(), many=True, context=self.context).data

    def _collect_related_media(self, obj, rel_candidates, file_fields):
        out = []
        for rel_name in rel_candidates:
            if not hasattr(obj, rel_name):
                continue
            try:
                qs = getattr(obj, rel_name).all()
            except Exception:
                continue
            for it in qs:
                url = None
                for ff in file_fields:
                    v = getattr(it, ff, None)
                    if v:
                        try:
                            url = v.url
                        except Exception:
                            url = v
                        break
                if url:
                    item = {"url": url}
                    if "image" in file_fields: item["image"] = url
                    if "file" in file_fields:  item["file"]  = url
                    for extra in ("name", "caption", "title"):
                        val = getattr(it, extra, None)
                        if val: item[extra] = val
                    out.append(item)
        return out

    def get_images(self, obj):
        return self._collect_related_media(
            obj,
            rel_candidates=("images", "gallery", "poomsaeimage_set", "photos", "pictures"),
            file_fields=("image", "file", "url", "path"),
        )

    def get_files(self, obj):
        return self._collect_related_media(
            obj,
            rel_candidates=("files", "documents", "poomsaedocument_set", "attachments"),
            file_fields=("file", "document", "url", "path"),
        )

    # --- registration / dates ---
    def get_registration_open(self, obj):
        return obj.registration_open_effective

    def get_registration_open_effective(self, obj):

        return obj.registration_open_effective

    def get_team_registration_open(self, obj):

        return False  # فعلاً تیمی بسته
    def get_registration_start_jalali(self, obj):
        return _to_jalali_date_str(getattr(obj, "registration_start", None))

    def get_registration_end_jalali(self, obj):
        return _to_jalali_date_str(getattr(obj, "registration_end", None))

    def get_competition_date_jalali(self, obj):
        return _to_jalali_date_str(getattr(obj, "competition_date", None) or getattr(obj, "start_date", None))

    def get_belt_groups_display(self, obj):
        labels = list(obj.belt_groups.values_list("label", flat=True))
        return "، ".join([l for l in labels if l])

    def get_age_category_name(self, obj):
        return getattr(obj.age_category, "name", None)

    def get_can_register(self, obj):
        return obj.registration_open_effective

    # --- eligibility parity with Kyorugi ---
    def _get_profile(self, user):
        prof = getattr(user, "profile", None)
        if prof and getattr(prof, "role", None) == "player":
            return prof
        return (
            UserProfile.objects.filter(user=user, role="player").first()
            or UserProfile.objects.filter(user=user).first()
        )

    def _get_player_belt(self, prof):
        return _player_belt_code_from_profile(prof)

    def get_allowed_belts(self, obj):
        return _allowed_belts(obj)

    def get_age_from(self, obj):
        return _j2str(_g2j(getattr(obj.age_category, "from_date", None))) if obj.age_category else None

    def get_age_to(self, obj):
        return _j2str(_g2j(getattr(obj.age_category, "to_date", None))) if obj.age_category else None

    def get_user_eligible_self(self, obj):
        req = self.context.get("request")
        user = getattr(req, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        prof = self._get_profile(user)
        if not prof:
            return False

        rg = _norm_gender(getattr(obj, "gender", None))
        pg = _norm_gender(getattr(prof, "gender", None))
        gender_ok = True if rg in (None, "", "both") else (pg and rg == pg)

        dob_j = _parse_jalali_str(getattr(prof, "birth_date", None))
        wins = _poomsae_age_windows(obj)
        age_ok = bool(dob_j and any(fr and to and (fr <= dob_j <= to) for fr, to in wins)) if wins else True

        allowed = set(self.get_allowed_belts(obj))
        player_belt = self._get_player_belt(prof)
        belt_ok = True if not allowed else bool(player_belt and player_belt in allowed)

        return bool(gender_ok and age_ok and belt_ok)

    def get_eligibility_debug(self, obj):
        req = self.context.get("request")
        user = getattr(req, "user", None)

        today = timezone.localdate()
        rs = _as_local_date(getattr(obj, "registration_start", None))
        re_ = _as_local_date(getattr(obj, "registration_end", None))
        in_reg_window = bool(rs and re_ and (rs <= today <= re_))


        wins = _poomsae_age_windows(obj)
        data = {
            "registration_open": bool(self.get_registration_open(obj)),
            "in_reg_window": bool(in_reg_window),
            "required_gender": _norm_gender(getattr(obj, "gender", None)),
            "player_gender": None,
            "gender_ok": None,
            "age_from": self.get_age_from(obj),
            "age_to": self.get_age_to(obj),
            "age_windows": [f"{_j2str(fr)}–{_j2str(to)}" for fr, to in wins if fr and to] or None,
            "player_dob": None,
            "age_ok": None,
            "allowed_belts": self.get_allowed_belts(obj),
            "player_belt": None,
            "belt_ok": None,
            "profile_role": None,
        }

        if not user or not getattr(user, "is_authenticated", False):
            return data

        prof = self._get_profile(user)
        if not prof:
            return data

        data["profile_role"] = getattr(prof, "role", None)
        data["player_gender"] = _norm_gender(getattr(prof, "gender", None))
        rg, pg = data["required_gender"], data["player_gender"]
        data["gender_ok"] = True if rg in (None, "", "both") else (pg and rg == pg)

        dob_j = _parse_jalali_str(getattr(prof, "birth_date", None))
        data["player_dob"] = _j2str(dob_j) if dob_j else None
        data["age_ok"] = (bool(dob_j and any(fr and to and (fr <= dob_j <= to) for fr, to in wins))
                          if wins else True)

        data["player_belt"] = self._get_player_belt(prof)
        allowed = set(data["allowed_belts"])
        data["belt_ok"] = True if not allowed else bool(data["player_belt"] and data["player_belt"] in allowed)
        return data


# -------------------------------------------------
# Register-self – POOMSAE  (اجباری شدن coach_code)
# -------------------------------------------------
class PoomsaeRegistrationSerializer(serializers.Serializer):
    coach_code = serializers.CharField(allow_blank=False, required=True)
    poomsae_type = serializers.ChoiceField(choices=PoomsaeEnrollment.POOMSAE_TYPE_CHOICES)  # ← این
    insurance_number = serializers.CharField()
    insurance_issue_date = serializers.CharField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._competition = self.context.get("competition")
        self._request = self.context.get("request")
        self._player = None
        self._coach = None
        self._coach_code = ""
        self._belt_group = None
        self._age_category = None
        self._issue_date_greg = None

    def _player_belt_code(self, prof: UserProfile):
        return _player_belt_code_from_profile(prof)

    def _resolve_age_category_for_player(self, comp, player)-> Optional[AgeCategory]:
        """از M2M age_categories یا FK age_category بهترین رده سنی مطابق DOB بازیکن را بده."""
        dob_j = _parse_jalali_str(getattr(player, "birth_date", None))
        if not dob_j:
            return None
        ags = list(comp.age_categories.all()) if hasattr(comp, "age_categories") else []
        if not ags and getattr(comp, "age_category", None):
            ags = [comp.age_category]
        for ac in ags:
            fr = _g2j(getattr(ac, "from_date", None))
            to = _g2j(getattr(ac, "to_date", None))
            if fr and to and (fr <= dob_j <= to):
                return ac
        return None

    def validate(self, attrs):
        comp = self._competition
        req = self._request
        if not comp:
            raise serializers.ValidationError({"__all__": "مسابقه یافت نشد."})

        # --- NEW: حالت «باز کردن اجباری»
        # از ویو داخل context پاس بده: context={"force_open": True} یا با ?force=1
        force_open = bool(
            (self.context.get("force_open") or self.context.get("registration_checked_ok"))
            or getattr(settings, "POOMSAE_ALLOW_TEST_REG", False)
        )

        # بازه/وضعیت ثبت‌نام (DateTime)
        if not force_open:
            now_dt = timezone.now()
            if getattr(comp, "registration_start", None) and now_dt < comp.registration_start:
                raise serializers.ValidationError({"__all__": "ثبت‌نام هنوز شروع نشده است."})
            if getattr(comp, "registration_end", None) and now_dt > comp.registration_end:
                raise serializers.ValidationError({"__all__": "مهلت ثبت‌نام به پایان رسیده است."})

            # اگر فیلد/پرُپرتی boolean روی مدل داری از همان استفاده کن؛

            reg_open_eff = getattr(comp, "registration_open_effective", None)
            if callable(reg_open_eff):
                is_open = bool(reg_open_eff())
            elif isinstance(reg_open_eff, bool):
                is_open = reg_open_eff
            else:
                # محاسبه‌ی سادهٔ لوکال (DateTime)
                now_dt = timezone.now()
                rs = getattr(comp, "registration_start", None)
                re_ = getattr(comp, "registration_end", None)
                is_open = bool(rs and re_ and (rs <= now_dt <= re_))

            if not force_open and not is_open:
                raise serializers.ValidationError({"__all__": "ثبت‌نام این مسابقه فعال نیست."})

        # کاربر/پروفایل بازیکن
        user = getattr(req, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            raise serializers.ValidationError({"__all__": "برای ثبت‌نام باید وارد شوید."})
        user = getattr(req, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            raise serializers.ValidationError({"__all__": "برای ثبت‌نام باید وارد شوید."})
        
        player = _get_player_like_profile(user)
        if not player:
            raise serializers.ValidationError({"__all__": "پروفایل بازیکن پیدا نشد."})
        
        self._player = player


        # تاریخ بیمه ≥ ۷۲ ساعت قبل از تاریخ برگزاری (این یکی را عمداً در حالت force هم نگه داشتیم)
        issue_g = _to_greg_from_str_jalali(attrs.get("insurance_issue_date"))
        if not issue_g:
            raise serializers.ValidationError({"insurance_issue_date": "تاریخ صدور نامعتبر است (مثلاً ۱۴۰۳/۰۵/۲۰)."})
        comp_d = getattr(comp, "competition_date", None) or getattr(comp, "start_date", None)
        cd = _as_local_date(comp_d)
        if cd and issue_g > (cd - timedelta(days=3)):
            raise serializers.ValidationError(
                {"insurance_issue_date": "تاریخ صدور باید حداقل ۷۲ ساعت قبل از برگزاری باشد."})
        self._issue_date_greg = issue_g

        # کُد مربی (اجباری) + اعتبارسنجی
        coach_code = (attrs.get("coach_code") or "").strip()
        if not coach_code:
            raise serializers.ValidationError({"coach_code": "کد تأیید مربی الزامی است."})
        appr = PoomsaeCoachApproval.objects.filter(
            competition=comp, code=coach_code, is_active=True, approved=True
        ).select_related("coach").first()
        if not appr:
            raise serializers.ValidationError({"coach_code": "کد مربی معتبر نیست یا فعال نیست."})
        self._coach = appr.coach
        self._coach_code = appr.code

        # گروه کمربند سازگار
        belt_group = None
        code = self._player_belt_code(player)
        if code:
            belt_group = _find_belt_group_obj(comp, code)
        if comp.belt_groups.exists() and not belt_group:
            raise serializers.ValidationError({"belt_group": "کمربند شما با گروه‌های مسابقه سازگار نیست."})
        self._belt_group = belt_group

        # شماره بیمه
        if not (attrs.get("insurance_number") or "").strip():
            raise serializers.ValidationError({"insurance_number": "شماره بیمه الزامی است."})

        # رده سنی مناسب بازیکن
        ac = self._resolve_age_category_for_player(comp, player)
        if not ac:
            raise serializers.ValidationError({"__all__": "ردهٔ سنی متناسب با تاریخ تولد شما در این مسابقه یافت نشد."})
        self._age_category = ac

        # نوع پومسه و وجود Division
        style = attrs.get("poomsae_type")  # standard/creative
        if not style:
            raise serializers.ValidationError({"poomsae_type": "انتخاب نوع پومسه الزامی است."})
        division_exists = PoomsaeDivision.objects.filter(
            competition=comp, age_category=ac, belt_group=belt_group, style=style
        ).exists()
        if not division_exists:
            raise serializers.ValidationError(
                {"__all__": "برای ترکیب رده سنی/کمربندی/سبک شما، ردهٔ پومسه تعریف نشده است."})

        # جلوگیری از ثبت‌نام تکراری
        if PoomsaeEnrollment.objects.filter(
                competition=comp, player=player, poomsae_type=style
        ).exclude(status="canceled").exists():
            raise serializers.ValidationError({"__all__": "در این نوع پومسه قبلاً ثبت‌نام کرده‌اید."})

        return attrs
    @transaction.atomic
    def create(self, validated_data):
        comp = self._competition
        player = self._player
        coach = self._coach
    
        req = self.context.get("request")
        user = getattr(req, "user", None)
    
        coach_name = f"{getattr(coach, 'first_name', '')} {getattr(coach, 'last_name', '')}".strip() if coach else ""
        club_obj, club_name = _extract_club_profile_and_name(player)
        board_obj = getattr(player, "tkd_board", None)
        board_name = getattr(board_obj, "name", "") or ""
    
        amount = int(getattr(comp, "entry_fee", 0) or 0)

        # 🔒 Guard ریال
        if amount > 0 and amount < 10_000:
            raise serializers.ValidationError(
                {"entry_fee": "مبلغ ثبت‌نام پومسه باید به ریال باشد (entry_fee خیلی کوچک است)."}
            )

        style = validated_data.get("poomsae_type")
    
        create_kwargs = dict(
            competition=comp,
            player=player,
    
            coach=coach,
            coach_name=coach_name,
            coach_approval_code=self._coach_code,
    
            club=club_obj, club_name=club_name,
            board=board_obj, board_name=board_name,
    
            belt_group=self._belt_group,
            age_category=self._age_category,
    
            poomsae_type=style,
    
            insurance_number=validated_data.get("insurance_number"),
            insurance_issue_date=self._issue_date_greg,
    
            status="pending",   # ✅ دیگر paid نیست
            is_paid=False,
            paid_amount=0,
            bank_ref_code=None,
        )
    
        # ✅ اگر فیلد created_by روی مدل هست ستش کن (safe)
        if "created_by" in {f.name for f in PoomsaeEnrollment._meta.fields}:
            if user and getattr(user, "is_authenticated", False):
                create_kwargs["created_by"] = user
    
        enrollment = PoomsaeEnrollment.objects.create(**create_kwargs)
    
        self._paid_amount = amount
        return enrollment


    def to_representation(self, instance: PoomsaeEnrollment):
        return {
            "enrollment_id": instance.id,
            "status": instance.status,
            "paid": instance.is_paid,
            "paid_amount": getattr(self, "_paid_amount", instance.paid_amount),
            "bank_ref_code": instance.bank_ref_code or "DEV-PAID",
        }


class PoomsaeEnrollmentCardSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()
    competition_title = serializers.CharField(source="competition.name", read_only=True)
    competition_date_jalali = serializers.SerializerMethodField()

    first_name = serializers.CharField(source="player.first_name", read_only=True)
    last_name  = serializers.CharField(source="player.last_name", read_only=True)
    birth_date = serializers.SerializerMethodField()
    photo      = serializers.SerializerMethodField()
    poomsae_types = serializers.SerializerMethodField()

    poomsae_type_display = serializers.SerializerMethodField()
    belt_group = serializers.SerializerMethodField()
    belt = serializers.SerializerMethodField()               # ⬅️ جدید — نام کمربند بازیکن
    age_category_name = serializers.SerializerMethodField()

    insurance_issue_date_jalali = serializers.SerializerMethodField()

    class Meta:
        model = PoomsaeEnrollment
        fields = [
            "kind",
            "competition_title", "competition_date_jalali",
            "first_name", "last_name", "birth_date", "photo",
            "poomsae_type", "poomsae_type_display", "poomsae_types",
            "belt_group", "belt", "age_category_name",           # ⬅️ belt اضافه شد
            "insurance_number", "insurance_issue_date_jalali",
            "coach_name", "club_name",
        ]

    def get_kind(self, obj):
        return "poomsae"

    def get_poomsae_types(self, obj):
        return list(
            PoomsaeEnrollment.objects
            .filter(competition=obj.competition, player=obj.player)
            .exclude(status="canceled")
            .values_list("poomsae_type", flat=True)
            .distinct()
        )

    def get_poomsae_type_display(self, obj):
        qs = (PoomsaeEnrollment.objects
              .filter(competition=obj.competition, player=obj.player)
              .exclude(status="canceled"))
        types = list(qs.values_list("poomsae_type", flat=True).distinct())
        order = {"standard": 0, "creative": 1}
        types.sort(key=lambda x: order.get(x, 99))
        mapping = dict(PoomsaeEnrollment.POOMSAE_TYPE_CHOICES)
        labels = [mapping.get(t, t) for t in types if t]
        if labels:
            return "، ".join(labels)
        try:
            return obj.get_poomsae_type_display()
        except Exception:
            return mapping.get(getattr(obj, "poomsae_type", None), None)

    def get_competition_date_jalali(self, obj):
        d = getattr(obj.competition, "competition_date", None) or getattr(obj.competition, "start_date", None)
        return _to_jalali_date_str(d)

    def get_birth_date(self, obj):
        bd = getattr(obj.player, "birth_date", None)
        if not bd:
            return None
        if isinstance(bd, (_datetime, _date)):
            return _to_jalali_date_str(bd)
        jd = _parse_jalali_str(bd)
        if jd:
            return _j2str(jd)
        g = _to_greg_from_str_jalali(bd)
        return _to_jalali_date_str(g) if g else str(bd)

    def get_photo(self, obj):
        request = self.context.get("request")
        prof = obj.player
        cand = getattr(prof, "profile_image", None)
        if not cand or (hasattr(cand, "name") and not getattr(cand, "name", "")):
            for alt in ("avatar", "photo", "image"):
                v = getattr(prof, alt, None)
                if v and (not hasattr(v, "name") or getattr(v, "name", "")):
                    cand = v
                    break
        return _abs_media(request, cand)

    def get_insurance_issue_date_jalali(self, obj):
        return _to_jalali_date_str(obj.insurance_issue_date)

    def get_belt_group(self, obj):
        return getattr(getattr(obj, "belt_group", None), "label", None)

    def get_belt(self, obj):
        """نمایش نام کمربند خودِ بازیکن (نه گروه)."""
        p = obj.player
        # اولویت با grade، بعد نام‌های متنی؛ در نهایت رابطه Belt
        for name in ("belt_grade", "belt_name", "belt_label", "belt_title"):
            v = getattr(p, name, None)
            if v:
                return str(v)

        b = getattr(p, "belt", None)
        if not b:
            return None
        for attr in ("name", "label", "title"):
            v = getattr(b, attr, None)
            if v:
                return str(v)
        return b if isinstance(b, str) else None
    def get_age_category_name(self, obj):
        # اگر روی Enrollment ست شده بود
        ac = getattr(obj, "age_category", None)
        if ac and getattr(ac, "name", None):
            return ac.name

        # تلاش برای حدس زدن از DOB بازیکن و رده‌های خود مسابقه
        bd = getattr(obj.player, "birth_date", None)
        g = None
        if isinstance(bd, (_date, _datetime)):
            g = bd.date() if isinstance(bd, _datetime) else bd
        else:
            g = _to_greg_from_str_jalali(bd)
        if not g:
            return None

        comp = obj.competition
        try:
            if getattr(comp, "age_categories", None) and comp.age_categories.exists():
                m = AgeCategory.objects.filter(
                    id__in=comp.age_categories.values_list("id", flat=True),
                    from_date__lte=g, to_date__gte=g
                ).first()
                if m:
                    return m.name
        except Exception:
            pass

        # fallback عمومی
        m = AgeCategory.objects.filter(from_date__lte=g, to_date__gte=g).first()
        return getattr(m, "name", None)
