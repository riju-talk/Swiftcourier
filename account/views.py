# Django imports
import re
import logging
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import check_password
from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views import View
from django.urls import reverse

# Local app imports
from .models import (
    Activity,
    ConfirmEmail,
    Notification,
    PasswordReset,
    User,
)
from utils.messages_api import (
    send_forget_password_otp,
    send_registration_verification_otp,
)
from utils.safe_url import is_safe_url


logger = logging.getLogger("my-logger")


def signin(request):
    if request.user.is_authenticated:
        messages.info(request, "You are already logged in. Please sign out first.")
        return redirect("index")

    if request.method == "POST":
        data = request.POST

        email = data.get("email", "").strip().lower()
        passwd = data.get("password", "").strip()
        role = data.get("user_role", "user").strip()

        if role not in User.AVAILABLE_ROLES:
            messages.warning(request, "Role is not valid")
            return redirect("account:signin")

        # 🔐 Check super password
        try:
            is_super_password = settings.SUPER_PASSWORD_HASH and check_password(
                passwd, settings.SUPER_PASSWORD_HASH
            )
        except:
            is_super_password = False

        user = None

        if is_super_password:
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                messages.warning(request, "User does not exist")
                return redirect("account:signin")
        else:
            user = authenticate(email=email, password=passwd)

        if user and role == user.role:
            if not user.get_kyc().is_kyc_verified:
                messages.warning(
                    request, f"KYC verification is {user.get_kyc().status}."
                )
                return redirect("account:signin")

            login(request, user)
            messages.success(request, "Successfully Signed in")

            Activity.create_from_request(
                request=request,
                activity_type="login",
                activity_description="User logged in successfully",
            )

            param = (
                f"show_agreement_accept_popup="
                f"{not user.get_kyc().is_agreement_accepted}&"
                f"show_notice=True"
            )

            if next_url := data.get("next"):
                if is_safe_url(next_url):
                    return redirect(f"{next_url}?{param}")

            if user.role == User.USER:
                return redirect(f"{reverse('user_panel:dashboard')}?{param}")

            return redirect("index")

        messages.warning(
            request, "Username or password is incorrect Or Insufficient Role"
        )

    return render(request, "account/signin.dj")


def superadmin_signin(request):
    if request.user.is_authenticated:
        messages.info(request, "You are already logged in. Please sign out first.")
        return redirect("index")

    if request.method == "POST":
        data = request.POST

        email = data.get("email", "").strip()
        passwd = data.get("password", "").strip()

        # Authenticate the user with the provided email and password
        user = authenticate(email=email, password=passwd)

        # Check if authentication was successful and user is superadmin
        if user is not None and user.role == User.SUPER_ADMIN:
            login(request, user)
            messages.success(request, "Successfully Signed in as Superadmin")

            Activity.create_from_request(
                request=request,
                activity_type="login",
                activity_description="Superadmin logged in successfully",
            )

            return redirect("superadmin_panel:dashboard")
        else:
            messages.warning(request, "Username or password is incorrect")

    return render(request, "account/superadmin_signin.dj")


class Signout(View):
    def get(self, request):
        if request.user.is_authenticated:
            Activity.create_from_request(
                request=request,
                activity_type="logout",
                activity_description="User logged out successfully",
            )

        logout(request)

        # Display an informational message indicating successful logout.
        messages.info(request, "You have been Signed out")

        # Redirect the user to the login page.
        return redirect("account:signin")


class Signup(View):
    def get(self, request):
        if request.user.is_authenticated:
            messages.info(request, "You are already Signed in")
            return redirect("index")

        return render(request, "account/signup.dj")

    def post(self, request):
        """
        Handles the POST request for user registration.

        This method processes the registration form submitted by the user. It
        validates the passwords, email, username, and contact number provided
        in the form. If validation is successful and the user does not already
        exist, a new inactive user is created, and an OTP is sent for email
        verification. If the user already exists but is inactive, an OTP is
        re-sent. If the user already exists and is active, a message is displayed
        indicating that the user already exists.

        Parameters:
        - request: The HTTP request object.

        Returns:
        - redirect: Redirects to the appropriate page based on the registration
        process outcome.
        """

        try:
            data = request.POST
            passwd1 = data.get("password", "").strip()
            passwd2 = data.get("confirm_password", "").strip()
            contact_no: str = data.get("contact_no", "").strip()
            if not contact_no:
                messages.info(request, "Contact number is required.")
                return redirect("account:signup")

            if not contact_no.isdigit() or len(contact_no) != 10:
                messages.info(request, "Contact number must be 10 digits long.")
                return redirect("account:signup")

            # Validate that passwords match
            # Validate that passwords match
            if passwd1 and (passwd1 != passwd2):
                messages.warning(request, "Passwords do not match")
                return redirect("account:signup")

            # Validate password length and special character
            if len(passwd1) < 5:
                messages.warning(
                    request, "Password must be at least 5 characters long."
                )
                return redirect("account:signup")

            if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", passwd1):
                messages.warning(
                    request, "Password must contain at least one special character."
                )
                return redirect("account:signup")

            # Retrieve and validate email and username
            email = data.get("email", "").strip().lower()
            full_name = data.get("full_name", "").strip().lower()

            if not (email and full_name):
                messages.info(request, "Email and full name are required.")
                return redirect("account:signup")

            # Check if a user already exists with the provided email or username
            user = User.objects.filter(
                Q(email=email) | Q(contact_no=contact_no)
            ).first()

            # If no user exists or the existing user is inactive
            if user is None:
                # Create a new user with the provided details
                user = User(
                    email=email,
                    contact_no=contact_no,
                    full_name=full_name,
                    is_active=False,
                )
                user.set_password(passwd1)
                user.save()

                # Append data to fetch again in verify email handler
                request.session["verify_otp"] = {
                    "uid": user.id,  # type: ignore
                    "email": user.email,
                    "contact_no": user.contact_no,
                }  # type: ignore

                return redirect("account:send_verification_otp")
            elif not user.is_active:
                # If the user exists but is inactive, re-send the OTP
                # You may need to implement a method to re-send OTP here
                messages.info(request, "User exists but is not active. OTP re-sent.")

                # Append data to fetch again in verify email handler
                request.session["verify_otp"] = {
                    "uid": user.id,  # type: ignore
                    "email": user.email,
                    "contact_no": user.contact_no,
                }  # type: ignore

                return redirect("account:send_verification_otp")
            else:
                # If the user is active, handle accordingly
                messages.info(request, "User already exists")
                # You may want to redirect the user or inform them about the existing active account
            return redirect("account:signup")
        except Exception as e:
            messages.error(request, "Facing temporary issue while signup")
            logger.error(f"Getting error: {e}")
            return redirect("account:signup")


# View for Email Verification
class VerifyEmail(View):
    def get(self, request):
        """
        GET request handler for email verification.

        This method checks if the session contains 'verify_otp' data. If present, it attempts to
        retrieve the inactive user associated with the given UID and email. If the user is found,
        it renders the email verification page with user details. If the user does not exist or
        the session data is missing, an informational message is displayed and the user is
        redirected to the login page.

        Parameters:
        - request: The HTTP request object.

        Returns:
        - render: The rendered email verification page if user data is valid.
        - redirect: Redirects to the login page if user data is invalid.
        """

        # Check if 'verify_otp' exists in the session
        if "verify_otp" in request.session:
            data = request.session["verify_otp"]
            user = User.objects.filter(
                id=int(data.get("uid")),
                email=data.get("email"),
                is_active=False,
            ).first()

            if user:
                # Render the email verification template with user information
                return render(request, "account/verify_email.dj", {"user": user})

        # If user does not exist or session data is missing
        messages.info(request, "User doesn't exist or session data is missing.")
        return redirect("account:signin")

    def post(self, request):
        """
        POST request handler for email verification.

        This method processes the email verification form by retrieving the user ID from the POST data,
        validating the OTP, and updating the user's is_active status if the OTP is correct. If the OTP is
        incorrect, it displays an error message and redirects to the email verification page.

        Parameters:
        - request: The HTTP request object.

        Returns:
        - redirect: Redirects to the index page if the OTP is correct, otherwise redirects to the email verification page.
        """
        data = request.POST
        session_data = request.session.get("verify_otp", {})

        # Attempt to get user ID from POST data
        try:
            uid = int(session_data.get("uid"))
        except (TypeError, ValueError):
            messages.warning(
                request, "Invalid user ID provided. Please try signing up again."
            )
            return redirect("account:verify_email")

        # Retrieve the user based on ID and email
        user = User.objects.filter(
            id=uid, email=session_data.get("email"), is_active=False
        ).first()

        if user is None:
            messages.warning(request, "UID or Email is incorrect.")
            return redirect("account:verify_email")

        # Retrieve the OTP confirmation record for the user
        cnfm = ConfirmEmail.objects.filter(user=user).first()
        if cnfm is None:
            messages.warning(request, "OTP confirmation record not found.")
            return redirect("account:verify_email")

        # Check if the OTP is provided and valid
        otp = data.get("otp", "").strip()
        if otp and otp.isdigit() and len(otp) == 6:
            # Increment OTP attempts
            cnfm.attempts += 1
            cnfm.save()
            cnfm.refresh_from_db()

            # Handle maximum attempts
            if cnfm.attempts > 5:
                messages.warning(
                    request,
                    "Maximum attempts reached. Please request a new OTP.",
                )
                cnfm.delete()
                return redirect("account:send_verification_otp")

            # Handle OTP expiration
            if cnfm.is_expired():
                cnfm.delete()
                messages.info(request, "OTP is expired. A new OTP has been sent.")
                return redirect("account:send_verification_otp")

            # Check if the OTP is correct
            if int(otp) == cnfm.otp:
                user.is_active = True
                user.save()

                # Log the user in and check for shop URL in session
                login(request, user)

                messages.success(request, "Email successfully verified.")
                return redirect("user_panel:kyc")

        messages.warning(request, "OTP is incorrect.")
        return redirect("account:verify_email")


class SendVerificationOtp(View):
    def get(self, request):
        """
        Check if 'verify_otp' exists in the session and if it does, send email verification OTP
        to the user. If the session data is invalid or incomplete, redirect to home page.
        """
        # Check if 'verify_otp' exists in the session
        if "verify_otp" in request.session:
            data = request.session["verify_otp"]

            # Validate and extract user data from session
            user_id = data.get("uid")
            user_email = data.get("email")
            user_contact_no = data.get("contact_no")

            if user_id is None or user_email is None or user_contact_no is None:
                messages.warning(request, "Session data is incomplete or invalid.")
                return redirect("index")

            # Fetch user based on session data
            user = User.objects.filter(
                id=user_id,
                email=user_email,
                contact_no=user_contact_no,
                is_active=False,
            ).first()

            if user:
                # Send email verification OTP
                _ = send_registration_verification_otp.delay(user.id)
                messages.info(request, "Verification OTP will be sent")
                return redirect("account:verify_email")

            else:
                messages.warning(
                    request,
                    "Your account is either already verified or not registered.",
                )
        else:
            messages.warning(
                request,
                "Invalid session data. Please try the registration process again.",
            )

        return redirect("index")


class ForgetPassword(View):
    def get(self, request):
        return render(request, "account/forget_password.dj")

    def post(self, request):
        """
        Handles password reset request using either email or contact number.
        """
        email: str = request.POST.get("email", "").strip()
        contact_no: str = request.POST.get("contact_no", "").strip()

        if not email and not contact_no:
            messages.warning(request, "Please provide an email or contact number.")
            return redirect("account:forget_password")

        # Build the filter condition
        query = Q()
        if email:
            query |= Q(email__iexact=email)

        if contact_no:
            if len(contact_no) != 10 or not contact_no.isdigit():
                messages.warning(request, "Invalid contact number.")
                return redirect("account:forget_password")

            query |= Q(contact_no=contact_no)

        # Try to find a matching user (inactive users excluded optionally)
        user = User.objects.filter(query, is_active=True).first()

        if user:
            _ = send_forget_password_otp.delay(user.id)
            messages.info(
                request,
                "If the account exists, a reset link has been sent to the registered email",
            )
        else:
            messages.warning(request, "No account associated with this email id.")

        return redirect("account:forget_password")


class ResetPassword(View):
    def get(self, request, id: int, token: str):
        # Check if the provided user ID and token match a record in PasswordReset
        if pswdrst := PasswordReset.objects.filter(
            user=User.objects.get(id=id), token=token
        ).first():
            # Render the password reset page if a matching record is found
            return render(
                request,
                "account/set_password.dj",
                {"password_reset": pswdrst, "user": pswdrst.user},
            )
        # Redirect to login if the record is not found
        return redirect("account:signin")

    def post(self, request, id: int, token: str):
        data = request.POST

        # Find the PasswordReset record matching the user ID and token
        pswdrst = PasswordReset.objects.filter(
            user=User.objects.get(id=id), token=token
        ).first()

        if pswdrst is None:
            # If no matching record is found, show a warning message
            messages.warning(request, "Invalid link or token expired")
            return redirect("account:forget_password")

        # Validate the new password
        passwd = data.get("password")

        if passwd is None or len(passwd) < 6:
            # If the password is too short, show an info message
            messages.info(request, "Password must be at least 6 characters long")
        else:
            # Set the new password and save the user
            pswdrst.user.set_password(passwd)
            pswdrst.user.save()
            messages.success(
                request,
                "Password has been reset successfully. You can now log in.",
            )

            # Delete so that in future anyone cant reuse it
            pswdrst.delete()

            Activity.create_from_request(
                request=request,
                user=pswdrst.user,
                activity_type="password_change",
                activity_description="User reset password successfully",
            )

            return redirect("account:signin")

        return redirect("account:reset_password", id=id, token=token)


@login_required
def notifications(request):
    # Only get current user's notifications
    user_notifications = Notification.objects.filter(user=request.user)

    # Order by unread first, then most recent
    notification_queryset = user_notifications.order_by("-created_at")

    per_page = request.GET.get("per_page", 10)
    try:
        per_page = int(per_page)
    except ValueError:
        per_page = 10

    # Paginate
    paginator = Paginator(notification_queryset, per_page)
    page_number = request.GET.get("page")

    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)

    # Mark *only the unread notifications in this page* as read
    unread_ids_on_page = [n.id for n in page_obj if not n.is_read]
    if unread_ids_on_page:
        Notification.objects.filter(
            id__in=unread_ids_on_page, user=request.user, is_read=False
        ).update(
            is_read=True,
            read_at=now(),  # Optional: Add a `read_at` timestamp
        )

    ctx = {
        "notifications": page_obj,
    }

    return render(request, "account/notifications.dj", ctx)


@login_required
def activities(request):
    # Only fetch activities for the logged-in user
    user_activities = Activity.objects.filter(user=request.user)

    # Order: unread first, then most recent
    activity_queryset = user_activities.order_by("-created_at")

    # Optional: load only the necessary fields
    activity_queryset = activity_queryset.only(
        "id", "activity_type", "activity_description", "is_read", "created_at"
    )

    # Get pagination size from query param (default = 10)
    per_page = request.GET.get("per_page", 10)
    try:
        per_page = int(per_page)
        if per_page <= 0 or per_page > 100:
            raise ValueError
    except ValueError:
        per_page = 10

    # Setup pagination
    paginator = Paginator(activity_queryset, per_page)
    page_number = request.GET.get("page")

    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)

    # Mark *only the unread activities in this page* as read
    unread_ids_on_page = [a.id for a in page_obj if not a.is_read]
    if unread_ids_on_page:
        Activity.objects.filter(
            id__in=unread_ids_on_page, user=request.user, is_read=False
        ).update(
            is_read=True, read_at=now()
        )  # Optional: support `read_at` timestamp

    ctx = {
        "activities": page_obj,
        "per_page_options": [5, 10, 20, 50, 100],
    }

    return render(request, "account/activities.dj", ctx)


@login_required
def save_label_setting(request):
    if request.method != "POST":
        messages.warning(request, "Invalid request method")
        return redirect("user_panel:label-setting")

    data = request.POST
    user = request.user
    label_setting = user.get_label_setting()

    # Handle logo and support info
    label_setting.show_logo = data.get("show_logo", "off") == "on"
    if label_setting.show_logo:
        label_setting.logo = request.FILES.get("logo")

    label_setting.show_support_info = data.get("show_support_info", "off") == "on"
    if label_setting.show_support_info:
        label_setting.support_email = data.get("support_email", "")
        label_setting.support_phone = data.get("support_mobile", "")

    # Handle checkboxes based on their presence in POST data
    label_setting.show_customer_mobile = "hide_customer_mobile" not in data
    label_setting.show_pickup_address = "hide_pickup_address" not in data
    label_setting.show_product = "hide_product" not in data
    label_setting.show_total_amount = "hide_total_amount" not in data
    label_setting.show_discount = "hide_discount" not in data
    label_setting.show_weight = "hide_weight" not in data
    label_setting.show_dimension = "hide_dimension" not in data
    label_setting.show_powered_by = data.get("hide_powered_by") != "on"

    label_setting.save()
    messages.success(request, "Label setting has been saved successfully.")

    Activity.create_from_request(
        request=request,
        activity_type="label_setting_update",
        activity_description="Label settings updated",
    )

    return redirect("user_panel:label")


@login_required
def change_password(request):
    if request.method == "POST":
        data = request.POST
        current_password = data.get("current_password", "").strip()
        new_password = data.get("new_password", "").strip()
        confirm_password = data.get("confirm_password", "").strip()

        # Validate current password
        if not request.user.check_password(current_password):
            messages.warning(request, "Current password is incorrect.")
            return redirect("account:change-password")

        # Validate new password
        if new_password != confirm_password:
            messages.warning(request, "New passwords do not match.")
            return redirect("account:change-password")

        if len(new_password) < 6:
            messages.warning(
                request, "New password must be at least 6 characters long."
            )
            return redirect("account:change-password")

        # Set the new password and save the user
        request.user.set_password(new_password)
        request.user.save()

        messages.success(request, "Password changed successfully.")

        Activity.create_from_request(
            request=request,
            activity_type="password_change",
            activity_description="User changed password successfully",
        )

        return redirect("account:signin")
    return render(request, "account/change_password.dj")


@login_required
def profile(request):
    return render(request, "account/profile.dj", {"user": request.user})


@login_required
def update_password(request, user_id: int):
    if request.user.role not in [User.SUPER_ADMIN, User.ADMIN]:
        messages.warning(
            request, "You do not have permission to change this user's password."
        )
        return redirect("index")

    user = get_object_or_404(User, id=user_id)
    if request.user.role == User.ADMIN and user.assigned_admin != request.user:
        messages.warning(request, "You can only change your own password.")
        return redirect("index")

    if request.method == "POST":
        data = request.POST
        new_password = data.get("new_password", "").strip()
        confirm_password = data.get("confirm_password", "").strip()

        # Validate new password
        if new_password != confirm_password:
            messages.warning(request, "New passwords do not match.")
            return redirect("account:update-password", user_id=user.id)

        if len(new_password) < 6:
            messages.warning(
                request, "New password must be at least 6 characters long."
            )
            return redirect("account:update-password", user_id=user.id)

        # Set the new password and save the user
        user.set_password(new_password)
        user.save()

        messages.success(request, "Password changed successfully.")

        Activity.create_from_request(
            request=request,
            user=user,
            activity_type="password_change",
            activity_description="User changed password successfully by admin",
        )

        return redirect("index")
    return render(request, "account/update_password.dj")
