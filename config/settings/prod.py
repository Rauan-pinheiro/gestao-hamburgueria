from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool('DJANGO_DEBUG', default=False)

# Nunca aceitar a SECRET_KEY insegura padrão em produção — falha rápido no boot em vez de rodar exposto.
SECRET_KEY = env('DJANGO_SECRET_KEY', default=None)
if not SECRET_KEY or SECRET_KEY.startswith('django-insecure'):
    raise ImproperlyConfigured('DJANGO_SECRET_KEY precisa ser definida com um valor seguro em produção.')

ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS')

DATABASES = {
    'default': env.db('DATABASE_URL')
}
# Sem strict mode o MySQL pode truncar/aceitar valores inválidos silenciosamente em vez de
# levantar erro (mysql.W002) — inaceitável com dados financeiros/estoque reais.
DATABASES['default']['OPTIONS'] = {
    'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
}

MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')  # noqa: F405
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

SECURE_SSL_REDIRECT = env.bool('DJANGO_SECURE_SSL_REDIRECT', default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int('DJANGO_SECURE_HSTS_SECONDS', default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
