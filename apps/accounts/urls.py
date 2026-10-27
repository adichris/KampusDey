from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("welcome/", views.after_login, name="after_login"),
    path("onboarding/", views.onboarding, name="onboarding"),
    path("profile/", views.profile, name="profile"),
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    path("appearance/", views.appearance, name="appearance"),
    path("theme/", views.set_theme, name="theme"),
    path("phone/", views.phone, name="phone"),
    path("verification/", views.verification, name="verification"),
    path("delete/", views.delete_account, name="delete"),
    path("export/", views.export_data, name="export"),
    path("u/<int:pk>/", views.public_profile, name="public_profile"),
]
