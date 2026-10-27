from django.urls import path

from . import views

app_name = "contacts"

urlpatterns = [
    path("tap/<int:pk>/<str:kind>/", views.tap, name="tap"),
    path("email/<int:pk>/", views.email_relay, name="email_relay"),
]
