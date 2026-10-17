"""Small-host settings layered on the pinned upstream production settings."""
from cvat.settings.production import *  # noqa: F403

ALLOWED_HOSTS = ['cvat.williamtrinh.online', 'localhost', '127.0.0.1', 'cvat-server', 'cvat_server']
CSRF_TRUSTED_ORIGINS = ['https://cvat.williamtrinh.online']
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
# K3s Traefik and the internal upstream router preserve/overwrite this trusted header.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
for handler in LOGGING.get('handlers', {}).values():  # noqa: F405
    if 'RotatingFileHandler' in handler.get('class', ''):
        handler['backupCount'] = 3
