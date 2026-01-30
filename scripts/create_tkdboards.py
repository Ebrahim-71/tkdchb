# -*- coding: utf-8 -*-
import os, sys
from django.db import IntegrityError

PROJECT_ROOT = "/home/fltqlsof/api.chbtkd.ir"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tkdjango.settings")

import django
django.setup()

from django.contrib.auth import get_user_model
from accounts.models import TkdBoard

User = get_user_model()

PROVINCE = "چهارمحال و بختیاری"
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

created, updated, missing_users, errors = [], [], [], []

for city, username in rows:
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        missing_users.append((city, username))
        continue

    name = f"هیئت {city}"

    try:
        obj, was_created = TkdBoard.objects.get_or_create(
            user=user,
            defaults={
                "name": name,
                "province": PROVINCE,
                "city": city,
                "ranking_total": 0,
            },
        )
        if was_created:
            created.append((city, username))
        else:
            # آپدیت در صورت وجود
            obj.name = name
            obj.province = PROVINCE
            obj.city = city
            if obj.ranking_total is None:
                obj.ranking_total = 0
            obj.save()
            updated.append((city, username))

    except IntegrityError as e:
        errors.append((city, username, f"IntegrityError: {e}"))
    except Exception as e:
        errors.append((city, username, str(e)))

print("==== TkdBoard upsert result ====")
print("Created:")
for c,u in created: print(f"  + {c}  ->  {u}")
print("Updated:")
for c,u in updated: print(f"  ~ {c}  ->  {u}")
if missing_users:
    print("Missing users:")
    for c,u in missing_users: print(f"  ! {c}  ->  {u}")
if errors:
    print("Errors:")
    for c,u,msg in errors: print(f"  x {c} / {u}: {msg}")
print("Done ✓")
