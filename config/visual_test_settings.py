from .settings import *

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# File-based SQLite so the live server thread can see data committed by the test thread.
# (:memory: is per-connection and invisible across threads.)
DATABASES = {
    **DATABASES,
    'default': {
        **DATABASES['default'],
        'NAME': BASE_DIR / 'visual.sqlite3',
    }
}
