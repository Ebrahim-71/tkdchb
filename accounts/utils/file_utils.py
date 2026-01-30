from __future__ import annotations
import os
import re
import unicodedata
import uuid

def clean_filename(filename: str) -> str:
    base, ext = os.path.splitext(filename)
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", base).strip("._")
    if not base:
        base = uuid.uuid4().hex
    return base + ext
