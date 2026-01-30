from typing import Optional, Tuple
from apps.discounts.models import DiscountCode

def compute_payable(
    *, base_amount: int,
    code: Optional[str],
    target_type: Optional[str],
    target_id: Optional[int],
) -> Tuple[int, int, Optional[str], str]:
    """
    خروجی: (payable, discount_amount, normalized_code, message)
    """
    if not code:
        return base_amount, 0, None, "no-code"

    try:
        d = DiscountCode.objects.get(code__iexact=code, is_active=True)
    except DiscountCode.DoesNotExist:
        return base_amount, 0, None, "not-found"

    if d.target_type and d.target_id:
        if not (target_type == d.target_type and target_id == d.target_id):
            return base_amount, 0, None, "invalid-target"

    if d.remaining_capacity <= 0:
        return base_amount, 0, None, "capacity-exhausted"

    discount = min(base_amount, d.amount)
    payable = base_amount - discount
    return payable, discount, d.code, "ok"
