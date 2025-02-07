from django.urls import re_path
from channels.routing import ProtocolTypeRouter, URLRouter
from .middleware import JwtAuthMiddleware  # Ensure middleware is applied
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/chat/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/team/(?P<team_id>\w+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/channel/(?P<channel_id>\w+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/dm/(?P<user_id>\w+)/$', consumers.ChatConsumer.as_asgi()),
]

# application = ProtocolTypeRouter({
#     "websocket": JwtAuthMiddleware(URLRouter(websocket_urlpatterns)),
# })
