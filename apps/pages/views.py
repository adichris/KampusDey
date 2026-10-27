import json

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control

from apps.locations.models import ImportLog
from apps.moderation.models import ScamAlert


def about(request):
    return render(request, "pages/about.html")


def data_sources(request):
    from apps.external.models import ExternalSource

    last = {}
    for log in ImportLog.objects.order_by("-created_at")[:200]:
        last.setdefault(log.source, log.created_at)
    return render(
        request,
        "pages/data_sources.html",
        {
            "last": last,
            "external_sources": ExternalSource.objects.exclude(permission_status="suspended"),
        },
    )


def safety(request):
    return render(request, "pages/safety.html")


def privacy(request):
    return render(request, "pages/privacy.html")


def terms(request):
    return render(request, "pages/terms.html")


def offline(request):
    return render(request, "pages/offline.html")


def scam_alerts(request):
    alerts = ScamAlert.objects.filter(is_published=True, confirmed_at__isnull=False)
    return render(request, "pages/scam_alerts.html", {"alerts": alerts})


@cache_control(max_age=86400)
def manifest(request):
    data = {
        "name": "KampusDey",
        "short_name": "KampusDey",
        "description": "Whatever you need on campus, e dey.",
        "start_url": "/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "background_color": "#F5F7F6",
        "theme_color": "#0E7C66",
        "icons": [
            {"src": static("img/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("img/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {
                "src": static("img/icon-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
    }
    return HttpResponse(json.dumps(data), content_type="application/manifest+json")


@cache_control(max_age=0, no_cache=True)
def service_worker(request):
    """Caches static assets and the offline page only. Never tiles, never authenticated HTML."""
    assets = [
        static("css/app.css"),
        static("js/app.js"),
        static("vendor/htmx.min.js"),
        static("vendor/alpine-csp.min.js"),
        static("img/icon.svg"),
    ]
    body = render(
        request, "pages/sw.js", {"assets": json.dumps(assets), "version": settings.STATIC_URL}
    ).content
    response = HttpResponse(body, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response


def robots(request):
    lines = [
        "User-agent: *",
        "Disallow: /" + settings.ADMIN_URL,
        "Disallow: /accounts/",
        "Disallow: /chat/",
        "Disallow: /dashboard/",
        "Disallow: /post/",
        "Disallow: /l/check/",
        f"Sitemap: {settings.SITE_URL}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")
