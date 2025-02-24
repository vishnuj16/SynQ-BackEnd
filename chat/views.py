from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.contrib.auth.models import User

from django.utils import timezone
from datetime import timedelta
from django.utils.crypto import get_random_string


from .models import Team, Channel, Message, TeamInvitation
from .serializers import TeamSerializer, ChannelSerializer, MessageSerializer, UserSerializer, TeamInvitationSerializer

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
        team_id = request.query_params.get('team_id')

        if not team_id:
            return Response({'error': 'team_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate if the team exists and the user is part of it
        team = get_object_or_404(Team, id=team_id, members=user)

        # Get users the current user has interacted with (direct messages)
        interacted_users = User.objects.filter(
            Q(sent_messages__recipient=user, sent_messages__message_type='direct') |
            Q(received_messages__sender=user, received_messages__message_type='direct'),
            teams=team  # Ensures filtering only within the given team
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
    
    @action(detail=True, methods=['post'])
    def create_invitation(self, request, pk=None):
        """Create a new invitation link for the team"""
        team = self.get_object()
        
        # Check if user has permission to create invitation (optional)
        if request.user not in team.members.all():
            return Response(
                {'error': 'You do not have permission to create invitations for this team'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Generate unique invitation code
        invite_code = get_random_string(length=12)
        
        # Set expiration (e.g., 7 days from now)
        expires_at = timezone.now() + timedelta(days=7)
        
        # Create invitation
        invitation = TeamInvitation.objects.create(
            team=team,
            created_by=request.user,
            invite_code=invite_code,
            expires_at=expires_at
        )
        
        invitation_url = f"/join-team/{invite_code}"  # Frontend URL format
        
        return Response({
            'invite_code': invite_code,
            'invitation_url': invitation_url,
            'expires_at': expires_at
        })
    
    @action(detail=False, methods=['post'])
    def join_via_invitation(self, request):
        """Join a team using an invitation code"""
        invite_code = request.data.get('invite_code')
        
        if not invite_code:
            return Response(
                {'error': 'Invitation code is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            invitation = TeamInvitation.objects.get(
                invite_code=invite_code,
                is_active=True,
                expires_at__gt=timezone.now()
            )
        except TeamInvitation.DoesNotExist:
            return Response(
                {'error': 'Invalid or expired invitation code'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        team = invitation.team
        
        # Check if user is already a member
        if request.user in team.members.all():
            return Response(
                {'error': 'You are already a member of this team'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Add user to team
        team.members.add(request.user)
        
        # Add user to all team channels
        for channel in team.channels.all():
            channel.members.add(request.user)
        
        # Optional: Deactivate invitation after use
        # invitation.is_active = False
        # invitation.save()
        
        serializer = self.get_serializer(team)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def invitations(self, request, pk=None):
        """Get all active invitations for a team"""
        team = self.get_object()
        
        if request.user not in team.members.all():
            return Response(
                {'error': 'You do not have permission to view invitations for this team'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        invitations = TeamInvitation.objects.filter(
            team=team,
            is_active=True,
            expires_at__gt=timezone.now()
        )
        
        serializer = TeamInvitationSerializer(invitations, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def revoke_invitation(self, request, pk=None):
        """Revoke a specific invitation"""
        team = self.get_object()
        invite_code = request.data.get('invite_code')
        
        if not invite_code:
            return Response(
                {'error': 'Invitation code is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            invitation = TeamInvitation.objects.get(
                team=team,
                invite_code=invite_code,
                is_active=True
            )
        except TeamInvitation.DoesNotExist:
            return Response(
                {'error': 'Invalid invitation code'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        if request.user not in team.members.all():
            return Response(
                {'error': 'You do not have permission to revoke invitations for this team'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        invitation.is_active = False
        invitation.save()
        
        return Response({'message': 'Invitation revoked successfully'})

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
        reply_to_id = self.request.data.get('reply_to')

        # Ensure valid message_type is provided
        if message_type not in ['channels', 'direct']:
            raise serializers.ValidationError({"message_type": "Invalid message type. Use 'channels' or 'direct'."})

        reply_to = None
        if reply_to_id:
            reply_to = get_object_or_404(Message, id=reply_to_id)

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

    @action(detail=True, methods=['delete'])
    def delete_message(self, request, pk=None):
        message = get_object_or_404(Message, id=pk)

        if message.sender != request.user: 
            return Response({"Error": "You can only delete your messages"}, status=status.HTTP_403_FORBIDDEN)
        
        message.delete()

        return Response({"Message": "Message deleted Successfully"}, status=status.HTTP_200_OK)

    
    @action(detail=True, methods=['post'])
    def react(self, request, pk=None):
        """React to a message with enhanced response"""
        message = get_object_or_404(Message, pk=pk)
        reaction = request.data.get('reaction')

        if not reaction:
            return Response({"error": "Reaction is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Initialize reactions dict if None
        if not message.reactions:
            message.reactions = {}

        user = request.user.username
        message.reactions[user] = reaction
        message.save()

        # Return the full reactions object for the frontend
        return Response({
            "message_id": message.id,
            "reactions": message.reactions,
            "updated_by": user,
            "reaction": reaction
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['delete'])
    def remove_reaction(self, request, pk=None):
        """Remove a reaction from a message with enhanced response"""
        message = get_object_or_404(Message, pk=pk)
        user = request.user.username

        if not message.reactions or user not in message.reactions:
            return Response({"error": "No reaction to remove for this user."}, 
                          status=status.HTTP_400_BAD_REQUEST)

        del message.reactions[user]
        message.save()

        return Response({
            "message_id": message.id,
            "reactions": message.reactions,
            "updated_by": user
        }, status=status.HTTP_200_OK)