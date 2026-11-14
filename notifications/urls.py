from .views import notifications, mark_as_seen
from django.urls import path

app_name = "notifications"
urlpatterns = [
    path("", notifications, name="view"),
    path("seen", mark_as_seen, name="mark_as_seen")
]