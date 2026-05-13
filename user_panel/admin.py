from django.contrib import admin

# Register your models here.
from .models import UserLocation

@admin.register(UserLocation)
class UserLocationAdmin(admin.ModelAdmin):
    list_display = ("city", "latitude", "longitude", "timestamp", "message", "created_at")
