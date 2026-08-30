from django.test import TestCase

from account.models import User


class DeactivatedUserTests(TestCase):
    """A user deactivated mid-session must be logged out on their next request,
    not left able to keep using the dashboard."""

    def test_deactivated_user_is_bounced(self):
        u = User.objects.create_user(
            email="deact@example.com", password="pw", role="user"
        )
        self.client.force_login(u)
        # still works while active
        self.assertLess(self.client.get("/user_panel/dashboard/").status_code, 400)

        u.is_active = False
        u.save(update_fields=["is_active"])

        # ModelBackend.get_user() checks is_active -> request.user is now
        # AnonymousUser -> role_required redirects to signin.
        r = self.client.get("/user_panel/dashboard/", follow=True)
        self.assertIn("signin", r.request["PATH_INFO"])
        self.assertNotEqual(r.redirect_chain, [])
