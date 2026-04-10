from .settings import *

DEBUG = False

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

LOGGING['root']['handlers'] = ['file', 'console']
LOGGING['root']['level'] = 'WARNING'
LOGGING['handlers']['console']['level'] = 'ERROR'
LOGGING['loggers']['audit'] = {'handlers': ['file'], 'level': 'INFO', 'propagate': False}
LOGGING['loggers']['access'] = {'handlers': ['file'], 'level': 'INFO', 'propagate': False}
