from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from ..models import DiscountCode
from .serializers import ApplyCodeIn, ApplyCodeOut


class ApplyDiscountCodeView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        s = ApplyCodeIn(data=request.data)
        s.is_valid(raise_exception=True)
        code = s.validated_data["code"]
        base = s.validated_data["base_amount"]
        ttype = s.validated_data.get("target_type")
        tid = s.validated_data.get("target_id")

        try:
            d = DiscountCode.objects.get(code__iexact=code, is_active=True)
        except DiscountCode.DoesNotExist:
            out = ApplyCodeOut(dict(
                valid=False, discount_amount=0, payable_amount=base, message="کد یافت نشد"
            )).data
            return Response(out, status=status.HTTP_404_NOT_FOUND)

        # اگر کد برای رویداد خاصی تعریف شده، باید مطابقت داشته باشد
        if d.target_type and d.target_id:
            if not (ttype == d.target_type and tid == d.target_id):
                out = ApplyCodeOut(dict(
                    valid=False, discount_amount=0, payable_amount=base, message="کد برای این رویداد معتبر نیست"
                )).data
                return Response(out, status=status.HTTP_400_BAD_REQUEST)

        # بررسی ظرفیت باقی‌مانده
        if d.remaining_capacity <= 0:
            out = ApplyCodeOut(dict(
                valid=False, discount_amount=0, payable_amount=base, message="ظرفیت کد تمام شده است"
            )).data
            return Response(out, status=status.HTTP_400_BAD_REQUEST)

        discount = min(base, d.amount)
        payable = base - discount

        out = ApplyCodeOut(dict(
            valid=True, discount_amount=discount, payable_amount=payable, message="ok"
        )).data
        return Response(out, status=status.HTTP_200_OK)
