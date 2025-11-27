import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import Message
from .models import Notification as _Notification

User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # booking_id used as room identifier (chat per booking)
        self.booking_id = self.scope['url_route']['kwargs'].get('booking_id')
        self.room_group_name = f'chat_{self.booking_id}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data.get('message')
        sender_id = data.get('sender_id')
        receiver_id = data.get('receiver_id')

        msg = await self.save_message(sender_id, receiver_id, message)
        # broadcast to group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': msg.content,
                'sender_id': msg.sender.id,
                'receiver_id': msg.receiver.id,
                'timestamp': msg.timestamp.isoformat()
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def save_message(self, sender_id, receiver_id, message):
        sender = User.objects.get(id=sender_id)
        receiver = User.objects.get(id=receiver_id)
        msg = Message.objects.create(sender=sender, receiver=receiver, content=message)
        # create notification if Notification model exists
        try:
            Notification = _Notification
            Notification.objects.create(user=receiver, message=f'New message from {sender.username}', type='chat')
        except Exception:
            pass
        return msg