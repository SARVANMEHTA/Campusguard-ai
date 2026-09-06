from django.urls import path
from . import views

app_name = 'surveillance'

urlpatterns = [
    path('live/', views.live_monitor_view, name='live_monitor'),
    path('stream/', views.live_stream_feed, name='live_stream'),
    path('process-frame/', views.process_single_image, name='process_single_image'),
]
