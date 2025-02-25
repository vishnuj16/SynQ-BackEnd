from django.utils import timezone
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import Team, Channel, Message, DirectMessageChannel
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
            print(f"User {self.user.id} added to group user_{self.user.id}")

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
            'team_notification': self.handle_team_notification,
            'create_channel': self.handle_create_channel,
            'add_team_member': self.handle_add_team_member,
            'get_channel_messages': self.handle_get_channel_messages,
            'get_direct_messages': self.handle_get_direct_messages,
            'get_team_channels': self.handle_get_team_channels,
            'get_team_members': self.handle_get_team_members,
            'get_interacted_users': self.handle_get_interacted_users,
            'delete_message': self.handle_delete_message,
            'reaction': self.handle_reaction,
        }

        handler = handlers.get(message_type)
        if handler:
            await handler(content)
        else:
            print(f"Unknown message type: {message_type}")
    
    async def handle_direct_message(self, content):
        recipient_id = content.get('recipient_id')
        message_text = content.get('content')
        team_id = content.get('team_id')
        reply_to = content.get('reply_to')
        channel_id = content.get('channel_id')  # Get the DM channel ID

        print("Getting direct message: ", content)
        if not all([recipient_id, message_text, team_id, channel_id]):
            return

        # Validate if the channel exists and user has access
        has_access = await self.validate_dm_channel_access(channel_id, recipient_id)
        if not has_access:
            print("User does not have permission to send messages in this DM channel.")
            return

        # Save the message to the DM channel
        message = await self.save_dm_channel_message(channel_id, message_text, reply_to)
        if message:
            await self.channel_layer.group_send(
                f"channel_{channel_id}",
                {   
                    "type": "chat.message",
                    "message": {
                        "id": message.id,
                        "sender": self.user.username,
                        "sender_id": self.user.id,
                        "content": message_text,
                        "timestamp": str(message.created_at),
                        "type": "direct",
                        "reply_to": reply_to,
                        "replied_message": message.reply_to.content if message.reply_to else None,
                        "team_id": team_id,
                        "channel_id": channel_id,
                        "recipient_id": recipient_id
                    }
                }
            )
            print("Sent DM through channel")

    async def handle_add_team_member(self, content):
        team_id = content.get('team_id')
        user_id = content.get('user_id')
        
        if await self.validate_team_membership(team_id):
            success = await self.add_team_member(team_id, user_id)
            if success:
                await self.channel_layer.group_send(
                    f"team_{team_id}",
                    {
                        "type": "member_added",
                        "data": {
                            "team_id": team_id,
                            "user_id": user_id
                        }
                    }
                )
    
    async def member_added(self, event):
        """Handler for broadcasting chat messages to clients."""
        print(f"Received message event: {event}")
        
        # Send message to WebSocket
        print(f"Sending message: {event['data']} with type {type(event['data'])}")
        await self.send_json(event["data"])

    async def handle_delete_message(self, content):
        print("Entering handle_delete_message method")
        print(f"Received content: {content}")

        message_id = content.get('message_id')
        message_type = content.get('type')  
        channel_id = await self.get_channel_for_message(message_id)

        print(f"Message ID: {message_id}")
        print(f"Message Type: {message_type}")
        print(f"Channel ID: {channel_id}")

        if not message_id or not channel_id:
            print("Missing message_id or channel_id")
            return

        try:
            print("Attempting to delete message")
            deleted = await self.delete_message(message_id)
            print(f"Delete result: {deleted}")
            
            if deleted:
                print("Message deletion confirmed")
                print(f"Sending message deletion to channel_{channel_id}")
                await self.channel_layer.group_send(
                    f"channel_{channel_id}",
                    {
                        "type": "message_deleted",
                        "data": {
                            "type": "message_deleted",
                            "message_id": message_id,
                            "message_type": message_type,
                            "channel_id": channel_id
                        }
                    }
                )
                print("Message deletion broadcast sent")
        except Exception as e:
            print(f"Error in handle_delete_message: {e}")
    
    
    async def handle_get_channel_messages(self, content):
        channel_id = content.get('channel_id')
        if await self.validate_channel_access(channel_id):
            messages = await self.get_channel_messages(channel_id)
            await self.send_json({
                "type": "channel_messages",
                "channel_id": channel_id,
                "messages": messages
            })

    
    async def handle_get_direct_messages(self, content):
        channel_id = content.get('channel_id')
        if await self.validate_channel_access(channel_id):
            messages = await self.get_channel_messages(channel_id)
            await self.send_json({
                "type": "direct_messages",
                "channel_id": channel_id,
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
        team_id = content.get('team_id')
        if await self.validate_team_membership(team_id):
            users = await self.get_interacted_users(team_id)
            await self.send_json({
                "type": "interacted_users",
                "team_id": team_id,
                "users": users
            })


    async def handle_channel_message(self, content):
        print(f"Handling channel message: {content}")

        channel_id = content.get('channel')
        message_text = content.get('content')
        reply_to = content.get('reply_to')

        if not all([channel_id, message_text]):
            print("Missing channel_id or message_text")
            return

        has_access = await self.validate_channel_access(channel_id)
        print(f"User has access to channel: {has_access}")

        if not has_access:
            print("User does not have permission to send messages in this channel.")
            return

        message = await self.save_channel_message(channel_id, message_text, reply_to)
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
                        "type": "channels",
                        "reply_to": reply_to,
                        "replied_message": message.reply_to.content if message.reply_to else None,
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
                        "type": "channel_created",
                        "channel": {
                            "id": channel.id,
                            "name": channel.name,
                            "team_id": team_id
                        }
                    }
                )
            
    async def channel_created(self, event):
        print(f"Received message event: {event}")
        
        # Send message to WebSocket
        print(f"Sending message: {event['channel']} with type {type(event['channel'])}")
        await self.send_json(event["channel"])

    async def handle_team_notification(self, content):
        team_id = content.get('team_id')
        notification_type = content.get('notification_type')
        
        if await self.validate_team_membership(team_id):
            await self.channel_layer.group_send(
                f"team_{team_id}",
                {
                    "type": "team_notification",
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

    async def handle_reaction(self, content):
        """Handle reaction updates and broadcast to relevant users"""
        message_id = content.get('message_id')
        reaction = content.get('reaction')
        
        # Get message details using database_sync_to_async
        message_data = await self.get_message_data(message_id)
        if not message_data:
            return
        
        # All messages are now in channels
        group_name = f"channel_{message_data['channel_id']}"

        # Broadcast the reaction update
        await self.channel_layer.group_send(
            group_name,
            {
                "type": "broadcast_reaction",
                "message_id": message_id,
                "reactions": message_data['reactions'],
                "user_id": self.user.id,
                "username": self.user.username,
                "reaction": reaction
            }
        )

    @database_sync_to_async
    def get_message_data(self, message_id):
        """Get message data from database in a sync context"""
        try:
            message = Message.objects.select_related('sender', 'channel').get(id=message_id)
            return {
                'id': message.id,
                'channel_id': message.channel.id if message.channel else None,
                'sender_id': message.sender.id,
                'reactions': message.reactions
            }
        except Message.DoesNotExist:
            return None
        except Exception as e:
            print(f"Error fetching message data: {e}")
            return None

    async def broadcast_reaction(self, event):
        """Send reaction update to connected clients"""
        await self.send_json({
            "type": "reaction_update",
            "message_id": event["message_id"],
            "reactions": event["reactions"],
            "user_id": event["user_id"],
            "username": event["username"],
            "reaction": event["reaction"]
        })

    @database_sync_to_async
    def get_user_teams(self):
        return list(Team.objects.filter(members=self.user))

    @database_sync_to_async
    def get_user_channels(self):
        return list(Channel.objects.filter(team__members=self.user, members=self.user))

    @database_sync_to_async
    def validate_channel_access(self, channel_id):
        try:
            channel = Channel.objects.get(id=channel_id, members=self.user)
            return True
        except Channel.DoesNotExist:
            return False

    @database_sync_to_async
    def validate_dm_channel_access(self, channel_id, recipient_id):
        try:
            # Check if this is a valid DM channel between the user and recipient
            channel = Channel.objects.get(
                id=channel_id, 
                is_direct_message=True,
                members=self.user
            )
            
            # Verify the recipient is also a member of this channel
            recipient = User.objects.get(id=recipient_id)
            return channel.members.filter(id=recipient.id).exists()
        except (Channel.DoesNotExist, User.DoesNotExist):
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
    def save_channel_message(self, channel_id, message_text, reply_to=None):
        try:
            channel = Channel.objects.get(id=channel_id, members=self.user)
            message = Message.objects.get(id=reply_to) if reply_to else None
            return Message.objects.create(
                sender=self.user,
                channel=channel,
                content=message_text,
                reply_to=message,
            )
        except Channel.DoesNotExist:
            return None

    @database_sync_to_async
    def save_dm_channel_message(self, channel_id, message_text, reply_to=None):
        try:
            channel = Channel.objects.get(id=channel_id, members=self.user, is_direct_message=True)
            message = Message.objects.get(id=reply_to) if reply_to else None
            return Message.objects.create(
                sender=self.user,
                channel=channel,
                content=message_text,
                reply_to=message,
            )
        except Channel.DoesNotExist:
            return None
        
    async def chat_message(self, event):
        """Handler for broadcasting chat messages to clients."""
        print(f"Received message event: {event}")
        
        # Send message to WebSocket
        print(f"Sending message: {event['message']} with type {type(event['message'])}")
        await self.send_json(event["message"])

    @database_sync_to_async
    def is_team_member(self):
        # Check if user is a member of any team
        return Team.objects.filter(members=self.user).exists()

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
            # Add user to all team channels (except DM channels)
            for channel in team.channels.filter(is_direct_message=False):
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
                "sender_id": msg.sender.id,
                "timestamp": str(msg.created_at),
                # "message_type": msg.message_type,
                "reply_to": msg.reply_to.id if msg.reply_to else None,
                "replied_message": msg.reply_to.content if msg.reply_to else None,
                "reactions": msg.reactions or {}
            }
            for msg in messages
        ]
    
    @database_sync_to_async
    def get_team_channels(self, team_id):
        channels = Channel.objects.filter(team_id=team_id, members=self.user)
        return [
            {
                "id": channel.id,
                "name": channel.name,
                "team_id": team_id,
                "is_direct_message": channel.is_direct_message,
                "channel_type": channel.channel_type
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
    def get_interacted_users(self, team_id):
        # Find users that have DM channels with the current user in this team
        team = Team.objects.get(id=team_id)
        
        # Get all DirectMessageChannel objects where this user is involved
        dm_channels = DirectMessageChannel.objects.filter(
            Q(user1=self.user) | Q(user2=self.user),
            channel__team=team
        )
        
        interacted_users = []
        for dm in dm_channels:
            # Add the other user in the DM channel
            other_user = dm.user1 if dm.user2.id == self.user.id else dm.user2
            interacted_users.append({
                "id": other_user.id,
                "username": other_user.username,
                "channel_id": dm.channel.id
            })
            
        return interacted_users

    @database_sync_to_async
    def delete_message(self, message_id):
        try:
            print(f"Attempting to delete message {message_id}")
            message = Message.objects.get(id=message_id, sender=self.user)
            print("Message found, proceeding with deletion")
            message.delete()
            print("Message deleted successfully")
            return True
        except Message.DoesNotExist:
            print("Message not found or user not authorized to delete")
            return False

    @database_sync_to_async
    def get_channel_for_message(self, message_id):
        try:
            print(f"Retrieving channel for message {message_id}")
            message = Message.objects.get(id=message_id)
            channel_id = message.channel.id if message.channel else None
            print(f"Retrieved channel ID: {channel_id}")
            return channel_id
        except Message.DoesNotExist:
            print("Message not found when retrieving channel")
            return None

    async def message_deleted(self, event):
        """Handler for message deletion events"""
        print(f"Received message deletion event: {event}")
        await self.send_json(event['data'])