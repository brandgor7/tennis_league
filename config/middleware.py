import logging

logger = logging.getLogger('access')


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
