# competitions/urls.py
from django.urls import path, register_converter

from .views import (
    # --------- Generic / Any ----------
    CompetitionDetailAnyView,

    # --------- Kyorugi ----------
    KyorugiCompetitionDetailView, KyorugiBracketView, KyorugiResultsView,
    CompetitionTermsView,
    RegisterSelfPrefillView, RegisterSelfView,
    CoachApprovalStatusView, ApproveCompetitionView,
    MyEnrollmentView, EnrollmentCardView, EnrollmentCardsBulkView,
    DashboardKyorugiListView, PlayerCompetitionsList, RefereeCompetitionsList,
    CoachStudentsEligibleListView, CoachRegisterStudentsView,

    # --------- Dashboard (ALL) ----------
    DashboardAllCompetitionsView,public_bracket_view  ,

    # --------- Seminars ----------
    SeminarListView, SeminarDetailView, SeminarRegisterView, sidebar_seminars,

    # --------- Poomsae ----------
    PoomsaeCompetitionDetailView,
    PoomsaeCoachApprovalStatusView, PoomsaeCoachApprovalApproveView,
    PoomsaeRegisterSelfView,MyPoomsaeEnrollmentsView
    # PoomsaeRegisterSelfPrefillView,  # اگر دارید، فعالش کنید
)

app_name = "competitions"

# کلید عددی یا public_id/slug (حساس به طول کمتر و کاراکتر _ هم مجاز)
class CompKeyConverter:
    # عددی خالص، یا اسلاگ با طول 1 تا 128 (حروف/عدد/خط تیره/خط زیرین)
    regex = r"(?:\d+|[A-Za-z0-9_-]{1,128})"


    def to_python(self, value):
        return value  # حساسیت حروف را در ویو هندل کنید

    def to_url(self, value):
        return str(value)

register_converter(CompKeyConverter, "ckey")

urlpatterns = [
    # ========================= عمومی Kyorugi =========================
    path("kyorugi/<ckey:key>/", KyorugiCompetitionDetailView.as_view(), name="kyorugi-detail"),
    path("kyorugi/<ckey:key>/terms/", CompetitionTermsView.as_view(), name="kyorugi-terms"),
    path("kyorugi/<ckey:key>/bracket/", KyorugiBracketView.as_view(), name="kyorugi-bracket"),
    path("kyorugi/<ckey:key>/results/", KyorugiResultsView.as_view(), name="kyorugi-results"),
    # سازگاری قدیمی نتایج
    path("competitions/<ckey:key>/results/", KyorugiResultsView.as_view(), name="kyorugi-results-compat"),

    # ========================= by-public (GENERIC برای هر دو مدل) =========================
    path("by-public/<ckey:key>/", CompetitionDetailAnyView.as_view(), name="detail-by-public"),
    path("by-public/<ckey:key>/terms/", CompetitionTermsView.as_view(), name="terms-by-public"),
    path("by-public/<ckey:key>/bracket/", KyorugiBracketView.as_view(), name="bracket-by-public"),
    path("by-public/<ckey:key>/results/", KyorugiResultsView.as_view(), name="results-by-public"),

    # ========================= احراز هویت Kyorugi =========================
    path("auth/kyorugi/<ckey:key>/prefill/", RegisterSelfPrefillView.as_view(), name="prefill"),
    path("auth/kyorugi/<ckey:key>/register/self/", RegisterSelfView.as_view(), name="register-self"),
    path("auth/kyorugi/<ckey:key>/coach-approval/status/", CoachApprovalStatusView.as_view(),
         name="coach-approval-status"),
    path("auth/kyorugi/<ckey:key>/coach-approval/approve/", ApproveCompetitionView.as_view(),
         name="coach-approval-approve"),
    path("auth/kyorugi/<ckey:key>/my-enrollment/", MyEnrollmentView.as_view(), name="my-enrollment"),
    path("auth/enrollments/<int:enrollment_id>/card/", EnrollmentCardView.as_view(), name="enrollment-card"),
    path("auth/enrollments/cards/bulk/", EnrollmentCardsBulkView.as_view(), name="enrollment-cards-bulk"),
    path("auth/kyorugi/<ckey:key>/coach/students/eligible/", CoachStudentsEligibleListView.as_view(),
         name="coach-eligible-students"),
    path("auth/kyorugi/<ckey:key>/coach/register/students/", CoachRegisterStudentsView.as_view(),
         name="coach-register-students"),
    path("auth/kyorugi/<ckey:key>/register/students/", CoachRegisterStudentsView.as_view(),
         name="register-students-bulk-alias"),

    # ========================= Dashboard =========================
    path("dashboard/all/", DashboardAllCompetitionsView.as_view(), name="dashboard-all"),
    path("dashboard/kyorugi/", DashboardKyorugiListView.as_view(), name="dashboard-kyorugi"),
    # alias با پیشوند auth/ برای سازگاری با فرانت
    path("auth/dashboard/all/", DashboardAllCompetitionsView.as_view(), name="dashboard-all-auth-alias"),
    path("auth/dashboard/kyorugi/", DashboardKyorugiListView.as_view(), name="dashboard-kyorugi-auth-alias"),

    # ========================= Kyorugi – لیست‌های نقش‌محور =========================
    path("kyorugi/player/competitions/", PlayerCompetitionsList.as_view(), name="player-competitions"),
    path("kyorugi/referee/competitions/", RefereeCompetitionsList.as_view(), name="referee-competitions"),
    path("public/kyorugi/<str:public_id>/bracket/", public_bracket_view, name="public-kyorugi-bracket"),

    # ========================= سمینار =========================
    path("seminars/", SeminarListView.as_view(), name="seminar-list"),
    path("seminars/<ckey:key>/", SeminarDetailView.as_view(), name="seminar-detail"),
    path("auth/seminars/<ckey:key>/register/", SeminarRegisterView.as_view(), name="seminar-register"),
    path("seminars/sidebar/", sidebar_seminars, name="seminars-sidebar"),

    # ========================= ترم‌ها (عمومی) =========================
    path("<ckey:key>/terms/", CompetitionTermsView.as_view(), name="terms-generic"),
    path("competitions/kyorugi/<ckey:key>/terms/", CompetitionTermsView.as_view(), name="kyorugi-terms-compat"),

    # ========================= پومسه: جزئیات و تأیید مربی =========================
    path("poomsae/<ckey:key>/", PoomsaeCompetitionDetailView.as_view(), name="poomsae-detail"),
    path("competitions/poomsae/<ckey:key>/", PoomsaeCompetitionDetailView.as_view(), name="poomsae-detail-compat"),

    path("auth/poomsae/<ckey:public_id>/coach-approval/status/",
         PoomsaeCoachApprovalStatusView.as_view(),
         name="poomsae-coach-approval-status"),
    path("auth/poomsae/<ckey:public_id>/coach-approval/approve/",
         PoomsaeCoachApprovalApproveView.as_view(),
         name="poomsae-coach-approval-approve"),

    # ========================= پومسه: ثبت‌نام فردی + prefill =========================
    path(
        "auth/poomsae/<ckey:public_id>/register/self/",
        PoomsaeRegisterSelfView.as_view(),
        name="poomsae-register-self",
    ),
    path("poomsae/<str:key>/my-enrollments/", MyPoomsaeEnrollmentsView.as_view(), name="poomsae-my-enrollments"),
    # ========================= جزئیات مسابقه (GENERIC) =========================
    path("<ckey:key>/", CompetitionDetailAnyView.as_view(), name="competition-detail-any"),
    path("competitions/<ckey:key>/", CompetitionDetailAnyView.as_view(), name="competition-detail-any-compat"),
]
