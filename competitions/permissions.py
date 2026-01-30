from rest_framework.permissions import BasePermission
from accounts.models import UserProfile


class IsCoach(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and UserProfile.objects.filter(user=request.user, is_coach=True).exists()
        )


class IsPlayer(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and UserProfile.objects.filter(user=request.user, role='player').exists()
        )


class IsCoachOrPlayer(BasePermission):
    """
    هر کاربری که یا مربی باشد یا بازیکن
    (برای جاهایی مثل کارت مسابقه که هر دو باید ببینند)
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        qs = UserProfile.objects.filter(user=request.user)
        return qs.filter(role='player').exists() or qs.filter(is_coach=True).exists()
