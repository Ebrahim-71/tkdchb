# -*- coding: utf-8 -*-
import logging
from django.conf import settings
from rest_framework import serializers

log = logging.getLogger("payments")

def _payments_cfg() -> dict:
    return getattr(settings, "PAYMENTS", {}) or {}

def _dummy_enabled() -> bool:
    # اگر هر کدام True باشد، gateway=dummy مجاز است
    if bool(_payments_cfg().get("DUMMY", False)):
        return True
    if bool(getattr(settings, "PAYMENTS_DUMMY", False)):
        return True
    return False
    
    
def _allowed_gateways():
    from django.conf import settings

    cfg = (getattr(settings, "PAYMENTS", {}) or {})
    allowed = set(cfg.get("ALLOWED_GATEWAYS") or [])

    # fallback امن
    if not allowed:
        allowed = {"dummy", "fake", "sadad", "bmi"}  # ✅ bmi اضافه شد

    # اگر با سوئیچ DUMMY کار می‌کنی
    if getattr(settings, "PAYMENTS_DUMMY", False):
        allowed.add("dummy")

    return allowed


def _default_gateway() -> str:
    g = (_payments_cfg().get("DEFAULT_GATEWAY") or "sadad").strip().lower()
    # فقط تایپوها را اصلاح کن
    if g in {"sodad", "saddad", "sadad"}:
        return "sadad"
    if g == "bmi":
        return "bmi"
    return g



class InitiateSerializer(serializers.Serializer):
    competition_id = serializers.IntegerField(required=False)
    competition_public_id = serializers.CharField(required=False, allow_blank=True)

    discount_code = serializers.CharField(required=False, allow_blank=True)

    amount = serializers.IntegerField(min_value=0, required=False)

    # ورودی قدیمی (تومان) برای سازگاری
    amount_toman = serializers.IntegerField(min_value=0, required=False)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    callback_url = serializers.URLField(required=False, allow_blank=True)
    gateway = serializers.CharField(required=False, allow_blank=True)
    style = serializers.CharField(required=False, allow_blank=True, default="kyorugi")

    def validate_discount_code(self, v: str) -> str:
        v = (v or "").strip()
        if not v:
            return ""
        return v.lower()

    def validate_gateway(self, v: str) -> str:
        name = (v or "").strip().lower() or _default_gateway()
        allowed = _allowed_gateways()
        if name not in allowed:
            raise serializers.ValidationError("unsupported gateway")
        return name

    def validate_style(self, v: str) -> str:
        v = (v or "").strip().lower()
        if not v:
            return "kyorugi"
        return v

    def validate(self, attrs):
        pub = attrs.get("competition_public_id")
        if pub is not None:
            attrs["competition_public_id"] = pub.strip()

        # --- Rial/Toman normalization ---
        amount = attrs.get("amount", None)
        amount_toman = attrs.get("amount_toman", None)

        # اگر amount ریال نیامده ولی تومان آمده: تبدیل کن
        if amount is None and amount_toman is not None:
            attrs["amount"] = int(amount_toman or 0) * 10

        # اگر هیچکدام نیامده
        if attrs.get("amount", None) is None:
            raise serializers.ValidationError({"amount": "amount (rial) is required"})

        # اطمینان از int
        attrs["amount"] = int(attrs["amount"] or 0)

        return attrs

    
# لاگ برای اطمینان از لود همین فایل
try:
    log.info(
        "PAYMENTS.SERIALIZER_LOADED allowed=%s DEBUG=%s DUMMY=%s",
        sorted(list(_allowed_gateways())),
        getattr(settings, "DEBUG", False),
        _dummy_enabled(),
    )
except Exception:
    pass
