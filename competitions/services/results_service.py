# competitions/services/results_service.py
from django.db import transaction
from django.db.models import Sum, F, Count, Case, When, Value

from competitions.models import KyorugiResult, RankingTransaction, Enrollment
from accounts.models import UserProfile, TkdClub, TkdBoard

PLAYER_POINTS = {1: 7.0, 2: 3.0, 3: 1.0}
COACH_POINTS  = {"gold": 1.0,  "silver": 0.75, "bronze": 0.5}
ORG_POINTS    = {"gold": 0.75, "silver": 0.5,  "bronze": 0.25}

def _medal_of_place(place: int) -> str:
    return "gold" if place == 1 else ("silver" if place == 2 else "bronze")

def _apply_points(subject_type: str, subject_id: int, delta: float):
    """
    ✅ بازیکن: به ranking_competition اضافه/کم کن
    ✅ مربی/باشگاه/هیئت: به ranking_total اضافه/کم کن
    """
    if not subject_id or not delta:
        return
    delta = float(delta)

    if subject_type == "player":
        UserProfile.objects.filter(pk=subject_id).update(
            ranking_competition=F("ranking_competition") + delta
        )
    elif subject_type == "coach":
        UserProfile.objects.filter(pk=subject_id).update(
            ranking_total=F("ranking_total") + delta
        )
    elif subject_type == "club":
        TkdClub.objects.filter(pk=subject_id).update(
            ranking_total=F("ranking_total") + delta
        )
    elif subject_type == "board":
        TkdBoard.objects.filter(pk=subject_id).update(
            ranking_total=F("ranking_total") + delta
        )

def _medal_counter_update(subject_type: str, subject_id: int, medal: str, delta: int):
    if not subject_id or medal not in ("gold", "silver", "bronze") or not delta:
        return

    field = f"{medal}_medals"

    if subject_type == "player":
        Model = UserProfile
    elif subject_type == "club":
        Model = TkdClub
    else:
        return

    qs = Model.objects.filter(pk=subject_id)

    if delta < 0:
        qs.update(**{
            field: Case(
                When(**{f"{field}__lte": abs(delta)}, then=Value(0)),
                default=F(field) + delta,
            )
        })
    else:
        qs.update(**{field: F(field) + delta})

def _award_transactions_for_enrollment(e: Enrollment, place: int, result: KyorugiResult):
    medal = _medal_of_place(place)

    # بازیکن
    RankingTransaction.objects.create(
        competition=result.competition,
        result=result,
        subject_type="player",
        subject_id=e.player_id,
        points=PLAYER_POINTS[place],
        medal=medal,
    )

    # مربی
    if e.coach_id:
        RankingTransaction.objects.create(
            competition=result.competition,
            result=result,
            subject_type="coach",
            subject_id=e.coach_id,
            points=COACH_POINTS[medal],
            medal=medal,
        )

    # باشگاه
    if e.club_id:
        RankingTransaction.objects.create(
            competition=result.competition,
            result=result,
            subject_type="club",
            subject_id=e.club_id,
            points=ORG_POINTS[medal],
            medal=medal,
        )

    # هیئت
    if e.board_id:
        RankingTransaction.objects.create(
            competition=result.competition,
            result=result,
            subject_type="board",
            subject_id=e.board_id,
            points=ORG_POINTS[medal],
            medal=medal,
        )

    if getattr(e, "medal", None) != medal:
        e.medal = medal
        e.save(update_fields=["medal"])

@transaction.atomic
def apply_results_and_points(result: KyorugiResult):
    # 1) اثر تراکنش‌های قبلی را برعکس کن
    prev_qs = RankingTransaction.objects.filter(result=result)

    for row in prev_qs.values("subject_type", "subject_id").annotate(total=Sum("points")):
        _apply_points(row["subject_type"], row["subject_id"], -float(row["total"] or 0.0))

    for row in prev_qs.values("subject_type", "subject_id", "medal").annotate(cnt=Count("id")):
        if row["medal"] in ("gold", "silver", "bronze"):
            _medal_counter_update(row["subject_type"], row["subject_id"], row["medal"], -int(row["cnt"] or 0))

    prev_qs.delete()

    # 3) تراکنش‌های جدید
    mapping = [
        (result.gold_enrollment,   1),
        (result.silver_enrollment, 2),
        (result.bronze1_enrollment, 3),
        (result.bronze2_enrollment, 3),
    ]
    for e, place in mapping:
        if isinstance(e, Enrollment):
            _award_transactions_for_enrollment(e, place, result)

    # 4) اعمال امتیازهای جدید
    new_qs = RankingTransaction.objects.filter(result=result)

    for row in new_qs.values("subject_type", "subject_id").annotate(total=Sum("points")):
        _apply_points(row["subject_type"], row["subject_id"], float(row["total"] or 0.0))

    for row in new_qs.values("subject_type", "subject_id", "medal").annotate(cnt=Count("id")):
        if row["medal"] in ("gold", "silver", "bronze"):
            _medal_counter_update(row["subject_type"], row["subject_id"], row["medal"], int(row["cnt"] or 0))
