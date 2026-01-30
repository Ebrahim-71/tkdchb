# payments/bridge.py
from django.conf import settings

def force_bridge_all_banktype_keys():
    """
    مطمئن می‌کند settings.BANK_GATEWAYS برای کلیدهای زیر مقدار داشته باشد:
      - azbankgateways.models.BankType.BMI
      - azbankgateways.enums.BankType.BMI (اگر موجود باشد)
      - "BMI" (کلید رشته‌ای)
    و DEFAULT را هم به نسخهٔ Enum مدل ست می‌کند.
    """
    bg = getattr(settings, "BANK_GATEWAYS", None)
    if not isinstance(bg, dict):
        return

    # مقدار کانفیگ معتبر را از یکی از منابع بگیر
    val = None
    # 1) اگر قبلاً با کلید رشته‌ای هست
    for k in ("BMI", "bmi", "SADAD", "Sadad", "sadad"):
        v = bg.get(k)
        if isinstance(v, dict) and {"MERCHANT_ID", "TERMINAL_ID", "TERMINAL_KEY"} <= v.keys():
            val = v
            break

    # 2) اگر نبود، از AZ_IRANIAN_BANK_GATEWAYS → SADAD بساز
    if not val:
        az = getattr(settings, "AZ_IRANIAN_BANK_GATEWAYS", {}) or {}
        s = (az.get("GATEWAYS") or {}).get("SADAD", {}) or {}
        if {"MERCHANT_ID", "TERMINAL_ID", "TERMINAL_KEY"} <= s.keys():
            val = {
                "MERCHANT_ID": s["MERCHANT_ID"],
                "TERMINAL_ID": s["TERMINAL_ID"],
                "TERMINAL_KEY": s["TERMINAL_KEY"],
            }

    if not val:
        return  # منبع معتبر نداریم؛ اجازه بده بعداً خطای واضح بده

    # ست کردن همه کلیدهای ممکن:
    try:
        from azbankgateways.models import BankType as ModelBankType
        bg.setdefault(ModelBankType.BMI, val)
        bg["DEFAULT"] = ModelBankType.BMI
    except Exception:
        pass

    try:
        from azbankgateways.enums import BankType as EnumBankType
        bg.setdefault(EnumBankType.BMI, val)
        bg.setdefault(str(EnumBankType.BMI), val)
    except Exception:
        pass

    bg.setdefault("BMI", val)
