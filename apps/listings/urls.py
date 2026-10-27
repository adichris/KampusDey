from django.urls import path

from . import views

app_name = "listings"

urlpatterns = [
    path("search/", views.search, name="search"),
    path("nearby/", views.nearby, name="nearby"),
    path("post/", views.post_picker, name="post"),
    path("post/new/<slug:section>/", views.post_start, name="post_start"),
    path("post/<int:pk>/step/<int:step>/", views.wizard, name="wizard"),
    path("post/<int:pk>/photos/", views.photo_upload, name="photo_upload"),
    path("post/<int:pk>/photos/<int:photo_id>/delete/", views.photo_delete, name="photo_delete"),
    path("post/<int:pk>/photos/<int:photo_id>/<str:direction>/", views.photo_move, name="photo_move"),
    path("post/<int:pk>/delete/", views.delete_draft, name="delete_draft"),
    path("l/check/<str:token>/", views.one_tap, name="one_tap"),
    path("l/<slug:slug>/", views.detail, name="detail"),
    path("l/<slug:slug>/still-available/", views.check, name="check"),
    path("s/<slug:section>/", views.section_redirect, name="section"),
    path("town/<slug:town_slug>/", views.town_home, name="town_home"),
    path("town/<slug:town_slug>/<slug:section>/", views.section_town, name="section_town"),
    # Campus routes come last; config/urls.py includes this module after every other app.
    path("<slug:campus_slug>/", views.campus_home, name="campus_home"),
    path("<slug:campus_slug>/<slug:section>/", views.section_campus, name="section_campus"),
]
