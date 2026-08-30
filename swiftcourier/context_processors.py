def ctx_processor(request):
    ctx = {
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
