# competitions/services/schedule_service.py
from __future__ import annotations
from collections import defaultdict
import math

from django.db import transaction

def _round_title(total_rounds: int, r: int) -> str:
    # total_rounds=log2(size)  ، r=1..total_rounds
    dist = total_rounds - r  # 0: Final, 1: Semi, 2: QF, 3: R16, ...
    names = {0:"فینال", 1:"نیمه‌نهایی", 2:"یک‌چهارم", 3:"یک‌هشتم", 4:"یک‌ شانزدهم"}
    return names.get(dist, f"دور {r}")

@transaction.atomic
def number_matches_for_competition(competition_id: int, *, reset_old: bool = True):
    """
    برای هر زمین، همهٔ مسابقات رده‌های وزنی اختصاص‌داده‌شده را
    به ترتیب «round_no صعودی، وزن صعودی، slot_a صعودی» شماره‌گذاری می‌کند.
    شمارهٔ هر زمین از 1 شروع می‌شود.
    """
    from competitions.models import KyorugiCompetition, MatAssignment, Draw, Match, WeightCategory

    comp = KyorugiCompetition.objects.get(pk=competition_id)

    # نگاشت وزن -> شماره زمین طبق تنظیمات مسابقه
    weight_to_mat = {}
    for assign in MatAssignment.objects.filter(competition=comp).prefetch_related("weights"):
        for w in assign.weights.all():
            weight_to_mat[w.id] = assign.mat_number

    # مسابقات واقعی (BYE نباشند) برای همهٔ Drawهای این مسابقه
    qs = (Match.objects
          .filter(draw__competition=comp, is_bye=False)
          .select_related("draw", "draw__weight_category")
          .order_by("round_no", "slot_a"))

    # گروه‌بندی بر حسب زمین
    per_mat = defaultdict(list)
    for m in qs:
        mat = weight_to_mat.get(m.draw.weight_category_id)
        if mat is not None:
            per_mat[mat].append(m)

    # پاکسازی شماره‌های قبلی در صورت نیاز
    if reset_old:
        (Match.objects
              .filter(draw__competition=comp)
              .update(mat_number=None, order_on_mat=None))

    # مرتب‌سازی داخل هر زمین و تخصیص شماره‌ها
    updated = []
    for mat, items in per_mat.items():
        # وزنِ کمتر جلوتر؛ اگر min_weight نداشت، صفر در نظر بگیر
        items.sort(key=lambda m: (m.round_no, getattr(m.draw.weight_category, "min_weight", 0) or 0, m.slot_a))
        seq = 1
        for m in items:
            m.mat_number = mat
            m.order_on_mat = seq
            seq += 1
            updated.append(m)

    if updated:
        Match.objects.bulk_update(updated, ["mat_number", "order_on_mat"])

    # خروجی برای نمایش/چاپ
    schedule = []
    for mat, items in sorted(per_mat.items(), key=lambda x: x[0]):
        rows = []
        # برای نمایش مرحله
        for m in items:
            total_rounds = max(1, int(math.log2(max(m.draw.size, 2))))
            rows.append({
                "order": m.order_on_mat,
                "mat": mat,
                "round_no": m.round_no,
                "round_title": _round_title(total_rounds, m.round_no),
                "weight": m.draw.weight_category.name if m.draw.weight_category else "",
                "belt": getattr(m.draw.belt_group, "label", ""),
                "player_a": getattr(m, "player_a", None) and m.player_a.full_name or None,
                "player_b": getattr(m, "player_b", None) and m.player_b.full_name or None,
            })
        schedule.append({"mat": mat, "rows": rows})
    return schedule
