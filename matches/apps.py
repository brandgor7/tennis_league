import logging

from django.apps import AppConfig

logger = logging.getLogger('audit')


def _log_audit_entry(sender, instance, created, **kwargs):
    if not created:
        return
    action = {1: 'ADDED', 2: 'CHANGED', 3: 'DELETED'}.get(instance.action_flag, 'ACTION')
    logger.info('%s %s "%s": %s', instance.user, action, instance.object_repr, instance.get_change_message())


class MatchesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'matches'

    def ready(self):
        from django.contrib.admin.models import LogEntry
        from django.db.models.signals import post_save
        post_save.connect(_log_audit_entry, sender=LogEntry)
