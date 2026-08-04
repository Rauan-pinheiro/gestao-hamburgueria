from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.urls import reverse

EXEMPT_PATH_PREFIXES = ('/admin/', '/static/', '/media/', '/__debug__/')


class LoginRequiredMiddleware:
    """Exige login em todo o site, exceto admin, estáticos/mídia e as próprias telas de login/logout."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._exigir_login(request):
            login_url = reverse(settings.LOGIN_URL)
            return redirect_to_login(request.get_full_path(), login_url=login_url)
        return self.get_response(request)

    def _exigir_login(self, request):
        if request.user.is_authenticated:
            return False
        if request.path.startswith(EXEMPT_PATH_PREFIXES):
            return False
        exemptas = {reverse(settings.LOGIN_URL)}
        if request.path in exemptas:
            return False
        return True
