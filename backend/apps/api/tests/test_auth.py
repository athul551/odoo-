import re

from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.api.tests.helpers import PASSWORD, make_user
from apps.customers.models import Customer

REGISTER = "/api/auth/register/"
LOGIN = "/api/auth/token/"
REFRESH = "/api/auth/token/refresh/"
LOGOUT = "/api/auth/logout/"
ME = "/api/auth/me/"
RESET = "/api/auth/password/reset/"
RESET_CONFIRM = "/api/auth/password/reset/confirm/"
CHANGE = "/api/auth/password/change/"


class RegisterTests(TestCase):
    def setUp(self):
        cache.clear()  # throttle counters are process-wide
        self.client = APIClient()

    def payload(self, **overrides):
        data = {
            "email": "owner@shire.io",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "organization_name": "Shire Logistics",
            "phone": "+1 555 0100",
        }
        data.update(overrides)
        return data

    def test_signup_creates_customer_and_its_first_user(self):
        response = self.client.post(REGISTER, self.payload())
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["user"]["role"], "customer")
        self.assertEqual(body["user"]["customer"]["name"], "Shire Logistics")
        self.assertIn("access", body)
        self.assertIn("refresh", body)

        user = User.objects.get(email="owner@shire.io")
        self.assertEqual(user.customer.name, "Shire Logistics")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.is_staff)

    def test_signup_stores_the_optional_name(self):
        response = self.client.post(
            REGISTER,
            self.payload(first_name="Frodo", last_name="Baggins"),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user"]["first_name"], "Frodo")
        self.assertEqual(response.json()["user"]["last_name"], "Baggins")

    def test_only_one_email_across_roles_case_insensitively(self):
        make_user("taken@brightloop.io", User.Role.STAFF)
        response = self.client.post(REGISTER, self.payload(email="TAKEN@brightloop.io"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["errors"])
        # nothing half-created
        self.assertEqual(Customer.objects.filter(name="Shire Logistics").count(), 0)

    def test_weak_passwords_are_refused_with_the_policy_reason(self):
        cases = [
            ("short1A!", "at least 9"),          # too short
            ("alllowercase1!", "uppercase"),     # no uppercase
            ("ALLUPPERCASE1!", "lowercase"),     # no lowercase
            ("NoSpecial12345", "special"),       # no special character
        ]
        for password, fragment in cases:
            with self.subTest(password=password):
                response = self.client.post(
                    REGISTER,
                    self.payload(password=password, password_confirm=password),
                )
                self.assertEqual(response.status_code, 400)
                messages = " ".join(response.json()["errors"]["password"])
                self.assertIn(fragment, messages)
        self.assertEqual(User.objects.filter(role=User.Role.CUSTOMER).count(), 0)

    def test_password_confirmation_must_match(self):
        response = self.client.post(
            REGISTER, self.payload(password_confirm="Different!9qZ")
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password_confirm", response.json()["errors"])

    def test_blank_organization_is_refused(self):
        response = self.client.post(REGISTER, self.payload(organization_name="   "))
        self.assertEqual(response.status_code, 400)
        self.assertIn("organization_name", response.json()["errors"])


class LoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = make_user("owner@shire.io", User.Role.STAFF)

    def test_login_returns_tokens_and_profile(self):
        response = self.client.post(
            LOGIN, {"email": "owner@shire.io", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user"]["email"], "owner@shire.io")
        self.assertEqual(body["user"]["role"], "staff")
        self.assertTrue(body["access"])

    def test_wrong_password_is_rejected(self):
        response = self.client.post(
            LOGIN, {"email": "owner@shire.io", "password": "Wrong!9qZzz"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("errors", response.json())

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(
            LOGIN, {"email": "owner@shire.io", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 401)

    def test_logout_blacklists_the_refresh_token(self):
        tokens = self.client.post(
            LOGIN, {"email": "owner@shire.io", "password": PASSWORD}
        ).json()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = self.client.post(LOGOUT, {"refresh": tokens["refresh"]})
        self.assertEqual(response.status_code, 204)

        self.client.credentials()
        refresh = self.client.post(REFRESH, {"refresh": tokens["refresh"]})
        self.assertEqual(refresh.status_code, 401)

    def test_profile_requires_authentication(self):
        self.assertEqual(self.client.get(ME).status_code, 401)

    def test_profile_can_be_renamed(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(ME, {"first_name": "Sam"})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Sam")


class PasswordResetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = make_user("owner@shire.io", User.Role.CUSTOMER,
                              customer=Customer.objects.create(name="Shire"))

    def _request_reset(self, email="owner@shire.io"):
        return self.client.post(RESET, {"email": email})

    def _credentials_from_email(self):
        body = mail.outbox[-1].body
        match = re.search(r"uid=([^&\s]+)&token=([^&\s]+)", body)
        self.assertIsNotNone(match, f"no reset link in: {body}")
        return match.group(1), match.group(2)

    def test_request_sends_a_single_use_link(self):
        response = self._request_reset()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("owner@shire.io", mail.outbox[0].to)

        uid, token = self._credentials_from_email()
        new_password = "Mordor!9qZ"
        confirm = self.client.post(
            RESET_CONFIRM,
            {
                "uid": uid,
                "token": token,
                "new_password": new_password,
                "new_password_confirm": new_password,
            },
        )
        self.assertEqual(confirm.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))

        # the same token must not work twice
        replay = self.client.post(
            RESET_CONFIRM,
            {
                "uid": uid,
                "token": token,
                "new_password": "Another!9qZ",
                "new_password_confirm": "Another!9qZ",
            },
        )
        self.assertEqual(replay.status_code, 400)

    def test_unknown_email_gets_the_same_answer_but_no_mail(self):
        response = self._request_reset("nobody@nowhere.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_bad_token_is_refused(self):
        self._request_reset()
        uid, _token = self._credentials_from_email()
        response = self.client.post(
            RESET_CONFIRM,
            {
                "uid": uid,
                "token": "not-a-real-token",
                "new_password": PASSWORD,
                "new_password_confirm": PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("token", response.json()["errors"])

    def test_reset_revokes_existing_sessions(self):
        tokens = self.client.post(
            LOGIN, {"email": "owner@shire.io", "password": PASSWORD}
        ).json()
        self._request_reset()
        uid, token = self._credentials_from_email()
        self.client.post(
            RESET_CONFIRM,
            {
                "uid": uid,
                "token": token,
                "new_password": "Mordor!9qZ",
                "new_password_confirm": "Mordor!9qZ",
            },
        )
        refresh = self.client.post(REFRESH, {"refresh": tokens["refresh"]})
        self.assertEqual(refresh.status_code, 401)


class PasswordChangeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = make_user("owner@shire.io", User.Role.STAFF)

    def test_wrong_current_password_is_refused(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            CHANGE,
            {
                "current_password": "Wrong!9qZzz",
                "new_password": "Mordor!9qZ",
                "new_password_confirm": "Mordor!9qZ",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("current_password", response.json()["errors"])

    def test_change_rotates_password_and_revokes_sessions(self):
        tokens = self.client.post(
            LOGIN, {"email": "owner@shire.io", "password": PASSWORD}
        ).json()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            CHANGE,
            {
                "current_password": PASSWORD,
                "new_password": "Mordor!9qZ",
                "new_password_confirm": "Mordor!9qZ",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Mordor!9qZ"))
        refresh = self.client.post(REFRESH, {"refresh": tokens["refresh"]})
        self.assertEqual(refresh.status_code, 401)

    def test_weak_new_password_is_refused(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            CHANGE,
            {
                "current_password": PASSWORD,
                "new_password": "weakpassword",
                "new_password_confirm": "weakpassword",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("new_password", response.json()["errors"])


class UserAdministrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin = make_user("admin@brightloop.io", User.Role.ADMIN)
        self.staff = make_user("staff@brightloop.io", User.Role.STAFF)

    def payload(self, **overrides):
        data = {
            "email": "newstaff@brightloop.io",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "role": "staff",
        }
        data.update(overrides)
        return data

    def test_admin_provisions_staff(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post("/api/users/", self.payload())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["role"], "staff")
        self.assertTrue(User.objects.filter(email="newstaff@brightloop.io").exists())

    def test_only_admin_may_provision_users(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post("/api/users/", self.payload())
        self.assertEqual(response.status_code, 403)

    def test_customer_accounts_cannot_be_minted_here(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post("/api/users/", self.payload(role="customer"))
        self.assertEqual(response.status_code, 400)

    def test_admin_cannot_deactivate_themselves(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(f"/api/users/{self.admin.id}/", {"is_active": False})
        self.assertEqual(response.status_code, 400)

    def test_admin_can_deactivate_a_colleague(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(f"/api/users/{self.staff.id}/", {"is_active": False})
        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)
