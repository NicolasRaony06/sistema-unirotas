from django.db import models

# Create your models here.
from django.utils import timezone
from authentication.models import User


class LastRouteDay(models.Model):
    line_id = models.PositiveIntegerField()
    route_id = models.PositiveIntegerField()
    is_concluded = models.BooleanField(default=False)
    date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
                    models.UniqueConstraint(
                        fields=['line_id', 'route_id', 'date'], 
                        name='unique_line_route_per_day'
                    )
                ]

    def __str__(self):
        return f"{self.line_id} - {self.route_id} ({self.date})"


class StopMetrics(models.Model):
    last_route_day = models.ForeignKey(
        LastRouteDay,
        on_delete=models.CASCADE,
        related_name='stop_metrics'
    )
    start_stop_id = models.PositiveIntegerField()
    end_stop_id = models.PositiveIntegerField()
    distance = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        null=True,
        blank=True
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    order = models.PositiveIntegerField()

    @property
    def line(self):
        return self.last_route_day.line_id

    @property
    def route(self):
        return self.last_route_day.route_id

    class Meta:
        ordering = ['start_time']
        constraints = [
            models.UniqueConstraint(
                fields=['last_route_day', 'order'], 
                name='unique_order_per_route_day'
            )
        ]

    def __str__(self):
        return f"{self.last_route_day}: {self.start_stop_id} -> {self.end_stop_id}"


class StudentsUsingBus(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bus_usages'
    )
    route_id = models.IntegerField()
    day = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ['-day']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'route_id', 'day'],
                name='unique_student_route_day'
            )
        ]

    def __str__(self):
        return f"{self.user.email} - {self.route_id} ({self.day})"

