from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'teams', views.TeamViewSet, basename='team')
router.register(r'channels', views.ChannelViewSet, basename='channel')
router.register(r'messages', views.MessageViewSet, basename='message')

urlpatterns = [
    path('', include(router.urls)),
    path('fetch-link-preview/', views.fetch_preview, name='fetch-preview'),
    path('upload-file/', views.upload_file, name='upload-file'),
    path('<int:file_id>/download/', views.download_file, name='download_file'),
]