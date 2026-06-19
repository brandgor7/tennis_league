from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    def save(self, *args, **kwargs):
        self.username = self.username.replace('/', '')
        super().save(*args, **kwargs)
