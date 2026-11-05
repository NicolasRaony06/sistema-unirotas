from .models import Notification, NotificationUser, NotificationTrip
from authentication.models import User
from operation.models import Viagem
from django.db import transaction
from django.db.models import QuerySet
from collections.abc import Iterable
from django.db.models import Q
from django.utils import timezone


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

def fetch_notifications(recipient):
    notifications = Notification.objects.filter(
        Q(notificationuser__recipient=recipient) | 
        Q(notificationtrip__trip__usuarios=recipient)
    ).distinct().order_by("-created_at")[:20]
    not_seen = Notification.objects.filter(
        Q(notificationuser__recipient=recipient) | 
        Q(notificationtrip__trip__usuarios=recipient),
        seen=None
    ).distinct().order_by("-created_at").count()
    return notifications, not_seen

def mark_notification_as_seen(recipient):
    notifications = list(
        Notification.objects.filter(
            Q(notificationuser__recipient=recipient) | 
            Q(notificationtrip__trip__usuarios=recipient),
            seen__isnull=True
        ).distinct()
    )
    if not notifications:
        return

    today = timezone.localdate()
    for notification in notifications:
        notification.seen = today

    Notification.objects.bulk_update(notifications, ['seen'])