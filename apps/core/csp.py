from csp.middleware import CSPMiddleware, PolicyParts
from django.urls import reverse

# The admin theme (django-unfold) ships the standard Alpine.js build, which evaluates its
# x-on/x-show expressions with `new Function` and sets inline styles. Without these, admin
# menus, dialogs (e.g. the keyboard-shortcuts list) and the sidebar can't open or close.
# The public site keeps the strict policy and the CSP build of Alpine.
ADMIN_CSP_UPDATE = {"script-src": ["'unsafe-eval'"], "style-src": ["'unsafe-inline'"]}


class KampusCSPMiddleware(CSPMiddleware):
    def get_policy_parts(self, request, response, report_only=False) -> PolicyParts:
        parts = super().get_policy_parts(request, response, report_only)
        if request.path.startswith(reverse("admin:index")):
            update = dict(parts.update or {})
            for directive, values in ADMIN_CSP_UPDATE.items():
                update[directive] = [*update.get(directive, []), *values]
            parts.update = update
        return parts
