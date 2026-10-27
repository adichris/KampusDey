from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("<int:pk>/", views.open_notification, name="open"),
    path("settings/", views.preferences, name="preferences"),
    path("read/", views.mark_read, name="mark_read"),
]
