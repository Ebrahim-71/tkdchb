from rest_framework import serializers


class ApplyCodeIn(serializers.Serializer):
    code = serializers.CharField(
        max_length=50,
        help_text="کد تخفیف (حساس به حروف نیست)"
    )
    base_amount = serializers.IntegerField(
        min_value=0,
        help_text="مبلغ اولیه قبل از اعمال تخفیف (تومان)"
    )
    target_type = serializers.ChoiceField(
        choices=[('competition', 'مسابقه'), ('seminar', 'سمینار')],
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="نوع هدف تخفیف (اختیاری)"
    )
    target_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="شناسه هدف (اختیاری)"
    )


class ApplyCodeOut(serializers.Serializer):
    valid = serializers.BooleanField(
        help_text="آیا کد معتبر است؟"
    )
    discount_amount = serializers.IntegerField(
        help_text="مقدار تخفیف اعمال‌شده (تومان)"
    )
    payable_amount = serializers.IntegerField(
        help_text="مبلغ قابل پرداخت بعد از تخفیف (تومان)"
    )
    message = serializers.CharField(
        help_text="پیام وضعیت تخفیف (مثلاً ok یا دلیل خطا)"
    )
