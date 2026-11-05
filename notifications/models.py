from django.db import models
from django.utils import timezone

# Create your models here.
class Notification(models.Model):
    title = models.CharField(max_length=120)
    body = models.TextField()
    seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_created=timezone.localdate)

class NotificationUser(models.Model):
    sender = models.ForeignKey("authentication.User", related_name="notications_sent", on_delete=models.CASCADE)
    recipient = models.ForeignKey("authentication.User", related_name="notification_recieved", on_delete=models.CASCADE)
    notification = models.ForeignKey(Notification, related_name="notification_user", on_delete=models.CASCADE)

class NotificationTrip(models.Model):
    sender = models.ForeignKey("authentication.User", related_name="notifications_sent", on_delete=models.CASCADE)
    trip = models.ForeignKey("operation.Viagem", related_name="notifications_recieved", on_delete=models.CASCADE)
    notification = models.ForeignKey(Notification, related_name="notification_trip", on_delete=models.CASCADE)
