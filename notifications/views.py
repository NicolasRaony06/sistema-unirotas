from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from . import service as notifications_service
from django.utils import timezone
# Create your views here.

@login_required()
def notifications(request):
    user = request.user
    notifications, _ = notifications_service.fetch_notifications(user)
    cleaned_not = []
    for notification in notifications:
        not_obj = notification.notification_user.filter(recipient=request.user).first() if notification.notification_user.filter(recipient=request.user).first() else notification.notification_trip.filter(trip__usuarios__estudante__user=request.user).first()
        cleaned_not.append(not_obj)
    return render(request, "notifications/notifications.html", {"notifications": cleaned_not, "now": timezone.now()})

@login_required()
def mark_as_seen(request):
    if request.method == "POST":
        notifications_service.mark_notification_as_seen(request.user)
        return redirect("notifications:view")
    else:
        return redirect("notifications:view")