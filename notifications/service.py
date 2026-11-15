from .models import NotficationsType, Notification, NotificationUser, NotificationTrip, UserSeenNotification
from authentication.models import User
from operation.models import Viagem, UsuarioDaViagem
from django.db import transaction
from django.db.models import QuerySet
from collections.abc import Iterable
from django.db.models import Q
from django.utils import timezone


def send_notification(title, message, sender, recipient, not_type=NotficationsType.DEFAULT):
    with transaction.atomic():
        notification = Notification.objects.create(title=title, body=message)

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
    if recipient.role == "STUDENT":
        trip_user = UsuarioDaViagem.objects.filter(estudante=recipient.student_profile, viagem__data__date = timezone.localdate())
        notifications = Notification.objects.filter(
            Q(notification_user__recipient=recipient) | 
            Q(notification_trip__trip__usuarios__in=trip_user)
        ).distinct().order_by("-created_at")[:20]
        not_seen = Notification.objects.filter(
            Q(notification_user__recipient=recipient, notification_user__seen__isnull=True) | 
            (
                Q(notification_trip__trip__usuarios__in=trip_user) & 
                ~Q(notification_trip__user_seen__user=recipient)
            )
        ).distinct().order_by("-created_at").count()
    else:
        notifications = Notification.objects.filter(
            Q(notification_user__recipient=recipient) 
        ).distinct().order_by("-created_at")[:20]
        not_seen = Notification.objects.filter(
            Q(notification_user__recipient=recipient, notification_user__seen=None)
        ).distinct().order_by("-created_at").count()
    return notifications, not_seen

def mark_notification_as_seen(recipient):
    if recipient.role == "STUDENT":
        trip_user = UsuarioDaViagem.objects.filter(estudante=recipient.student_profile, viagem__data__date = timezone.localdate())
        notifications = list(
            Notification.objects.filter(
                Q(notification_user__recipient=recipient, notification_user__seen=None) | 
                (
                    Q(notification_trip__trip__usuarios__in=trip_user) & 
                    ~Q(notification_trip__user_seen__user=recipient)
                ),
            ).distinct()
        )
        print(notifications)
    else:
        notifications = list(
            Notification.objects.filter(
                Q(notification_user__recipient=recipient, notification_user__seen=None)
            ).distinct()
        )
    
    if not notifications:
        return

    today = timezone.localdate()

    user_notifs_to_update = list(
        NotificationUser.objects.filter(
            notification__in=notifications,
            recipient=recipient,
            seen__isnull=True
        )
    )
    for nu in user_notifs_to_update:
        nu.seen = today

    if user_notifs_to_update:
        NotificationUser.objects.bulk_update(user_notifs_to_update, ['seen'])

    trip_notifs_to_update = list(
        NotificationTrip.objects.filter(
            notification__in=notifications,
            trip__usuarios__in=trip_user if recipient.role == "STUDENT" else [],
        ).exclude(user_seen__user=recipient).distinct()
    )
    for nt in trip_notifs_to_update:
        UserSeenNotification.objects.update_or_create(user=recipient, notification=nt, defaults={"date_seen": today})
