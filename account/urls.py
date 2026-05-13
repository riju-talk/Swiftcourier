from django.urls import path
from . import views

app_name = "account"

urlpatterns = [
    path("signin/", views.signin, name="signin"),
    path("superadmin-signin/", views.superadmin_signin, name="superadmin_signin"),
    path("signout/", views.Signout.as_view(), name="signout"),
    path("signup/", views.Signup.as_view(), name="signup"),
    path("verify/", views.VerifyEmail.as_view(), name="verify_email"),
    path(
        "verify/send-otp/",
        views.SendVerificationOtp.as_view(),
        name="send_verification_otp",
    ),
    path("forget-password/", views.ForgetPassword.as_view(), name="forget_password"),
    path(
        "reset/password/<int:id>/<str:token>/",
        views.ResetPassword.as_view(),
        name="reset_password",
    ),
    path("notifications/", views.notifications, name="notifications"),
    path("activities/", views.activities, name="activities"),
    path("save-label-setting/", views.save_label_setting, name="save_label_setting"),
    path("change-password/", views.change_password, name="change-password"),
    path("update-password/<int:user_id>/", views.update_password, name="update-password"),
    path("profile/", views.profile, name="profile"),
]
