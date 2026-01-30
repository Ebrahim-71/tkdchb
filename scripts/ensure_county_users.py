import os, sys
PROJECT_ROOT = "/home/fltqlsof/api.chbtkd.ir"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tkdjango.settings")

import django
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

User = get_user_model()

DEFAULT_PASSWORD = "Chb@12345"
PROVINCE = "چهارمحال و بختیاری"

rows = [
    ("شهرکرد",   "chb_shahrekord",   "shahrekord"),
    ("بروجن",    "chb_borujen",      "borujen"),
    ("فارسان",   "chb_farsan",       "farsan"),
    ("لردگان",   "chb_lordegan",     "lordegan"),
    ("کوهرنگ",   "chb_kohrang",      "kohrang"),
    ("اردل",     "chb_ardal",        "ardal"),
    ("سامان",    "chb_saman",        "saman"),
    ("بن",       "chb_ben",          "ben"),
    ("کیار",     "chb_kiar",         "kiar"),
    ("فرخشهر",   "chb_farrokhshahr", "farrokhshahr"),
]

created, existed = [], []

# گروه اختیاری برای دسترسی‌ها
grp, _ = Group.objects.get_or_create(name="CountyAdmin")

for city, username, slug in rows:
    email = f"{slug}@chbtkd.ir"
    u, made = User.objects.get_or_create(
        username=username,
        defaults={"email": email, "is_staff": True},
    )
    if made:
        u.set_password(DEFAULT_PASSWORD)
        u.is_staff = True
        u.save()
        created.append((city, username))
    else:
        existed.append((city, username))

    u.groups.add(grp)

print("==== County Users ====")
print("Created:")
for c,u in created: print(f"  + {c} -> {u} / {DEFAULT_PASSWORD}")
print("Existed:")
for c,u in existed: print(f"  = {c} -> {u}")
print("Done ✓")
