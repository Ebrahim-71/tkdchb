# accounts/urls.py
from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView, TokenRefreshView, TokenVerifyView
)
from .views import (
    SendCodeAPIView, VerifyCodeAPIView, form_data_view, form_data_player_view,
    RegisterCoachAPIView, approve_pending_user, check_national_code,
    RegisterPlayerAPIView, coaches_by_club_gender, RegisterPendingClubAPIView,
    approve_pending_club, ForgotPasswordSendCodeAPIView,
    ForgotPasswordVerifyAPIView, DashboardCombinedView,
    user_profile_with_form_data_view, UpdateProfilePendingAPIView,
    approve_edited_profile, CoachStudentsAPIView, CoachClubsAPIView,
    UpdateCoachClubsAPIView, AllClubsAPIView, ClubStudentsView, ClubCoachesView,
    ClubAllCoachesView, UpdateClubCoachesView, PendingCoachRequestsView,
    RespondToCoachRequestView, HeyatLoginAPIView, HeyatStudentsAPIView,
    heyat_form_data, HeyatCoachesAPIView, HeyatRefereesAPIView,
    heyat_clubs_list, KyorugiCompetitionListView, UniversalLoginAPIView
)

app_name = "accounts"

urlpatterns = [
    # --- Auth (OTP + Password) ---
    path('send-code/', SendCodeAPIView.as_view(), name='send-code'),
    path('verify-code/', VerifyCodeAPIView.as_view(), name='verify-code'),
    path('login/', UniversalLoginAPIView.as_view(), name='universal-login'),
    path("password/forgot/send/",   ForgotPasswordSendCodeAPIView.as_view(), name="password-forgot-send"),
    path("password/forgot/verify/", ForgotPasswordVerifyAPIView.as_view(),  name="password-forgot-verify"),

    # --- JWT (SimpleJWT) ---
    path("jwt/create/",  TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("jwt/refresh/", TokenRefreshView.as_view(),    name="token_refresh"),
    path("jwt/verify/",  TokenVerifyView.as_view(),     name="token_verify"),

    # --- Profile / Dashboard ---
    path('form-data/',          form_data_view,               name='form-data'),
    path('form-data-player/',   form_data_player_view,        name='form-data-player'),
    path('user-profile-with-options/', user_profile_with_form_data_view, name='user-profile-with-options'),
    path('profile/edit/',       UpdateProfilePendingAPIView.as_view(),   name='edit_profile'),
    path("dashboard/<role>/",   DashboardCombinedView.as_view(),         name="dashboard-combined"),
    path("dashboard/kyorugi/",  KyorugiCompetitionListView.as_view(),    name="kyorugi-list"),

    # --- Coach / Club (App views) ---
    path('coaches/',                 coaches_by_club_gender,             name='coaches-by-club-gender'),
    path('register-coach/',          RegisterCoachAPIView.as_view(),     name='register-coach'),
    path('register-player/',         RegisterPlayerAPIView.as_view(),    name='register-player'),
    path('check-national-code/',     check_national_code,                name='check_national_code'),

    path('register-club/',           RegisterPendingClubAPIView.as_view(), name='register-club'),
    path('admin/approve-club/<int:pk>/', approve_pending_club,             name='approve_pending_club'),

    path("coach/students/",          CoachStudentsAPIView.as_view(),     name="coach-students"),
    path("coach/clubs/",             CoachClubsAPIView.as_view(),        name="coach-clubs"),
    path("coach/update-clubs/",      UpdateCoachClubsAPIView.as_view(),  name="update-coach-clubs"),
    path("all-clubs/",               AllClubsAPIView.as_view(),          name="all-clubs"),
    path("club/students/",           ClubStudentsView.as_view(),         name="club-students"),
    path("club/coaches/",            ClubCoachesView.as_view(),          name="club-coaches"),
    path("club/all-coaches/",        ClubAllCoachesView.as_view(),       name="club-all-coaches"),
    path("club/update-coaches/",     UpdateClubCoachesView.as_view(),    name="update-club-coaches"),

    path("coach/requests/",                  PendingCoachRequestsView.as_view(),           name="coach-requests"),
    path("coach/requests/<int:pk>/respond/", RespondToCoachRequestView.as_view(),          name="respond-coach-request"),

    # --- Heyat (Board) ---
    path('login/board/',      HeyatLoginAPIView.as_view(),   name='board-login'),
    path("heyat/students/",   HeyatStudentsAPIView.as_view(), name="heyat-students"),
    path("heyat/form-data/",  heyat_form_data,                name="heyat-form-data"),
    path('heyat/coaches/',    HeyatCoachesAPIView.as_view(),  name="heyat-coaches"),
    path("heyat/referees/",   HeyatRefereesAPIView.as_view(), name="heyat-referees"),
    path("heyat/clubs/",      heyat_clubs_list,               name="heyat-clubs"),

    # --- Admin approvals in app namespace ---
    path('approve/<int:pk>/',          approve_pending_user,   name='approve_pending_user'),
    path('admin/approve-edit/<int:pk>/', approve_edited_profile, name='approve_edited_profile'),
]
