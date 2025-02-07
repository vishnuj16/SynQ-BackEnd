from django.utils import timezone
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import Team, Channel, Message
from django.db.models import Q

class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        print(f"User connecting: {self.user}")

        if self.user.is_anonymous:
            print("User is anonymous, closing connection.")
            await self.close()
            return

        print("Connection accepted!")
        await self.accept()

        self.teams = await self.get_user_teams()
        self.channels = await self.get_user_channels()

        print(f"User teams: {self.teams}")
        print(f"User channels: {self.channels}")

        if self.is_team_member():
            await self.channel_layer.group_add(f"user_{self.user.id}", self.channel_name)

            for team in self.teams:
                print(f"Adding user to team_{team.id}")
                await self.channel_layer.group_add(f"team_{team.id}", self.channel_name)

            for channel in self.channels:
                print(f"Adding user to channel_{channel.id}")
                await self.channel_layer.group_add(f"channel_{channel.id}", self.channel_name)



    async def disconnect(self, close_code):
        if not hasattr(self, 'user') or self.user.is_anonymous:
            return

        # Leave personal group
        await self.channel_layer.group_discard(f"user_{self.user.id}", self.channel_name)

        # Leave team groups
        user_teams = await self.get_user_teams()
        for team in user_teams:
            await self.channel_layer.group_discard(f"team_{team.id}", self.channel_name)

        # Leave channel groups
        user_channels = await self.get_user_channels()
        for channel in user_channels:
            await self.channel_layer.group_discard(f"channel_{channel.id}", self.channel_name)


    async def receive_json(self, content):
        print(f"Received message: {content}")

        message_type = content.get('message_type')

        if message_type == 'channel_message':
            print("Handling channel message")
            await self.handle_channel_message(content)
        elif message_type == 'direct_message':
            print("Handling direct message")
            await self.handle_direct_message(content)
        elif message_type == 'join_team':
            print("Handling join team request")
            await self.handle_join_team(content)
        elif message_type == 'leave_team':
            print("Handling leave team request")
            await self.handle_leave_team(content)
        elif message_type == 'team_notification':
            print("Handling team notification")
            await self.handle_team_notification(content)


    async def handle_channel_message(self, content):
        print(f"Handling channel message: {content}")

        channel_id = content.get('channel')
        message_text = content.get('content')

        if not all([channel_id, message_text]):
            print("Missing channel_id or message_text")
            return

        has_access = await self.validate_team_channel_access(channel_id)
        print(f"User has access to channel: {has_access}")

        if not has_access:
            print("User does not have permission to send messages in this channel.")
            return

        message = await self.save_channel_message(channel_id, message_text)
        print(f"Message saved: {message}")

        if message:
            team_id = await self.get_team_id_for_channel(channel_id)
            print(f"Broadcasting message to channel_{channel_id}")

            await self.channel_layer.group_send(
                f"channel_{channel_id}",
                {
                    "type": "chat.message",
                    "message": {
                        "id": message.id,
                        "sender": self.user.username,
                        "content": message_text,
                        "timestamp": str(message.created_at),
                        "message_type": "channels",
                        "team_id": team_id,
                        "channel_id": channel_id
                    }
                }
            )
            print("Message sent to channel group")


    async def handle_team_notification(self, content):
        team_id = content.get('team_id')
        notification_type = content.get('notification_type')
        
        if await self.validate_team_membership(team_id):
            await self.channel_layer.group_send(
                f"team_{team_id}",
                {
                    "type": "team.notification",
                    "notification": {
                        "type": notification_type,
                        "team_id": team_id,
                        "sender": self.user.username,
                        "timestamp": str(timezone.now())
                    }
                }
            )

    async def team_notification(self, event):
        """Handler for team-wide notifications"""
        await self.send_json(event['notification'])

    @database_sync_to_async
    def get_user_teams(self):
        return list(Team.objects.filter(members=self.user))

    @database_sync_to_async
    def get_user_channels(self):
        return list(Channel.objects.filter(team__members=self.user))

    @database_sync_to_async
    def validate_team_channel_access(self, channel_id):
        try:
            channel = Channel.objects.get(id=channel_id)
            return channel.team.members.filter(id=self.user.id).exists()
        except Channel.DoesNotExist:
            return False

    @database_sync_to_async
    def validate_team_membership(self, team_id):
        return Team.objects.filter(id=team_id, members=self.user).exists()

    @database_sync_to_async
    def get_team_id_for_channel(self, channel_id):
        try:
            channel = Channel.objects.get(id=channel_id)
            return channel.team.id
        except Channel.DoesNotExist:
            return None

    @database_sync_to_async
    def save_channel_message(self, channel_id, message_text):
        try:
            channel = Channel.objects.get(id=channel_id)
            if channel.team.members.filter(id=self.user.id).exists():
                return Message.objects.create(
                    sender=self.user,
                    channel=channel,
                    content=message_text,
                    message_type='channels'
                )
        except Channel.DoesNotExist:
            return None

    @database_sync_to_async
    def save_direct_message(self, recipient_id, message_text):
        try:
            recipient = User.objects.get(id=recipient_id)
            return Message.objects.create(
                sender=self.user,
                recipient=recipient,
                content=message_text,
                message_type='direct'
            )
        except User.DoesNotExist:
            return None
        
    async def chat_message(self, event):
        """Handler for broadcasting chat messages to clients."""
        print(f"Received message event: {event}")
        
        # Send message to WebSocket
        print(f"Sending message: {event['message']} with type {type(event['message'])}")
        await self.send_json(event["message"])

    
    @database_sync_to_async
    def is_team_member(self, team_id):
        return Team.objects.filter(id=team_id, members=self.user).exists()
