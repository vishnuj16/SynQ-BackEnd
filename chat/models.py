from django.db import models
from django.contrib.auth.models import User

# User = get_user_model()

# Create your models here.
class Team (models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    members = models.ManyToManyField(User, related_name='teams')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Channel (models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='channels')
    members = models.ManyToManyField(User, related_name='channels')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Message (models.Model):
    MESSAGE_TYPES = (
        ('channels', 'Channel Message'),
        ('direct', 'Direct Message'),
    )

    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField()
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages', null=True, blank=True)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='messages', null=True, blank=True)
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created_at',)

    def __str__(self):
        if self.message_type == 'direct':
            return f'{self.sender.username} to {self.recipient.username}'
        else:
            return f'{self.sender.username} in {self.channel.name}'

class TeamInvitation(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='invitations')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_invitations')
    invite_code = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

