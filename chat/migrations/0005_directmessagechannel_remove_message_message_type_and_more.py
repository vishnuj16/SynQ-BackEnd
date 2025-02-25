# Generated by Django 5.1.6 on 2025-02-24 17:03

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0004_message_reactions_message_reply_to'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DirectMessageChannel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
        ),
        migrations.RemoveField(
            model_name='message',
            name='message_type',
        ),
        migrations.RemoveField(
            model_name='message',
            name='recipient',
        ),
        migrations.AddField(
            model_name='channel',
            name='channel_type',
            field=models.CharField(choices=[('group', 'Group Channel'), ('direct', 'Direct Message Channel')], default='group', max_length=10),
        ),
        migrations.AddField(
            model_name='channel',
            name='is_direct_message',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='message',
            name='channel',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='chat.channel'),
        ),
        migrations.AddConstraint(
            model_name='channel',
            constraint=models.UniqueConstraint(condition=models.Q(('is_direct_message', True)), fields=('team', 'is_direct_message'), name='unique_dm_channel_per_team_members'),
        ),
        migrations.AddField(
            model_name='directmessagechannel',
            name='channel',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='dm_metadata', to='chat.channel'),
        ),
        migrations.AddField(
            model_name='directmessagechannel',
            name='user1',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dm_channels_as_user1', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='directmessagechannel',
            name='user2',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dm_channels_as_user2', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterUniqueTogether(
            name='directmessagechannel',
            unique_together={('user1', 'user2', 'channel')},
        ),
    ]
