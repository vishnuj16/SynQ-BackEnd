from django.urls import re_path
from channels.routing import ProtocolTypeRouter, URLRouter
from .middleware import JwtAuthMiddleware  # Ensure middleware is applied
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/chat/$', consumers.ChatConsumer.as_asgi()),
]


