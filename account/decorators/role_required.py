from functools import wraps
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator


def role_required(required_role):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # A user deactivated mid-session is already handled: the default
            # ModelBackend.get_user() checks is_active, so request.user has
            # become AnonymousUser and the check below redirects to signin.
            if not request.user.is_authenticated:
                # Redirect to login page if not authenticated
                login_url = reverse("account:signin")
                url = f"{login_url}?role={required_role}&next={request.path}"

                return redirect(url)
            if getattr(request.user, "role", "").lower() != required_role.lower():
                # Role doesn't match - show the styled 403 page, not a bare
                # plaintext response.
                return render(request, "403.dj", status=403)
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    def class_decorator(view_class):
        view_class.dispatch = method_decorator(decorator)(view_class.dispatch)
        return view_class

    def wrapper(view):
        if isinstance(view, type):
            return class_decorator(view)
        return decorator(view)

    return wrapper
