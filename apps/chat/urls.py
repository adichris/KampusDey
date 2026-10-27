from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("unread/", views.unread_badge, name="unread_badge"),
    path("start/<int:listing_pk>/", views.start, name="start"),
    path("guest/<int:listing_pk>/", views.guest_start, name="guest_start"),
    path("g/<str:key>/", views.guest_thread, name="guest_thread"),
    path("g/<str:key>/poll/", views.guest_poll, name="guest_poll"),
    path("g/<str:key>/send/", views.guest_send, name="guest_send"),
    path("g/<str:key>/claim/", views.guest_claim, name="guest_claim"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/poll/", views.poll, name="poll"),
    path("<int:pk>/send/", views.send, name="send"),
    path("<int:pk>/share/", views.share_number, name="share"),
    path("<int:pk>/block/", views.block, name="block"),
]
