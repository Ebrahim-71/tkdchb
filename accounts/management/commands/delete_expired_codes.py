from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from accounts.models import SMSVerification

class Command(BaseCommand):
    help = "حذف کدهای تایید منقضی‌شده از دیتابیس"

    def handle(self, *args, **kwargs):
        expire_time = timezone.now() - timedelta(minutes=3)
        expired = SMSVerification.objects.filter(created_at__lt=expire_time)
        count = expired.count()
        expired.delete()

        self.stdout.write(self.style.SUCCESS(f"{count} کد منقضی حذف شد."))
