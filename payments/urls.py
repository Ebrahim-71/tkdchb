# payments/urls.py
# -*- coding: utf-8 -*-
from django.urls import path
from django.http import HttpResponse

def _missing_view(name):
    def _v(*args, **kwargs):
        return HttpResponse(f"Missing view: {name}", status=500)
    return _v

try:
    from .views import create_intent
except Exception:
    create_intent = _missing_view("create_intent")

try:
    from .views import StartPaymentView
except Exception:
    StartPaymentView = None

try:
    from .views import GatewayCallbackView
except Exception:
    GatewayCallbackView = None

try:
    from .views import create_payment_link
except Exception:
    create_payment_link = _missing_view("create_payment_link")

try:
    from .views import SadadBankReturnView
except Exception:
    SadadBankReturnView = None

try:
    from .views import PaymentIntentEnrollmentsView
except Exception:
    PaymentIntentEnrollmentsView = None

# ✅ NEW: endpoint that redirects to frontend with ok=1/0
try:
    from .views import payment_result_redirect
except Exception:
    payment_result_redirect = _missing_view("payment_result_redirect")


app_name = "payments"

urlpatterns = [
    path("intent/", create_intent, name="create_intent"),
]

if PaymentIntentEnrollmentsView:
    urlpatterns += [
        path("intent/<str:pid>/enrollments/", PaymentIntentEnrollmentsView.as_view(), name="intent-enrollments"),
    ]

if StartPaymentView:
    urlpatterns += [
        path("start/<str:public_id>/", StartPaymentView.as_view(), name="start_payment"),
    ]

if GatewayCallbackView:
    urlpatterns += [
        path("callback/<str:gateway_name>/", GatewayCallbackView.as_view(), name="callback"),
    ]

urlpatterns += [
    path("link/<str:public_id>/", create_payment_link, name="create-payment-link"),
]

if SadadBankReturnView:
    urlpatterns += [
        path("bank-return/<str:public_id>/", SadadBankReturnView.as_view(), name="bank_return"),
    ]

urlpatterns += [
    path("result/<str:tc>/", payment_result_redirect, name="payment_result_redirect"),
]
