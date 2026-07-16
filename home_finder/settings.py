"""
Django settings for home_finder project.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.2/ref/settings/
"""

import os
from pathlib import Path

import dj_database_url
from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _config_bool(name: str, *, default: bool) -> bool:
    """Read a bool env var, falling back safely on invalid deployment values.

    Vercel and debug tooling can populate generic names such as DEBUG with
    values like "production" or "undefined". python-decouple correctly rejects
    those, but settings import must still succeed during deployment discovery.
    """
    value = config(name, default=None)
    if value is None:
        return default
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in {'1', 'true', 't', 'yes', 'y', 'on'}:
        return True
    if normalized in {'0', 'false', 'f', 'no', 'n', 'off', ''}:
        return False
    return default


def _config_csv(name: str, *, default: str = '') -> list[str]:
    return [item.strip() for item in config(name, default=default).split(',') if item.strip()]


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


VERCEL_CUSTOM_HOSTS = (
    'homefinder.patbuilds.dev',
    'pinellasmarketlens.patbuilds.dev',
)


def _append_vercel_custom_hosts(allowed_hosts: list[str], trusted_origins: list[str]) -> None:
    for host in VERCEL_CUSTOM_HOSTS:
        _append_unique(allowed_hosts, host)
        _append_unique(trusted_origins, f'https://{host}')


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = _config_bool('DEBUG', default=False)

ALLOWED_HOSTS = _config_csv('ALLOWED_HOSTS', default='localhost,127.0.0.1')

# CSRF trusted origins for proxied deployments (Django 4.0+)
CSRF_TRUSTED_ORIGINS = _config_csv('CSRF_TRUSTED_ORIGINS')

if os.environ.get('VERCEL'):
    # Preview deployments use unique *.vercel.app hostnames per branch/commit.
    _append_unique(ALLOWED_HOSTS, '.vercel.app')
    _append_unique(CSRF_TRUSTED_ORIGINS, 'https://*.vercel.app')
    _append_vercel_custom_hosts(ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS)

    vercel_url = os.environ.get('VERCEL_URL', '').strip()
    if vercel_url:
        _append_unique(ALLOWED_HOSTS, vercel_url)
        _append_unique(CSRF_TRUSTED_ORIGINS, f'https://{vercel_url}')

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.Pages.apps.PagesConfig',
    'apps.analytics.apps.AnalyticsConfig',
    'rest_framework',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'home_finder.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'home_finder.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = '/static/'

if os.environ.get('VERCEL'):
    # Vercel doesn't run collectstatic; serve from source static/ dir
    STATIC_ROOT = os.path.join(BASE_DIR, 'static')
    STATICFILES_DIRS = []
    STATICFILES_BACKEND = 'whitenoise.storage.CompressedStaticFilesStorage'
else:
    STATICFILES_DIRS = [
        os.path.join(BASE_DIR, 'static'),
    ]
    STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
    STATICFILES_BACKEND = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': STATICFILES_BACKEND,
    },
}

# Default primary key column type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-column

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Ensure this directory exists and is writable
XLSX_BASE_DIR = os.path.join(BASE_DIR, 'misc', 'temp')
try:
    os.makedirs(XLSX_BASE_DIR, exist_ok=True)
except OSError:
    XLSX_BASE_DIR = os.path.join('/tmp', 'misc', 'temp')
    os.makedirs(XLSX_BASE_DIR, exist_ok=True)

# Media directory
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# X frame config
X_FRAME_OPTIONS = 'DENY'

# Cache: database-backed (works on Vercel without an external cache service).
# Run `python manage.py createcachetable` once after deploy to create the table.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'cache_table',
        'OPTIONS': {'MAX_ENTRIES': 1000},
    }
}

# Document Paths
EXCEL_PATH = config('EXCEL_PATH', default=os.path.join(BASE_DIR, 'exports'))
PDF_PATH = config('PDF_PATH', default=os.path.join(BASE_DIR, 'exports'))

# Proxy Address
PROXY_ADDRESS = config('PROXY_ADDRESS', default='')

# API Key
SCRAPING_API_KEY = config('SCRAPING_API_KEY', default='')

# Logging configuration for production visibility
# All logs go to stdout for the serverless/container runtime to capture
LOG_LEVEL = config('LOG_LEVEL', default='INFO')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} [{levelname}] {name}: {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '[{levelname}] {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        # Django framework logs
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Application logs - verbose for debugging
        'apps': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'apps.analytics': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'apps.analytics.tasks': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'apps.analytics.tasks.pcpao_scraper': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'apps.analytics.tasks.scrape_data': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'apps.analytics.tasks.tax_collector_scraper': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        # Selenium/WebDriver logs (reduce noise)
        'selenium': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'urllib3': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# Production security hardening
if not DEBUG:
    SECURE_SSL_REDIRECT = _config_bool('SECURE_SSL_REDIRECT', default=True)
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Sentry error tracking (optional)
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment='production' if not DEBUG else 'development',
    )
