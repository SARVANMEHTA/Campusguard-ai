from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_overview, name='overview'),
    path('queue/high-confidence/', views.high_confidence_queue, name='high_confidence_queue'),
    path('queue/low-confidence/', views.low_confidence_queue, name='low_confidence_queue'),
    path('detection/<int:pk>/verify/', views.verify_detection, name='verify_detection'),
    path('detection/<int:pk>/verify-only/', views.verify_only_detection, name='verify_only_detection'),
    path('detection/<int:pk>/send-alert/', views.send_alert_detection, name='send_alert_detection'),
    path('detection/<int:pk>/reject/', views.reject_detection, name='reject_detection'),
    path('detection/<int:pk>/ok/', views.acknowledge_detection, name='acknowledge_detection'),
    path('detection/<int:pk>/', views.detection_detail, name='detection_detail'),
    path('logs/', views.detection_logs, name='detection_logs'),
    path('analytics/', views.analytics_view, name='analytics'),
]
