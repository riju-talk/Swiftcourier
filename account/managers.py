from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext as _


class UserManager(BaseUserManager):
    def create_user(self, email, password, **extra_fields):
        """
        Creates and returns a new user with the given email and password.
        Args:
            email (str): The email address of the user. This field is required.
            password (str): The password for the user.
            **extra_fields: Additional fields to include when creating the user.
        Raises:
            ValueError: If the email is not provided.
        Returns:
            user: The created user instance.
        """
        if not email:
            raise ValueError(_("Users must have an email"))

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)

        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and return a superuser with the given email, password, and extra fields.
        This method ensures that the created user has the required permissions to be a superuser.
        Specifically, it sets the `is_staff` and `is_superuser` fields to `True` by default.
        If these fields are not explicitly set to `True`, a `ValueError` is raised.
        Args:
            email (str): The email address of the superuser.
            password (str): The password for the superuser.
            **extra_fields: Additional fields to set on the superuser.
        Returns:
            User: The created superuser instance.
        Raises:
            ValueError: If `is_staff` or `is_superuser` is not set to `True`.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "super_admin")

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self.create_user(email, password, **extra_fields)


def get_or_create_default_admin():
    User = get_user_model()
    admin_email = settings.DEFAULT_ADMIN_USER
    assigned_admin = User.objects.filter(email=admin_email).first()

    if not assigned_admin:
        assigned_admin = User(
            email=admin_email,
            full_name="Default Admin User",
            role=User.ADMIN,
        )
        assigned_admin.set_password(settings.DEFAULT_ADMIN_USER_PASSWORD)
        assigned_admin.save()
        
    return assigned_admin
