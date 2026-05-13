from functools import wraps
from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from django.urls import reverse
from django.utils.decorators import method_decorator


def role_required(required_role):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                # Redirect to login page if not authenticated
                login_url = reverse("account:signin")
                url = f"{login_url}?role={required_role}&next={request.path}"

                return redirect(url)
            if getattr(request.user, "role", "").lower() != required_role.lower():
                # Role doesn't match
                return HttpResponseForbidden(
                    f"You must be {required_role} to access this page."
                )
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
