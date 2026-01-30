from __future__ import annotations
import logging
import re
from typing import Optional
import requests
from django.conf import settings

# -------------- اضافه‌شده‌ها --------------
import os
import unicodedata
import uuid
# -----------------------------------------

logger = logging.getLogger(__name__)

PAYAMAK_ENDPOINT = "https://api.payamak-panel.com/post/send.asmx/SendByBaseNumber"
_RE_NORMALIZE = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _normalize_digits(s: Optional[str]) -> str:
    if s is None:
        return ""
    return str(s).strip().translate(_RE_NORMALIZE)



# ================================
# ارسال پیامک
# ================================
def _is_ok_response(text: str) -> bool:
    """
    پاسخ موفق Payamak:
      - بدنه معمولاً XML است که داخلش یک عدد (MessageId یا کد خطا) می‌آید.
      - عدد مثبت = موفق، عدد منفی = خطا.
    نکته: در XML اول عدد 1.0 برای نسخه می‌آید، برای همین
    باید آخرین عدد موجود در متن را بررسی کنیم، نه اولین.
    """
    t = (text or "").strip()

    # همه اعداد را پیدا کن
    nums = re.findall(r"(-?\d+)", t)
    if not nums:
        return False

    last_num = nums[-1]  # آخرین عدد: همون پیامک آی‌دی یا کد خطا
    return not last_num.startswith("-")



def send_verification_code(phone: str, code: str) -> bool:
    """
    ارسال کد تایید پیامکی از طریق Payamak Panel.
    """
    phone = _normalize_digits(phone)
    code = _normalize_digits(code)

    # اعتبارسنجی اولیه
    if not (phone.isdigit() and phone.startswith("09") and len(phone) == 11):
        logger.warning("send_verification_code: invalid phone: %r", phone)
        return False
    if not (code.isdigit() and 3 <= len(code) <= 6):
        logger.warning("send_verification_code: invalid code: %r", code)
        return False

    # حالت توسعه
    if getattr(settings, "SMS_DRY_RUN", False):
        logger.warning("[DEV SMS] OTP for %s: %s", phone, code)
        return True

    username = getattr(settings, "MELIPAYAMAK_USERNAME", "")
    password = getattr(settings, "MELIPAYAMAK_PASSWORD", "")
    body_id = getattr(settings, "MELIPAYAMAK_BODY_ID", "")

    if not (username and password and body_id):
        logger.error("send_verification_code: missing credentials/body_id")
        return False

    payload = {
        "username": username,
        "password": password,
        "to": phone,
        "text": code,
        "bodyId": body_id,
    }

    try:
        r = requests.post(
            PAYAMAK_ENDPOINT,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
            timeout=20,
        )
        body = (r.text or "").strip()
        ok = (r.status_code == 200) and _is_ok_response(body)

        if ok:
            logger.info("payamak send OK: status=%s message_id=%s", r.status_code, body)
            return True
        else:
            logger.error("payamak send FAILED: status=%s body=%s", r.status_code, body)
            return False

    except requests.RequestException as e:
        logger.exception("payamak send exception: %s", e)
        return False
        
        
def send_reject_signup_sms(phone: str, reason: str) -> bool:
    """
    ارسال پیامک هنگام رد شدن درخواست ثبت نام.
    الگوی ملی پیامک: 395583
    متن الگو:
    درخواست ثبت نام شما ... به دلایل زیر رد شد. {0} هیئت تکواندو استان چهارمحال و بختیاری
    """
    phone = _normalize_digits(phone)
    reason = (reason or "").strip()

    # اعتبارسنجی اولیه
    if not (phone.isdigit() and phone.startswith("09") and len(phone) == 11):
        logger.warning("send_reject_signup_sms: invalid phone: %r", phone)
        return False
    if not reason:
        logger.warning("send_reject_signup_sms: empty reason for phone %s", phone)
        return False

    # حالت توسعه (فقط لاگ، پیامک واقعی ارسال نشود)
    if getattr(settings, "SMS_DRY_RUN", False):
        logger.warning("[DEV SMS] REJECT signup for %s: %s", phone, reason)
        return True

    username = getattr(settings, "MELIPAYAMAK_USERNAME", "")
    password = getattr(settings, "MELIPAYAMAK_PASSWORD", "")
    body_id = getattr(settings, "MELIPAYAMAK_REJECT_BODY_ID", "395583")

    if not (username and password and body_id):
        logger.error("send_reject_signup_sms: missing credentials/body_id")
        return False

    payload = {
        "username": username,
        "password": password,
        "to": phone,
        "text": reason,   # اینجا به جای کد، علت رد را می‌فرستیم تا {0} پر شود
        "bodyId": body_id,
    }

    try:
        r = requests.post(
            PAYAMAK_ENDPOINT,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
            timeout=20,
        )
        body = (r.text or "").strip()
        ok = (r.status_code == 200) and _is_ok_response(body)

        if ok:
            logger.info("payamak reject SMS OK: status=%s body=%s", r.status_code, body)
            return True
        else:
            logger.error("payamak reject SMS FAILED: status=%s body=%s", r.status_code, body)
            return False

    except requests.RequestException as e:
        logger.exception("payamak reject SMS exception: %s", e)
        return False

def send_approve_credentials_sms(phone: str, national_code: str) -> bool:
    """
    ارسال پیامک تأیید:
    {0} = شماره موبایل کاربر
    {1} = کد ملی کاربر
    """
    phone = _normalize_digits(phone)
    national_code = _normalize_digits(national_code)

    # اعتبارسنجی اولیه
    if not (phone.isdigit() and phone.startswith("09") and len(phone) == 11):
        logger.warning("send_approve_credentials_sms: invalid phone: %r", phone)
        return False
    if not (national_code.isdigit() and len(national_code) == 10):
        logger.warning(
            "send_approve_credentials_sms: invalid national_code for phone %s: %r",
            phone, national_code,
        )
        return False

    # حالت توسعه
    if getattr(settings, "SMS_DRY_RUN", False):
        logger.warning(
            "[DEV SMS] APPROVE signup for %s -> username=%s password=%s",
            phone, phone, national_code
        )
        return True

    username_cfg = getattr(settings, "MELIPAYAMAK_USERNAME", "")
    password_cfg = getattr(settings, "MELIPAYAMAK_PASSWORD", "")
    body_id = getattr(settings, "MELIPAYAMAK_APPROVE_BODY_ID", "395884")

    if not (username_cfg and password_cfg and body_id):
        logger.error("send_approve_credentials_sms: missing credentials/body_id")
        return False

    # اینجا هر متغیر قالب، یک پارامتر جداگانه‌ی text است:
    # {0} -> phone
    # {1} -> national_code
    payload = [
        ("username", username_cfg),
        ("password", password_cfg),
        ("to", phone),
        ("text", phone),          # مقدار {0}
        ("text", national_code),  # مقدار {1}
        ("bodyId", body_id),
    ]

    try:
        r = requests.post(
            PAYAMAK_ENDPOINT,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
            timeout=20,
        )
        body = (r.text or "").strip()
        ok = (r.status_code == 200) and _is_ok_response(body)

        if ok:
            logger.info("payamak approve SMS OK: status=%s body=%s", r.status_code, body)
            return True
        else:
            logger.error(
                "payamak approve SMS FAILED: status=%s body=%s",
                r.status_code, body
            )
            return False

    except requests.RequestException as e:
        logger.exception("payamak approve SMS exception: %s", e)
        return False
