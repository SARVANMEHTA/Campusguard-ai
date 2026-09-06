from django.urls import path
from . import views

app_name = 'surveillance'

urlpatterns = [
    path('live/', views.live_monitor_view, name='live_monitor'),
    path('stream/', views.live_stream_feed, name='live_stream'),
    path('node/push/', views.ingest_node_frame, name='node_push'),
    path('node/status/', views.node_status_view, name='node_status'),
    path('process-frame/', views.process_single_image, name='process_single_image'),
]
