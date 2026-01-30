import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tkdjango.settings")
import django; django.setup()
from django.contrib.auth import get_user_model

# --- FALLBACK (فقط برای یک‌بار اجرا؛ بعداً حذف کنید) ---
FALLBACK_USERNAME = "tkdadmin"
FALLBACK_EMAIL    = "tkdchb9@gmail.com"
FALLBACK_PASSWORD = "@Tkdchb1404tkd".replace(" ", "")  # اگر فاصله‌ای در اسکرین‌شات بود

# از env بخوان؛ اگر نبود از fallback استفاده کن
u = os.environ.get("DJANGO_SUPERUSER_USERNAME") or FALLBACK_USERNAME
e = os.environ.get("DJANGO_SUPERUSER_EMAIL", "") or FALLBACK_EMAIL
p = os.environ.get("DJANGO_SUPERUSER_PASSWORD") or FALLBACK_PASSWORD

if not u or not p:
    print("ERROR: username/password not provided")
    sys.exit(1)

User = get_user_model()
user, created = User.objects.get_or_create(
    username=u,
    defaults={"email": e, "is_staff": True, "is_superuser": True},
)
user.email = e
user.is_staff = True
user.is_superuser = True
user.set_password(p)
user.save()
print("✓ Superuser", u, "created" if created else "updated")
