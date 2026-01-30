from django.urls import path
from . import views

app_name = "reports"

urlpatterns = [
    path("", views.center, name="center"),
    path("users/", views.users_report, name="users"),
    path("competitions/", views.competitions_report, name="competitions"),
    path("finance/", views.finance_report, name="finance"),
    path("export/<str:kind>/", views.export_csv, name="export_csv"),
]
