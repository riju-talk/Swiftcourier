import warnings

# apscheduler 3.10 is pulled in transitively by phonepe-sdk (which pins it) and
# imports the deprecated pkg_resources at module load. We don't use apscheduler
# directly and can't unpin it, so silence just that one warning to keep
# `manage.py` output readable.
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API",
    category=UserWarning,
    module="apscheduler",
)

from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv
from phonepe.sdk.pg.env import Env
from django.core.exceptions import ImproperlyConfigured
import os


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Real environment variables (systemd EnvironmentFile, container env, CI secrets)
# MUST win over a checked-out .env - otherwise a stale dev .env on the prod box
# silently forces DEBUG=True / dev secrets. .env only fills what the env doesn't set.
load_dotenv(dotenv_path=BASE_DIR / ".env", override=False)

# Vercel sets VERCEL=1 at build and runtime. Serverless: read-only filesystem
# (except /tmp), no Redis/Celery workers, short-lived processes.
IS_VERCEL = bool(os.getenv("VERCEL"))

# ---- DEMO-ONLY hardcoded fallbacks (used ONLY on Vercel, and only when the
# matching env var is unset; real env vars always win). ROTATE ALL OF THESE and
# delete this block before production - they live in git history.
_DEMO_DATABASE_URL = (
    "postgresql://neondb_owner:npg_OehmgE0UN6rl@"
    "ep-dark-brook-b54vrcd3-pooler.c-7.us-east-2.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)
_DEMO_SECRET_KEY = "pCiFwLAxSL-vwHv-FFWp87zi9TODGIgXoonuMljJ6w-jSEE_FISv-hC9u8nefmQaY00"
_DEMO_ADMIN_PASSWORD = "mFn32Qj6HfSCnwE8IK6aCltx"

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.1/howto/deployment/checklist/

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", default="False" if IS_VERCEL else "True") == "True"

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY") or (_DEMO_SECRET_KEY if IS_VERCEL else None)
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "xKQ4azxkpTqa7Jjv4i7rlyIllTwFImhr"  # dev-only fallback, never used when DEBUG=False
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY environment variable must be set when DEBUG=False"
        )

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")

# Single knob for "what domain are we". Set PRIMARY_HOST (e.g. "app.example.com")
# once the org settles on a domain and it flows into CSRF/CORS trusted origins,
# the Shopify app URL, and the default From address. Everything still falls back
# to the historical idiotship.tech values when it is unset, so nothing breaks
# today. Bare host, no scheme.
PRIMARY_HOST = os.getenv("PRIMARY_HOST", "").strip().replace("https://", "").replace("http://", "").rstrip("/")
if PRIMARY_HOST and PRIMARY_HOST not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(PRIMARY_HOST)
if IS_VERCEL:
    ALLOWED_HOSTS.append(".vercel.app")

# Production hardening (env-overridable; secure-by-default once DEBUG=False).
# HSTS starts at 1 hour rather than the usual 1 year so a botched HTTPS rollout
# doesn't lock browsers out of the site for a full year - raise it once HTTPS is confirmed stable.
SECURE_SSL_REDIRECT = (
    os.getenv("SECURE_SSL_REDIRECT", default="False" if DEBUG else "True") == "True"
)
SESSION_COOKIE_SECURE = (
    os.getenv("SESSION_COOKIE_SECURE", default="False" if DEBUG else "True") == "True"
)
CSRF_COOKIE_SECURE = (
    os.getenv("CSRF_COOKIE_SECURE", default="False" if DEBUG else "True") == "True"
)
SECURE_HSTS_SECONDS = int(
    os.getenv("SECURE_HSTS_SECONDS", "").strip() or ("0" if DEBUG else "3600")
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG


if not DEBUG:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from django.core.exceptions import DisallowedHost

    def before_send(event, hint):
        # Ignore DisallowedHost errors
        if isinstance(hint.get("exc_info"), tuple):
            exc_type, exc_value, _ = hint["exc_info"]
            if isinstance(exc_value, DisallowedHost):
                return None  # Returning None will ignore the event
        return event

    # from django.core.exceptions import DisallowedHost
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[
            DjangoIntegration(),
        ],
        # Do NOT ship PII (emails, IPs, request bodies) to Sentry by default;
        # opt in per-environment only if the DPA / privacy review allows it.
        send_default_pii=os.getenv("SENTRY_SEND_PII", "False") == "True",
        # Capture 10% of transactions for tracing
        traces_sample_rate=0.1,
        _experiments={
            # Set continuous_profiling_auto_start to True
            # to automatically start the profiler on when
            # possible.
            "continuous_profiling_auto_start": True,
        },
        environment="development" if DEBUG else "production",
        before_send=before_send,  # Add the before_send callback
    )


# (S3 / media storage config lives in the "Storage" section further down.)


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "storages",
    "tailwind",
    "theme",
    "import_export",
    "django_tasks",
    "django_tasks.backends.database",
    "django.contrib.humanize",
    "corsheaders",
    "django_crontab",
    "django_celery_results",
    "django_celery_beat",
    "shopify_integration.apps.ShopifyIntegrationConfig",
]

EXTERNAL_APPS = [
    "superadmin_panel.apps.SuperadminPanelConfig",
    "admin_panel.apps.AdminPanelConfig",
    "user_panel.apps.UserPanelConfig",
    "account.apps.AccountConfig",
    "wallet.apps.WalletConfig",
    "order_manager.apps.OrderManagerConfig",
    "xpressbees_integration.apps.XpressbeesIntegrationConfig",
    "lastmiles_integration.apps.LastmilesIntegrationConfig",
    "zippyy_integration.apps.ZippyyIntegrationConfig",
    "purple_drone_integration.apps.PurpleDroneIntegrationConfig",
    "parcelx_integration.apps.ParcelxIntegrationConfig",
    "shiprocket_integration.apps.ShiprocketIntegrationConfig",
    "fship_integration.apps.FshipIntegrationConfig",
    "bdl_integration.apps.BdlIntegrationConfig",
    "smartship_integration.apps.SmartshipIntegrationConfig",
    "rapidshyp_integration.apps.RapidshypIntegrationConfig",
    "rapidshyp_new_integration.apps.RapidshypNewIntegrationConfig",
    "nimbuspost_integration.apps.NimbuspostIntegrationConfig",
    # pincode serviceability + rate calculator (no DB models)
    "serviceability.core.apps.ServiceabilityConfig",
    "rate_calculator.apps.RateCalculatorConfig",
    # customer notifications (Twilio; disabled per-user until configured)
    "whatsapp_integration.apps.WhatsappIntegrationConfig",
    "SMS_integration.apps.SMSIntegrationConfig",
]


INSTALLED_APPS += EXTERNAL_APPS


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",  # must be first
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serve static files (prod)
    "corsheaders.middleware.CorsMiddleware",  # before CommonMiddleware
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_auto_logout.middleware.auto_logout",
]

# Behind an ALB / nginx doing TLS termination, trust the proto header so
# request.is_secure() is correct (otherwise SECURE_SSL_REDIRECT loops forever).
if IS_VERCEL or os.getenv("TRUST_PROXY_SSL_HEADER", default="False" if DEBUG else "True") == "True":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

ROOT_URLCONF = "swiftcourier.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "swiftcourier.context_processors.ctx_processor",
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "swiftcourier.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.1/ref/settings/#databases

_DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or (
    _DEMO_DATABASE_URL if IS_VERCEL else ""
)

if _DATABASE_URL:
    # Single-URL config (Vercel + Neon). Takes precedence over DATABASE_ENGINE.
    # Neon's "-pooler" host is PgBouncer in transaction mode, so: no persistent
    # connections, no server-side cursors, and no startup `options` (PgBouncer
    # rejects them). Run migrations against the direct (non-pooler) host.
    from urllib.parse import parse_qsl, unquote, urlparse

    _u = urlparse(_DATABASE_URL)
    _pooled = "-pooler" in (_u.hostname or "")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(_u.path.lstrip("/")),
            "USER": unquote(_u.username or ""),
            "PASSWORD": unquote(_u.password or ""),
            "HOST": _u.hostname,
            "PORT": str(_u.port or 5432),
            "CONN_MAX_AGE": int(os.getenv("DATABASE_CONN_MAX_AGE", "0")),
            "DISABLE_SERVER_SIDE_CURSORS": _pooled,
            "OPTIONS": {
                "sslmode": "require",
                "connect_timeout": int(os.getenv("DATABASE_CONNECT_TIMEOUT", "10")),
                **dict(parse_qsl(_u.query)),
            },
        }
    }
elif os.getenv("DATABASE_ENGINE") == "django.db.backends.postgresql":
    # AWS RDS (PostgreSQL). Notes:
    #  - CONN_MAX_AGE keeps connections alive between requests (RDS charges a real
    #    TCP+TLS handshake per connect); pair with a PgBouncer/RDS Proxy in front
    #    when running many gunicorn/celery workers.
    #  - CONN_HEALTH_CHECKS re-validates a pooled connection before reuse so a
    #    dropped RDS connection surfaces as a retry, not a 500.
    #  - sslmode=require: RDS should have `rds.force_ssl=1`; verify-full is better
    #    once the RDS CA bundle is shipped (set DATABASE_SSL_ROOT_CERT).
    #  - statement_timeout: no single web query may run longer than 15s.
    _db_options = {
        "sslmode": os.getenv("DATABASE_SSLMODE", "require"),
        "connect_timeout": int(os.getenv("DATABASE_CONNECT_TIMEOUT", "10")),
        "options": f"-c statement_timeout={os.getenv('DATABASE_STATEMENT_TIMEOUT_MS', '15000')}",
    }
    # RDS CA bundle: use an explicit path from the env, otherwise fall back to the
    # public Amazon RDS global bundle committed at the repo root. When a cert is
    # available we verify the server identity (verify-full), not just encrypt.
    _rds_ca = os.getenv("DATABASE_SSL_ROOT_CERT") or (
        str(BASE_DIR / "rds-ca-bundle.pem")
        if (BASE_DIR / "rds-ca-bundle.pem").exists()
        else ""
    )
    if _rds_ca:
        _db_options["sslmode"] = os.getenv("DATABASE_SSLMODE", "verify-full")
        _db_options["sslrootcert"] = _rds_ca

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DATABASE_NAME"),
            "USER": os.getenv("DATABASE_USER"),
            "PASSWORD": os.getenv("DATABASE_PASSWORD"),
            "HOST": os.getenv("DATABASE_HOST"),
            "PORT": os.getenv("DATABASE_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("DATABASE_CONN_MAX_AGE", "60")),
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": _db_options,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {"timeout": 20},
        }
    }


# Password validation
# https://docs.djangoproject.com/en/4.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


NPM_BIN_PATH = os.getenv("NPM_BIN_PATH", default="C:\\Program Files\\nodejs\\npm.cmd")

# Internationalization
# https://docs.djangoproject.com/en/4.1/topics/i18n/

LANGUAGE_CODE = "en-us"

# before changing see CELERY_TIMEZONE
TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True


# Default primary key field type
# https://docs.djangoproject.com/en/4.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TAILWIND_APP_NAME = "theme"
TAILWIND_CSS_PATH = "assets/css/styles.css"

AUTH_USER_MODEL = "account.User"


# email settings
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", default="True") == "True"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", default="False") == "True"
EMAIL_PORT = int(os.getenv("EMAIL_PORT", default="587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    default=EMAIL_HOST_USER
    or (f"noreply@{PRIMARY_HOST}" if PRIMARY_HOST else "noreply@idiotship.tech"),
)


# custom settings
MAXIMUM_WALLET_BALANCE = float(os.getenv("MAXIMUM_WALLET_BALANCE", default="1000000"))
MINIMUM_BALANCE_ADD_AMOUNT = int(os.getenv("MINIMUM_BALANCE_ADD_AMOUNT", default="100"))


# PhonePe credentials and environment
PHONEPE_CLIENT_ID = os.getenv("PHONEPE_CLIENT_ID", default="")
PHONEPE_CLIENT_SECRET = os.getenv("PHONEPE_CLIENT_SECRET", default="")
PHONEPE_CLIENT_VERSION = 1
PHONEPE_ENV = Env.SANDBOX if DEBUG else Env.PRODUCTION
PHONEPE_SHOULD_PUBLISH_EVENTS = False


# ----------------------------------------------------------------------------
# Storage
# ----------------------------------------------------------------------------
# Static: always WhiteNoise (served by gunicorn, compressed, far-future cached;
#         run `collectstatic` on every deploy).
# Media (user uploads - KYC docs, labels, barcodes, logos, invoices): local disk
#       in dev; S3 in prod once AWS_STORAGE_BUCKET_NAME is set. Local `media/` is
#       wrong on EC2 - it is lost on redeploy and not shared between the web
#       process, celery workers and the db_worker.
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static_prod"
# Serve straight from app/STATICFILES_DIRS when static_prod/ was not built (Vercel).
WHITENOISE_USE_FINDERS = True

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media/"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# S3 bucket for media, e.g. AWS_STORAGE_BUCKET_NAME="swift-courier"
# (arn:aws:s3:::swift-courier). Leave unset to keep media on local disk.
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "").strip()
AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "ap-south-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID") or None
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY") or None

if AWS_STORAGE_BUCKET_NAME:
    AWS_S3_CUSTOM_DOMAIN = os.getenv(
        "AWS_S3_CUSTOM_DOMAIN",
        f"{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com",
    )
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None  # modern buckets disable ACLs - use a bucket policy
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    # Signed URLs by default (bucket can stay fully private / "Block all public
    # access" ON). Set AWS_QUERYSTRING_AUTH="False" in env + add a public-read
    # bucket policy if you want plain https://<domain>/media/... URLs instead.
    AWS_QUERYSTRING_AUTH = (
        os.getenv("AWS_QUERYSTRING_AUTH", "True") == "True"
    )
    if not AWS_QUERYSTRING_AUTH:
        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/media/"
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {"location": "media"},
    }


# site settings
# SITE_URL = os.getenv("SITE_URL", default="http://localhost:8000")
LOGIN_URL = "account:signin"

# Assuming BASE_DIR is already defined in your settings
LOGS_DIR = "/tmp/logs" if IS_VERCEL else os.path.join(BASE_DIR, "logs")

# Create the logs directory if it doesn't exist
os.makedirs(LOGS_DIR, exist_ok=True)

# logger
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "verbose": {
            # Output: 2025-01-16 11:00:00 [DEBUG] /path/project/app/views.py : Debug message here
            "format": "{asctime} [{levelname}] {pathname}:{lineno} {message}",
            "style": "{",
        },
        "simple": {
            # Output: 2025-01-16 11:00:00 [DEBUG] /path/project/app/views.py : Debug message here
            "format": "{asctime} [{levelname}] {pathname}:{lineno} {message}",
            "style": "{",
        },
    },
    "handlers": {
        # Logs all messages with DEBUG or higher to debug.log
        "debug_file": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOGS_DIR, "debug.log"),
            "maxBytes": 5 * 1024 * 1024,  # 5 MB per file
            "backupCount": 5,  # Keep last 5 logs
            "formatter": "verbose",
        },
        # Logs all messages with ERROR or higher to error.log
        "error_file": {
            "level": "ERROR",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOGS_DIR, "error.log"),
            # 5 MB per file
            "maxBytes": 5 * 1024 * 1024,
            # Keep last 5 logs
            "backupCount": 5,
            "formatter": "verbose",
        },
        "cronjob_logs": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOGS_DIR, "cronjobs.log"),
            # 5 MB per file
            "maxBytes": 5 * 1024 * 1024,
            # Keep last 5 logs
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "loggers": {
        # Single logger for all levels
        "my-logger": {
            "handlers": ["debug_file", "error_file"],
            "level": "DEBUG",  # Capture all levels
            "propagate": False,
        },
        "cronjob-logger": {
            "handlers": ["cronjob_logs"],
            "level": "DEBUG",  # Capture all levels
            "propagate": False,
        },
    },
}

TMP_DIR = Path("/tmp/swiftcourier") if IS_VERCEL else BASE_DIR / "tmp"  # Vercel FS is read-only except /tmp
TMP_DIR.mkdir(parents=True, exist_ok=True)

XPRESSBEES_USERNAME = os.getenv("XPRESSBEES_USERNAME")
XPRESSBEES_PASSWORD = os.getenv("XPRESSBEES_PASSWORD")

ZIPPYY_EMAIL = os.getenv("ZIPPYY_EMAIL")
ZIPPYY_PASSWORD = os.getenv("ZIPPYY_PASSWORD")


JIFFY_DELHIVERY_500GM_EMAIL = os.environ.get("JIFFY_DELHIVERY_500GM_EMAIL")
JIFFY_DELHIVERY_500GM_PASSWORD = os.environ.get("JIFFY_DELHIVERY_500GM_PASSWORD")

JIFFY_DTDC_500GM_EMAIL = os.environ.get("JIFFY_DTDC_500GM_EMAIL")
JIFFY_DTDC_500GM_PASSWORD = os.environ.get("JIFFY_DTDC_500GM_PASSWORD")

JIFFY_BLUEDART_500GM_EMAIL = os.environ.get("JIFFY_BLUEDART_500GM_EMAIL")
JIFFY_BLUEDART_500GM_PASSWORD = os.environ.get("JIFFY_BLUEDART_500GM_PASSWORD")

JIFFY_EKART_500GM_EMAIL = os.environ.get("JIFFY_EKART_500GM_EMAIL")
JIFFY_EKART_500GM_PASSWORD = os.environ.get("JIFFY_EKART_500GM_PASSWORD")

JIFFY_SHADOWFAX_500GM_EMAIL = os.environ.get("JIFFY_SHADOWFAX_500GM_EMAIL")
JIFFY_SHADOWFAX_500GM_PASSWORD = os.environ.get("JIFFY_SHADOWFAX_500GM_PASSWORD")

JIFFY_AMAZON_500GM_EMAIL = os.environ.get("JIFFY_AMAZON_500GM_EMAIL")
JIFFY_AMAZON_500GM_PASSWORD = os.environ.get("JIFFY_AMAZON_500GM_PASSWORD")

JIFFY_XPRESSBEES_500GM_EMAIL = os.environ.get("JIFFY_XPRESSBEES_500GM_EMAIL")
JIFFY_XPRESSBEES_500GM_PASSWORD = os.environ.get("JIFFY_XPRESSBEES_500GM_PASSWORD")


LASTMILES_EMAIL = os.getenv("LASTMILES_EMAIL")
LASTMILES_PASSWORD = os.getenv("LASTMILES_PASSWORD")

PURPLEDRONE_HOST = os.environ.get(
    "PURPLEDRONE_HOST", "https://backend-uat.fulfillzy.com"
)
PURPLEDRONE_USERNAME = os.environ.get("PURPLEDRONE_USERNAME", "")
PURPLEDRONE_PASSWORD = os.environ.get("PURPLEDRONE_PASSWORD", "")
PURPLEDRONE_CLIENT_CODE = os.environ.get("PURPLEDRONE_CLIENT_CODE", "RATEDANE")

PARCELX_ACCESS_KEY = os.environ.get("PARCELX_ACCESS_KEY", "")
PARCELX_SECRET_KEY = os.environ.get("PARCELX_SECRET_KEY", "")

# NimbusPost partner API credentials (Settings -> API in their dashboard).
# Used by nimbuspost_integration.nimbuspost to log in and push/track/cancel
# shipments. NIMBUS_POST_URL is the login endpoint; the rest of the API is
# derived from its host in nimbuspost_integration/constants.py.
NIMBUS_POST_URL = os.environ.get(
    "NIMBUS_POST_URL", "https://api.nimbuspost.com/v1/users/login"
)
NIMBUS_API_EMAIL = os.environ.get("NIMBUS_API_EMAIL", "")
NIMBUS_API_PASS = os.environ.get("NIMBUS_API_PASS", "")

# The "Secret" configured on the webhook in the NimbusPost partner dashboard
# (Settings -> Webhooks). Used to verify the X-Hmac-Sha256 header NimbusPost
# sends with every webhook call. Left blank = signature check is skipped,
# matching NimbusPost's own "no hash generated if left blank" behavior.
# Accepts either NIMBUS_WEBHOOK_SECRET (current .env name) or the older
# NIMBUSPOST_WEBHOOK_SECRET spelling.
NIMBUSPOST_WEBHOOK_SECRET = os.environ.get("NIMBUS_WEBHOOK_SECRET") or os.environ.get(
    "NIMBUSPOST_WEBHOOK_SECRET", ""
)

# Twilio credentials for customer notifications (whatsapp_integration /
# SMS_integration). The provider calls Twilio's REST API directly with `requests`
# (no SDK). Leave blank to keep messaging inert: with no creds every send is
# recorded as "failed: Twilio credentials missing" and nothing goes out. Sending
# is ALSO gated per-merchant by WhatsAppSettings.enabled / SMSSettings.enabled
# (both default False), so notifications stay off until a merchant opts in.
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "")
TWILIO_SMS_NUMBER = os.environ.get("TWILIO_SMS_NUMBER", "") or os.environ.get(
    "TWILIO_PHONE_NUMBER", ""
)
# Master kill-switch for the Order.update_status -> notification dispatch. When
# False (default) no WhatsApp/SMS task is ever queued, regardless of per-user
# settings - flip to True in the env once Twilio is configured and verified.
CUSTOMER_NOTIFICATIONS_ENABLED = (
    os.environ.get("CUSTOMER_NOTIFICATIONS_ENABLED", "False") == "True"
)

SHIPROCKET_ATS_250GM_EMAIL = os.environ.get("SHIPROCKET_ATS_250GM_EMAIL", "")
SHIPROCKET_ATS_250GM_PASSWORD = os.environ.get("SHIPROCKET_ATS_250GM_PASSWORD", "")

SHIPROCKET_ATS_500GM_EMAIL = os.environ.get("SHIPROCKET_ATS_500GM_EMAIL", "")
SHIPROCKET_ATS_500GM_PASSWORD = os.environ.get("SHIPROCKET_ATS_500GM_PASSWORD", "")

SHIPROCKET_BD_500GM_EMAIL = os.environ.get("SHIPROCKET_BD_500GM_EMAIL", "")
SHIPROCKET_BD_500GM_PASSWORD = os.environ.get("SHIPROCKET_BD_500GM_PASSWORD", "")

SHIPROCKET_BD_AIR_500GM_EMAIL = os.environ.get("SHIPROCKET_BD_AIR_500GM_EMAIL")
SHIPROCKET_BD_AIR_500GM_PASSWORD = os.environ.get("SHIPROCKET_BD_AIR_500GM_PASSWORD")

SHIPROCKET_BD_2KG_EMAIL = os.environ.get("SHIPROCKET_BD_2KG_EMAIL", "")
SHIPROCKET_BD_2KG_PASSWORD = os.environ.get("SHIPROCKET_BD_2KG_PASSWORD", "")

SHIPROCKET_EK_500GM_EMAIL = os.environ.get("SHIPROCKET_EK_500GM_EMAIL", "")
SHIPROCKET_EK_500GM_PASSWORD = os.environ.get("SHIPROCKET_EK_500GM_PASSWORD", "")

SHIPROCKET_EK_2KG_EMAIL = os.environ.get("SHIPROCKET_EK_2KG_EMAIL", "")
SHIPROCKET_EK_2KG_PASSWORD = os.environ.get("SHIPROCKET_EK_2KG_PASSWORD", "")

SHIPROCKET_DV_2KG_EMAIL = os.environ.get("SHIPROCKET_DV_2KG_EMAIL", "")
SHIPROCKET_DV_2KG_PASSWORD = os.environ.get("SHIPROCKET_DV_2KG_PASSWORD", "")

SHIPROCKET_DV_250GM_EMAIL = os.environ.get("SHIPROCKET_DV_250GM_EMAIL", "")
SHIPROCKET_DV_250GM_PASSWORD = os.environ.get("SHIPROCKET_DV_250GM_PASSWORD", "")

SHIPROCKET_DV_500GM_EMAIL = os.environ.get("SHIPROCKET_DV_500GM_EMAIL", "")
SHIPROCKET_DV_500GM_PASSWORD = os.environ.get("SHIPROCKET_DV_500GM_PASSWORD", "")

SHIPROCKET_DV_1KG_EMAIL = os.environ.get("SHIPROCKET_DV_1KG_EMAIL", "")
SHIPROCKET_DV_1KG_PASSWORD = os.environ.get("SHIPROCKET_DV_1KG_PASSWORD", "")

FSHIP_TOKEN = os.environ.get("FSHIP_TOKEN")

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")


MAX_ORDER_DOWNLOAD_LIMIT = 2000


TASKS = {"default": {"BACKEND": "django_tasks.backends.database.DatabaseBackend"}}


SITE_SETTINGS = {
    "site": {
        "SITE_LINK": os.getenv("SITE_LINK", default="http://localhost:8000/"),
        "WP_SITE_LINK": os.getenv("WP_SITE_LINK", default="http://localhost:8000/"),
    },
    "email": {
        "expire_in": 10,  # in days
        "otp_length": 6,
    },
}


AUTO_LOGOUT = {
    "IDLE_TIME": timedelta(hours=1),
    "MESSAGE": "The session has expired. Please login again to continue.",
}

AGGREGATOR_BLACKLISTED_TEXTS = [
    # Couriers
    "amazon",
    "Amazon",
    "delhivery",
    "Delhivery",
    "DelhiVery",
    "bluedart",
    "Bluedart",
    "BlueDart",
    "BlueDart",
    "dtdc",
    "DTDC",
    "ekart",
    "Ekart",
    "eKart",
    "EKart",
    "ecom express",
    "Ecom express",
    "Ecom Express",
    "EcomExpress",
    "gati",
    "Gati",
    "dhl",
    "DHL",
    "fedex",
    "FedEx",
    "india post",
    "India post",
    "India Post",
    "safexpress",
    "Safexpress",
    "SafeXpress",
    # Aggregators
    "rapidshyp",
    "Rapidshyp",
    "RapidShyp",
    "bdl",
    "BoxdLogistics",
    "fship",
    "Fship",
    "Fship",
    "jiffy",
    "Jiffy",
    "lastmile",
    "Lastmile",
    "LastMile",
    "parcelx",
    "Parcelx",
    "ParcelX",
    "purpledrone",
    "Purpledrone",
    "PurpleDrone",
    "shiprocket",
    "Shiprocket",
    "ShipRocket",
    "shadowfax",
    "Shadowfax",
    "ShadowFax",
    "tci express",
    "Tci Express",
    "TCI Express",
    "xpressbees",
    "Xpressbees",
    "XpressBees",
    "zippyy",
    "Zippyy",
    "nimbuspost",
    "Nimbuspost",
    "NimbusPost",
    "nimbus post",
    "Nimbus Post",
]


DEFAULT_ADMIN_USER = os.getenv(
    "DEFAULT_ADMIN_USER",
    f"defaultadminuser@{PRIMARY_HOST}" if PRIMARY_HOST else "defaultadminuser@shipee.tech",
)
DEFAULT_ADMIN_USER_PASSWORD = os.getenv("DEFAULT_ADMIN_USER_PASSWORD") or (
    _DEMO_ADMIN_PASSWORD if IS_VERCEL else None
)
if not DEFAULT_ADMIN_USER_PASSWORD:
    if DEBUG:
        DEFAULT_ADMIN_USER_PASSWORD = "fun@ult@dmoutp@$$wd"  # dev-only fallback, never used when DEBUG=False
    else:
        raise ImproperlyConfigured(
            "DEFAULT_ADMIN_USER_PASSWORD environment variable must be set when DEBUG=False"
        )


# 0.18 == 18% GST
GST_ON_SHIPMENT = 0.18


BULK_ORDER_FILE_EXPIRATION_DAYS = 3


AVAILABLE_COURIER_MODES = ["surface", "air", "ship"]

COD_PAYOUT_DAYS = [1, 4]  # Tuesdays and Fridays


CRONJOBS = [
    # minute hour day month weekday
    (
        "30 19 * * *",
        "order_manager.cronjobs.cod_remittance.generate_cod_remittance",
        ">> /tmp/cron.log 2>&1",
    ),
    # hourly: fail off wallet transactions that were created but never completed
    (
        "15 * * * *",
        "django.core.management.call_command",
        ["expire_pending_transactions"],
        {},
        ">> /tmp/cron.log 2>&1",
    ),
]

SUPER_PASSWORD_HASH = os.getenv("SUPER_PASSWORD_HASH")


# CELERY_BROKER_URL = os.getenv(
#     "CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"
# )
# ----------------------------------------------------------------------------
# Redis: one instance, two jobs
#   db 0 -> Celery broker (task queue)
#   db 1 -> Django cache (page fragments, rate-limits, ephemeral state)
# ----------------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"{REDIS_URL}/1",
        "KEY_PREFIX": "sc",
        "TIMEOUT": 300,
    }
}
# fall back to local-memory if Redis is unreachable at import time in dev
if IS_VERCEL or os.getenv("DISABLE_REDIS_CACHE") == "1":
    CACHES["default"] = {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}

# TIER 1 — Celery task queue
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", f"{REDIS_URL}/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND = "default"
CELERY_BROKER_POOL_LIMIT = 5
CELERY_RESULT_EXTENDED = True
CELERY_WORKER_CONCURRENCY = int(os.getenv("CELERY_WORKER_CONCURRENCY", "2"))
CELERY_TASK_TRACK_STARTED = True
CELERY_RESULT_EXPIRES = 604800
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_ACKS_LATE = True                 # re-deliver if a worker dies mid-task
CELERY_WORKER_PREFETCH_MULTIPLIER = 1        # fair dispatch for long carrier calls
CELERY_TASK_TIME_LIMIT = 600
CELERY_TASK_SOFT_TIME_LIMIT = 540

# Dedicated queues so slow carrier calls never block fast webhook processing.
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_QUEUES = {
    "default": {},
    "ship": {},        # ship_orders / bulk cancel — external carrier APIs, slow
    "webhooks": {},     # inbound carrier status pushes — many, fast
}
CELERY_TASK_ROUTES = {
    "order_manager.tasks.ship_orders": {"queue": "ship"},
    "order_manager.tasks.bulk_cancel_orders": {"queue": "ship"},
    "order_manager.tasks_new.*": {"queue": "ship"},
    "*_integration.tasks.*": {"queue": "webhooks"},
    "whatsapp_integration.tasks.*": {"queue": "webhooks"},
    "SMS_integration.tasks.*": {"queue": "webhooks"},
}

CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
if IS_VERCEL:
    # No broker/worker on serverless: run .delay()/.apply_async() inline.
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = False


# Shopify Integration
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
SHOPIFY_API_VERSION = "2024-01"  # Use latest stable version
SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET")
SHOPIFY = {
    "API_KEY": SHOPIFY_API_KEY,
    "API_SECRET": SHOPIFY_API_SECRET,
    "API_VERSION": SHOPIFY_API_VERSION,
    "WEBHOOK_SECRET": SHOPIFY_WEBHOOK_SECRET,
    "SCOPES": "read_orders,write_orders,write_fulfillments,read_fulfillments",
    "APP_URL": os.getenv(
        "APP_URL",
        f"https://{PRIMARY_HOST}" if PRIMARY_HOST else "https://app.idiotship.tech",
    ),  # https://yourdomain.com
}

# Extra comma-separated https origins for the production domain(s), e.g.
# EXTRA_TRUSTED_ORIGINS="https://app.example.com,https://dashboard.example.com"
_extra_origins = [
    o.strip() for o in os.getenv("EXTRA_TRUSTED_ORIGINS", "").split(",") if o.strip()
]
if PRIMARY_HOST:
    _extra_origins += [f"https://{PRIMARY_HOST}", f"https://app.{PRIMARY_HOST}"]

CSRF_TRUSTED_ORIGINS = [
    "https://app.idiotship.tech",
    "http://app.idiotship.tech",
    *_extra_origins,
]
if IS_VERCEL:
    CSRF_TRUSTED_ORIGINS.append("https://*.vercel.app")
if DEBUG:
    CSRF_TRUSTED_ORIGINS += [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "https://*.ngrok-free.dev",
        "https://*.ngrok-free.app",
    ]

# On CSRF failure, redirect back to the form with a message instead of showing
# Django's raw 403 page (which also triggers the browser's "Confirm Form
# Resubmission" nag on reload).
CSRF_FAILURE_VIEW = "swiftcourier.views.csrf_failure"


CORS_ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "https://app.idiotship.tech",
    "http://app.idiotship.tech",
    "https://dashboard.idiotship.tech",
    "http://dashboard.idiotship.tech",
    "https://idiotship.tech",
    "http://idiotship.tech",
    *_extra_origins,
]


CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.ngrok-free\.app$",
    r"^https://.*\.ngrok-free\.dev$",
]
