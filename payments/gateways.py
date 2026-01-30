# payments/gateways.py
"""
درگاه‌های سفارشی یا تستی پروژه
درحال‌حاضر فقط درگاه آزمایشی (fake) برای تست لوکال پیاده‌سازی شده است.
"""

class FakeGateway:
    """درگاه آزمایشی جهت تست جریان پرداخت بدون بانک"""
    def start(self, intent):
        """شروع پرداخت آزمایشی"""
        return {
            "ref_id": f"FAKE-{intent.public_id.upper()}",
            "card_pan": "603799******0000",
        }

    def verify(self, request):
        """تأیید آزمایشی"""
        ok = str(request.GET.get("ok", "1")) == "1"
        return {
            "ok": ok,
            "ref_id": f"FAKE-VERIFY-{request.GET.get('pid', '')}",
            "card_pan": "603799******0000",
        }


def get_gateway(name: str):
    """برگشت شیء درگاه بر اساس نام"""
    name = (name or "").lower()
    if name == "fake":
        return FakeGateway()
    raise ValueError(f"Unknown gateway: {name}")
