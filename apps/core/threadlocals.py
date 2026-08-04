import threading

_local = threading.local()


class CurrentRequestMiddleware:
    """Guarda o request atual em thread-local para que signals (post_save/post_delete)
    consigam saber quem fez a alteração, sem precisar passar o usuário manualmente
    por toda a cadeia de chamadas."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request = request
        try:
            return self.get_response(request)
        finally:
            _local.request = None


def get_current_request():
    return getattr(_local, 'request', None)


def get_current_user():
    request = get_current_request()
    if request is not None and getattr(request, 'user', None) and request.user.is_authenticated:
        return request.user
    return None


def get_current_ip():
    request = get_current_request()
    if request is None:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')
