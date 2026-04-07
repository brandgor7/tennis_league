from .settings import *

DATABASES = {**DATABASES, 'default': {**DATABASES['default'], 'NAME': ':memory:'}}

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
