from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from apps.core import views as core_views
from apps.dashboard import settings_overview
from apps.external import views as external_views
from apps.growth import views as growth_views
from apps.growth.sitemaps import SITEMAPS
from apps.listings import views as listing_views
from apps.pages import views as page_views

handler404 = "apps.core.views.page_not_found"
handler500 = "apps.core.views.server_error"

urlpatterns = [
    path("", listing_views.home, name="home"),
    path(
        f"{settings.ADMIN_URL}overview/",
        admin.site.admin_view(settings_overview.overview),
        name="settings_overview",
    ),
    path(settings.ADMIN_URL, admin.site.urls),
    # Local uploads (no S3). On alwaysdata a static mapping of /media/ can serve them instead.
    path(f"{settings.MEDIA_URL.strip('/')}/<path:path>", core_views.media, name="media"),
    path("accounts/", include("allauth.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("location/", include("apps.locations.urls")),
    path("contacts/", include("apps.contacts.urls")),
    path("e/", include("apps.engagement.urls")),
    path("chat/", include("apps.chat.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("h/", include("apps.hostels.urls")),
    path("around/", include("apps.external.urls")),
    path("webpush/", include("webpush.urls")),
    path("r/<str:code>/", growth_views.referral, name="referral"),
    path("manifest.webmanifest", page_views.manifest, name="manifest"),
    path("sw.js", page_views.service_worker, name="service_worker"),
    path("robots.txt", page_views.robots, name="robots"),
    path(
        "sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="django.contrib.sitemaps.views.sitemap"
    ),
    path("", include("apps.pages.urls")),
    path("<slug:campus_slug>/around/", external_views.around, name="around"),
    path("<slug:campus_slug>/rent-check/", growth_views.rent_check, name="rent_check"),
    # Listings last: it ends with the campus catch-all routes.
    path("", include("apps.listings.urls")),
]

if settings.DEBUG:
    if "debug_toolbar" in settings.INSTALLED_APPS:
        urlpatterns = [path("__debug__/", include("debug_toolbar.urls"))] + urlpatterns
