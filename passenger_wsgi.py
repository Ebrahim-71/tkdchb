# ~/api.chbtkd.ir/passenger_wsgi.py
import os
import sys
sys.stderr.write(f"### LOADED passenger_wsgi FROM: {__file__} ###\n")
sys.stderr.flush()



BASE_DIR = os.path.dirname(__file__)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tkdjango.settings")
from tkdjango.wsgi import application
