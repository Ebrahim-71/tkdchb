# tkdjango/reports/services.py
from datetime import date, timedelta
import datetime as _dt
from django.db.models import Count, Sum, Q, F, DateTimeField
from django.db.models import DateField as _DateField

# jdatetime برای تبدیل جلالی←→میلادی (اختیاری)
try:
    import jdatetime
    _HAS_JDATETIME = True
except Exception:
    jdatetime = None
    _HAS_JDATETIME = False


# ===== پیکربندی نقش‌ها =====
ROLE_FIELD_NAME = "role"
ROLE_VALUES = {
    "player":  ["player", "athlete", "بازیکن"],
    "coach":   ["coach", "مربی", "coach_referee", "both"],
    "referee": ["referee", "داور", "coach_referee", "both"],
    "club":    ["club", "باشگاه"],
}

# مقادیر مدال (فارسی/انگلیسی/عددی)
MEDAL_STRINGS = {
    "gold":   {"gold", "طلایی", "طلا", "۱", "1"},
    "silver": {"silver", "نقره‌ای", "نقره", "۲", "2"},
    "bronze": {"bronze", "برنزی", "برنز", "۳", "3"},
}

# ---------- هِلپرهای عمومی متن/تاریخ ----------
_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_EN_DIGITS = "0123456789"
_AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"  # Arabic-Indic U+0660..U+0669


def get_belt_choices():

    try:
        from accounts.models import UserProfile
        return list(UserProfile.BELT_CHOICES)
    except Exception:
        return []




def _fa_to_en(s: str) -> str:
    if not s:
        return ""
    out = []
    for ch in str(s):
        if ch in _FA_DIGITS:
            out.append(_EN_DIGITS[_FA_DIGITS.index(ch)])
        elif ch in _AR_DIGITS:
            out.append(_EN_DIGITS[_AR_DIGITS.index(ch)])
        else:
            out.append(ch)
    return "".join(out)

def _norm_date_str(s: str) -> str:
    """
    '۱۴۰۲/۴/۵' → '1402-04-05'
    '1402.4.5' → '1402-04-05'
    """
    if not s:
        return ""
    s = _fa_to_en(str(s)).strip()
    for sep in ("/", ".", "–", "—", "−"):
        s = s.replace(sep, "-")
    parts = [p for p in s.split("-") if p]
    if len(parts) == 3:
        y, m, d = parts[0], parts[1].zfill(2), parts[2].zfill(2)
        return f"{y}-{m}-{d}"
    return s

def _to_gdate_from_any(v):
    """
    هر چیزی که شبیه تاریخ باشد را به datetime.date میلادی تبدیل می‌کند.
    ورودی می‌تواند date/datetime یا رشته جلالی/میلادی (با ارقام فارسی یا انگلیسی) باشد.
    """
    if not v:
        return None

    # اگر خودش تاریخ/دیتایم باشد
    if hasattr(v, "date") and isinstance(v, _dt.datetime):
        return v.date()
    if hasattr(v, "year") and hasattr(v, "month") and hasattr(v, "day"):
        # datetime.date یا jdatetime.date
        if _HAS_JDATETIME and isinstance(v, jdatetime.date):
            try:
                return v.togregorian()
            except Exception:
                return None
        # احتمالاً datetime.date
        try:
            _ = v.year + v.month + v.day
            return v
        except Exception:
            pass

    # رشته
    s = _norm_date_str(v)
    if not s or "-" not in s:
        return None

    try:
        y, m, d = [int(x) for x in s.split("-")]
    except Exception:
        return None

    # اگر سال بزرگ بود، میلادی فرض کن
    if y >= 1600:
        try:
            return _dt.date(y, m, d)
        except Exception:
            return None

    # جلالی → میلادی
    if _HAS_JDATETIME:
        try:
            return jdatetime.date(y, m, d).togregorian()
        except Exception:
            return None
    return None


# ---------- هِلپرهای کمربند ----------
def _norm(s):
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = (s.replace("ي", "ی").replace("ك", "ک")
           .replace("آ", "ا").replace("\u200c", "").replace("‌", ""))
    s = " ".join(s.split())
    return s

def _belt_label_from_instance(belt_obj):
    if belt_obj is None:
        return None
    for f in ("name", "title", "fa_name", "display"):
        if hasattr(belt_obj, f) and getattr(belt_obj, f):
            return str(getattr(belt_obj, f))
    return str(belt_obj)

def _apply_belt_filter(players_qs, UserProfile, belt):
    if not belt:
        return players_qs

    if _field_exists(UserProfile, "belt") and hasattr(belt, "id"):
        return players_qs.filter(belt_id=belt.id)

    label = belt if isinstance(belt, str) else _belt_label_from_instance(belt)
    if not label:
        return players_qs
    label_n = _norm(label)

    if _field_exists(UserProfile, "belt") and not hasattr(belt, "id"):
        try:
            bqs = get_belt_qs()
            if bqs is not None:
                bel = bqs.filter(
                    Q(name__iexact=label) | Q(title__iexact=label) |
                    Q(fa_name__iexact=label) | Q(display__iexact=label)
                ).first()
                if not bel:
                    for b in bqs:
                        if _norm(_belt_label_from_instance(b)) == label_n:
                            bel = b; break
                if bel:
                    return players_qs.filter(belt_id=bel.id)
        except Exception:
            pass

    q = Q()
    TEXT_FIELDS = (
        "belt_name", "belt_title", "belt", "grade", "level",
        "dan", "gup", "kup", "belt_color", "color_belt",
    )
    for f in TEXT_FIELDS:
        if _field_exists(UserProfile, f):
            q |= Q(**{f + "__iexact": label}) | Q(**{f + "__iexact": label.replace("آ", "ا")})

    CHOICE_FIELDS = ("level", "grade", "belt_level", "belt_grade", "dan", "kup", "gup", "belt", "belt_color")
    for f in CHOICE_FIELDS:
        if _field_exists(UserProfile, f):
            try:
                fld = UserProfile._meta.get_field(f)
                if getattr(fld, "choices", None):
                    keys = []
                    for k, lbl in fld.choices:
                        if _norm(lbl) == label_n or _norm(k) == label_n:
                            keys.append(k)
                    if keys:
                        q |= Q(**{f + "__in": keys})
            except Exception:
                pass

    return players_qs.filter(q) if q else players_qs


# ---------- هِلپرهای عمومی ----------
def _created_field(model):
    for name in ("created_at", "date_joined", "created", "created_on", "joined_at"):
        try:
            model._meta.get_field(name)
            return name
        except Exception:
            continue
    return None

def _field_exists(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
        return True
    except Exception:
        return False

def _date_filter_kwargs(model, field_name, start, end):
    if not field_name:
        return {}
    try:
        f = model._meta.get_field(field_name)
    except Exception:
        f = None
    pre = "date__" if isinstance(f, DateTimeField) else ""
    if start and end:
        return {f"{field_name}__{pre}range": (start, end)}
    if start:
        return {f"{field_name}__{pre}gte": start}
    if end:
        return {f"{field_name}__{pre}lte": end}
    return {}

def _role_counts(qs, model):
    out = {'player': 0, 'coach': 0, 'referee': 0, 'club': 0}

    if _field_exists(model, ROLE_FIELD_NAME):
        rf = ROLE_FIELD_NAME
        for key, vals in ROLE_VALUES.items():
            q = Q()
            for v in vals:
                q |= Q(**{f"{rf}__iexact": v})
            out[key] = qs.filter(q).count()
        return out

    if any(_field_exists(model, f) for f in ("is_player", "is_coach", "is_referee", "is_club")):
        if _field_exists(model, "is_player"):   out['player']  = qs.filter(is_player=True).count()
        if _field_exists(model, "is_coach"):    out['coach']   = qs.filter(is_coach=True).count()
        if _field_exists(model, "is_referee"):  out['referee'] = qs.filter(is_referee=True).count()
        if _field_exists(model, "is_club"):     out['club']    = qs.filter(is_club=True).count()
        return out

    role_field = None
    for cand in ("role", "user_role", "role_name", "roles"):
        if _field_exists(model, cand):
            role_field = cand
            break
    if not role_field:
        return out

    f = model._meta.get_field(role_field)
    if getattr(f, "choices", None):
        def _n(s): return str(s or "").strip().lower()
        keysets = {k: set() for k in out.keys()}
        for key, label in f.choices:
            k = _n(key); lbl = _n(label)
            for cat, vals in ROLE_VALUES.items():
                for v in vals:
                    v = _n(v)
                    if v == k or v == lbl:
                        keysets[cat].add(key)
        for cat, keys in keysets.items():
            if keys:
                out[cat] = qs.filter(**{f"{role_field}__in": list(keys)}).count()
        return out

    for cat, vals in ROLE_VALUES.items():
        q = Q()
        for v in vals:
            q |= Q(**{f"{role_field}__iexact": v})
        out[cat] = qs.filter(q).count()
    return out


# ---------- سرویس گزارش کاربران (کارت‌ها + جدول) ----------
def users_summary(start, end):
    from accounts.models import UserProfile

    created_field = _created_field(UserProfile)

    range_qs = UserProfile.objects.all()
    if created_field:
        range_qs = range_qs.filter(**_date_filter_kwargs(UserProfile, created_field, start, end))
    total_in_range = range_qs.count()

    role_field = "role" if _field_exists(UserProfile, "role") else None
    by_role = []
    if role_field:
        by_role = list(range_qs.values(role_field).annotate(c=Count("id")).order_by("-c"))

    all_qs = UserProfile.objects.all()
    totals_all = _role_counts(all_qs, UserProfile)
    total_all = all_qs.count()

    clubs_all = totals_all.get("club", 0)
    last7_clubs = 0
    try:
        from accounts.models import TkdClub
        clubs_all = TkdClub.objects.count()
        club_created_field = _created_field(TkdClub)
        if club_created_field:
            today = date.today()
            last7_start = today - timedelta(days=7)
            last7_clubs = TkdClub.objects.filter(
                **_date_filter_kwargs(TkdClub, club_created_field, last7_start, today)
            ).count()
    except Exception:
        pass

    last7_total = 0
    last7_counts = {'player': 0, 'coach': 0, 'referee': 0, 'club': 0}
    if created_field:
        today = date.today()
        last7_start = today - timedelta(days=7)
        last7_qs = all_qs.filter(**_date_filter_kwargs(UserProfile, created_field, last7_start, today))
        last7_total = last7_qs.count()
        last7_counts = _role_counts(last7_qs, UserProfile)

    totals_all["club"] = clubs_all
    if last7_clubs:
        last7_counts["club"] = last7_clubs

    return {
        "total": total_in_range,
        "by_role": by_role,
        "start": start, "end": end,
        "summary": {
            "total_all": total_all,
            "players_all":   totals_all.get("player", 0),
            "coaches_all":   totals_all.get("coach", 0),
            "referees_all":  totals_all.get("referee", 0),
            "clubs_all":     totals_all.get("club", 0),
            "new_last7_total":    last7_total,
            "new_last7_players":  last7_counts.get("player", 0),
            "new_last7_coaches":  last7_counts.get("coach", 0),
            "new_last7_referees": last7_counts.get("referee", 0),
            "new_last7_clubs":    last7_counts.get("club", 0),
        },
    }


# ---------- لیست‌ها برای فرم «شاگردان اساتید» ----------
def list_coaches_qs():
    from accounts.models import UserProfile
    qs = UserProfile.objects.all()
    if _field_exists(UserProfile, ROLE_FIELD_NAME):
        q = Q()
        for v in ROLE_VALUES["coach"]:
            q |= Q(**{f"{ROLE_FIELD_NAME}__iexact": v})
        qs = qs.filter(q)
    elif _field_exists(UserProfile, "is_coach"):
        qs = qs.filter(is_coach=True)
    return qs.order_by("id")

def get_belt_qs():
    """
    همیشه یک QuerySet برگردان. اگر مدل پیدا نشد، QS خالی بده تا فرم‌ها نشکنند.
    """
    try:
        from accounts.models import Belt
        return Belt.objects.all()
    except Exception:
        pass
    try:
        from competitions.models import Belt
        return Belt.objects.all()
    except Exception:
        pass
    from django.contrib.auth import get_user_model
    return get_user_model().objects.none()

def get_club_qs():
    try:
        from accounts.models import TkdClub
        return TkdClub.objects.all()
    except Exception:
        return None


# ---------- سرویس «شاگردان اساتید» (بدون جستجوی تاریخ تولد) ----------
def coach_students(coach_id, belt_id=None, club_id=None, national_code=None):
    """
    فقط از coach_id داخل خود UserProfile رابطه مربی ↔ شاگرد را تشخیص می‌دهد.
    * هیچ فیلتر تاریخ تولدی اعمال نمی‌شود.
    """
    from accounts.models import UserProfile

    if not coach_id:
        return {"rows": [], "filters_applied": {
            "coach_id": None, "belt_id": belt_id, "club_id": club_id,
            "national_code": national_code
        }}

    players_qs = _students_qs_by_user_coach(coach_id)

    if _field_exists(UserProfile, ROLE_FIELD_NAME):
        qrole = Q()
        for v in ROLE_VALUES["player"]:
            qrole |= Q(**{f"{ROLE_FIELD_NAME}__iexact": v})
        players_qs = players_qs.filter(qrole)
    elif _field_exists(UserProfile, "is_player"):
        players_qs = players_qs.filter(is_player=True)

    players_qs = _apply_belt_filter(players_qs, UserProfile, belt_id)

    if club_id and _field_exists(UserProfile, "club"):
        players_qs = players_qs.filter(club_id=club_id)

    if national_code:
        for cand in ("national_code", "nid", "national_id"):
            if _field_exists(UserProfile, cand):
                players_qs = players_qs.filter(**{f"{cand}__iexact": national_code})
                break

    # بدون فیلتر تاریخ؛ صرفاً لیست را تولید کن
    players_iter = list(players_qs)

    # شمارش مسابقات (اگر Enrollment دارید)
    EnrollmentModel = None
    try:
        from competitions.models import Enrollment as _E
        EnrollmentModel = _E
    except Exception:
        pass

    def _count_competitions(pid):
        if not EnrollmentModel:
            return 0
        pf = next((c for c in ("player","athlete","user","profile") if _field_exists(EnrollmentModel, c)), None)
        if not pf:
            return 0
        return EnrollmentModel.objects.filter(**{f"{pf}_id": pid}).count()

    # ساخت ردیف‌ها
    rows = []
    for p in players_iter:
        fname = getattr(p, "first_name", "") or ""
        lname = getattr(p, "last_name", "") or ""
        full_name = (fname + " " + lname).strip() or getattr(p, "name", "") or str(p)

        belt_val = _belt_text(p)

        nid = ""
        for cand in ("national_code", "nid", "national_id"):
            if hasattr(p, cand) and getattr(p, cand):
                nid = getattr(p, cand); break

        club_name = ""
        if hasattr(p, "club") and getattr(p, "club", None):
            c = getattr(p, "club")
            club_name = getattr(c, "name", str(c)) if c else ""

        # نمایش تاریخ تولد فقط برای جدول/جستجوی متنی؛ نه فیلتر
        birth_str = ""
        birth_jalali = ""
        for dob_field in (
            "birth_date", "date_of_birth", "dob", "birthdate", "birthday",
            "dateBirth", "datebirth", "birth"
        ):
            if hasattr(p, dob_field):
                _dv = getattr(p, dob_field)
                if hasattr(_dv, "strftime"):
                    birth_str = _dv.strftime("%Y-%m-%d")
                    try:
                        if jdatetime and isinstance(_dv, (_dt.date, _dt.datetime)):
                            if isinstance(_dv, _dt.datetime): _dv = _dv.date()
                            j = jdatetime.date.fromgregorian(date=_dv)
                            birth_jalali = f"{j.year:04d}-{j.month:02d}-{j.day:02d}"
                    except Exception:
                        pass
                elif _dv:
                    birth_str = str(_dv)
                break

        comp_cnt = _count_competitions(p.id)
        g, s, b = _medals_for_player(p.id)
        r_comp, r_total = _rankings_for_player(p.id)

        rows.append({
            "full_name": full_name,
            "belt": belt_val,
            "national_code": nid,
            "club_name": club_name,
            "birth_date": birth_str,
            "birth_date_jalali": birth_jalali,
            "competitions": comp_cnt,
            "medal_gold": g, "medal_silver": s, "medal_bronze": b,
            "rank_comp": r_comp, "rank_total": r_total,
        })

    return {
        "rows": rows,
        "filters_applied": {
            "coach_id": coach_id, "belt_id": getattr(belt_id, "id", belt_id),
            "club_id": club_id, "national_code": national_code
        },
    }


# ---------- نمایش کمربند یک پروفایل ----------
def _belt_text(profile):
    if not profile:
        return ""
    for fk in ("belt", "rank", "belt_degree"):
        if hasattr(profile, fk) and getattr(profile, fk, None):
            obj = getattr(profile, fk)
            for name in ("name", "title", "display"):
                if hasattr(obj, name) and getattr(obj, name):
                    return str(getattr(obj, name))
            return str(obj)
    for fn in ("level", "grade", "belt_level", "belt_grade", "dan", "kup", "gup"):
        if hasattr(profile, fn):
            try:
                f = profile._meta.get_field(fn)
                if getattr(f, "choices", None):
                    val = getattr(profile, fn)
                    for k, lbl in f.choices:
                        if k == val:
                            return str(lbl)
            except Exception:
                pass
    for fn in ("belt_name", "belt_title", "belt", "grade", "dan", "gup", "kup"):
        if hasattr(profile, fn) and getattr(profile, fn):
            return str(getattr(profile, fn))
    return ""


# ---------- مدال‌ها ----------
def _medals_for_player(pid):
    gold = silver = bronze = 0

    def _count_by_value(qs, field, values):
        q = Q()
        for v in values:
            if str(v).isdigit():
                q |= Q(**{field: int(v)})
            q |= Q(**{field + "__iexact": str(v)})
        return qs.filter(q).count()

    result_models = []
    for dotted in (
        "competitions.KyorugiResult",
        "competitions.CompetitionResult",
        "competitions.Result",
    ):
        try:
            mod_name, cls_name = dotted.split(".")
            mod = __import__(f"{mod_name}.models", fromlist=[cls_name])
            R = getattr(mod, cls_name)
            result_models.append(R)
        except Exception:
            pass

    for R in result_models:
        link = None
        for cand in ("player", "athlete", "user", "profile"):
            try:
                R._meta.get_field(cand); link = cand; break
            except Exception:
                continue
        if not link:
            try:
                R._meta.get_field("enrollment"); link = "enrollment__player"
            except Exception:
                pass
        if not link:
            continue

        base = R.objects.filter(**({f"{link}_id": pid} if "__" not in link else {link + "_id": pid}))

        medal_field = None
        for mf in ("medal", "medal_type", "medal_color", "place", "rank", "position", "standing"):
            try:
                R._meta.get_field(mf); medal_field = mf; break
            except Exception:
                continue
        if not medal_field:
            continue

        gold   += _count_by_value(base, medal_field, MEDAL_STRINGS["gold"])
        silver += _count_by_value(base, medal_field, MEDAL_STRINGS["silver"])
        bronze += _count_by_value(base, medal_field, MEDAL_STRINGS["bronze"])

    try:
        from competitions.models import Enrollment as E
        link_field = next((c for c in ("player","athlete","user","profile") if _field_exists(E, c)), None)
        if link_field:
            base = E.objects.filter(**{f"{link_field}_id": pid})
            medal_field = None
            for mf in ("medal","medal_type","medal_color","place","rank","position","standing","result"):
                try:
                    E._meta.get_field(mf); medal_field = mf; break
                except Exception:
                    continue
            if medal_field:
                gold   += _count_by_value(base, medal_field, MEDAL_STRINGS["gold"])
                silver += _count_by_value(base, medal_field, MEDAL_STRINGS["silver"])
                bronze += _count_by_value(base, medal_field, MEDAL_STRINGS["bronze"])
    except Exception:
        pass

    return gold, silver, bronze


# ---------- رنکینگ ----------
def _rankings_for_player(pid):
    comp_pts = total_pts = 0

    for dotted in ("competitions.RankingTransaction", "competitions.Ranking"):
        try:
            mod_name, cls_name = dotted.split(".")
            mod = __import__(f"{mod_name}.models", fromlist=[cls_name])
            M = getattr(mod, cls_name)
        except Exception:
            continue

        link = None
        for cand in ("user", "player", "athlete", "profile"):
            try:
                M._meta.get_field(cand); link = cand; break
            except Exception:
                continue
        if not link:
            continue

        qs = M.objects.filter(**{f"{link}_id": pid})

        points_field = None
        for pf in ("points", "score", "value", "amount", "total_points"):
            try:
                M._meta.get_field(pf); points_field = pf; break
            except Exception:
                continue
        if points_field:
            total_pts += qs.aggregate(s=Sum(points_field))["s"] or 0

        comp_filter = Q()
        for cf in ("source", "scope", "kind", "reason", "category", "type", "context"):
            try:
                M._meta.get_field(cf)
                comp_filter |= Q(**{f"{cf}__icontains": "comp"})
                comp_filter |= Q(**{f"{cf}__icontains": "competition"})
                comp_filter |= Q(**{f"{cf}__icontains": "مسابق"})
            except Exception:
                continue
        if comp_filter and points_field:
            comp_pts += qs.filter(comp_filter).aggregate(s=Sum(points_field))["s"] or 0

    if comp_pts == 0 and total_pts == 0:
        try:
            from accounts.models import UserProfile
            up = UserProfile.objects.filter(id=pid).first()
            if up:
                for pf in ("ranking","ranking_points","rank_points","total_points","score"):
                    if hasattr(up, pf):
                        total_pts = getattr(up, pf) or 0
                for pf in ("competition_points","comp_points"):
                    if hasattr(up, pf):
                        comp_pts = getattr(up, pf) or 0
        except Exception:
            pass

    if comp_pts == 0 and total_pts == 0:
        g, s, b = _medals_for_player(pid)
        comp_pts = g*4 + s*3 + b*2
        total_pts = comp_pts

    return comp_pts, total_pts


def _students_qs_by_user_coach(coach_id):
    """
    برمی‌گرداند QuerySet از UserProfile هایی که 'مستقیماً' در خود پروفایل‌شان
    به این coach_id وصل شده‌اند (FK یا M2M).
    """
    from accounts.models import UserProfile

    q = Q()
    for name in ("coach", "coach_user", "teacher", "mentor", "master",
                 "main_coach", "head_coach"):
        if _field_exists(UserProfile, name):
            q |= Q(**{f"{name}_id": coach_id})

    for f in UserProfile._meta.fields:
        try:
            if (getattr(getattr(f, "remote_field", None), "model", None) == UserProfile
                and "coach" in f.name.lower()):
                q |= Q(**{f"{f.name}_id": coach_id})
        except Exception:
            pass

    qs = UserProfile.objects.filter(q) if q else UserProfile.objects.none()

    for m2m in UserProfile._meta.many_to_many:
        try:
            if "coach" in m2m.name.lower() and m2m.remote_field.model == UserProfile:
                qs = qs.union(UserProfile.objects.filter(**{f"{m2m.name}__id": coach_id}))
        except Exception:
            pass

    return qs.distinct()

#-*-*-*-**-*-*-*-*-*-**-*--*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*

def club_students(club_id, belt_id=None, coach_id=None, national_code=None):
    """
    لیست شاگردان یک باشگاه:
      - club_id اجباری برای نمایش (مثل coach_id در coach_students)
      - فیلترها: کمربند، مربی، کدملی
      - بدون فیلتر تاریخ تولد؛ فقط نمایش ستون birth_date/birth_date_jalali
      - در خروجی به‌جای club_name، coach_name می‌دهیم
    """
    from accounts.models import UserProfile

    if not club_id:
        return {"rows": [], "filters_applied": {
            "club_id": None, "belt_id": belt_id, "coach_id": coach_id,
            "national_code": national_code
        }}

    # پایه: همه اعضای باشگاه
    base_qs = UserProfile.objects.all()
    if _field_exists(UserProfile, "club"):
        base_qs = base_qs.filter(club_id=club_id)
    else:
        # اگر فیلد club مستقیم نبود، از M2M احتمالی (coaching_clubs/members) استفاده کن
        # (ایمن در برابر نبودن)
        try:
            base_qs = UserProfile.objects.filter(coaching_clubs__id=club_id)
        except Exception:
            base_qs = UserProfile.objects.none()

    # فقط بازیکن‌ها
    if _field_exists(UserProfile, ROLE_FIELD_NAME):
        role_q = Q()
        for v in ROLE_VALUES["player"]:
            role_q |= Q(**{f"{ROLE_FIELD_NAME}__iexact": v})
        base_qs = base_qs.filter(role_q)
    elif _field_exists(UserProfile, "is_player"):
        base_qs = base_qs.filter(is_player=True)

    # فیلتر کمربند (رشته‌ای / choices / FK)
    base_qs = _apply_belt_filter(base_qs, UserProfile, belt_id)

    # فیلتر مربی (اختیاری)
    if coach_id:
        # FKهای رایج به مربی در UserProfile: coach / coach_user / ...
        coach_q = Q()
        for name in ("coach", "coach_user", "teacher", "mentor", "master",
                     "main_coach", "head_coach"):
            if _field_exists(UserProfile, name):
                coach_q |= Q(**{f"{name}_id": coach_id})
        if coach_q:
            base_qs = base_qs.filter(coach_q)

    # فیلتر کدملی
    if national_code:
        for cand in ("national_code", "nid", "national_id"):
            if _field_exists(UserProfile, cand):
                base_qs = base_qs.filter(**{f"{cand}__iexact": national_code})
                break

    players = list(base_qs)

    # شمارش مسابقات (اگر Enrollment دارید)
    EnrollmentModel = None
    try:
        from competitions.models import Enrollment as _E
        EnrollmentModel = _E
    except Exception:
        pass

    def _count_competitions(pid):
        if not EnrollmentModel:
            return 0
        pf = next((c for c in ("player","athlete","user","profile") if _field_exists(EnrollmentModel, c)), None)
        if not pf:
            return 0
        return EnrollmentModel.objects.filter(**{f"{pf}_id": pid}).count()

    rows = []
    for p in players:
        fname = getattr(p, "first_name", "") or ""
        lname = getattr(p, "last_name", "") or ""
        full_name = (fname + " " + lname).strip() or getattr(p, "name", "") or str(p)

        belt_val = _belt_text(p)

        nid = ""
        for cand in ("national_code", "nid", "national_id"):
            if hasattr(p, cand) and getattr(p, cand):
                nid = getattr(p, cand); break

        # استخراج نام مربی
        coach_name = ""
        for cfield in ("coach", "coach_user", "teacher", "mentor", "master",
                       "main_coach", "head_coach"):
            if hasattr(p, cfield) and getattr(p, cfield, None):
                cobj = getattr(p, cfield)
                cf = getattr(cobj, "first_name", "") or ""
                cl = getattr(cobj, "last_name", "") or ""
                coach_name = (cf + " " + cl).strip() or getattr(cobj, "coach_name", "") or str(cobj)
                if coach_name:
                    break

        # تاریخ تولد فقط برای نمایش
        birth_str = ""
        birth_jalali = ""
        for dob_field in ("birth_date","date_of_birth","dob","birthdate","birthday","dateBirth","datebirth","birth"):
            if hasattr(p, dob_field):
                _dv = getattr(p, dob_field)
                if hasattr(_dv, "strftime"):
                    birth_str = _dv.strftime("%Y-%m-%d")
                    try:
                        if jdatetime and isinstance(_dv, (_dt.date, _dt.datetime)):
                            if isinstance(_dv, _dt.datetime): _dv = _dv.date()
                            j = jdatetime.date.fromgregorian(date=_dv)
                            birth_jalali = f"{j.year:04d}-{j.month:02d}-{j.day:02d}"
                    except Exception:
                        pass
                elif _dv:
                    birth_str = str(_dv)
                break

        comp_cnt = _count_competitions(p.id)
        g, s, b = _medals_for_player(p.id)
        r_comp, r_total = _rankings_for_player(p.id)

        rows.append({
            "full_name": full_name,
            "belt": belt_val,
            "national_code": nid,
            "coach_name": coach_name,     # 👈 بجای club_name
            "birth_date": birth_str,
            "birth_date_jalali": birth_jalali,
            "competitions": comp_cnt,
            "medal_gold": g, "medal_silver": s, "medal_bronze": b,
            "rank_comp": r_comp, "rank_total": r_total,
        })

    return {
        "rows": rows,
        "filters_applied": {
            "club_id": club_id,
            "belt_id": getattr(belt_id, "id", belt_id),
            "coach_id": coach_id,
            "national_code": national_code,
        },
    }


# tkdjango/reports/services.py

# tkdjango/reports/services.py

def get_board_qs():
    try:
        from accounts.models import TkdBoard
        return TkdBoard.objects.all()
    except Exception:
        pass
    try:
        from accounts.models import Board
        return Board.objects.all()
    except Exception:
        pass
    return None


def _clubs_qs_for_board(board_id):
    """
    همه‌ی باشگاه‌های زیرمجموعه‌ی یک هیئت را برمی‌گرداند، بدون فرض نام دقیق فیلد.
    """
    try:
        from accounts.models import TkdClub as _Club
    except Exception:
        try:
            from accounts.models import Club as _Club
        except Exception:
            return None

    # فهرست نام‌های محتمل فیلد ارجاع به هیئت (FK یا M2M)
    cand_fk = ["board", "tkd_board", "federation_board", "province_board", "hyat", "heyat"]
    cand_m2m = ["boards", "tkd_boards", "related_boards"]

    q = None
    # FK ها
    for name in cand_fk:
        if _field_exists(_Club, name):
            return _Club.objects.filter(**{f"{name}_id": board_id})
    # M2M ها
    for name in cand_m2m:
        try:
            fld = _Club._meta.get_field(name)
            if getattr(fld, "many_to_many", False):
                return _Club.objects.filter(**{f"{name}__id": board_id})
        except Exception:
            continue

    # هیچ فیلدی پیدا نشد
    return None

def board_students(board_id=None, belt_id=None, coach_id=None, club_id=None, national_code=None):
    """
    لیست شاگردان زیرمجموعه‌ی یک هیئت:
      - اگر club_id داده شود، از همان باشگاه فیلتر می‌کنیم؛
        وگرنه از هیئت → باشگاه‌ها استخراج می‌کنیم.
    """
    from accounts.models import UserProfile

    if not (board_id or club_id):
        return {"rows": [], "filters_applied": {
            "board_id": None, "club_id": club_id, "belt_id": belt_id,
            "coach_id": coach_id, "national_code": national_code
        }}

    # 1) مبنا: اعضای باشگاه(ها)
    base_qs = UserProfile.objects.all()

    # اگر باشگاه مشخص شده، همان را بگیر؛ وگرنه همه‌ی باشگاه‌های هیئت را پیدا کن
    club_ids = None
    if club_id:
        club_ids = [club_id]
    else:
        cqs = _clubs_qs_for_board(board_id)
        if cqs is not None:
            club_ids = list(cqs.values_list("id", flat=True))

    if club_ids:
        if _field_exists(UserProfile, "club"):
            base_qs = base_qs.filter(club_id__in=club_ids)
        else:
            # fallback اگر club مستقیم تو پروفایل نیست
            try:
                base_qs = base_qs.filter(club__id__in=club_ids)
            except Exception:
                # اگر رابطه‌ی دیگری بین پروفایل و باشگاه دارید، اینجا اضافه‌اش کنید
                base_qs = UserProfile.objects.none()
    else:
        # اگر به هر دلیلی باشگاهی پیدا نشد، هیچ نتیجه‌ای نده
        base_qs = UserProfile.objects.none()

    # 2) فقط بازیکن‌ها
    if _field_exists(UserProfile, ROLE_FIELD_NAME):
        role_q = Q()
        for v in ROLE_VALUES["player"]:
            role_q |= Q(**{f"{ROLE_FIELD_NAME}__iexact": v})
        base_qs = base_qs.filter(role_q)
    elif _field_exists(UserProfile, "is_player"):
        base_qs = base_qs.filter(is_player=True)

    # 3) فیلتر کمربند
    base_qs = _apply_belt_filter(base_qs, UserProfile, belt_id)

    # 4) فیلتر مربی (اختیاری)
    if coach_id:
        cq = Q()
        for name in ("coach", "coach_user", "teacher", "mentor", "master", "main_coach", "head_coach"):
            if _field_exists(UserProfile, name):
                cq |= Q(**{f"{name}_id": coach_id})
        if cq:
            base_qs = base_qs.filter(cq)

    # 5) فیلتر کدملی
    if national_code:
        for cand in ("national_code", "nid", "national_id"):
            if _field_exists(UserProfile, cand):
                base_qs = base_qs.filter(**{f"{cand}__iexact": national_code})
                break

    players = list(base_qs)

    # شمارش مسابقات و … (مثل بقیه سرویس‌ها)
    EnrollmentModel = None
    try:
        from competitions.models import Enrollment as _E
        EnrollmentModel = _E
    except Exception:
        pass

    def _count_competitions(pid):
        if not EnrollmentModel:
            return 0
        pf = next((c for c in ("player","athlete","user","profile") if _field_exists(EnrollmentModel, c)), None)
        if not pf:
            return 0
        return EnrollmentModel.objects.filter(**{f"{pf}_id": pid}).count()

    rows = []
    for p in players:
        fname = getattr(p, "first_name", "") or ""
        lname = getattr(p, "last_name", "") or ""
        full_name = (fname + " " + lname).strip() or getattr(p, "name", "") or str(p)
        belt_val = _belt_text(p)
        nid = next((getattr(p, cand) for cand in ("national_code","nid","national_id") if getattr(p, cand, None)), "")

        # coach_name برای جدول
        coach_name = ""
        for cfield in ("coach","coach_user","teacher","mentor","master","main_coach","head_coach"):
            if hasattr(p, cfield) and getattr(p, cfield, None):
                cobj = getattr(p, cfield)
                cf = getattr(cobj, "first_name", "") or ""
                cl = getattr(cobj, "last_name", "") or ""
                coach_name = (cf + " " + cl).strip() or getattr(cobj, "coach_name", "") or str(cobj)
                if coach_name:
                    break

        birth_str = ""; birth_jalali = ""
        for dob_field in ("birth_date","date_of_birth","dob","birthdate","birthday","dateBirth","datebirth","birth"):
            if hasattr(p, dob_field):
                _dv = getattr(p, dob_field)
                if hasattr(_dv, "strftime"):
                    birth_str = _dv.strftime("%Y-%m-%d")
                elif _dv:
                    birth_str = str(_dv)
                break

        comp_cnt = _count_competitions(p.id)
        g, s, b = _medals_for_player(p.id)
        r_comp, r_total = _rankings_for_player(p.id)

        rows.append({
            "full_name": full_name,
            "belt": belt_val,
            "national_code": nid,
            "coach_name": coach_name,
            "birth_date": birth_str,
            "birth_date_jalali": birth_jalali,
            "competitions": comp_cnt,
            "medal_gold": g, "medal_silver": s, "medal_bronze": b,
            "rank_comp": r_comp, "rank_total": r_total,
        })

    return {
        "rows": rows,
        "filters_applied": {
            "board_id": board_id,
            "club_id": club_id,
            "belt_id": getattr(belt_id, "id", belt_id),
            "coach_id": coach_id,
            "national_code": national_code,
        },
    }
#-*-*-*-**-*-*-*-*-*-**-*--*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*



def _role_label(val: str) -> str:
    s = (str(val or "")).strip().lower()
    if s in {"coach","coach_referee","both","مربی"}: return "مربی"
    if s in {"referee","coach_referee","both","داور"}: return "داور"
    return s or "—"


def _created_or_approved_field(model):
    """به ترتیب approved_at، created_at، date_joined، created، joined_at را برمی‌گرداند اگر وجود داشته باشد."""
    for name in ("approved_at", "created_at", "date_joined", "created", "joined_at"):
        try:
            model._meta.get_field(name)
            return name
        except Exception:
            continue
    return None


def _board_field_name(model):
    """نام فیلد FK/M2M احتمالی به هیئت روی UserProfile یا Club را حدس می‌زند."""
    for nm in ("board", "tkd_board", "federation_board", "province_board", "hyat", "heyat"):
        if _field_exists(model, nm):
            return nm
    for nm in ("boards", "tkd_boards", "related_boards"):
        try:
            f = model._meta.get_field(nm)
            if getattr(f, "many_to_many", False):
                return nm
        except Exception:
            continue
    return None

# --- جدید: نقش ترکیبی ---
def _has_role_val(val: str, bucket: str) -> bool:
    s = (str(val or "")).strip().lower()
    return any(s == str(v).strip().lower() for v in ROLE_VALUES[bucket])

def _role_combo(up, UserProfile):
    # بر اساس فیلد role یا بولی‌ها
    coach = ref = False
    if _field_exists(UserProfile, ROLE_FIELD_NAME):
        rv = getattr(up, ROLE_FIELD_NAME, "")
        coach = _has_role_val(rv, "coach")
        ref   = _has_role_val(rv, "referee")
        # مقادیر مرکب متداول
        if str(rv).lower() in {"coach_referee","both","مربی/داور","coach-referee"}:
            coach = ref = True
    else:
        coach = bool(getattr(up, "is_coach", False))
        ref   = bool(getattr(up, "is_referee", False))
    if coach and ref: return "مربی/داور"
    if coach: return "مربی"
    if ref:   return "داور"
    return "—"

# --- جدید: لیست همه‌ی باشگاه‌ها (FK + M2Mهای رایج) ---
def _clubs_list_for_profile(up):
    names = set()
    # FK رایج
    if getattr(up, "club", None):
        c = up.club
        names.add(getattr(c, "name", str(c)))
    # چند به چندهای رایج
    for m in ("coaching_clubs","clubs","related_clubs","managed_clubs"):
        try:
            rel = getattr(up, m, None)
            if rel and hasattr(rel, "all"):
                for c in rel.all():
                    names.add(getattr(c, "name", str(c)))
        except Exception:
            continue
    return "، ".join([n for n in names if n]) or ""

# --- جدید: شمارش بازیکنانِ این مربی (اگر مربی است) ---
def _players_count_for_person(up_id: int) -> int:
    try:
        qs = _students_qs_by_user_coach(up_id)
        return qs.count()
    except Exception:
        return 0
def board_coaches_referees(board_id=None, role=None, club_id=None, national_code=None):

    from accounts.models import UserProfile

    # 1) مبنا: UserProfile
    base_qs = UserProfile.objects.all()

    # فیلتر براساس باشگاه/هیئت
    if club_id:
        # مستقیم club_id روی پروفایل
        if _field_exists(UserProfile, "club"):
            base_qs = base_qs.filter(club_id=club_id)
        else:
            # fallback اگر رابطه غیرمستقیم باشد
            base_qs = base_qs.filter(club__id=club_id) if _field_exists(UserProfile, "club") else base_qs.none()
    elif board_id:
        # الف) اگر خود پروفایل فیلد board دارد
        bfield = _board_field_name(UserProfile)
        if bfield:
            if "__" in bfield or getattr(UserProfile._meta.get_field(bfield), "many_to_many", False):
                base_qs = base_qs.filter(**{f"{bfield}__id": board_id})
            else:
                base_qs = base_qs.filter(**{f"{bfield}_id": board_id})
        else:
            # ب) از روی باشگاه‌های هیئت
            cqs = _clubs_qs_for_board(board_id)
            if cqs is not None:
                club_ids = list(cqs.values_list("id", flat=True))
                if club_ids:
                    if _field_exists(UserProfile, "club"):
                        base_qs = base_qs.filter(club_id__in=club_ids)
                    else:
                        try:
                            base_qs = base_qs.filter(club__id__in=club_ids)
                        except Exception:
                            base_qs = UserProfile.objects.none()
                else:
                    base_qs = UserProfile.objects.none()
            else:
                base_qs = UserProfile.objects.none()
    else:
        # هیچ فیلتری روی هیئت/باشگاه داده نشده
        base_qs = UserProfile.objects.none()

    # 2) فیلتر نقش (coach/referee)
    # اگر فیلد نقش داری:
    if _field_exists(UserProfile, ROLE_FIELD_NAME):
        rq = Q()
        if not role:
            for v in set(ROLE_VALUES["coach"])|set(ROLE_VALUES["referee"]):
                rq |= Q(**{f"{ROLE_FIELD_NAME}__iexact": v})
        else:
            for v in ROLE_VALUES[role]:
                rq |= Q(**{f"{ROLE_FIELD_NAME}__iexact": v})
        base_qs = base_qs.filter(rq)
    else:
        # fallback: فیلدهای boolean
        if role == "coach":
            if _field_exists(UserProfile, "is_coach"):
                base_qs = base_qs.filter(is_coach=True)
        elif role == "referee":
            if _field_exists(UserProfile, "is_referee"):
                base_qs = base_qs.filter(is_referee=True)
        else:
            # هرکدام که در دسترس‌اند
            q = Q()
            if _field_exists(UserProfile, "is_coach"): q |= Q(is_coach=True)
            if _field_exists(UserProfile, "is_referee"): q |= Q(is_referee=True)
            base_qs = base_qs.filter(q) if q else base_qs.none()

    # 3) فیلتر کد ملی (اختیاری)
    if national_code:
        for cand in ("national_code","nid","national_id"):
            if _field_exists(UserProfile, cand):
                base_qs = base_qs.filter(**{f"{cand}__iexact": national_code})
                break

    # 4) آماده‌سازی فیلدهای نام، تماس، باشگاه/هیئت
    created_field = _created_or_approved_field(UserProfile)
    base_qs = base_qs.select_related("club").order_by("last_name", "first_name", "id")

    rows = []
    for p in base_qs:
        fname = getattr(p, "first_name", "") or ""
        lname = getattr(p, "last_name", "") or ""
        full_name = (fname + " " + lname).strip() or getattr(p, "name", "") or str(p)

        role_label = _role_combo(p, UserProfile)  # 👈 ترکیبی
        nid = next((getattr(p, cand) for cand in ("national_code", "nid", "national_id") if getattr(p, cand, None)), "")
        phone = ""
        for cand in ("phone", "mobile", "phone_number", "cellphone"):
            if getattr(p, cand, None): phone = getattr(p, cand); break

        club_names = _clubs_list_for_profile(p)  # 👈 همه باشگاه‌ها

        joined = getattr(p, created_field, None) if created_field else None
        joined_jalali = ""
        if joined and _HAS_JDATETIME:
            try:
                d = joined.date() if isinstance(joined, _dt.datetime) else joined
                j = jdatetime.date.fromgregorian(date=d)
                joined_jalali = f"{j.year:04d}/{j.month:02d}/{j.day:02d}"
            except Exception:
                pass

        # تعداد بازیکنان شخص (اگر مربی نباشد احتمالاً 0 می‌ماند)
        players_count = _players_count_for_person(p.id)

        g = s = b = 0
        try:
            g, s, b = _medals_for_player(p.id)
        except Exception:
            pass
        r_comp, r_total = _rankings_for_player(p.id)

        rows.append({
            "full_name": full_name,
            "role_label": role_label,
            "national_code": nid or "",
            "phone": phone or "",
            "club_name": club_names,  # 👈 لیستی
            "players_count": players_count,  # 👈 جایگزین ستون هیئت
            "joined_jalali": joined_jalali or "",
            "medal_gold": g, "medal_silver": s, "medal_bronze": b,
            "rank_total": r_total or 0,
        })

    return {
        "rows": rows,
        "filters_applied": {
            "board_id": board_id,
            "club_id": club_id,
            "role": role or "",
            "national_code": national_code,
        }
    }