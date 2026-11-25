from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken, TokenError


class JWTAuthenticationMiddleware:
    """Authenticate requests with a Bearer JWT or access_token cookie when no session user is active."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._jwt_auth = None

    def __call__(self, request):
        if not getattr(request, 'user', None) or not request.user.is_authenticated:
            raw_token = self._extract_token(request)
            if raw_token:
                try:
                    if self._jwt_auth is None:
                        self._jwt_auth = JWTAuthentication()
                    validated_token = self._jwt_auth.get_validated_token(raw_token)
                    user = self._jwt_auth.get_user(validated_token)
                    request.user = user
                    request._cached_user = user
                except (InvalidToken, TokenError, AuthenticationFailed):
                    # Leave unauthenticated so views/permissions enforce normal 401/login redirects.
                    pass

        return self.get_response(request)

    @staticmethod
    def _extract_token(request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1].strip()
            if token:
                return token
        return request.COOKIES.get('access_token')
