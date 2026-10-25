from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .models import LoginEvent, User
from .permissions import moderator_required, seller_required
from .security import MAX_FAILED_PER_IP, MAX_FAILED_PER_USER_IP, get_client_ip

PASSWORD = "Bardzo-Dobre-Haslo-123"


class RegistrationTests(TestCase):
    def test_register_creates_customer_and_logs_in(self):
        resp = self.client.post(reverse("accounts:register"), {
            "username": "jan", "email": "Jan@Example.com", "first_name": "", "last_name": "",
            "password1": PASSWORD, "password2": PASSWORD,
        })
        self.assertRedirects(resp, reverse("core:home"))
        user = User.objects.get(username="jan")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertEqual(user.email, "jan@example.com")
        self.assertIn("_auth_user_id", self.client.session)

    def test_register_as_seller(self):
        self.client.post(reverse("accounts:register"), {
            "username": "ola", "email": "ola@example.com", "wants_to_sell": "on",
            "password1": PASSWORD, "password2": PASSWORD,
        })
        self.assertTrue(User.objects.get(username="ola").is_seller)

    def test_cannot_register_as_moderator_via_post(self):
        self.client.post(reverse("accounts:register"), {
            "username": "hacker", "email": "h@example.com", "role": "admin",
            "password1": PASSWORD, "password2": PASSWORD,
        })
        user = User.objects.get(username="hacker")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertFalse(user.is_moderator)

    def test_duplicate_email_rejected(self):
        User.objects.create_user("a", "x@example.com", PASSWORD)
        resp = self.client.post(reverse("accounts:register"), {
            "username": "b", "email": "X@example.com", "password1": PASSWORD, "password2": PASSWORD,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="b").exists())


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("kasia", "k@example.com", PASSWORD)

    def test_login_records_event_and_rotates_session(self):
        self.client.get(reverse("accounts:login"))
        resp = self.client.post(reverse("accounts:login"), {"username": "kasia", "password": PASSWORD})
        self.assertRedirects(resp, reverse("core:home"))
        self.assertTrue(LoginEvent.objects.filter(user=self.user, kind="success").exists())

    def _fail(self, username, ip, times):
        for _ in range(times):
            self.client.post(reverse("accounts:login"), {"username": username, "password": "zle"}, REMOTE_ADDR=ip)

    def _login(self, ip):
        return self.client.post(reverse("accounts:login"), {"username": "kasia", "password": PASSWORD}, REMOTE_ADDR=ip)

    def test_failed_logins_lead_to_lockout(self):
        self._fail("kasia", "10.0.0.1", MAX_FAILED_PER_USER_IP)
        resp = self._login("10.0.0.1")
        self.assertEqual(resp.status_code, 200)  # zablokowane
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(LoginEvent.objects.filter(username="kasia", kind="locked").exists())

    def test_attacker_cannot_lock_user_from_other_ip(self):
        self._fail("kasia", "10.0.0.66", MAX_FAILED_PER_USER_IP)
        resp = self._login("10.0.0.1")
        self.assertRedirects(resp, reverse("core:home"))

    def test_password_spraying_blocks_ip(self):
        for i in range(MAX_FAILED_PER_IP):
            self._fail(f"user{i}", "10.0.0.66", 1)
        resp = self._login("10.0.0.66")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_profile_requires_login(self):
        resp = self.client.get(reverse("accounts:profile"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp["Location"])


class RolePermissionTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _call(self, decorator, user):
        view = decorator(lambda request: HttpResponse("ok"))
        request = self.rf.get("/")
        request.user = user
        return view(request)

    def test_seller_required(self):
        seller = User.objects.create_user("s", "s@e.com", PASSWORD, role=User.Role.SELLER)
        customer = User.objects.create_user("c", "c@e.com", PASSWORD)
        self.assertEqual(self._call(seller_required, seller).status_code, 200)
        with self.assertRaises(PermissionDenied):
            self._call(seller_required, customer)

    def test_moderator_required_allows_admin(self):
        admin = User.objects.create_superuser("adm", "a@e.com", PASSWORD)
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertEqual(self._call(moderator_required, admin).status_code, 200)


class ClientIpTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_without_proxy_ignores_header(self):
        request = self.rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4")
        self.assertEqual(get_client_ip(request), "10.0.0.1")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_behind_alb_takes_last_entry(self):
        # klient podrobil 1.2.3.4, ALB dopisal prawdziwe 5.6.7.8
        request = self.rf.get("/", REMOTE_ADDR="172.31.0.10", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8")
        self.assertEqual(get_client_ip(request), "5.6.7.8")
