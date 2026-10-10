def ctx_processor(request):
    from django.conf import settings

    ctx = {
        "show_demo_credentials": getattr(settings, "SHOW_DEMO_CREDENTIALS", False),
        "demo_accounts": getattr(settings, "DEMO_ACCOUNTS", []),
        "notifications": [],
        "total_unread_notifications": 0,
        "activities": [],
        "total_unread_activities": 0,
    }

    if request.user.is_authenticated:
        # Fetch notifications for the authenticated user
        notifications = request.user.notifications.filter(is_read=False)
        ctx["total_unread_notifications"] = notifications.count()
        ctx["unread_5_notifications"] = notifications[:5]

        # Fetch activities for the authenticated user
        activities = request.user.activities.filter(is_read=False)
        ctx["total_unread_activities"] = activities.count()
        ctx["unread_5_activities"] = activities[:5]

    return ctx
