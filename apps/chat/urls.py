from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("unread/", views.unread_badge, name="unread_badge"),
    path("start/<int:listing_pk>/", views.start, name="start"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/poll/", views.poll, name="poll"),
    path("<int:pk>/send/", views.send, name="send"),
    path("<int:pk>/share/", views.share_number, name="share"),
    path("<int:pk>/block/", views.block, name="block"),
]
