# tkdjango/urls.py
from __future__ import annotations

import logging

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import approve_edited_profile, mini_profile

from azbankgateways.urls import az_bank_gateways_urls

# ✅ override ها را از payments/views می‌گیریم (منبع واحد)
from payments.views import (
    bankgateways_callback_override,
    go_to_bank_gateway_override,
)

logger = logging.getLogger(__name__)

# ======================================================
# URLPATTERNS
# ======================================================
urlpatterns = [
    path("api/discounts/", include("apps.discounts.api.urls")),

    path("admin/reports/", include(("reports.urls", "reports"), namespace="reports")),
    path("admin/", admin.site.urls),

    path("api/auth/profile/mini/", mini_profile, name="profile-mini"),
    path("api/auth/", include(("accounts.urls", "accounts"), namespace="accounts")),

    path("api/competitions/", include(("competitions.urls", "competitions"), namespace="competitions")),
    path("api/payments/", include(("payments.urls", "payments"), namespace="payments")),
    path("api/", include(("main.urls", "main"), namespace="main")),

    # ✅ overrides (قبل از include اصلی azbankgateways)
    path("bankgateways/callback/", bankgateways_callback_override),
    # اگر نسخه پکیج شما callback/<bank_type>/ را هم صدا می‌زند، نگه دار:
    path("bankgateways/callback/<str:bank_type>/", bankgateways_callback_override),
    path("bankgateways/go-to-bank-gateway/", go_to_bank_gateway_override),
]

# include صحیح azbankgateways (سازگار با همه نسخه‌ها)
bank_urls = az_bank_gateways_urls()

if isinstance(bank_urls, tuple) and len(bank_urls) == 3:
    bank_patterns, bank_app_name, bank_namespace = bank_urls
    urlpatterns += [
        path("bankgateways/", include((bank_patterns, bank_app_name), namespace=bank_namespace)),
    ]
elif isinstance(bank_urls, tuple) and len(bank_urls) == 2:
    bank_patterns, bank_app_name = bank_urls
    urlpatterns += [
        path("bankgateways/", include((bank_patterns, bank_app_name), namespace="azbankgateways")),
    ]
else:
    urlpatterns += [
        path("bankgateways/", include(bank_urls)),
    ]

# alias قدیمی ادمین
urlpatterns += [
    path(
        "admin/accounts/pendingeditprofile/<int:pk>/approve/",
        approve_edited_profile,
        name="accounts_pendingeditprofile_approve",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
