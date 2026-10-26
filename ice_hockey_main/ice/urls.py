from django.urls import path
from .views import  create_transmitter, status_log_view
from . import views
from django.conf.urls import handler404
from django.conf.urls.static import static
from django.conf import settings







urlpatterns = [


    path('transmitters/', views.create_transmitter),
    path('', views.transmitter_list,name='home'),
    path('transmitter-data/', views.transmitter_data_json, name='transmitter_data_json'),

    path('delete/<str:device_uid>/', views.delete_read, name='delete_read'),
    path('status-logs/', status_log_view, name='status_log_view'),
    path('status-logs/json/', views.status_log_json, name='status_log_json'),
    path('trim-video/', views.trim_video, name='trim_video'),
    path('check-statuslog/', views.check_statuslog, name='check_statuslog'),
    path('upload-video/', views.upload_video, name='upload_video'),
    path('trimmed-videos/', views.trimmed_videos, name='trimmed_videos'),
    path('delete-trimmed/', views.delete_trimmed_video, name='delete_trimmed_video'),
    path('trim-video/start/', views.start_trim, name='start_trim'),
    path('trim-video/progress/', views.trim_progress, name='trim_progress'),
    path('uploaded-videos/', views.uploaded_videos, name='uploaded_videos'),
    path('delete-uploaded/', views.delete_uploaded_video, name='delete_uploaded_video'), 
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = 'ice.views.custom_404_view'
