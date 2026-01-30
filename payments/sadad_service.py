import base64
import logging
import requests
from dataclasses import dataclass
from Crypto.Cipher import DES3
from django.conf import settings
from django.utils import timezone

log = logging.getLogger(__name__)

PAYMENT_REQUEST_URL = "https://sadad.shaparak.ir/VPG/api/v0/Request/PaymentRequest"
PURCHASE_URL        = "https://sadad.shaparak.ir/VPG/Purchase"
VERIFY_URL          = "https://sadad.shaparak.ir/VPG/api/v0/Advice/Verify"

def _pkcs7_pad(b: bytes, block: int = 8) -> bytes:
    pad = block - len(b) % block
    return b + bytes([pad]) * pad

def _key_bytes():
    # کلید از settings → AZ_IRANIAN_BANK_GATEWAYS → SADAD → TERMINAL_KEY
    key_raw = settings.AZ_IRANIAN_BANK_GATEWAYS["GATEWAYS"]["SADAD"]["TERMINAL_KEY"]
    # معمولاً Base64 است؛ اگر نبود، یک‌بار Base64 می‌کنیم تا با هر دو حالت سازگار باشد
    try:
        return base64.b64decode(key_raw, validate=True)
    except Exception:
        return base64.b64decode(base64.b64encode(key_raw.encode("utf-8")))

def _encrypt_3des_b64(plaintext: str) -> str:
    cipher = DES3.new(_key_bytes(), DES3.MODE_ECB)
    enc = cipher.encrypt(_pkcs7_pad(plaintext.encode("utf-8")))
    return base64.b64encode(enc).decode("ascii")

def _sign_for_request(order_id: int, amount_rial: int) -> str:
    terminal_id = settings.AZ_IRANIAN_BANK_GATEWAYS["GATEWAYS"]["SADAD"]["TERMINAL_ID"]
    s = f"{terminal_id};{order_id};{amount_rial}"
    return _encrypt_3des_b64(s)

def _sign_for_verify(token: str) -> str:
    return _encrypt_3des_b64(token)

@dataclass
class SadadConfig:
    merchant_id: str
    terminal_id: str
    callback_url: str  # سرور ما (POST سداد)
    return_url: str    # صفحه‌ی نتیجه در فرانت

def get_cfg() -> SadadConfig:
    return SadadConfig(
        merchant_id=settings.AZ_IRANIAN_BANK_GATEWAYS["GATEWAYS"]["SADAD"]["MERCHANT_ID"],
        terminal_id=settings.AZ_IRANIAN_BANK_GATEWAYS["GATEWAYS"]["SADAD"]["TERMINAL_ID"],
        callback_url=(settings.PAY_CALLBACK_BASE.rstrip("/") + "/sadad/"),
        return_url=settings.PAY_RETURN_URL,
    )

def request_token(*, order_id: int, amount_toman: int, public_id: str) -> dict:
    """PaymentRequest → دریافت Token از سداد."""
    cfg = get_cfg()
    amount_rial = int(amount_toman) * 10
    payload = {
        "MerchantId": cfg.merchant_id,
        "TerminalId": cfg.terminal_id,
        "Amount": amount_rial,
        "OrderId": order_id,
        "LocalDateTime": timezone.now().strftime("%Y/%m/%d %H:%M:%S"),
        "ReturnUrl": cfg.callback_url,       # کال‌بک سرور ما
        "SignData": _sign_for_request(order_id, amount_rial),
        "AdditionalData": public_id,         # برای ردیابی اضافی (اختیاری)
    }
    r = requests.post(PAYMENT_REQUEST_URL, json=payload, timeout=25)
    r.raise_for_status()
    return r.json()

def verify_token(token: str) -> dict:
    """Advice/Verify → تأیید قطعی پرداخت."""
    payload = {"Token": token, "SignData": _sign_for_verify(token)}
    r = requests.post(VERIFY_URL, json=payload, timeout=25)
    r.raise_for_status()
    return r.json()

def purchase_url(token: str) -> str:
    return f"{PURCHASE_URL}?Token={token}"
