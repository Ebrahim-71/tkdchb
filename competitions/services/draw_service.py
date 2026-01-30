# competitions/services/draw_service.py
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Tuple, Set

from django.db import transaction
from django.utils import timezone
from django.core.management import call_command

ELIGIBLE_STATUSES = ("paid", "confirmed", "accepted", "completed")

# جریمه‌ها: تکرار حریفِ دور اول خیلی مهم‌تر از هم‌باشگاهی‌بودن است
REPEAT_PAIR_PENALTY = 100
SAME_CLUB_PENALTY = 1  # فقط وقتی تعداد واقعی بازیکنان > club_threshold باشد


@dataclass
class _Entry:
    enrollment_id: int
    player_id: Optional[int]
    club_id: Optional[int]
    coach_id: Optional[int]


def _is_pow2(x: int) -> bool:
    return x > 0 and (x & (x - 1)) == 0


def _next_pow2(n: int) -> int:
    s = 1
    while s < max(n, 2):
        s <<= 1
    return s


# ---------- BYE placement patterns ----------
# ترتیب دقیق خانه‌های BYE (از B1 به بعد) برای اندازه‌های مرسوم براکت (۱-بیسی)
# 16 تایی مطابق برگه‌ی ارسالی شماست. 32 و 64 بر اساس الگوی متعادل رسمیِ seed-position ساخته شده‌اند.
BYE_ORDER_MAP: dict[int, List[int]] = {
    2:  [2, 1],
    4:  [4, 1, 3, 2],
    8:  [8, 1, 5, 4, 6, 3, 7, 2],
    16: [16, 1, 9, 8, 13, 5, 12, 6, 14, 3, 11, 7, 10, 2, 15, 4],
    32: [32, 1, 17, 16, 25, 8, 24, 9, 29, 4, 20, 13, 28, 5, 21, 12,
         31, 2, 18, 15, 26, 7, 23, 10, 30, 3, 19, 14, 27, 6, 22, 11],
    64: [64, 1, 33, 32, 49, 16, 48, 17, 57, 8, 40, 25, 56, 9, 41, 24,
         61, 4, 36, 29, 52, 13, 45, 20, 60, 5, 37, 28, 53, 12, 44, 21,
         63, 2, 34, 31, 50, 15, 47, 18, 58, 7, 39, 26, 55, 10, 42, 23,
         62, 3, 35, 30, 51, 14, 46, 19, 59, 6, 38, 27, 54, 11, 43, 22],
}


def _bye_slots(size: int, bye_count: int) -> List[int]:
    """
    برمی‌گرداند لیست اسلات‌هایی که باید BYE قرار بگیرد (۱-بیسی).
    اگر الگوی آماده نبود، یک fallback متعادل می‌سازد.
    """
    order = BYE_ORDER_MAP.get(size)
    if order is None:
        # fallback: از انتها/ابتدا به‌صورت متقارن
        order = []
        l, r = 1, size
        while l <= r:
            order.append(r)
            if len(order) >= size:
                break
            order.append(l)
            l += 1
            r -= 1
    return order[:max(0, bye_count)]


# ---------- هزینه/بهینه‌سازی ----------

def _pair_cost(
    a: _Entry,
    b: _Entry,
    *,
    effective_count: int,               # تعداد واقعی بازیکنان (بدون BYE)
    club_threshold: int,
    history_pairs: Set[Tuple[int, int]],
) -> int:
    """هزینه‌ی برخورد این جفت در دور اول."""
    if a.player_id is None or b.player_id is None:
        return 0  # BYE
    x, y = (a.player_id, b.player_id) if a.player_id < b.player_id else (b.player_id, a.player_id)
    cost = 0
    if (x, y) in history_pairs:
        cost += REPEAT_PAIR_PENALTY
    if effective_count > club_threshold and a.club_id and b.club_id and a.club_id == b.club_id:
        cost += SAME_CLUB_PENALTY
    return cost


def _order_cost_for_slots(
    players_order: List[_Entry],
    *,
    non_bye_slots: List[int],
    size: int,
    effective_count: int,
    club_threshold: int,
    history_pairs: Set[Tuple[int, int]],
) -> int:
    """هزینه‌ی کل برای یک ترتیب مشخص از بازیکن‌ها روی اسلات‌های غیر BYE."""
    # نگاشت اسلات -> بازیکن
    slot_to_entry: dict[int, _Entry] = {}
    for idx, s in enumerate(non_bye_slots):
        slot_to_entry[s] = players_order[idx]

    total = 0
    # بازی‌های دور اول: (1vs2), (3vs4), ...
    for s in range(1, size, 2):
        A = slot_to_entry.get(s)      # ممکن است BYE باشد => None
        B = slot_to_entry.get(s + 1)  # ممکن است BYE باشد => None
        if not A or not B:
            continue
        total += _pair_cost(
            A, B,
            effective_count=effective_count,
            club_threshold=club_threshold,
            history_pairs=history_pairs,
        )
    return total


def _best_order_by_penalty_on_slots(
    players_only: List[_Entry],
    *,
    non_bye_slots: List[int],
    size: int,
    attempts: int,
    club_threshold: int,
    history_pairs: Set[Tuple[int, int]],
    effective_count: int,
    rng_seed: Optional[str] = None,
) -> List[_Entry]:
    """کم‌هزینه‌ترین ترتیب بازیکن‌ها فقط روی اسلات‌های غیر BYE را پیدا می‌کند."""
    if len(players_only) <= 2:
        return players_only

    rnd = random.Random(rng_seed)
    best = None
    best_cost = None

    for _ in range(max(1, attempts)):
        tmp = players_only[:]
        rnd.shuffle(tmp)
        cost = _order_cost_for_slots(
            tmp,
            non_bye_slots=non_bye_slots,
            size=size,
            effective_count=effective_count,
            club_threshold=club_threshold,
            history_pairs=history_pairs,
        )
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best = tmp
            if best_cost == 0:
                break

    return best or players_only


# ---------- سرویس اصلی ----------

@transaction.atomic
def create_draw_for_group(
    *,
    competition_id: int,
    age_category_id: Optional[int],
    belt_group_id: int,
    weight_category_id: int,
    club_threshold: int = 8,
    seed: str = "",
    shuffle_attempts: int = 200,
    cleanup_months: int = 12,   # اگر کامند فروردین‌محور است، استفاده نمی‌شود
    cleanup_keep_last: int = 5, # اگر کامند فروردین‌محور است، استفاده نمی‌شود
    size_override: Optional[int] = None,
):
    """
    قرعه‌کشی را می‌سازد و مسابقات دور اول را تولید می‌کند و تاریخچهٔ برخورد دور اول را به‌روزرسانی می‌کند.
    خروجی: شیء Draw
    """
    # برای جلوگیری از import حلقه‌ای، داخل تابع ایمپورت می‌کنیم
    from competitions.models import (
        Draw, Match, Enrollment, KyorugiCompetition, FirstRoundPairHistory
    )

    comp = KyorugiCompetition.objects.select_related("age_category").get(pk=competition_id)

    # ثبت‌نام‌های واجد شرایط
    enroll_qs = (
        Enrollment.objects
        .filter(
            competition_id=competition_id,
            belt_group_id=belt_group_id,
            weight_category_id=weight_category_id,
            status__in=ELIGIBLE_STATUSES,
        )
        .select_related("player", "club", "coach")
        .order_by("id")
    )

    entries: List[_Entry] = []
    for e in enroll_qs:
        p = e.player
        entries.append(
            _Entry(
                enrollment_id=e.id,
                player_id=p.id if p else None,
                club_id=e.club_id or getattr(p, "club_id", None),
                coach_id=e.coach_id or getattr(p, "coach_id", None),
            )
        )

    real_count = sum(1 for x in entries if x.player_id is not None)
    if real_count < 1:
        raise ValueError("برای این گروه حداقل ۱ شرکت‌کننده لازم است.")

    # ---- تعیین اندازه جدول ----
    # ---- تعیین اندازه جدول ----
    if size_override is not None:
        if not _is_pow2(size_override):
            raise ValueError("اندازه جدول باید توان ۲ باشد (مثلاً 2، 4، 8، 16، 32، 64).")
        min_needed = 4 if 1 <= real_count <= 4 else 2
        size = max(size_override, min_needed)  # ← به جای ارور، ارتقا بده
    else:
        size = 4 if 1 <= real_count <= 4 else _next_pow2(real_count)

    # --- جایگذاری BYE بر اساس الگوی ثابت ---
    bye_count = size - real_count
    bye_set = set(_bye_slots(size, bye_count))  # اسلات‌هایی که BYE هستند (۱..size)

    # فقط بازیکن‌ها
    players_only = [e for e in entries if e.player_id is not None]

    # اسلات‌های غیر BYE به ترتیب طبیعی جدول
    non_bye_slots = [s for s in range(1, size + 1) if s not in bye_set]

    # ست تاریخچه‌ی برخوردهای دور اول قبلی برای همین scope
    hist_qs = FirstRoundPairHistory.objects.filter(
        gender=comp.gender,
        age_category_id=age_category_id,
        belt_group_id=belt_group_id,
        weight_category_id=weight_category_id,
    ).values_list("player_a_id", "player_b_id")
    history_pairs: Set[Tuple[int, int]] = set(hist_qs)

    # کم‌هزینه‌ترین ترتیب برای اسلات‌های غیر BYE
    best_order = _best_order_by_penalty_on_slots(
        players_only,
        non_bye_slots=non_bye_slots,
        size=size,
        attempts=shuffle_attempts,
        club_threshold=club_threshold,
        history_pairs=history_pairs,
        effective_count=real_count,
        rng_seed=seed or None,
    )

    # مونتاژ نهایی: بازیکن‌ها روی اسلات‌های غیر BYE، و در اسلات‌های BYE ورودی خالی
    entries_final: List[_Entry] = []
    it = iter(best_order)
    for s in range(1, size + 1):
        if s in bye_set:
            entries_final.append(_Entry(enrollment_id=-1, player_id=None, club_id=None, coach_id=None))
        else:
            entries_final.append(next(it))

    # اگر قبلاً قرعه‌ای برای این ترکیب وجود دارد و قفل نیست، حذف کن
    prev = Draw.objects.filter(
        competition_id=competition_id,
        gender=comp.gender,
        age_category_id=age_category_id,
        belt_group_id=belt_group_id,
        weight_category_id=weight_category_id,
    ).order_by("-created_at").first()

    if prev and not prev.is_locked:
        Match.objects.filter(draw=prev).delete()
        prev.delete()

    # ایجاد Draw
    draw = Draw.objects.create(
        competition_id=competition_id,
        gender=comp.gender,
        age_category_id=age_category_id,
        belt_group_id=belt_group_id,
        weight_category_id=weight_category_id,
        size=size,
        club_threshold=club_threshold,
        rng_seed=seed or "",
        is_locked=False,
    )

    # ساخت مسابقات دور اول
    matches = []
    slot = 1
    for i in range(0, size, 2):
        A = entries_final[i]
        B = entries_final[i + 1]
        is_bye = (A.player_id is None) or (B.player_id is None)

        m = Match(
            draw=draw,
            round_no=1,
            slot_a=slot,
            slot_b=slot + 1,
            player_a_id=A.player_id,
            player_b_id=B.player_id,
            is_bye=is_bye,
        )
        matches.append(m)
        slot += 2

    Match.objects.bulk_create(matches)

    # --- به‌روزرسانی تاریخچه‌ی برخورد دور اول برای جفت‌های واقعی (نه BYE) ---
    now = timezone.now()
    for i in range(0, size, 2):
        a = entries_final[i].player_id
        b = entries_final[i + 1].player_id
        if a is None or b is None:
            continue
        x, y = (a, b) if a < b else (b, a)
        FirstRoundPairHistory.objects.update_or_create(
            player_a_id=x,
            player_b_id=y,
            gender=comp.gender,
            age_category_id=age_category_id,
            belt_group_id=belt_group_id,
            weight_category_id=weight_category_id,
            defaults={
                "last_competition_id": competition_id,
                "last_met_at": now,
            },
        )

    # (اختیاری) پاک‌سازی تاریخچه‌ها؛ اگر کامندت فقط ۱ فروردین پاک می‌کند، بدون آرگومان صدا بزن
    try:
        call_command("cleanup_pair_history")
    except Exception:
        pass

    return draw
