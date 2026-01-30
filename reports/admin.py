from django.contrib import admin
from django.shortcuts import redirect
from django.contrib.admin.sites import AlreadyRegistered
from .models import ReportCenter

class ReportCenterAdmin(admin.ModelAdmin):
    list_display = ("__str__",)

    # به‌جای تمپلیت اختصاصی، مستقیم به داشبورد گزارش‌ها ریدایرکت می‌کنیم
    def changelist_view(self, request, extra_context=None):
        return redirect("reports:center")

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

try:
    admin.site.register(ReportCenter, ReportCenterAdmin)
except AlreadyRegistered:
    pass
