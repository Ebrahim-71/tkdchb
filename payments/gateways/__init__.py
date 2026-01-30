# payments/gateways/__init__.py
from django.conf import settings
from .base import PaymentGatewayBase
from .fake import FakeGateway
# from .sadad import SadadGateway  # ← بعداً فعال کن

def get_gateway(name=None) -> PaymentGatewayBase:
    cfg = getattr(settings, "PAYMENTS", {})
    name = name or cfg.get("DEFAULT_GATEWAY", "fake")
    options = cfg.get("GATEWAYS", {}).get(name, {})

    if name == "fake":
        return FakeGateway(options)
    # elif name == "sadad":
    #     return SadadGateway(options)

    # پیش‌فرض
    return FakeGateway(options)
