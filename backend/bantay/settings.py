"""Django settings for BantayBarangay."""
import os
from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Load local .env automatically (without overriding explicitly exported env vars)
for _env_path in (BASE_DIR / '.env', BASE_DIR.parent / '.env'):
    if _env_path.is_file():
        for _line in _env_path.read_text(encoding='utf-8').splitlines():
            _stripped = _line.strip()
            if _stripped and not _stripped.startswith('#') and '=' in _stripped:
                _key, _val = _stripped.split('=', 1)
                os.environ.setdefault(_key.strip(), _val.strip().strip('"').strip("'"))

env = os.environ.get

DEBUG = env('DEBUG', '0') == '1'
SECRET_KEY = env('SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError('SECRET_KEY is required when DEBUG=0')
    SECRET_KEY = 'dev-only-insecure-key'

ALLOWED_HOSTS = [h.strip() for h in env('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in env('CSRF_TRUSTED_ORIGINS', 'http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173' if DEBUG else '').split(',')
    if o.strip()
]

RENDER_EXTERNAL_HOSTNAME = env('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f'https://{RENDER_EXTERNAL_HOSTNAME}')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.middleware.PrivateNoCacheMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.CSPMiddleware',
    'core.middleware.HealthMiddleware',
]

ROOT_URLCONF = 'bantay.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'core.context.site',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    }
]

WSGI_APPLICATION = 'bantay.wsgi.application'

DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
        conn_health_checks=True,
    )
}
if env('DB_SSL') == '1' and DATABASES['default']['ENGINE'].endswith('postgresql'):
    DATABASES['default'].setdefault('OPTIONS', {})['sslmode'] = 'require'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'bb_cache',
    }
}

AUTH_USER_MODEL = 'core.User'

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': f'django.contrib.auth.password_validation.{name}'}
    for name in (
        'UserAttributeSimilarityValidator',
        'MinimumLengthValidator',
        'CommonPasswordValidator',
        'NumericPasswordValidator',
    )
]

# Session & Transport Security (BR-07: 30-minute inactivity timeout)
SESSION_COOKIE_AGE = 1800
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG and env('SSL_REDIRECT', '1') == '1'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {'anon': '60/min', 'user': '300/min', 'auth': '10/min'},
}

LANGUAGE_CODE = 'en'
TIME_ZONE = 'Asia/Manila'
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media storage: automatically uses S3-compatible storage (e.g. Supabase Storage) when configured
STORAGE_BUCKET_NAME = env('STORAGE_BUCKET_NAME', '')
if STORAGE_BUCKET_NAME:
    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3.S3Storage',
            'OPTIONS': {
                'bucket_name': STORAGE_BUCKET_NAME,
                'endpoint_url': env('STORAGE_ENDPOINT_URL', ''),
                'region_name': env('STORAGE_REGION_NAME', 'ap-southeast-1'),
                'access_key': env('STORAGE_ACCESS_KEY_ID', ''),
                'secret_key': env('STORAGE_SECRET_ACCESS_KEY', ''),
                'default_acl': None,
                'querystring_auth': True,
            },
        },
        'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
    }
else:
    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
    }

LOGIN_URL = '/login/'
MEDIA_ROOT = Path(env('MEDIA_ROOT', str(BASE_DIR / 'media')))
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024 * 1024
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend' if env('EMAIL_HOST') else 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', '')
EMAIL_PORT = int(env('EMAIL_PORT', '587'))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', 'BantayBarangay <no-reply@localhost>')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
