from datetime import timezone
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import os
import uuid


class Team(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    members = models.ManyToManyField(User, related_name='teams')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
def get_file_path(instance, filename):
    """Generate a unique file path for the uploaded file."""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('uploads', filename)

class FileAttachment(models.Model):
    file = models.FileField(upload_to=get_file_path)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.IntegerField()  # Size in bytes
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_files')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_filename

class Channel(models.Model):
    CHANNEL_TYPES = (
        ('group', 'Group Channel'),
        ('direct', 'Direct Message Channel'),
    )
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='channels')
    members = models.ManyToManyField(User, related_name='channels')
    created_at = models.DateTimeField(auto_now_add=True)
    channel_type = models.CharField(max_length=10, choices=CHANNEL_TYPES, default='group')
    pinned_message_id = models.CharField(max_length=100, blank=True, null=True)
    # For DM channels, we'll use this to store the participants
    is_direct_message = models.BooleanField(default=False)
    
    class Meta:
        pass
    
    def __str__(self):
        return self.name

class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField()
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='messages')
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies')
    reactions = models.JSONField(null=True, blank=True)
    link_preview = models.JSONField(null=True, blank=True)
    is_forwarded = models.BooleanField(default=False, null=True)
    is_pinned = models.BooleanField(default=False, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    edit_history = models.JSONField(null=True, blank=True)
    files = models.ManyToManyField(FileAttachment, related_name='messages', blank=True)

    class Meta:
        ordering = ('created_at',)

    def __str__(self):
        try:
            return f'Message in {self.channel.name}'
        except Exception:
            return f'Message {self.id}'

class TeamInvitation(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='invitations')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_invitations')
    invite_code = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

class DirectMessageChannel(models.Model):
    channel = models.OneToOneField(Channel, on_delete=models.CASCADE, related_name='dm_metadata')
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dm_channels_as_user1')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dm_channels_as_user2')
    
    class Meta:
        # Ensure that the combination of user1, user2, and channel.team is unique
        unique_together = [['user1', 'user2', 'channel']]
        # To avoid duplicates due to user order, ensure user1.id < user2.id
        constraints = [
            models.CheckConstraint(
                check=models.Q(user1_id__lt=models.F('user2_id')),
                name='user1_id_lt_user2_id'
            )
        ]

class UserPresence(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='presence')
    online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(default=timezone.now)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='user_presences')

    class Meta:
        unique_together = ('user', 'team')
