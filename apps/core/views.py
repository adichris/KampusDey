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
