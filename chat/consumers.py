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

        handlers = {
            'channel_message': self.handle_channel_message,
            'direct_message': self.handle_direct_message,
            'join_team': self.handle_join_team,
            'leave_team': self.handle_leave_team,
            'team_notification': self.handle_team_notification,
            'create_channel': self.handle_create_channel,
            'add_team_member': self.handle_add_team_member,
            'get_channel_messages': self.handle_get_channel_messages,
            'get_direct_messages': self.handle_get_direct_messages,
            'get_team_channels': self.handle_get_team_channels,
            'get_team_members': self.handle_get_team_members,
            'get_interacted_users': self.handle_get_interacted_users
        }

        handler = handlers.get(message_type)
        if handler:
            await handler(content)
        else:
            print(f"Unknown message type: {message_type}")
    
    async def handle_direct_message(self, content):
        recipient_id = content.get('recipient')
        message_text = content.get('content')

        if not all([recipient_id, message_text]):
            return

        message = await self.save_direct_message(recipient_id, message_text)
        if message:
            # Send to recipient's personal group
            await self.channel_layer.group_send(
                f"user_{recipient_id}",
                {
                    "type": "chat.message",
                    "message": {
                        "id": message.id,
                        "sender": self.user.username,
                        "content": message_text,
                        "timestamp": str(message.created_at),
                        "message_type": "direct",
                        "recipient_id": recipient_id
                    }
                }
            )
    
    async def handle_add_team_member(self, content):
        team_id = content.get('team_id')
        user_id = content.get('user_id')
        
        if await self.validate_team_membership(team_id):
            success = await self.add_team_member(team_id, user_id)
            if success:
                await self.channel_layer.group_send(
                    f"team_{team_id}",
                    {
                        "type": "member.added",
                        "data": {
                            "team_id": team_id,
                            "user_id": user_id
                        }
                    }
                )
    
    async def handle_get_channel_messages(self, content):
        channel_id = content.get('channel_id')
        if await self.validate_team_channel_access(channel_id):
            messages = await self.get_channel_messages(channel_id)
            await self.send_json({
                "type": "channel_messages",
                "channel_id": channel_id,
                "messages": messages
            })
    
    async def handle_get_direct_messages(self, content):
        user_id = content.get('user_id')
        messages = await self.get_direct_messages(user_id)
        await self.send_json({
            "type": "direct_messages",
            "user_id": user_id,
            "messages": messages
        })

    async def handle_get_team_channels(self, content):
        team_id = content.get('team_id')
        if await self.validate_team_membership(team_id):
            channels = await self.get_team_channels(team_id)
            await self.send_json({
                "type": "team_channels",
                "team_id": team_id,
                "channels": channels
            })
    
    async def handle_get_team_members(self, content):
        team_id = content.get('team_id')
        if await self.validate_team_membership(team_id):
            members = await self.get_team_members(team_id)
            await self.send_json({
                "type": "team_members",
                "team_id": team_id,
                "members": members
            })
    
    async def handle_get_interacted_users(self, content):
        users = await self.get_interacted_users()
        await self.send_json({
            "type": "interacted_users",
            "users": users
        })


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

    async def handle_create_channel(self, content):
        team_id = content.get('team_id')
        channel_name = content.get('name')
        
        if await self.validate_team_membership(team_id):
            channel = await self.create_channel(team_id, channel_name)
            if channel:
                await self.channel_layer.group_send(
                    f"team_{team_id}",
                    {
                        "type": "channel.created",
                        "channel": {
                            "id": channel.id,
                            "name": channel.name,
                            "team_id": team_id
                        }
                    }
                )

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

    @database_sync_to_async
    def create_channel(self, team_id, channel_name):
        team = Team.objects.get(id=team_id)
        channel = Channel.objects.create(team=team, name=channel_name)
        channel.members.set(team.members.all())
        return channel

    @database_sync_to_async
    def add_team_member(self, team_id, user_id):
        try:
            team = Team.objects.get(id=team_id)
            user = User.objects.get(id=user_id)
            team.members.add(user)
            # Add user to all team channels
            for channel in team.channels.all():
                channel.members.add(user)
            return True
        except (Team.DoesNotExist, User.DoesNotExist):
            return False
    
    @database_sync_to_async
    def get_channel_messages(self, channel_id):
        messages = Message.objects.filter(channel_id=channel_id).order_by('created_at')
        return [
            {
                "id": msg.id,
                "content": msg.content,
                "sender": msg.sender.username,
                "timestamp": str(msg.created_at)
            }
            for msg in messages
        ]
    
    @database_sync_to_async
    def get_direct_messages(self, user_id):
        messages = Message.objects.filter(
            Q(message_type='direct') &
            (Q(sender=self.user, recipient_id=user_id) | 
             Q(sender_id=user_id, recipient=self.user))
        ).order_by('created_at')
        return [
            {
                "id": msg.id,
                "content": msg.content,
                "sender": msg.sender.username,
                "recipient": msg.recipient.username,
                "timestamp": str(msg.created_at)
            }
            for msg in messages
        ]
    
    @database_sync_to_async
    def get_team_channels(self, team_id):
        channels = Channel.objects.filter(team_id=team_id)
        return [
            {
                "id": channel.id,
                "name": channel.name,
                "team_id": team_id
            }
            for channel in channels
        ]
    
    @database_sync_to_async
    def get_team_members(self, team_id):
        team = Team.objects.get(id=team_id)
        return [
            {
                "id": user.id,
                "username": user.username
            }
            for user in team.members.all()
        ]

    @database_sync_to_async
    def get_interacted_users(self):
        interacted_users = User.objects.filter(
            Q(sent_messages__recipient=self.user, sent_messages__message_type='direct') | 
            Q(received_messages__sender=self.user, received_messages__message_type='direct')
        ).distinct()
        return [
            {
                "id": user.id,
                "username": user.username
            }
            for user in interacted_users
        ]