from __future__ import annotations
import logging, requests
from typing import Any, Dict, Optional, Union
from django.conf import settings

logger = logging.getLogger(__name__)

class SmsError(Exception): ...

def send_verification_code(phone: str, code: Union[str,int]) -> Dict[str, Any]:
    code = str(code)

    # اگر بخواهی در دیباگ هم واقعاً ارسال شود، SMS_ALLOW_IN_DEBUG را False نگذار
    if getattr(settings, "SMS_DRY_RUN", False):
        logger.info("[SMS_DRY_RUN] to=%s code=%s", phone, code)
        return {"ok": True, "provider": "dry_run", "to": phone, "code": code}

    # مسیر پیشنهادی کنسول با API Key
    api_key: Optional[str] = getattr(settings, "MELIPAYAMAK_API_KEY", None)
    if api_key:
        url = "https://console.melipayamak.com/api/verify/"
        payload: Dict[str, Any] = {
            "to": phone,
            "bodyId": str(settings.MELIPAYAMAK_BODY_ID),
            "args": [code],  # اگر الگوی بدنه name-based است، بجاش: {"code": code}
        }
        sender = getattr(settings, "MELIPAYAMAK_SENDER", "")
        if sender:
            payload["from"] = sender
        try:
            r = requests.post(url, json=payload, timeout=20, headers={"x-api-key": api_key})
            if r.status_code == 200 and r.text.strip():
                logger.info("SMS via console OK: %s", r.text[:200])
                return {"ok": True, "provider": "console", "status": r.status_code, "body": r.text}
            logger.error("SMS console failed: %s %s", r.status_code, r.text[:300])
        except Exception as e:
            logger.exception("SMS console exception: %s", e)

    # مسیر قدیمی؛ فقط اگر DNS هاست درست باشد
    user = getattr(settings, "MELIPAYAMAK_USERNAME", "")
    pwd  = getattr(settings, "MELIPAYAMAK_PASSWORD", "")
    if user and pwd:
        url = "https://rest.melipayamak.com/api/VerificationCode/Send"
        data = {
            "username": user, "password": pwd, "to": phone,
            "text": code, "bodyId": str(settings.MELIPAYAMAK_BODY_ID),
        }
        try:
            r = requests.post(url, data=data, timeout=20)
            if r.status_code == 200:
                logger.info("SMS via legacy REST OK: %s", r.text[:200])
                return {"ok": True, "provider": "rest", "status": r.status_code, "body": r.text}
            logger.error("SMS REST failed: %s %s", r.status_code, r.text[:300])
        except Exception as e:
            logger.exception("SMS REST exception: %s", e)

    raise SmsError("ارسال پیامک ناموفق بود (console/REST).")
