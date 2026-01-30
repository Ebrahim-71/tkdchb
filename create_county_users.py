# /home/fltqlsof/api.chbtkd.ir/scripts/create_tkdboards.py
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tkdjango.settings")

import django
django.setup()

from django.contrib.auth import get_user_model
from accounts.models import TkdBoard   # مدل شما

User = get_user_model()

PROVINCE = "چهارمحال و بختیاری"

# شهرها و یوزرنیم‌هایی که قبلاً ساختیم
rows = [
    ("شهرکرد",   "chb_shahrekord"),
    ("بروجن",    "chb_borujen"),
    ("فارسان",   "chb_farsan"),
    ("لردگان",   "chb_lordegan"),
    ("کوهرنگ",   "chb_kohrang"),
    ("اردل",     "chb_ardal"),
    ("سامان",    "chb_saman"),
    ("بن",       "chb_ben"),
    ("کیار",     "chb_kiar"),
    ("فرخشهر",   "chb_farrokhshahr"),
]

created, updated, missing_users = [], [], []

for city, username in rows:
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        missing_users.append((city, username))
        continue

    obj, was_created = TkdBoard.objects.get_or_create(
        user=user,
        defaults={"province": PROVINCE, "city": city, "ranking_total": 0},
    )
    # اگر قبلاً وجود داشت، به‌روزرسانی کن تا شهر/استان صحیح باشد
    if not was_created:
        obj.province = PROVINCE
        obj.city = city
        # اگر فیلد ranking_total دارید و None بود، صفرش کن
        try:
            if obj.ranking_total is None:
                obj.ranking_total = 0
        except Exception:
            pass
        obj.save()
        updated.append((city, username))
    else:
        created.append((city, username))

print("==== TkdBoard upsert result ====")
print("Created:")
for c,u in created: print(f"  + {c}  ->  {u}")
print("Updated:")
for c,u in updated: print(f"  ~ {c}  ->  {u}")
if missing_users:
    print("Missing users (not found):")
    for c,u in missing_users: print(f"  ! {c}  ->  {u}")
print("Done ✓")
