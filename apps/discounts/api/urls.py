from django.urls import path
from .views import ApplyDiscountCodeView

urlpatterns = [
    path('apply/', ApplyDiscountCodeView.as_view(), name='discount-apply'),
]
