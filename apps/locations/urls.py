from django.urls import path

from . import views

app_name = "locations"

urlpatterns = [
    path("", views.picker_page, name="picker_page"),
    path("picker/", views.picker, name="picker"),
    path("search/", views.campus_search, name="search"),
    path("nearest/", views.nearest, name="nearest"),
    path("towns/", views.towns, name="towns"),
    path("choose/", views.choose, name="choose"),
    path("request/", views.campus_request, name="request"),
    path("follow/<int:pk>/", views.follow, name="follow"),
]
