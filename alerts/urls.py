from django.urls import path
from . import views

app_name = 'alerts'

urlpatterns = [
    path('recipients/', views.recipient_list, name='recipient_list'),
    path('recipients/<int:pk>/edit/', views.recipient_edit, name='recipient_edit'),
    path('recipients/<int:pk>/delete/', views.recipient_delete, name='recipient_delete'),
    path('recipients/<int:pk>/toggle/', views.recipient_toggle, name='recipient_toggle'),
    path('send-test/', views.send_test_email, name='send_test_email'),
    path('send-test-whatsapp/', views.send_test_whatsapp, name='send_test_whatsapp'),
]
