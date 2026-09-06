from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    path('students/', views.SuspendedStudentListAPI.as_view(), name='student_list_api'),
    path('students/<int:pk>/', views.SuspendedStudentDetailAPI.as_view(), name='student_detail_api'),
    path('detections/', views.DetectionLogListAPI.as_view(), name='detection_list_api'),
    path('queues/high-confidence/', views.HighConfidenceQueueAPI.as_view(), name='high_confidence_queue_api'),
    path('queues/low-confidence/', views.LowConfidenceQueueAPI.as_view(), name='low_confidence_queue_api'),
    path('detections/<int:pk>/verify/', views.verify_detection_api, name='verify_detection_api'),
    path('detections/<int:pk>/reject/', views.reject_detection_api, name='reject_detection_api'),
    path('stats/', views.system_stats_api, name='system_stats_api'),
]
