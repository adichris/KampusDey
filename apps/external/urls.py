from django.urls import path

from . import views

app_name = "external"

urlpatterns = [
    path("place/<slug:slug>/", views.place, name="place"),
    path("place/<slug:slug>/go/<str:kind>/", views.place_tap, name="place_tap"),
    path("place/<slug:slug>/claim/", views.claim, name="claim"),
    path("place/<slug:slug>/edit/", views.edit_place, name="edit_place"),
]
