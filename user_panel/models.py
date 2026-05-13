from django.db import models

# Create your models here.
class UserLocation(models.Model):
    latitude = models.FloatField()
    longitude = models.FloatField()
    city = models.CharField(max_length=255, blank=True, null=True)
    timestamp = models.DateTimeField()
    message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.city or 'Unknown'} @ {self.timestamp}"