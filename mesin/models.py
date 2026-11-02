from django.db import models
from django.contrib.auth.models import User
from django.utils.timezone import now

class Device(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    ip = models.CharField(max_length=50)
    port = models.IntegerField(default=4370)
    comm_key = models.IntegerField(default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name or f"Mesin {self.id}",
            "ip": self.ip,
            "port": self.port,
            "comm_key": self.comm_key
        }

class AdminLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    ip_address = models.CharField(max_length=50, null=True, blank=True)
    action = models.CharField(max_length=255) # Menyimpan aktivitas (Login, Hapus User, dll)
    timestamp = models.DateTimeField(default=now)

    def __str__(self):
        return f"{self.user.username if self.user else 'Sistem'} - {self.action} - {self.timestamp}"