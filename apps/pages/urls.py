from django.urls import path

from . import views

app_name = "pages"

urlpatterns = [
    path("about/", views.about, name="about"),
    path("about/data-sources/", views.data_sources, name="data_sources"),
    path("safety/", views.safety, name="safety"),
    path("scam-alerts/", views.scam_alerts, name="scam_alerts"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("offline/", views.offline, name="offline"),
]
