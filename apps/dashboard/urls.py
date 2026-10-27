from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("<int:pk>/stats/", views.stats, name="stats"),
    path("<int:pk>/renew/", views.renew, name="renew"),
    path("<int:pk>/taken/", views.taken, name="taken"),
    path("<int:pk>/boost/", views.boost_listing, name="boost"),
]
