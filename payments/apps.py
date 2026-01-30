# payments/apps.py
from django.apps import AppConfig

class PaymentsConfig(AppConfig):
    name = "payments"

    def ready(self):
        # در لحظه‌ی بوت، پل‌زدن کلیدها را انجام بده
        try:
            from .bridge import force_bridge_all_banktype_keys
            force_bridge_all_banktype_keys()
        except Exception:
            # اگر چیزی شد، نگذار بوت بترکه
            pass
