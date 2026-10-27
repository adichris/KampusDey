from django.utils.functional import SimpleLazyObject


class CampusContextMiddleware:
    """Attach `request.location` (campus/town) lazily so pages that don't use it pay nothing."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .services import resolve_location

        request.location = SimpleLazyObject(lambda: resolve_location(request))
        return self.get_response(request)
