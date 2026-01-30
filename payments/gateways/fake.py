# payments/gateways/fake.py
from django.conf import settings
from .base import PaymentGatewayBase

class FakeGateway(PaymentGatewayBase):
    name = "fake"

    def initiate(self, intent):
        return_url = intent.callback_url or settings.PAYMENTS.get("RETURN_URL", "http://localhost:3000/payment/result")
        # شبیه‌سازی ریدایرکت به صفحه نتیجه‌ی فرانت
        redirect = f"{return_url}?pid={intent.public_id}&status=OK&ref=TEST-{intent.public_id[:8].upper()}"
        return {"redirect_url": redirect, "token": f"FAKE-{intent.public_id}"}

    def verify(self, request):
        # در حالت فیک، موفق برمی‌گردونیم
        ref = request.GET.get("ref") or f"FAKE-{request.GET.get('pid','')[:8].upper()}"
        return {"ok": True, "ref_id": ref, "card_pan": "****-****-****-0000"}
