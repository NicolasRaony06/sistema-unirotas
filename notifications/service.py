from .models import Notification, NotificationUser, NotificationTrip
from authentication.models import User
from operation.models import Viagem
from django.db import transaction
from django.db.models import QuerySet
from collections.abc import Iterable

def send_notification(title, message, sender, recipient):
    with transaction.atomic():
        notification = Notification.objects.create(title=title, message=message)

        if isinstance(recipient, Viagem):
            NotificationTrip.objects.create(
                notification=notification, 
                sender=sender, 
                trip=recipient
            )
            return notification

        if isinstance(recipient, User):
            users = [recipient]

        elif isinstance(recipient, (QuerySet, Iterable)):
            users = recipient
        else:
            raise ValueError("Recipient deve ser um User, uma Trip ou uma coleção de Users.")

        notification_users = [
            NotificationUser(
                notification=notification, 
                sender=sender, 
                recipient=user
            )
            for user in users
        ]
        
        NotificationUser.objects.bulk_create(notification_users)
        return notification

