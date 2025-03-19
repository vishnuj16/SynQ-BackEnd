import os
from django.http import FileResponse
from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action, permission_classes, api_view
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.contrib.auth.models import User

from django.utils import timezone
from datetime import timedelta
from django.utils.crypto import get_random_string

from .models import Team, Channel, Message, TeamInvitation, DirectMessageChannel
from .serializers import (TeamSerializer, ChannelSerializer, MessageSerializer, 
                         UserSerializer, TeamInvitationSerializer, DirectMessageChannelSerializer)
from .utils import fetch_link_preview

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from .models import FileAttachment

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """ Viewset to fetch user-related data """
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer
    queryset = User.objects.all()

    @action(detail=False, methods=['get'])
    def in_team(self, request):
        team_id = request.query_params.get('team_id')
        team = get_object_or_404(Team, id=team_id)
        users = team.members.all()
        serializer = self.get_serializer(users, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def in_channel(self, request):
        channel_id = request.query_params.get('channel_id')
        channel = get_object_or_404(Channel, id=channel_id)
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

        # Get users the current user has direct message channels with
        interacted_users = User.objects.filter(
            (
                Q(dm_channels_as_user1__user2=user) | 
                Q(dm_channels_as_user2__user1=user)
            ),
            teams=team
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
        
        # Add user to all public team channels (excluding DM channels)
        for channel in team.channels.filter(is_direct_message=False):
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
        return Channel.objects.filter(team__members=self.request.user, members=self.request.user)
    
    def perform_create(self, serializer):
        channel = serializer.save()
        if not channel.is_direct_message:
            # For regular channels, add all team members
            channel_members = channel.team.members.all()
            channel.members.set(channel_members)
    
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        channel = self.get_object()
        messages = Message.objects.filter(channel=channel)
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def team_id(self, request):
        team_id = request.data.get('team_id')
        if not team_id:
            return Response({'error': 'team_id is required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        team = get_object_or_404(Team, id=team_id, members=request.user)
        
        # Return all channels the user is a member of (both group and DM)
        channels = Channel.objects.filter(team=team, members=request.user)
        serializer = self.get_serializer(channels, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def create_or_get_dm_channel(self, request):
        """Create or get a DM channel between the current user and another user"""
        team_id = request.data.get('team_id')
        user_id = request.data.get('user_id')

        if not team_id or not user_id:
            return Response({'error': 'team_id and user_id are required'},
                            status=status.HTTP_400_BAD_REQUEST)

        team = get_object_or_404(Team, id=team_id, members=request.user)
        other_user = get_object_or_404(User, id=user_id)

        # Make sure other user is in the same team
        if other_user not in team.members.all():
            return Response({'error': 'User is not a member of this team'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Sort users by ID to ensure consistent order
        user1, user2 = sorted([request.user, other_user], key=lambda u: u.id)

        # Try to find existing DM channel
        try:
            dm_channel = DirectMessageChannel.objects.get(
                user1=user1,
                user2=user2,
                channel__team=team
            )
            serializer = ChannelSerializer(dm_channel.channel)
            return Response(serializer.data)

        except DirectMessageChannel.DoesNotExist:
            # Create new DM channel
            channel_name = f"DM: {request.user.username} and {other_user.username}"
            channel = Channel.objects.create(
                name=channel_name,
                team=team,
                is_direct_message=True,
                channel_type='direct'
            )
            # Add both users to the channel
            channel.members.add(request.user, other_user)

            # Create the DM metadata
            DirectMessageChannel.objects.create(
                channel=channel,
                user1=user1,
                user2=user2
            )

            serializer = ChannelSerializer(channel)
            return Response(serializer.data)


class MessageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer

    def get_queryset(self):
        return Message.objects.filter(
            channel__members=self.request.user
        )

    def perform_create(self, serializer):
        """Handles posting a message to a channel"""
        channel_id = self.request.data.get('channel')
        reply_to_id = self.request.data.get('reply_to')
        link_preview = self.request.data.get('link_preview')

        if not channel_id:
            raise serializers.ValidationError({"channel": "Channel ID is required for messages."})

        channel = get_object_or_404(Channel, id=channel_id)

        # Check if user is a member of the channel
        if self.request.user not in channel.members.all():
            raise serializers.ValidationError({"error": "You are not a member of this channel."})
        

        reply_to = None
        if reply_to_id:
            reply_to = get_object_or_404(Message, id=reply_to_id)

        serializer.save(sender=self.request.user, channel=channel, reply_to=reply_to, link_preview=link_preview)

    @action(detail=False, methods=['get'])
    def direct_messages(self, request):
        """Get direct messages with a specific user.
        This maintains API compatibility with the frontend."""
        user_id = request.query_params.get('user_id')

        if not user_id:
            return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        other_user = get_object_or_404(User, id=user_id)
        
        # Find the DM channel for these users (in any team)
        try:
            dm_channels = DirectMessageChannel.objects.filter(
                Q(user1=request.user, user2=other_user) | 
                Q(user1=other_user, user2=request.user)
            )
            
            # Get messages from all DM channels between these users
            messages = Message.objects.filter(
                channel__in=[dm.channel for dm in dm_channels]
            ).order_by('created_at')
            
            serializer = MessageSerializer(messages, many=True)
            return Response(serializer.data)
            
        except DirectMessageChannel.DoesNotExist:
            # No messages yet
            return Response([])

    @action(detail=True, methods=['delete'])
    def delete_message(self, request, pk=None):
        message = get_object_or_404(Message, id=pk)

        if message.sender != request.user: 
            return Response({"Error": "You can only delete your messages"}, status=status.HTTP_403_FORBIDDEN)
        
        message.delete()
        return Response({"Message": "Message deleted Successfully"}, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'])
    def fetch_preview(self, request):
        """Fetch preview data for a URL"""
        url = request.data.get('url')
        
        if not url:
            return Response({'error': 'URL is required'}, 
                        status=status.HTTP_400_BAD_REQUEST)
        
        preview_data = fetch_link_preview(url)
        return Response(preview_data, status=status.HTTP_200_OK)
    
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
    
    @action(detail=True, methods=['put', 'patch'])
    def edit_message(self, request, pk=None):
        """Edit an existing message with edit history tracking"""
        message = get_object_or_404(Message, id=pk)
        
        # Check if user is the original sender
        if message.sender != request.user:
            return Response({"error": "You can only edit your own messages"}, 
                        status=status.HTTP_403_FORBIDDEN)
        
        # Get the new content
        new_content = request.data.get('content')
        if not new_content:
            return Response({"error": "New content is required"}, 
                        status=status.HTTP_400_BAD_REQUEST)
        
        # Initialize edit_history if it doesn't exist
        if not hasattr(message, 'edit_history') or message.edit_history is None:
            message.edit_history = []
        
        # Add the original content to edit history if this is the first edit
        if len(message.edit_history) == 0:
            message.edit_history.append({
                'content': message.content,
                'edited_at': message.created_at.isoformat()
            })
        
        # Add the current content to history before updating
        message.edit_history.append({
            'content': message.content,
            'edited_at': timezone.now().isoformat()
        })
        
        # Update the message content
        message.content = new_content
        message.is_edited = True
        message.edited_at = timezone.now()
        message.save()
        
        # Return the updated message
        serializer = MessageSerializer(message)
        return Response(serializer.data)
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def fetch_preview(request):
        """Fetch preview data for a URL"""
        url = request.data.get('url')
        
        if not url:
            return Response({'error': 'URL is required'}, 
                        status=status.HTTP_400_BAD_REQUEST)
        
        preview_data = fetch_link_preview(url)
        return Response(preview_data, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_file(request):
    """
    Upload a file and return the file ID.
    """
    if 'file' not in request.FILES:
        return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    file_obj = request.FILES['file']
    
    # Create a new FileAttachment instance
    attachment = FileAttachment(
        file=file_obj,
        original_filename=file_obj.name,
        content_type=file_obj.content_type,
        size=file_obj.size,
        uploaded_by=request.user
    )
    attachment.save()
    
    return Response({
        'id': attachment.id,
        'filename': attachment.original_filename,
        'url': request.build_absolute_uri(attachment.file.url),
        'content_type': attachment.content_type,
        'size': attachment.size
    }, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_file(request, file_id):
    """
    Download a file attachment by its ID.
    """
    try:
        # Try to get the file attachment
        attachment = FileAttachment.objects.get(id=file_id)
        
        # Check if the file exists
        if not attachment.file or not os.path.exists(attachment.file.path):
            return Response({'error': 'File not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Open the file and create a FileResponse
        file_handle = open(attachment.file.path, 'rb')
        response = FileResponse(file_handle, content_type=attachment.content_type)
        
        # Set the content-disposition header to force download with the original filename
        response['Content-Disposition'] = f'attachment; filename="{attachment.original_filename}"'
        
        return response
    
    except FileAttachment.DoesNotExist:
        return Response({'error': 'File not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
