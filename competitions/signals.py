from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Enrollment
from .models import _award_points_after_payment  # همان هِلپر تعریف‌شده

@receiver(post_save, sender=Enrollment)
def award_on_manual_paid(sender, instance: Enrollment, created, **kwargs):
    # اگر پرداخت شده و هنوز award ندارد، بعد از commit امتیاز بده
    if instance.is_paid and not hasattr(instance, 'ranking_award'):
        transaction.on_commit(lambda: _award_points_after_payment(instance))
