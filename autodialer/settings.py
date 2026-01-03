# autodialer/settings.py

from pathlib import Path
import os
# from decouple import config

def config(key, default=None, cast=None):
    """Simple config function to replace decouple temporarily"""
    import os
    value = os.environ.get(key, default)
    if cast and value is not None:
        return cast(value)
    return value

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='your-secret-key-change-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    
    # Third party apps
    'channels',
    'django_extensions',
    
    # Local apps
    'core',
    'users',
    'campaigns',
    'leads',
    'telephony',
    'agents',
    'calls',
    'reports',
    'settings',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.UserActivityMiddleware',  # Custom middleware for user activity
]

ROOT_URLCONF = 'autodialer.urls'

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
                'core.context_processors.global_settings',  # Custom context processor
            ],
        },
    },
]

WSGI_APPLICATION = 'autodialer.wsgi.application'
ASGI_APPLICATION = 'autodialer.asgi.application'

# Database
# Switch to PostgreSQL (uses env vars with safe defaults for local dev)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='autodialer_db'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default='Shiwansh@123'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

# Redis Configuration
def _strtobool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')

USE_REDIS = _strtobool(config('USE_REDIS', default='1'))
REDIS_URL = config('REDIS_URL', default='redis://127.0.0.1:6379/0')

# Channels Configuration
if USE_REDIS:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# If you want to force SQLite for quick local runs, temporarily comment out the block above
# and uncomment the block below.
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / "db.sqlite3",
#     }
# }


ASTERISK_SERVERS = {
    'default': {
        'HOST': '172.26.7.107',  # WSL accessible via localhost
        'AMI_PORT': 5038,
        'SIP_PORT': 5060,
        'USERNAME': 'admin',
        'PASSWORD': 'amp111'
    }
}


# Cache Configuration
if USE_REDIS:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            }
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'autodialer-local-cache',
        }
    }

# Celery Configuration
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default=REDIS_URL)
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default=REDIS_URL)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_ALWAYS_EAGER = True  # Run tasks synchronously to avoid broker connection issues
CELERY_TASK_EAGER_PROPAGATES = True

# DISABLED: Old outbound queue processing - replaced by hopper-based predictive dialer
# CELERY_BEAT_SCHEDULE = {
#     'process-outbound-queue-every-2s': {
#         'task': 'campaigns.process_outbound_queue',
#         'schedule': 2.0,
#         'args': ()
#     },
# }
CELERY_BEAT_SCHEDULE = {}

# Password validation
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
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentication
LOGIN_URL = '/users/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/users/login/'

# Session Configuration
if USE_REDIS:
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
else:
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_SAVE_EVERY_REQUEST = True

# Security Settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'autodialer.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'autodialer': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Asterisk Configuration
ASTERISK_CONFIG = {
    'AMI_HOST': config('AMI_HOST', default='localhost'),
    'AMI_PORT': config('AMI_PORT', default=5038, cast=int),
    'AMI_USERNAME': config('AMI_USERNAME', default='admin'),
    'AMI_PASSWORD': config('AMI_PASSWORD', default='password'),
    'ARI_HOST': config('ARI_HOST', default='localhost'),
    'ARI_PORT': config('ARI_PORT', default=8088, cast=int),
    'ARI_USERNAME': config('ARI_USERNAME', default='asterisk'),
    'ARI_PASSWORD': config('ARI_PASSWORD', default='password'),
}

# Autodialer Specific Settings
AUTODIALER_SETTINGS = {
    'MAX_CONCURRENT_CALLS': config('MAX_CONCURRENT_CALLS', default=100, cast=int),
    'CALL_TIMEOUT': config('CALL_TIMEOUT', default=30, cast=int),
    'RECORDING_PATH': config('RECORDING_PATH', default=str(BASE_DIR / 'media' / 'recordings')),
    'LEAD_IMPORT_CHUNK_SIZE': config('LEAD_IMPORT_CHUNK_SIZE', default=1000, cast=int),
    'AGENT_TIMEOUT': config('AGENT_TIMEOUT', default=300, cast=int),  # 5 minutes
}

# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='localhost')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='autodialer@localhost')

# File Upload Settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MB

# Create logs directory
os.makedirs(BASE_DIR / 'logs', exist_ok=True)
os.makedirs(AUTODIALER_SETTINGS['RECORDING_PATH'], exist_ok=True)
