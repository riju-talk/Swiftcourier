from django.shortcuts import render
from account.decorators import admin_required


# Create your views here.
@admin_required
def dashboard(request):
    return render(request, "admin_panel/all_users.dj")

@admin_required
def all_users(request):
    return render(request, "admin_panel/all_users.dj")

@admin_required
def user_details(request):
    return render(request, "admin_panel/user_details.dj")
