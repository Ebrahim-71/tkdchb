# competitions/permissions.py
# -*- coding: utf-8 -*-
from rest_framework.permissions import BasePermission
from accounts.models import UserProfile


def _get_profile(user):
    """اولین پروفایل کاربر را برمی‌گرداند (اگر باشد)."""
    try:
        return UserProfile.objects.filter(user=user).first()
    except Exception:
        return None


def _has_role(user, accepted_roles):
    """
    بررسی می‌کند که کاربر احراز هویت شده و نقشش یکی از نقش‌های مجاز باشد.
    سوپریوزر همیشه مجاز است.
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    prof = _get_profile(user)
    return bool(prof and getattr(prof, "role", None) in accepted_roles)


class IsPlayer(BasePermission):
    message = "برای این عملیات باید با نقش بازیکن وارد شوید."

    def has_permission(self, request, view):
        return _has_role(request.user, {"player", "both"})

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsCoach(BasePermission):
    message = "برای این عملیات باید با نقش مربی وارد شوید."

    def has_permission(self, request, view):
        return _has_role(request.user, {"coach", "both"})

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


# نقش‌های کمکی (در صورت نیاز به استفاده در ویوهای دیگر)

class IsReferee(BasePermission):
    message = "برای این عملیات باید با نقش داور وارد شوید."

    def has_permission(self, request, view):
        return _has_role(request.user, {"referee"})

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsClub(BasePermission):
    message = "برای این عملیات باید با نقش باشگاه وارد شوید."

    def has_permission(self, request, view):
        return _has_role(request.user, {"club"})

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsHeyat(BasePermission):
    message = "برای این عملیات باید با نقش هیئت وارد شوید."

    def has_permission(self, request, view):
        return _has_role(request.user, {"heyat"})

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)
