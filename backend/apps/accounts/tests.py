from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.utils import DataError
from django.test import TestCase

from apps.accounts.models import User
from apps.customers.models import Customer


def strong_password(base="Sunshine"):
    return f"{base}!9qZ"  # 10 chars, upper, lower, digit, special


class UserDomainTests(TestCase):
    def test_password_policy_requires_all_character_classes(self):
        weak = [
            ("alllowercase!", "uppercase"),          # no uppercase
            ("ALLUPPERCASE1!", "lowercase"),         # no lowercase
            ("NoSpecial123ab", "special"),           # no special char
        ]
        for password, fragment in weak:
            with self.subTest(password=password):
                with self.assertRaises(ValidationError) as ctx:
                    validate_password(password)
                self.assertIn(fragment, str(ctx.exception))

        # happy path passes
        validate_password(strong_password())

    def test_email_is_globally_unique_across_roles(self):
        User.objects.create_superuser("admin@example.com", strong_password())
        # same email, different case, different role -> must be refused
        self.assertEqual(
            User.objects.count(), 1
        )  # only the admin so far
        with self.assertRaises(ValidationError):
            User.objects.create_user(
                "ADMIN@example.com", strong_password(),
                role=User.Role.CUSTOMER, customer=Customer.objects.create(name="Acme"),
            )
        self.assertEqual(User.objects.count(), 1)

    def test_email_identity_folded_to_lowercase(self):
        user = User.objects.create_user("Utf@EXAMPLE.COM", strong_password(), role=User.Role.STAFF)
        user.refresh_from_db()
        self.assertEqual(user.email, "utf@example.com")

    def test_customer_role_requires_a_customer(self):
        customer = Customer.objects.create(name="Acme")
        with self.assertRaises(ValidationError):
            User.objects.create_user("port@example.com", strong_password(), role=User.Role.CUSTOMER)

        user = User.objects.create_user(
            "port2@example.com", strong_password(),
            role=User.Role.CUSTOMER, customer=customer,
        )
        self.assertEqual(user.customer_id, customer.id)
        self.assertFalse(user.is_staff)

    def test_staff_role_must_not_belong_to_a_customer(self):
        customer = Customer.objects.create(name="Acme")
        with self.assertRaises(ValidationError):
            User.objects.create_user(
                "staff@example.com", strong_password(),
                role=User.Role.STAFF, customer=customer,
            )

    def test_staff_role_customer_linkage_enforced_at_db_level(self):
        """The CheckConstraint backstops full_clean bypasses (bulk ops)."""
        customer = Customer.objects.create(name="Acme")
        User.objects.all().delete()
        try:
            with transaction.atomic():
                User.objects.bulk_create([
                    User(email="hacker@example.com", role=User.Role.STAFF, customer=customer,
                         password=strong_password()),
                ])
            self.fail("Expected IntegrityError")
        except IntegrityError:
            pass

    def test_create_superuser_sets_staff_flag_and_role(self):
        admin = User.objects.create_superuser("root@example.com", strong_password())
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_admin)

    def test_email_case_insensitive_unique_at_db_level(self):
        """Bulk writes bypass clean(); the CI unique constraint backstops them."""
        User.objects.create_user("a@x.io", strong_password(), role=User.Role.STAFF)
        try:
            with transaction.atomic():
                User.objects.bulk_create([
                    User(email="A@X.IO", role=User.Role.STAFF, password=strong_password()),
                ])
            self.fail("Expected IntegrityError from ci-unique constraint")
        except IntegrityError:
            pass


class CustomerTests(TestCase):
    def test_customer_users_bulk_reverse_relation(self):
        customer = Customer.objects.create(name="Bright Shop")
        alice = Customer.objects.get(pk=customer.pk)  # sanity on reverse access
        self.assertEqual(list(alice.users.all()), [])
        User.objects.create_user("a@x.io", strong_password(), role=User.Role.CUSTOMER, customer=customer)
        User.objects.create_user("b@x.io", strong_password(), role=User.Role.CUSTOMER, customer=customer)
        self.assertEqual(customer.users.count(), 2)

    def test_name_required(self):
        with self.assertRaises(ValidationError):
            Customer(name="   ").full_clean()
