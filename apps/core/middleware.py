from django.conf import settings


class StagingNoIndexMiddleware:
    """On staging, tell every crawler to stay away (robots.txt also disallows everything)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.IS_STAGING:
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response
