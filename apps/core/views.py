from django.shortcuts import render
from django.utils.translation import gettext as _


def ratelimited(request, exception=None):
    context = {"title": _("Slow down"), "message": _("Too many requests. Please wait a minute.")}
    if request.htmx:
        return render(request, "partials/toast.html", {"message": context["message"]}, status=429)
    return render(request, "errors/simple.html", context, status=429)


def page_not_found(request, exception=None):
    return render(request, "errors/simple.html", {"title": _("Not found"), "code": 404}, status=404)


def server_error(request):
    return render(request, "errors/500.html", status=500)


# Uploaded files are served with a locked-down policy so a mislabelled file can't run scripts.
MEDIA_CSP = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"


def media(request, path):
    """Public uploads from MEDIA_ROOT when files are kept on this server (no S3)."""
    from django.conf import settings
    from django.http import Http404
    from django.views.static import serve

    if not settings.SERVE_MEDIA:
        raise Http404
    response = serve(request, path, document_root=settings.MEDIA_ROOT)
    # Upload names are random and image renditions are content-hashed, so cache hard.
    response["Cache-Control"] = "public, max-age=2592000, immutable"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = MEDIA_CSP
    response["Cross-Origin-Resource-Policy"] = "same-site"
    return response
