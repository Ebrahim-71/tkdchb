from django.core.management import BaseCommand
from competitions.models import KyorugiCompetition
import jdatetime

FIELDS = ["registration_start", "registration_end", "weigh_date", "draw_date", "competition_date"]

class Command(BaseCommand):
    help = "تبدیل تاریخ‌هایی که به اشتباه جلالی ذخیره شدن به میلادی"

    def handle(self, *args, **kwargs):
        fixed = 0
        for obj in KyorugiCompetition.objects.all():
            changed = False
            for f in FIELDS:
                d = getattr(obj, f)
                if d and d.year < 1700:  # احتمالاً جلالی خامه
                    g = jdatetime.date(d.year, d.month, d.day).togregorian()
                    setattr(obj, f, g)
                    changed = True
            if changed:
                obj.save(update_fields=FIELDS)
                fixed += 1
        self.stdout.write(self.style.SUCCESS(f"{fixed} رکورد اصلاح شد"))
