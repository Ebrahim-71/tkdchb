from pathlib import Path
import os
from datetime import timedelta
from dotenv import load_dotenv

# ───────────── BASE / ENV ─────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ───────────── env helpers ─────────────
try:
    from decouple import config as _decouple_config
except Exception:
    _decouple_config = None


def _to_bool(v, default=False):
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in ("1", "true", "t", "yes", "y", "on")


def env_str(key, default=""):
    if _decouple_config:
        try:
            return _decouple_config(key, default=default)
        except Exception:
            return os.getenv(key, default)
    return os.getenv(key, default)


def env_bool(key, default=False):
    return _to_bool(env_str(key, None), default)


def env_int(key, default=0):
    v = env_str(key, None)
    try:
        return int(v) if v is not None else default
    except Exception:
        return default


# ───────────── Base Config ─────────────
SECRET_KEY = env_str("SECRET_KEY", "change-me")
DEBUG = env_bool("DEBUG", False)

ALLOWED_HOSTS = [
    "api.chbtkd.ir",
    "chbtkd.ir",
    "www.chbtkd.ir",
    "127.0.0.1",
    "localhost",
]

SITE_ID = 1
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ───────────── Installed Apps ─────────────
INSTALLED_APPS = [
    "corsheaders",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sites",
    "django_jalali",
    "rest_framework",
    "main",
    "reports",
    "accounts",
    "competitions",
    "payments",
    "azbankgateways",
    "apps.discounts",
]

# ───────────── Middleware ─────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "tkdjango.middlewares.PreflightMiddleware",

    # ✅ این خط را اضافه کن (قبل از CsrfViewMiddleware)
    "tkdjango.middlewares.StripCsrfFromGatewayQueryMiddleware",

    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ───────────── Templates ─────────────
ROOT_URLCONF = "tkdjango.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "tkdjango.wsgi.application"

# ───────────── Database ─────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env_str("DB_NAME", "fltqlsof_chbtkd_db"),
        "USER": env_str("DB_USER", "fltqlsof_tkdadmin"),
        "PASSWORD": env_str("DB_PASSWORD", "@Tkd1404tkdchb"),
        "HOST": "localhost",
        "PORT": "3306",
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            "use_unicode": True,
            "unix_socket": "/var/lib/mysql/mysql.sock",
        },
    }
}

# ───────────── Auth / JWT ─────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ───────────── i18n / TZ ─────────────
LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

# ───────────── Static & Media ─────────────
STATIC_URL = "/static/"
STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# ───────────── Jalali ─────────────
JALALI_DATE_DEFAULTS = {
    "Strftime": {"date": "%Y/%m/%d", "datetime": "%Y/%m/%d _ %H:%M:%S"}
}

# ───────────── CORS / CSRF ─────────────
FRONTEND_URL = env_str("FRONTEND_URL", "https://chbtkd.ir").rstrip("/")

CORS_ALLOWED_ORIGINS = [
    "https://chbtkd.ir",
    "https://www.chbtkd.ir",
]
CORS_ALLOWED_ORIGIN_REGEXES = [r"^https://([a-z0-9-]+\.)?chbtkd\.ir$"]
CORS_ALLOW_CREDENTIALS = True

from corsheaders.defaults import default_headers

CORS_ALLOW_HEADERS = list(default_headers) + ["x-role-group"]
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_EXPOSE_HEADERS = ["Authorization", "Content-Disposition"]

CSRF_TRUSTED_ORIGINS = [
    "https://chbtkd.ir",
    "https://www.chbtkd.ir",
    "https://api.chbtkd.ir",
]

if DEBUG:
    CORS_ALLOWED_ORIGINS += [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    CSRF_TRUSTED_ORIGINS += [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

# ───────────── Security / Cookies ─────────────
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # ✅ دامنه واحد (اگر واقعاً می‌خواهید بین ساب‌دامین‌ها مشترک باشد)
    SESSION_COOKIE_DOMAIN = ".chbtkd.ir"
    CSRF_COOKIE_DOMAIN = ".chbtkd.ir"

    # ✅ مقدار صحیح
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"

    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
else:
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"


# ───────────── Payments (Sadad / BMI) ─────────────
BANK_SADAD_MERCHANT_ID = env_str("BANK_SADAD_MERCHANT_ID", "")
BANK_SADAD_TERMINAL_ID = env_str("BANK_SADAD_TERMINAL_ID", "")
BANK_SADAD_KEY = env_str("BANK_SADAD_KEY", "")

PAYMENTS_ENABLED = env_bool("PAYMENTS_ENABLED", True)
PAYMENTS_DUMMY = env_bool("PAYMENTS_DUMMY", False)

PAY_RETURN_URL = env_str(
    "PAY_RETURN_URL", f"{FRONTEND_URL}/payment/result"
).rstrip("/")

PAY_CALLBACK_URL = env_str(
    "PAY_CALLBACK_URL",
    "https://api.chbtkd.ir/bankgateways/callback/",
).rstrip("/") + "/"

PAYMENTS = {
    "DEFAULT_GATEWAY": "bmi",
    "ENABLED": PAYMENTS_ENABLED,
    "DUMMY": PAYMENTS_DUMMY,
    "RETURN_URL": PAY_RETURN_URL,
    "CALLBACK_URL": PAY_CALLBACK_URL,
    "ALLOWED_CALLBACK_HOSTS": [
        "chbtkd.ir",
        "www.chbtkd.ir",
        "api.chbtkd.ir",
        "localhost",
        "127.0.0.1",
    ],
}

AZ_IRANIAN_BANK_GATEWAYS = {
    "GATEWAYS": {
        "BMI": {
            "MERCHANT_ID": BANK_SADAD_MERCHANT_ID,
            "TERMINAL_ID": BANK_SADAD_TERMINAL_ID,
            "TERMINAL_KEY": BANK_SADAD_KEY,
            "MERCHANT_CODE": BANK_SADAD_MERCHANT_ID,
            "TERMINAL_CODE": BANK_SADAD_TERMINAL_ID,
            "SECRET_KEY": BANK_SADAD_KEY,
        },
    },
    "DEFAULT": "BMI",
    "BANK_PRIORITIES": ["BMI"],
    "CURRENCY": "IRR",
    "IS_SAMPLE_FORM_ENABLE": False,
    "TRACKING_CODE_QUERY_PARAM": "tc",
    "CALLBACK_URL": PAY_CALLBACK_URL,
}

BANK_GATEWAYS = {
    "BMI": {
        "MERCHANT_CODE": BANK_SADAD_MERCHANT_ID,
        "MERCHANT_ID": BANK_SADAD_MERCHANT_ID,
        "TERMINAL_CODE": BANK_SADAD_TERMINAL_ID,
        "TERMINAL_ID": BANK_SADAD_TERMINAL_ID,
        "SECRET_KEY": BANK_SADAD_KEY,
        "TERMINAL_KEY": BANK_SADAD_KEY,
    },
    "DEFAULT": "BMI",
    "CURRENCY": "IRR",
    "IS_SAMPLE_FORM_ENABLE": False,
    "TRACKING_CODE_QUERY_PARAM": "tc",
    "CALLBACK_URL": PAY_CALLBACK_URL,
}

# ───────────── SMS (Melipayamak) ─────────────
POOMSAE_ALLOW_TEST_REG = env_bool("POOMSAE_ALLOW_TEST_REG", True)
SMS_DRY_RUN = env_bool("SMS_DRY_RUN", False)
SMS_ALLOW_IN_DEBUG = env_bool("SMS_ALLOW_IN_DEBUG", True)

MELIPAYAMAK_API_KEY = env_str("MELIPAYAMAK_API_KEY", "")
MELIPAYAMAK_USERNAME = env_str("MELIPAYAMAK_USERNAME", "")
MELIPAYAMAK_PASSWORD = env_str("MELIPAYAMAK_PASSWORD", "")
MELIPAYAMAK_BODY_ID = env_str("MELIPAYAMAK_BODY_ID", "")
MELIPAYAMAK_SENDER = env_str("MELIPAYAMAK_SENDER", "")

# ───────────── Locale tweaks ─────────────
from django.conf.locale.fa import formats as fa_formats

fa_formats.FIRST_DAY_OF_WEEK = 6
FIRST_DAY_OF_WEEK = 6

# ───────────── Logging ─────────────
LOG_DIR = BASE_DIR / "logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {name} :: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        "file": {
            "class": "logging.FileHandler",
            "filename": str(LOG_DIR / "app.log"),
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {"handlers": ["console", "file"], "level": "INFO"},
        "azbankgateways": {"handlers": ["console", "file"], "level": "DEBUG"},
        "payments": {"handlers": ["console", "file"], "level": "DEBUG"},
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
}
