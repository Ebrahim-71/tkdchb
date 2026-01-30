# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Iterable, Dict, List, Set
from django.db import transaction

from competitions.models import KyorugiCompetition, Draw, Match
from django.db.models import Q

class NumberingError(Exception):
    pass


def _weight_to_mat_map(comp: KyorugiCompetition) -> Dict[int, int]:
    mapping: Dict[int, int] = {}
    for ma in comp.mat_assignments.all().prefetch_related("weights"):
        for w in ma.weights.all():
            if w.id not in mapping:
                mapping[w.id] = ma.mat_number
            else:
                mapping[w.id] = min(mapping[w.id], ma.mat_number)
    return mapping


def _rounds_of(draw: Draw) -> List[int]:
    qs = (
        Match.objects
        .filter(draw=draw)
        .values_list("round_no", flat=True)
        .distinct()
        .order_by("round_no")
    )
    return list(qs)


def _matches_in_round(draw: Draw, round_no: int) -> List[Match]:
    return list(
        Match.objects
        .filter(draw=draw, round_no=round_no)
        .order_by("slot_a", "slot_b", "id")
    )


def _first_round_no(draw: Draw) -> int | None:
    rs = _rounds_of(draw)
    return rs[0] if rs else None


def _last_round_no(draw: Draw) -> int | None:
    rs = _rounds_of(draw)
    return rs[-1] if rs else None


def _ensure_rounds_exist(draw: Draw) -> None:
    """
    اگر برای راندهای بعد از راند اول Match ساخته نشده باشد، این تابع آن‌ها را می‌سازد.
    فقط slot_a/slot_b برای نظمِ نمایش پر می‌شود.
    """
    fr = _first_round_no(draw) or 1

    # اندازهٔ جدول: از خود مدل، یا بر اساس تعداد مسابقات راند اول
    total_size = int(getattr(draw, "size", 0) or 0)
    if total_size <= 0:
        cnt_r1 = Match.objects.filter(draw=draw, round_no=fr).count()
        total_size = max(1, cnt_r1 * 2)

    # تعداد راندها برای اندازهٔ 2^k
    rounds_count = 0
    s = 1
    while s < total_size:
        rounds_count += 1
        s <<= 1

    # برای هر راند بعد از اول: اگر کم داریم بساز
    for step in range(1, rounds_count):  # 1..(rounds_count-1)
        r = fr + step
        expected = max(1, total_size // (2 ** (step + 1)))  # راند دوم: N/4 ، سوم: N/8 ، ... فینال: 1
        existing = Match.objects.filter(draw=draw, round_no=r).count()
        if existing < expected:
            bulk = []
            for idx in range(existing, expected):
                bulk.append(Match(
                    draw=draw, round_no=r,
                    slot_a=idx, slot_b=idx,  # فقط جهت order
                    is_bye=False
                ))
            if bulk:
                Match.objects.bulk_create(bulk)


def _real_players_count(draw: Draw) -> int:

    ids = set()
    for a_id, b_id in (Match.objects
                       .filter(draw=draw)
                       .values_list("player_a_id", "player_b_id")):
        if a_id: ids.add(a_id)
        if b_id: ids.add(b_id)
    return len(ids)

def _has_real_match(draw: Draw) -> bool:
    """
    قبلی را دقیق‌تر می‌کنیم: تا وقتی حداقل دو بازیکن نداشته باشیم، «بازی واقعی» نداریم.
    """
    if _real_players_count(draw) < 2:
        return False
    fr = _first_round_no(draw)
    if fr is None:
        return False
    return (
        Match.objects.filter(draw=draw).exclude(round_no=fr).exists()
        or Match.objects.filter(draw=draw, round_no=fr, is_bye=False).exists()
    )

@transaction.atomic
def number_matches_for_competition(
    competition_id: int,
    weight_ids: Iterable[int],
    *,
    clear_prev: bool = True,
) -> Dict[int, int]:
    """
    فاز۱: همهٔ راندها به‌جز «فینال» شماره می‌گیرند (در راند اول بای نمی‌گیرد؛ از راند دوم به بعد بای ممنوع).
    فاز۲: «فینال»‌های همهٔ جدول‌های هر زمین، پشت‌سرهم و در انتهای شماره‌ها شماره می‌گیرند.
    خروجی: {mat_no: last_assigned_number}
    """
    comp = KyorugiCompetition.objects.select_related().get(pk=competition_id)

    weight_ids = {int(w) for w in (weight_ids or [])}
    if not weight_ids:
        raise NumberingError("هیچ رده‌ی وزنی انتخاب نشده است.")

    # وزن → زمین
    w2m = _weight_to_mat_map(comp)
    missing = [wid for wid in weight_ids if wid not in w2m]
    if missing:
        raise NumberingError(f"برای این وزن‌ها زمین تعریف نشده: {missing}")

    # قرعه‌ها (وزن از کم به زیاد)
    all_draws_qs = (
        Draw.objects
        .filter(competition=comp, weight_category_id__in=weight_ids)
        .select_related("weight_category")
        .order_by("weight_category__min_weight", "id")
    )
    if not all_draws_qs.exists():
        raise NumberingError("برای اوزان انتخاب‌شده قرعه‌ای وجود ندارد.")

    # شمارندهٔ هر زمین
    all_mats: Set[int] = set(w2m[dr.weight_category_id] for dr in all_draws_qs)
    counters: Dict[int, int] = {m: 0 for m in sorted(all_mats)}

    # پاک‌کردن شماره‌های قبلی
    if clear_prev:
        Match.objects.filter(draw__in=all_draws_qs).update(match_number=None)

    # نکتهٔ مهم: قبل از سنجش «بازی واقعی»، راندهای بعدی را بساز
    all_draws: List[Draw] = list(all_draws_qs)
    for dr in all_draws:
        _ensure_rounds_exist(dr)

    # فقط قرعه‌هایی که بازی واقعی دارند
    draws_for_numbering: List[Draw] = [dr for dr in all_draws if _has_real_match(dr)]
    if not draws_for_numbering:
        return counters

    # نقشهٔ «اولین/آخرین راندِ هر قرعه»
    first_round_of: Dict[int, int | None] = {}
    last_round_of: Dict[int, int | None] = {}
    for dr in draws_for_numbering:
        first_round_of[dr.id] = _first_round_no(dr)
        last_round_of[dr.id] = _last_round_no(dr)

    # گروه‌بندی قرعه‌ها به‌تفکیک زمین (ترتیب وزن‌ها حفظ می‌شود)
    drs_by_mat: Dict[int, List[Draw]] = {}
    for dr in draws_for_numbering:
        drs_by_mat.setdefault(w2m[dr.weight_category_id], []).append(dr)

    # مجموعهٔ همهٔ راندها
    all_rounds_set = {r for dr in draws_for_numbering for r in _rounds_of(dr)}
    if not all_rounds_set:
        return counters
    all_rounds: List[int] = sorted(all_rounds_set)

    # ------------- فاز ۱: همهٔ راندها به‌جز فینال‌ها -------------
    # ------------- فاز ۱: همهٔ راندها به‌جز فینال‌ها -------------
    for rnd in all_rounds:
        for mat_no in sorted(counters.keys()):
            for dr in drs_by_mat.get(mat_no, []):  # حفظ ترتیب وزن‌ها
                fr = first_round_of.get(dr.id)
                lr = last_round_of.get(dr.id)

                # فینال را می‌گذاریم برای فاز ۲
                if lr is not None and rnd == lr:
                    continue

                # 👈 اضافه کن: آیا این قرعه عملاً تک‌نفره است؟
                is_single = (_real_players_count(dr) < 2)

                for m in _matches_in_round(dr, rnd):
                    # فقط در راند اول قرعه، بای شماره نگیرد
                    if rnd == fr and m.is_bye:
                        continue
                    # از راند دوم به بعد، بای را فقط وقتی تبدیل به بازی واقعی کن که قرعه تک‌نفره نباشد
                    if fr is not None and rnd > fr and m.is_bye and not is_single:
                        m.is_bye = False

                    counters[mat_no] += 1
                    if not m.mat_no:
                        m.mat_no = mat_no
                    m.match_number = counters[mat_no]
                    m.save(update_fields=["is_bye", "mat_no", "match_number"])

    # ------------- فاز ۲: فینال‌ها پشت‌سرهم در انتهای هر زمین -------------
    for mat_no in sorted(counters.keys()):
        for dr in drs_by_mat.get(mat_no, []):  # ترتیب وزن‌ها
            lr = last_round_of.get(dr.id)
            fr = first_round_of.get(dr.id)
            if lr is None:
                continue
            finals = _matches_in_round(dr, lr)
            for m in finals:
                # اگر فینال همان راند اول باشد و بای باشد → شماره نگیرد
                if lr == fr and m.is_bye:
                    continue
                # در غیر این صورت بای ممنوع
                if fr is not None and lr > fr and m.is_bye:
                    m.is_bye = False

                counters[mat_no] += 1
                if not m.mat_no:
                    m.mat_no = mat_no
                m.match_number = counters[mat_no]
                m.save(update_fields=["is_bye", "mat_no", "match_number"])

    return counters

@transaction.atomic
def clear_match_numbers_for_competition(competition_id: int, weight_ids: Iterable[int]) -> None:
    comp = KyorugiCompetition.objects.select_related().get(pk=competition_id)
    weight_ids = {int(w) for w in (weight_ids or [])}
    if not weight_ids:
        return
    draws = Draw.objects.filter(competition=comp, weight_category_id__in=weight_ids)
    Match.objects.filter(draw__in=draws).update(match_number=None)
