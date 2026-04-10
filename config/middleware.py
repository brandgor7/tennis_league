import logging
import re

from django.conf import settings

logger = logging.getLogger('access')

_SEASON_PATH_RE = re.compile(r'^/seasons/([^/]+)/')

LAST_SEASON_COOKIE = 'last_season'
LAST_SEASON_COOKIE_MAX_AGE = 365 * 24 * 60 * 60


class SeasonCookieMiddleware:
    """Sets a cookie tracking the most recently visited season slug."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = _SEASON_PATH_RE.match(request.path)
        if match:
            slug = match.group(1)
            response.set_cookie(
                LAST_SEASON_COOKIE,
                slug,
                max_age=LAST_SEASON_COOKIE_MAX_AGE,
                httponly=True,
                samesite='Lax',
                secure=not settings.DEBUG,
            )
        return response


class RequestLogMiddleware:
    """Logs every request: method, path, status, and originating IP."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = forwarded_for.split(',')[0].strip() if forwarded_for else request.META.get('REMOTE_ADDR', '-')
        user = request.user.username if hasattr(request, 'user') and request.user.is_authenticated else '-'

        logger.info('%s %s %s %s %s', ip, user, request.method, request.get_full_path(), response.status_code)

        return response
