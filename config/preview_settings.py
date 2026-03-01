from .settings import *

# Use a local SQLite file so the dev server runs without PostgreSQL.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'preview.sqlite3',
    }
}
