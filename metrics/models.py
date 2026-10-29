from django.db import models

# Create your models here.
from django.utils import timezone
from authentication.models import User
from management.models import Linha, Rota, BusStop

class LastRouteDay(models.Model):
    line = models.ForeignKey(Linha, on_delete=models.CASCADE, related_name="metric_route_day")
    route = models.ForeignKey(Rota, on_delete=models.CASCADE, related_name="metric_route_day")
    is_concluded = models.BooleanField(default=False)
    date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
                    models.UniqueConstraint(
                        fields=['line', 'route', 'date'], 
                        name='unique_line_route_per_day'
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

    start_stop = models.ForeignKey(BusStop, on_delete=models.CASCADE, related_name="startstop_metric")
    end_stop = models.ForeignKey(BusStop, on_delete=models.CASCADE, related_name="endstop_metric", null=True)
    distance = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        null=True,
        blank=True
    )
    order = models.PositiveIntegerField()
    
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True)

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
        return f"{self.last_route_day}: {self.start_stop} -> {self.end_stop}"


class StudentsUsingBus(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bus_usages'
    )
    route = models.ForeignKey(Rota, on_delete=models.CASCADE, related_name="student_on_route_day")
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

