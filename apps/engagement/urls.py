from django.urls import path

from . import views

app_name = "engagement"

urlpatterns = [
    path("like/<int:pk>/", views.like, name="like"),
    path("comment/<int:pk>/", views.comment, name="comment"),
    path("comment/<int:pk>/hide/", views.hide_comment, name="hide_comment"),
    path("share/<int:pk>/", views.share, name="share"),
    path("report/<str:kind>/<int:pk>/", views.report, name="report"),
    path("saved/", views.saved, name="saved"),
    path("alerts/save/", views.save_search, name="save_search"),
    path("alerts/<int:pk>/delete/", views.delete_saved_search, name="delete_saved_search"),
    path("review/<str:kind>/<int:pk>/", views.review, name="review"),
]
