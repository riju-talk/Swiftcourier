import datetime
import logging
from random import randint

from django.conf import settings
from django.urls import reverse
from account.models import ConfirmEmail, PasswordReset, User
# from django.core.mail import send_mail
from django_tasks import task
from celery import shared_task

from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags

logger = logging.getLogger("my-logger")


def send_message(
    user: User,
    content: str,
    subject: str = "Notification from IdiotShip",
    send_email: bool = False,
    send_sms: bool = False,
) -> tuple[bool, bool]:
    """
    Sends a message to the user via email and/or SMS.
    Returns:
        tuple: (email_sent_success, sms_sent_success)
    """
    email_otp_send_status: bool = False
    sms_otp_send_status: bool = False

    logger.info(
        f"Sending message to user {user.id} - Email: {send_email}, SMS: {send_sms}"
    )

    subject = subject.strip()
    content = content.strip()

    if send_email:
        try:
            text_content = strip_tags(content)
            html_content = content

            email = EmailMultiAlternatives(
                subject,
                text_content,
                settings.EMAIL_HOST_USER,
                [user.email],
            )
            email.attach_alternative(html_content, "text/html")

            connection = email.get_connection(fail_silently=False)
            sent = connection.send_messages([email])
            connection.close()

            email_otp_send_status = sent > 0
        except Exception as e:
            logger.exception(f"Error sending email to {user.email}: {str(e)}")
            email_otp_send_status = False

    if send_sms:
        try:
            # Placeholder for SMS sending logic
            sms_otp_send_status = False
        except Exception as e:
            logger.exception(f"Error sending SMS to {user.contact_no}: {str(e)}")
            sms_otp_send_status = False

    return email_otp_send_status, sms_otp_send_status


@shared_task
def send_registration_verification_otp(
    user_id: int, send_email: bool = True, send_sms: bool = False
) -> tuple[bool, bool]:
    """
    Sends a verification OTP to the user's email.

    return:
        bool: True if the email was sent successfully, False otherwise.
        bool: True if the sms was sent successfully, False otherwise.
    """
    email_status = False
    sms_status = False

    try:
        user = User.objects.get(id=user_id)

        # Generate a random OTP (One Time Password) for email verification
        otp = randint(100000, 999999)
        # Prepare email subject and content
        subject = "Welcome to IdiotShip! Verify Your Contact Details"
        content = f"""
        <html>
          <body style="margin:0; padding:0; background-color:#f4f4f4;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
              <tr>
                <td align="center" style="padding:20px 0;">
                  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="background:#ffffff; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.1); font-family:Arial, sans-serif;">
                    <!-- Header -->
                    <tr>
                      <td align="center" style="background-color:#007BFF; padding:20px;">
                        <h1 style="margin:0; font-size:24px; color:#ffffff;">IdiotShip</h1>
                      </td>
                    </tr>
                    <!-- Body -->
                    <tr>
                      <td style="padding:30px; color:#333; font-size:16px; line-height:1.6;">
                        <p>Hello <strong>{user.full_name}</strong>,</p>
                        <p>Thank you for registering with <strong>IdiotShip</strong>!</p>
                        <p>To complete your registration and verify your email address, please use the following One-Time Password (OTP):</p>
                        <p style="text-align:center; margin:30px 0;">
                          <span style="display:inline-block; padding:14px 28px; font-size:28px; font-weight:bold; letter-spacing:6px; color:#ffffff; background-color:#007BFF; border-radius:6px;">{otp}</span>
                        </p>
                        <p>Enter this OTP on our registration page to finalize your account setup. If you did not attempt to register, please ignore this message.</p>
                        <p>If you need any assistance or have any questions, feel free to contact our support team at <a href="mailto:support@idiotship.tech" style="color:#007BFF; text-decoration:none;">support@idiotship.tech</a>.</p>
                        <p>Best regards,<br><strong>The IdiotShip Team</strong></p>
                      </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                      <td align="center" style="background-color:#f4f4f4; padding:15px; font-size:12px; color:#777;">
                        © {datetime.datetime.now().year} IdiotShip. All rights reserved.
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </body>
        </html>
        """

        # Check if there is an existing ConfirmEmail object for the user, delete it if it exists
        cnfm = ConfirmEmail.objects.filter(user=user).first()
        if cnfm:
            cnfm.delete()

        # Create a new ConfirmEmail object for the current user with the generated OTP
        cnfm = ConfirmEmail(user=user, otp=otp)
        cnfm.save()

        email_status, sms_status = send_message(
            user=user,
            content=content,
            subject=subject,
            send_email=send_email,
            send_sms=send_sms,
        )

    except Exception as e:
        logger.exception(
            f"Failed to generate or send registration verification OTP for user {user_id}: {str(e)}"
        )

    return email_status, sms_status


@shared_task
def send_forget_password_otp(
    user_id: int, send_email: bool = True, send_sms: bool = False
) -> tuple[bool, bool]:
    email_status = False
    sms_status = False

    try:
        user = User.objects.get(id=user_id)
        # Delete any existing OTPs for the user
        for i in PasswordReset.objects.filter(user=user):
            i.delete()

        # Create and store the new PasswordReset object
        pswdrst = PasswordReset.objects.create(user=user)

        subject = "Reset Your IdiotShip Password"
        reset_link = f"{settings.SITE_SETTINGS['site']['SITE_LINK']}{reverse('account:reset_password', args=[user.id, pswdrst.token])}"

        # HTML email with professional design
        message = f"""
        <html>
          <body style="margin:0; padding:0; background-color:#f4f4f4;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
              <tr>
                <td align="center" style="padding:20px 0;">
                  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="background:#ffffff; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.1); font-family:Arial, sans-serif;">
                    <!-- Header -->
                    <tr>
                      <td align="center" style="background-color:#007BFF; padding:20px;">
                        <h1 style="margin:0; font-size:24px; color:#ffffff;">IdiotShip</h1>
                      </td>
                    </tr>
                    <!-- Body -->
                    <tr>
                      <td style="padding:30px; color:#333; font-size:16px; line-height:1.6;">
                        <p>Hello <strong>{user.full_name}</strong>,</p>
                        <p>We received a request to reset your password for your <strong>IdiotShip</strong> account.</p>
                        <p>Please click the button below to reset your password:</p>
                        <p style="text-align:center; margin:30px 0;">
                          <a href="{reset_link}" 
                             style="display:inline-block; padding:14px 28px; font-size:16px; 
                                    color:#ffffff; background-color:#007BFF; text-decoration:none; 
                                    border-radius:6px; font-weight:bold;">
                             Reset Password
                          </a>
                        </p>
                        <p>If you did not request this password reset, you can safely ignore this email. 
                        Your current password will remain unchanged.</p>
                        <p>If you need help or have any questions, feel free to contact our support team at 
                        <a href="mailto:support@idiotship.tech" style="color:#007BFF; text-decoration:none;">support@idiotship.tech</a>.</p>
                        <p>Best regards,<br><strong>The IdiotShip Team</strong></p>
                      </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                      <td align="center" style="background-color:#f4f4f4; padding:15px; font-size:12px; color:#777;">
                        © {datetime.datetime.now().year} IdiotShip. All rights reserved.
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </body>
        </html>
        """

        email_status, sms_status = send_message(
            user=user,
            content=message,
            subject=subject,
            send_email=send_email,
            send_sms=send_sms,
        )

    except Exception as e:
        logger.exception(
            f"Failed to generate or send password reset OTP for user {user_id}: {str(e)}"
        )

    return email_status, sms_status
