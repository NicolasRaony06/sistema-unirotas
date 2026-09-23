from django.urls import path
from . import views

app_name = 'metrics'

urlpatterns = [
    # Views de template
    path('', views.dashboard, name='dashboard'),
    path('route/<str:route_name>/', views.route_detail, name='route_detail'),
    path('routes/', views.all_routes, name='all_routes'),
    path('student/<int:user_id>/', views.student_usage, name='student_usage'),
    
    # API endpoints - POST (registro)
    path('api/register-route/', views.api_register_route, name='api_register_route'),
    path('api/register-stop/', views.api_register_stop_metric, name='api_register_stop_metric'),
    path('api/student-bus/', views.api_record_student_bus, name='api_student_bus'),
    
    # API endpoints - GET (consulta)
    path('api/daily-metrics/', views.api_get_daily_metrics, name='api_daily_metrics'),
    path('api/route/<str:route_name>/summary/', views.api_get_route_summary, name='api_route_summary'),
    path('api/student/<int:user_id>/usage/', views.api_get_student_usage, name='api_student_usage'),
    path('api/eta/', views.api_estimate_eta, name='api_estimate_eta'),
]
