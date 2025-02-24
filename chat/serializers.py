from rest_framework import serializers
from .models import Message, Channel, Team, TeamInvitation
from django.contrib.auth.models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']
    
class TeamSerializer(serializers.ModelSerializer):
    members = UserSerializer(many=True, read_only=True)
    class Meta:
        model = Team
        fields = ['id', 'name', 'description', 'members', 'created_at']

class ChannelSerializer(serializers.ModelSerializer):
    members = UserSerializer(many=True, read_only=True)
    class Meta:
        model = Channel
        fields = ['id', 'name', 'description', 'team', 'members', 'created_at']

class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    recipient = UserSerializer(read_only=True)
    class Meta:
        model = Message
        fields = ['id', 'sender', 'content', 'recipient', 'channel', 'message_type', 'reply_to', 'reactions', 'created_at']
        read_only_fields = ['sender', 'created_at']

class TeamInvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamInvitation
        fields = ['id', 'team', 'invite_code', 'created_at', 'expires_at', 'is_active']
        read_only_fields = ['invite_code', 'created_at', 'expires_at']