from django.contrib import admin
from .models import LastRouteDay, StopMetrics, StudentsUsingBus


@admin.register(LastRouteDay)
class LastRouteDayAdmin(admin.ModelAdmin):
    list_display = ('line', 'route', 'date', 'created_at')
    list_filter = ('line', 'date')
    search_fields = ('line', 'route')
    readonly_fields = ('created_at',)
    date_hierarchy = 'date'
    ordering = ('-date',)


@admin.register(StopMetrics)
class StopMetricsAdmin(admin.ModelAdmin):
    list_display = ('id', 'last_route_day', 'start_stop', 'end_stop', 'start_time', 'end_time')
    list_filter = ('last_route_day__line', 'last_route_day__date')
    search_fields = ('start_stop', 'end_stop', 'last_route_day__route')
    readonly_fields = ()
    date_hierarchy = 'last_route_day__date'
    ordering = ('-last_route_day__date', '-start_time')


@admin.register(StudentsUsingBus)
class StudentsUsingBusAdmin(admin.ModelAdmin):
    list_display = ('user', 'route', 'day')
    list_filter = ('route', 'day')
    search_fields = ('user__email', 'user__full_name', 'route')
    date_hierarchy = 'day'
    ordering = ('-day',)

