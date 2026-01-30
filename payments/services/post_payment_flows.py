# payments/services/post_payment_flows.py
from __future__ import annotations

import logging

log = logging.getLogger("payments")

def kyorugi_bulk_after_payment(extra: dict, bank_obj):
    """
    extra شامل همه چیز هست:
      - competition_id
      - coach_id / user_id
      - items = لیست بازیکنان
      - unit_fee / amount / discount / ...
    اینجا باید همان ثبت‌نام bulk شما اجرا شود و کارت‌ها ساخته شوند.
    """
    log.info("POSTPAY ky_bulk start bank_id=%s intent=%s items=%s",
             getattr(bank_obj, "id", None),
             extra.get("intent_id") or extra.get("payment_intent_id"),
             len(extra.get("items") or []))

    # TODO: اینجا سرویس/ویوی ثبت‌نام خودتان را صدا بزنید
    # مثال (اسم‌ها را مطابق پروژه خودتان اصلاح کنید):
    # from competitions.services.kyorugi import register_bulk_after_payment
    # register_bulk_after_payment(
    #     competition_id=extra["competition_id"],
    #     coach_id=extra["coach_id"],
    #     items=extra["items"],
    #     bank=bank_obj,
    #     amount=extra.get("amount"),
    # )

    log.info("POSTPAY ky_bulk done bank_id=%s", getattr(bank_obj, "id", None))


def poomsae_team_after_payment(extra: dict, bank_obj):
    log.info("POSTPAY poomsae_team start bank_id=%s", getattr(bank_obj, "id", None))
    # TODO: مشابه بالا
    log.info("POSTPAY poomsae_team done bank_id=%s", getattr(bank_obj, "id", None))
