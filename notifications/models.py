from datetime import datetime

from django.db import models
from django.utils import timezone

from authentication.models import User

class NotficationsType(models.TextChoices):
    DEFAULT = 'DEFAULT', 'Default'
    NOTICE = 'NOTICE', 'Notice'
    ALERT = 'ALERT', 'Alert'

# Create your models here.
class Notification(models.Model):
    title = models.CharField(max_length=120)
    body = models.TextField()
    notification_type = models.CharField(
            max_length=20,
            choices=NotficationsType.choices,
            default=NotficationsType.DEFAULT
        )
    created_at = models.DateTimeField(default=timezone.now)

    def sent_at(self):
        time:float = (timezone.now() - self.created_at).total_seconds()
        if (time*60) <= 10:
            return "agora"
        hour = time//60//60
        minutes = (time-(hour*60*60))//60
        return f"há {int(hour)}h e {int(minutes)}m atrás"

    def trip_user_seen(self):
        return self.notification_trip.all()

    def __str__(self):
        return User.objects.filter(
    seen_trip_notification__notification__notification=self
).distinct()

class NotificationUser(models.Model):
    seen = models.DateTimeField(null=True, blank=True)
    sender = models.ForeignKey("authentication.User", related_name="notications_sent", on_delete=models.CASCADE)
    recipient = models.ForeignKey("authentication.User", related_name="notification_recieved", on_delete=models.CASCADE)
    notification = models.ForeignKey(Notification, related_name="notification_user", on_delete=models.CASCADE)

    def __str__(self):
        return f"de:{self.sender} para:{self.recipient} \n {self.notification} "
class NotificationTrip(models.Model): #possivel melhoria para caso sobre tempo melhorar o seen, neste models ele não marca visto por usuario e sim apenas um usuario marca visto para todos, melhorar caso sobre tempo
    sender = models.ForeignKey("authentication.User", related_name="notifications_sent", on_delete=models.CASCADE)
    trip = models.ForeignKey("operation.Viagem", related_name="notifications_recieved", on_delete=models.CASCADE)
    notification = models.ForeignKey(Notification, related_name="notification_trip", on_delete=models.CASCADE)
    def __str__(self):
        return f"de: {self.sender} para usuarios da viagem : {self.trip} \n {self.notification}"

class UserSeenNotification(models.Model):
    user = models.ForeignKey('authentication.User', related_name="seen_trip_notification", on_delete=models.CASCADE)
    notification = models.ForeignKey(NotificationTrip, related_name="user_seen", on_delete=models.CASCADE)
    date_seen = models.DateField(null=True, blank=True)
    class Meta:
        unique_together = ('user', 'notification')