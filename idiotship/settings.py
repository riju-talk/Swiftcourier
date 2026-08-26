from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv
from phonepe.sdk.pg.env import Env
from django.core.exceptions import ImproperlyConfigured
import os


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.1/howto/deployment/checklist/

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", default="True") == "True"

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "xKQ4azxkpTqa7Jjv4i7rlyIllTwFImhr"  # dev-only fallback, never used when DEBUG=False
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY environment variable must be set when DEBUG=False"
        )

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")

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
    os.getenv("SECURE_HSTS_SECONDS", default="0" if DEBUG else "3600")
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
        # Capture Personally Identifiable Information
        send_default_pii=True,
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


# AWS_STORAGE_BUCKET_NAME = "shipee-static-media-storage"
# AWS_S3_REGION_NAME = "ap-south-1"
# AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"

# AWS_S3_FILE_OVERWRITE = False
# AWS_DEFAULT_ACL = "public-read"
# AWS_QUERYSTRING_AUTH = False

# STATICFILES_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
# DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"


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
]


INSTALLED_APPS += EXTERNAL_APPS


MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # Must be as high as possible
    "django.middleware.common.CommonMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_auto_logout.middleware.auto_logout",
]

ROOT_URLCONF = "idiotship.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "idiotship.context_processors.ctx_processor",
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "idiotship.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.1/ref/settings/#databases

if os.getenv("DATABASE_ENGINE") == "django.db.backends.postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DATABASE_NAME"),
            "USER": os.getenv("DATABASE_USER"),
            "PASSWORD": os.getenv("DATABASE_PASSWORD"),
            "HOST": os.getenv("DATABASE_HOST"),
            "PORT": os.getenv("DATABASE_PORT"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
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
    "DEFAULT_FROM_EMAIL", default=EMAIL_HOST_USER or "noreply@idiotship.tech"
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


# AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
# AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

# AWS_STORAGE_BUCKET_NAME = 'idiotship-static-media-files'
# AWS_S3_REGION_NAME = 'ap-south-1'
# AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'

# AWS_S3_OBJECT_PARAMETERS = {
#     'CacheControl': 'max-age=86400',
# }
# AWS_S3_FILE_OVERWRITE = True
# AWS_DEFAULT_ACL = None
# AWS_QUERYSTRING_AUTH = False

# Static files
# STATICFILES_STORAGE = 'idiotship.storage_backends.StaticStorage'
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
# STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/static/'
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static_prod"

# Media files
# DEFAULT_FILE_STORAGE = "idiotship.storage_backends.MediaStorage"
MEDIA_URL = "/media/"
# MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/media/"
MEDIA_ROOT = BASE_DIR / "media/"


# site settings
# SITE_URL = os.getenv("SITE_URL", default="http://localhost:8000")
LOGIN_URL = "account:signin"

# Assuming BASE_DIR is already defined in your settings
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Create the logs directory if it doesn't exist
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

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

TMP_DIR = BASE_DIR / "tmp"
if not TMP_DIR.exists():
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

# The "Secret" configured on the webhook in the NimbusPost partner dashboard
# (Settings -> Webhooks). Used to verify the X-Hmac-Sha256 header NimbusPost
# sends with every webhook call. Left blank = signature check is skipped,
# matching NimbusPost's own "no hash generated if left blank" behavior.
NIMBUSPOST_WEBHOOK_SECRET = os.environ.get("NIMBUSPOST_WEBHOOK_SECRET", "")

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


DEFAULT_ADMIN_USER = "defaultadminuser@shipee.tech"
DEFAULT_ADMIN_USER_PASSWORD = os.getenv("DEFAULT_ADMIN_USER_PASSWORD")
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
]

SUPER_PASSWORD_HASH = os.getenv("SUPER_PASSWORD_HASH")


# CELERY_BROKER_URL = os.getenv(
#     "CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"
# )
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND = "django-cache"
CELERY_BROKER_POOL_LIMIT = 5
CELERY_RESULT_EXTENDED = True
CELERY_WORKER_CONCURRENCY = 2
CELERY_TASK_TRACK_STARTED = True
CELERY_RESULT_EXPIRES = 604800

CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"


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
        "APP_URL", "https://app.idiotship.tech"
    ),  # https://yourdomain.com
}

CSRF_TRUSTED_ORIGINS = [
    "https://app.idiotship.tech",
    "http://app.idiotship.tech",
]
if DEBUG:
    CSRF_TRUSTED_ORIGINS += [
        "https://*.ngrok-free.dev",  
        "https://*.ngrok-free.app",  
    ]


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
]


CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.ngrok-free\.app$",
    r"^https://.*\.ngrok-free\.dev$",
]
