from django.contrib import admin
from .models import NotificationTrip, Notification, NotificationUser, UserSeenNotification
# Register your models here.
admin.site.register(NotificationUser)
admin.site.register(NotificationTrip)
admin.site.register(Notification)
admin.site.register(UserSeenNotification)