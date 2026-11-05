from .models import Notification, NotificationUser, NotificationTrip

def send_notification(title, message, sender, recipient):
    notification = Notification.objects.create(title=title, message=message)