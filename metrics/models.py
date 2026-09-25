from django.db import models

# Create your models here.
from django.db import models
from django.utils import timezone
from authentication.models import User


class LastRouteDay(models.Model):
    line = models.CharField(max_length=50)
    route = models.CharField(max_length=50)
    is_concluded = models.BooleanField(default=False)
    date = models.DateField()
    created_at = models.DateTimeField(auto_created=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
                    models.UniqueConstraint(
                        fields=['line', 'route', 'date'], 
                        name='unique_order_per_route_day'
                    )
                ]

    def __str__(self):
        return f"{self.line} - {self.route} ({self.date})"


class StopMetrics(models.Model):
    last_route_day = models.ForeignKey(
        LastRouteDay,
        on_delete=models.CASCADE,
        related_name='stop_metrics'
    )
    start_stop = models.CharField(max_length=100)
    end_stop = models.CharField(max_length=100)
    distance = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        null=False,      # Ajuste conforme necessidade
        blank=False
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    order = models.PositiveIntegerField()

    @property
    def line(self):
        return self.last_route_day.line

    @property
    def route(self):
        return self.last_route_day.route

    class Meta:
        ordering = ['start_time']
        constraints = [
            models.UniqueConstraint(
                fields=['last_route_day', 'order'], 
                name='unique_order_per_route_day'
            )
        ]

    def __str__(self):
        return f"{self.route}: {self.start_stop} -> {self.end_stop}"


class StudentsUsingBus(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bus_usages'
    )
    route = models.CharField(max_length=50, null=False)
    day = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ['-day']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'route', 'day'],
                name='unique_student_route_day'
            )
        ]

    def __str__(self):
        return f"{self.user.email} - {self.route} ({self.day})"

