from django.conf import settings


def site(request):
    from constance import config

    from apps.sitesettings.models import IntegrationSettings

    integ = IntegrationSettings.get_cached()
    themes = [t.strip() for t in config.THEMES_OFFERED.split(",") if t.strip()]
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        theme = user.theme or "system"
    else:
        theme = None  # guests: localStorage decides, applied by the no-flash script
    unread = 0
    if user is not None and user.is_authenticated:
        from apps.notifications.selectors import unread_count

        unread = unread_count(user)
    return {
        "SITE_URL": settings.SITE_URL,
        "THEMES_OFFERED": themes,
        "user_theme": theme,
        "umami_script_url": integ.umami_script_url,
        "umami_website_id": integ.umami_website_id,
        "turnstile_site_key": integ.turnstile_site_key if integ.turnstile_secret else "",
        "unread_notifications": unread,
        "VAPID_PUBLIC_KEY": settings.WEBPUSH_SETTINGS.get("VAPID_PUBLIC_KEY", ""),
    }
