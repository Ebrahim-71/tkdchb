# payments/gateways/sadad.py
# import requests
# from django.conf import settings
from .base import PaymentGatewayBase

class SadadGateway(PaymentGatewayBase):
    name = "sadad"

    def initiate(self, intent):
        # TODO: وقتی درگاه آماده شد اینجا رو از کامنت دربیار:
        # cfg = self.config or {}
        # MERCHANT_ID = cfg.get("merchant_id")
        # TERMINAL_ID = cfg.get("terminal_id")
        # TERMINAL_KEY = cfg.get("terminal_key")
        # amount_rials = intent.amount * 10  # اگر درگاه ریال می‌خواهد
        # payload = {...}  # بر اساس مستند سداد
        # r = requests.post(SADAD_INIT_URL, json=payload, timeout=20)
        # data = r.json()
        # redirect_url = data["ResData"]["Token"] ...
        # return {"redirect_url": redirect_url, "token": data["ResData"]["Token"]}
        raise NotImplementedError("Sadad not wired yet")

    def verify(self, request):
        # TODO: کد Verify سداد
        raise NotImplementedError("Sadad not wired yet")
