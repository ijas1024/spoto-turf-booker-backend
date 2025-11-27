from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/turf/chat/(?P<booking_id>[^/]+)/$', consumers.ChatConsumer.as_asgi()),
]