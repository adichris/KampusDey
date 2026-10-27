from django.urls import path

from . import views

app_name = "hostels"

urlpatterns = [
    path("manage/", views.manager, name="manager"),
    path("manage/new/", views.edit_hostel, name="create"),
    path("manage/<int:pk>/", views.manage, name="manage"),
    path("manage/<int:pk>/edit/", views.edit_hostel, name="edit"),
    path("manage/<int:pk>/rooms/new/", views.room_type, name="room_type_new"),
    path("manage/<int:pk>/rooms/<int:rt_pk>/", views.room_type, name="room_type_edit"),
    path("manage/<int:pk>/rooms/<int:rt_pk>/<str:delta>/", views.step, name="step"),
    path("manage/<int:pk>/photos/", views.photo_upload, name="photo_upload"),
    path("manage/<int:pk>/photos/<int:photo_pk>/delete/", views.photo_delete, name="photo_delete"),
    path("manage/<int:pk>/inquiries/", views.inquiries, name="inquiries"),
    path("<slug:slug>/", views.detail, name="detail"),
]
