from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.contrib.auth.models import User

from .models import Team, Channel, Message
from .serializers import TeamSerializer, ChannelSerializer, MessageSerializer, UserSerializer

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """ Viewset to fetch user-related data """
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer
    queryset = User.objects.all()  # ✅ 1. Get all users

    @action(detail=False, methods=['get'])
    def in_team(self, request, team_id=None):
        team_id = request.query_params.get('team_id')
        team = get_object_or_404(Team, id=team_id)
        print("Team: ", team)
        users = team.members.all()
        print("Users: ", users)
        serializer = self.get_serializer(users, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def in_channel(self, request, channel_id=None):
        channel_id = request.query_params.get('channel_id')
        channel = get_object_or_404(Channel, id=channel_id)
        print("Channel: ", channel)
        users = channel.members.all()
        serializer = self.get_serializer(users, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='interacted')
    def interacted_users(self, request):
        user = request.user
        interacted_users = User.objects.filter(
            Q(sent_messages__recipient=user, sent_messages__message_type='direct') | 
            Q(received_messages__sender=user, received_messages__message_type='direct')
        ).distinct()
        serializer = self.get_serializer(interacted_users, many=True)
        return Response(serializer.data)


class TeamViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = TeamSerializer
    
    def get_queryset(self):
        return Team.objects.filter(members=self.request.user)
    
    def perform_create(self, serializer):
        team = serializer.save()
        team.members.add(self.request.user)
    
    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        team = self.get_object()
        user_id = request.data.get('user_id')
        
        if not user_id:
            return Response({'error': 'user_id is required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        user = get_object_or_404(User, id=user_id)
        team.members.add(user)
        
        return Response({'message': f'Added {user.username} to {team.name}'})

class ChannelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ChannelSerializer
    
    def get_queryset(self):
        return Channel.objects.filter(team__members=self.request.user)
    
    def perform_create(self, serializer):
        channel = serializer.save()
        channel_members = channel.team.members.all()
        channel.members.set(channel_members)
    
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        channel = self.get_object()
        messages = Message.objects.filter(channel=channel)
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def team_id(self, request, pk=None):
        team_id = request.data.get('team_id')
        if not team_id:
            return Response({'error': 'team_id is required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        team = get_object_or_404(Team, id=team_id, members=request.user)
        
        channels = Channel.objects.filter(team = team)
        serializer = self.get_serializer(channels, many=True)
        return Response(serializer.data)

class MessageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer

    def get_queryset(self):
        return Message.objects.filter(
            Q(channel__team__members=self.request.user) |
            Q(sender=self.request.user) |
            Q(recipient=self.request.user)
        )

    def perform_create(self, serializer):
        """Handles posting a message to a channel or a direct message"""
        message_type = self.request.data.get('message_type')
        channel_id = self.request.data.get('channel')
        recipient_id = self.request.data.get('recipient')

        # Ensure valid message_type is provided
        if message_type not in ['channels', 'direct']:
            raise serializers.ValidationError({"message_type": "Invalid message type. Use 'channels' or 'direct'."})

        # Validate Channel Message
        if message_type == 'channels':
            if not channel_id:
                raise serializers.ValidationError({"channel": "Channel ID is required for channel messages."})

            channel = get_object_or_404(Channel, id=channel_id)

            if self.request.user not in channel.members.all():
                raise serializers.ValidationError({"error": "You are not a member of this channel."})

            serializer.save(sender=self.request.user, channel=channel, message_type='channels')

        # Validate Direct Message
        elif message_type == 'direct':
            if not recipient_id:
                raise serializers.ValidationError({"recipient": "Recipient ID is required for direct messages."})

            recipient = get_object_or_404(User, id=recipient_id)

            if recipient == self.request.user:
                raise serializers.ValidationError({"recipient": "You cannot send a message to yourself."})

            serializer.save(sender=self.request.user, recipient=recipient, message_type='direct')

    @action(detail=False, methods=['get'])
    def direct_messages(self, request):

        user_id = request.query_params.get('user_id')

        if not user_id:
            return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        messages = Message.objects.filter(
            Q(message_type='direct') &
            (Q(sender=request.user, recipient_id=user_id) | 
            Q(sender_id=user_id, recipient=request.user))
        ).order_by('created_at')
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)
