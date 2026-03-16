from .settings import *

DATABASES = {**DATABASES, 'default': {**DATABASES['default'], 'NAME': ':memory:'}}
