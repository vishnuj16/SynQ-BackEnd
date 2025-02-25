from django.db import models
from django.contrib.auth.models import User

# User = get_user_model()

# Create your models here.

class Team(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    members = models.ManyToManyField(User, related_name='teams')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

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
    # For DM channels, we'll use this to store the participants
    is_direct_message = models.BooleanField(default=False)
    
    class Meta:
        # Add unique constraint to prevent duplicate DM channels between the same members
        # constraints = [
        #     models.UniqueConstraint(
        #         fields=['team', 'is_direct_message'],
        #         condition=models.Q(is_direct_message=True),
        #         name='unique_dm_channel_per_team_members'
        #     )
        # ]
        pass
    
    def __str__(self):
        return self.name

class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField()
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='messages')
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies')
    reactions = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

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
    """Helper model to find DM channels quickly"""
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