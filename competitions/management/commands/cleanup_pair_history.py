# competitions/management/commands/cleanup_pair_history.py
from django.core.management.base import BaseCommand
from competitions.models import FirstRoundPairHistory
import jdatetime

class Command(BaseCommand):
    help = "حذف کامل تاریخچه برخورد دور اول در ابتدای هر سال شمسی"

    def handle(self, *args, **opts):
        today = jdatetime.date.today()
        if today.month == 1 and today.day == 1:
            deleted, _ = FirstRoundPairHistory.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(
                f"Done. Deleted {deleted} history rows for new Persian year {today.year}."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"Not Now — today is {today.strftime('%Y/%m/%d')} (only runs on 01 Farvardin)"
            ))
