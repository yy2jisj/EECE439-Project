"""Regression checks for the assignment workflows and the two local wallets.

Run with ``python manage.py test``. Django creates a separate test database;
these tests never use or modify the saved development accounts/expenses.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.core import signing
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import ExpenseFilterForm, ExpenseForm, RegisterForm
from .models import AccountIdentity, Expense, ExpenseSubmission, MonthlyBudget, OverallBudget


PASSWORD = "Harbor!73Plum#Track"
TODAY = date(2026, 10, 17)


class AppTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = cls.make_user("Alice", "alice@example.com")
        cls.bob = cls.make_user("Bob", "bob@example.com")

    @classmethod
    def make_user(cls, username, email):
        user = User.objects.create_user(username=username, email=email, password=PASSWORD)
        AccountIdentity.objects.update_or_create(
            user=user,
            defaults={"username_key": username.casefold(), "email_key": email.casefold()},
        )
        return user

    def setUp(self):
        cache.clear()
        self.clock = patch("app1.views.timezone.localdate", return_value=TODAY)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.form_clock = patch("app1.forms.timezone.localdate", return_value=TODAY)
        self.form_clock.start()
        self.addCleanup(self.form_clock.stop)

    def expense(self, **overrides):
        values = {
            "user": self.alice,
            "description": "Lunch",
            "amount": Decimal("12.50"),
            "category": "Food",
            "currency": "USD",
            "date": TODAY,
        }
        values.update(overrides)
        return Expense.objects.create(**values)

    def expense_data(self, **overrides):
        values = {
            "description": "Lunch",
            "amount": "12.50",
            "category": "Food",
            "date": TODAY.isoformat(),
        }
        values.update(overrides)
        return values

    def registration_data(self, **overrides):
        values = {
            "username": "Charlie",
            "first_name": "Charlie",
            "last_name": "Brown",
            "email": "charlie@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        values.update(overrides)
        return values

    def history_url(self, currency="usd"):
        return reverse("expense_history", kwargs={"currency": currency})

    def add_url(self, currency="usd"):
        return reverse("add_expense", kwargs={"currency": currency})

    def add_token(self, currency="usd"):
        response = self.client.get(self.add_url(currency))
        self.assertEqual(response.status_code, 200)
        return response.context["form"]["submission_token"].value()

    def add_data(self, wallet="usd", **overrides):
        values = self.expense_data(submission_token=self.add_token(wallet))
        values.update(overrides)
        return values


class ExpenseValidationTests(AppTestCase):
    def test_all_six_assignment_categories_are_available(self):
        self.assertEqual(
            [value for value, label in Expense.CATEGORY_CHOICES],
            ["Food", "Transport", "Bills", "Shopping", "Entertainment", "Other"],
        )
        for category, label in Expense.CATEGORY_CHOICES:
            with self.subTest(category=category):
                form = ExpenseForm(data=self.expense_data(category=category))
                self.assertTrue(form.is_valid(), form.errors)

    def test_money_accepts_decimal_boundaries_without_float_rounding(self):
        for amount in ("0.01", "1", "12.50", "99999999.99"):
            with self.subTest(amount=amount):
                form = ExpenseForm(data=self.expense_data(amount=amount))
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["amount"], Decimal(amount))

    def test_invalid_money_is_rejected(self):
        for amount in ("", "0", "-0.01", "one", "NaN", "sNaN", "Infinity", "-Infinity", "1.001", "100000000"):
            with self.subTest(amount=amount):
                form = ExpenseForm(data=self.expense_data(amount=amount))
                self.assertFalse(form.is_valid())
                self.assertIn("amount", form.errors)

    def test_description_length_and_required_fields(self):
        form = ExpenseForm(data=self.expense_data(description="x" * 200))
        self.assertTrue(form.is_valid(), form.errors)
        for description in ("", "   ", "x" * 201):
            with self.subTest(description=description[:20]):
                form = ExpenseForm(data=self.expense_data(description=description))
                self.assertFalse(form.is_valid())
                self.assertIn("description", form.errors)
        for field, value in (("category", "Made up"), ("category", ""), ("date", "")):
            with self.subTest(field=field, value=value):
                form = ExpenseForm(data=self.expense_data(**{field: value}))
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_dates_accept_today_and_past_but_reject_future_dates(self):
        for value in ("2024-02-29", "2026-10-17"):
            with self.subTest(date=value):
                form = ExpenseForm(data=self.expense_data(date=value))
                self.assertTrue(form.is_valid(), form.errors)
        for value in ("2026-10-18", "2026-12-31", "2027-01-01"):
            with self.subTest(date=value):
                form = ExpenseForm(data=self.expense_data(date=value))
                self.assertFalse(form.is_valid())
                self.assertIn("date", form.errors)
        values = self.expense_data()
        del values["date"]
        values.update(date_day="29", date_month="2", date_year="2024")
        form = ExpenseForm(data=values)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["date"], date(2024, 2, 29))

    def test_impossible_dates_and_incomplete_date_parts_are_rejected(self):
        for value in ("2026-02-29", "2026-04-31", "2026-13-01", "not a date"):
            with self.subTest(date=value):
                form = ExpenseForm(data=self.expense_data(date=value))
                self.assertFalse(form.is_valid())
                self.assertIn("date", form.errors)
        values = self.expense_data()
        del values["date"]
        values.update(date_day="31", date_month="2", date_year="2026")
        self.assertFalse(ExpenseForm(data=values).is_valid())
        values["date_month"] = ""
        self.assertFalse(ExpenseForm(data=values).is_valid())

    def test_database_also_rejects_nonpositive_expenses(self):
        for amount in (Decimal("0"), Decimal("-0.01")):
            with self.subTest(amount=amount):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.expense(amount=amount)

    def test_new_expense_defaults_to_today_without_overwriting_edit_date(self):
        self.assertEqual(ExpenseForm().initial["date"], TODAY)
        expense = self.expense(date=date(2024, 2, 29))
        self.assertEqual(ExpenseForm(instance=expense).initial["date"], date(2024, 2, 29))

    def test_database_rejects_unknown_wallets_and_categories(self):
        for changes in ({"currency": "EUR"}, {"category": "Unknown"}):
            with self.subTest(changes=changes):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.expense(**changes)


class FilterValidationTests(AppTestCase):
    def test_empty_one_sided_and_equal_ranges_are_valid(self):
        cases = (
            {},
            {"start_date": "2026-01-01"},
            {"end_date": "2026-12-31"},
            {"minimum_amount": "0"},
            {"maximum_amount": "10"},
            {"start_date": "2026-10-17", "end_date": "2026-10-17"},
            {"minimum_amount": "12.50", "maximum_amount": "12.50"},
            {"start_date": "2025-12-31", "end_date": "2026-01-01"},
        )
        for values in cases:
            with self.subTest(values=values):
                form = ExpenseFilterForm(data=values)
                self.assertTrue(form.is_valid(), form.errors)

    def test_reversed_ranges_and_invalid_values_are_rejected(self):
        cases = (
            {"start_date": "2026-10-18", "end_date": "2026-10-17"},
            {"minimum_amount": "20", "maximum_amount": "10"},
            {"start_date": "2026-02-30"},
            {"minimum_amount": "-1"},
            {"maximum_amount": "NaN"},
            {"minimum_amount": "1.001"},
            {"category": "Missing"},
        )
        for values in cases:
            with self.subTest(values=values):
                self.assertFalse(ExpenseFilterForm(data=values).is_valid())

    def test_filters_combine_and_include_equal_boundaries(self):
        self.client.force_login(self.alice)
        wanted = self.expense()
        self.expense(amount=Decimal("13"))
        self.expense(category="Other")
        self.expense(date=date(2026, 10, 16))
        response = self.client.get(self.history_url(), {
            "category": "Food", "start_date": TODAY.isoformat(),
            "end_date": TODAY.isoformat(), "minimum_amount": "12.50", "maximum_amount": "12.50",
        })
        self.assertEqual(list(response.context["expenses"]), [wanted])

    def test_invalid_filter_shows_no_results_and_preserves_values(self):
        self.client.force_login(self.alice)
        self.expense()
        response = self.client.get(self.history_url(), {"minimum_amount": "50", "maximum_amount": "10"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["expenses"]), [])
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(response.context["form"]["minimum_amount"].value(), "50")
        self.assertEqual(response.context["form"]["maximum_amount"].value(), "10")

    def test_valid_filter_can_return_an_empty_history(self):
        self.client.force_login(self.alice)
        self.expense()
        response = self.client.get(self.history_url(), {"category": "Bills"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["expenses"]), [])
        self.assertFalse(response.context["form"].errors)

    def test_date_part_filter_fields_work_in_the_actual_history(self):
        self.client.force_login(self.alice)
        wanted = self.expense()
        self.expense(date=date(2026, 10, 16))
        response = self.client.get(self.history_url(), {
            "start_date_day": "17", "start_date_month": "10", "start_date_year": "2026",
            "end_date_day": "17", "end_date_month": "10", "end_date_year": "2026",
        })
        self.assertEqual(list(response.context["expenses"]), [wanted])


class AccountTests(AppTestCase):
    def test_registration_normalizes_identity_and_hashes_password(self):
        values = self.registration_data(username="  Ｃharlie  ", email=" CHARLIE@EXAMPLE.COM ")
        response = self.client.post(reverse("register"), values)
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="Charlie")
        self.assertEqual(user.email, "charlie@example.com")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertEqual(user.accountidentity.username_key, "charlie")
        self.assertEqual(user.accountidentity.email_key, "charlie@example.com")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_duplicate_username_and_email_are_friendly_errors(self):
        cases = (
            ({"username": "Alice"}, "username"),
            ({"username": " alice "}, "username"),
            ({"username": "ＡLICE"}, "username"),
            ({"email": " ALICE@EXAMPLE.COM "}, "email"),
        )
        for changes, field in cases:
            with self.subTest(changes=changes):
                response = self.client.post(reverse("register"), self.registration_data(**changes))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
                self.assertEqual(User.objects.count(), 2)

    def test_email_is_required_and_must_have_valid_format(self):
        for email in ("", "not-an-email", "name@", "@example.com"):
            with self.subTest(email=email):
                form = RegisterForm(data=self.registration_data(email=email))
                self.assertFalse(form.is_valid())
                self.assertIn("email", form.errors)

    def test_password_rules_reject_blank_weak_numeric_similar_and_mismatched(self):
        cases = (
            {"password1": "        ", "password2": "        "},
            {"password1": "abc", "password2": "abc"},
            {"password1": "password", "password2": "password"},
            {"password1": "123456789123", "password2": "123456789123"},
            {"password1": "Charlie", "password2": "Charlie"},
            {"password2": "Different!Password99"},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertFalse(RegisterForm(data=self.registration_data(**changes)).is_valid())

    def test_overlapping_registration_save_failure_is_reported_without_a_500(self):
        with patch("app1.views.RegisterForm.save", side_effect=IntegrityError("UNIQUE constraint failed")):
            response = self.client.post(reverse("register"), self.registration_data())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(User.objects.count(), 2)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_database_rejects_duplicate_identity_keys(self):
        for changes in ({"username_key": "alice", "email_key": "unused@example.com"},
                        {"username_key": "unused", "email_key": "alice@example.com"}):
            with self.subTest(changes=changes):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    AccountIdentity.objects.filter(user=self.bob).update(**changes)

    def test_login_accepts_case_and_whitespace_variations(self):
        response = self.client.post(reverse("login"), {"username": " ＡLICE ", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.alice.pk)

    def test_wrong_password_retains_username_but_never_authenticates(self):
        response = self.client.post(reverse("login"), {"username": "Alice", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertEqual(response.context["form"]["username"].value(), "Alice")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotContains(response, 'value="wrong"')

    def test_inactive_accounts_cannot_sign_in(self):
        self.alice.is_active = False
        self.alice.save(update_fields=["is_active"])
        response = self.client.post(reverse("login"), {"username": "Alice", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_authenticated_users_cannot_reopen_login_or_register(self):
        self.client.force_login(self.alice)
        for name in ("login", "register"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)

    def test_logout_requires_post_and_clears_session(self):
        self.client.force_login(self.alice)
        self.client.get(reverse("logout"))
        self.assertIn("_auth_user_id", self.client.session)
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_protected_pages_require_login(self):
        expense = self.expense()
        urls = [reverse("dashboard"), reverse("profile"), self.history_url(), self.add_url(),
                reverse("edit_expense", args=[expense.pk]), reverse("delete_expense", args=[expense.pk])]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)


class ExpenseWorkflowTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.alice)

    def test_create_uses_selected_wallet_and_current_user(self):
        for currency, amount in (("usd", "0.01"), ("lbp", "1250000.50")):
            with self.subTest(currency=currency):
                values = self.add_data(currency, amount=amount, user=self.bob.pk,
                                       currency="LBP" if currency == "usd" else "USD")
                response = self.client.post(self.add_url(currency), values)
                self.assertEqual(response.status_code, 302)
                expense = Expense.objects.get(currency=currency.upper())
                self.assertEqual(expense.user, self.alice)
                self.assertEqual(expense.amount, Decimal(amount))

    def test_add_another_returns_to_entry_and_intentional_duplicates_are_allowed(self):
        values = self.add_data(action="add_another")
        response = self.client.post(self.add_url(), values)
        self.assertRedirects(response, self.add_url(), fetch_redirect_response=False)
        response = self.client.post(self.add_url(), self.add_data(action="history"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Expense.objects.count(), 2)

    def test_repeated_submission_token_creates_exactly_one_expense(self):
        values = self.add_data()
        first = self.client.post(self.add_url(), values)
        second = self.client.post(self.add_url(), values)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(Expense.objects.count(), 1)

    def test_replaying_a_deleted_expense_form_does_not_recreate_it(self):
        values = self.add_data()
        self.assertEqual(self.client.post(self.add_url(), values).status_code, 302)
        expense = Expense.objects.get()
        receipt = ExpenseSubmission.objects.get(expense=expense)
        receipt_key = receipt.key
        self.assertEqual(self.client.post(reverse("delete_expense", args=[expense.pk])).status_code, 302)
        receipt.refresh_from_db()
        self.assertIsNone(receipt.expense_id)
        # The receipt must protect the old token across browser sessions too.
        another_browser = Client()
        another_browser.force_login(self.alice)
        response = another_browser.post(self.add_url(), values)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Expense.objects.count(), 0)
        self.assertEqual(ExpenseSubmission.objects.count(), 1)
        self.assertTrue(ExpenseSubmission.objects.filter(key=receipt_key, expense__isnull=True).exists())

    def test_missing_forged_wrong_user_and_wrong_wallet_tokens_are_rejected(self):
        wrong_user = signing.dumps({"user_id": self.bob.pk, "currency": "USD", "key": str(uuid4())}, salt="expense-add")
        wrong_wallet = signing.dumps({"user_id": self.alice.pk, "currency": "LBP", "key": str(uuid4())}, salt="expense-add")
        for token in ("", "forged", wrong_user, wrong_wallet):
            with self.subTest(token=token[:25]):
                response = self.client.post(self.add_url(), self.expense_data(submission_token=token))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertEqual(Expense.objects.count(), 0)

    def test_expired_signed_token_is_rejected_without_saving(self):
        with patch("django.core.signing.time.time", return_value=1):
            token = signing.dumps({"user_id": self.alice.pk, "currency": "USD", "key": str(uuid4())}, salt="expense-add")
        response = self.client.post(self.add_url(), self.expense_data(submission_token=token))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(Expense.objects.count(), 0)

    def test_malformed_signed_payloads_produce_friendly_errors(self):
        payloads = (
            [], ["not", "a", "mapping"], None, "not a mapping", {},
            {"user_id": self.alice.pk, "currency": "USD", "key": "not-a-uuid"},
            {"user_id": self.alice.pk, "currency": "USD", "key": None},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                token = signing.dumps(payload, salt="expense-add")
                response = self.client.post(self.add_url(), self.expense_data(submission_token=token))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertEqual(Expense.objects.count(), 0)
                self.assertEqual(ExpenseSubmission.objects.count(), 0)

    def test_invalid_add_preserves_input_and_can_be_corrected(self):
        values = self.add_data(description="Bus pass", amount="-1", category="Transport", date="2026-10-17")
        response = self.client.post(self.add_url(), values)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"]["description"].value(), "Bus pass")
        self.assertEqual(response.context["form"]["category"].value(), "Transport")
        self.assertEqual(response.context["form"]["amount"].value(), "-1")
        self.assertEqual(Expense.objects.count(), 0)
        values["amount"] = "15.25"
        response = self.client.post(self.add_url(), values)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Expense.objects.get().description, "Bus pass")

    def test_edit_prefills_all_saved_values_and_updates_existing_record(self):
        expense = self.expense(currency="LBP", date=date(2026, 11, 20))
        url = reverse("edit_expense", args=[expense.pk])
        response = self.client.get(url)
        form = response.context["form"]
        self.assertEqual(form.initial["description"], expense.description)
        self.assertEqual(form.initial["amount"], expense.amount)
        self.assertEqual(form.initial["category"], expense.category)
        self.assertEqual(form.initial["date"], expense.date)
        values = self.expense_data(description="Dinner", amount="18.75", version=expense.version,
                                   currency="USD", user=self.bob.pk)
        response = self.client.post(url, values)
        self.assertEqual(response.status_code, 302)
        expense.refresh_from_db()
        self.assertEqual(expense.description, "Dinner")
        self.assertEqual(expense.amount, Decimal("18.75"))
        self.assertEqual(expense.currency, "LBP")
        self.assertEqual(expense.user, self.alice)
        self.assertEqual(expense.version, 1)
        self.assertEqual(Expense.objects.count(), 1)

    def test_stale_and_missing_version_edits_cannot_overwrite_a_newer_save(self):
        expense = self.expense()
        url = reverse("edit_expense", args=[expense.pk])
        values = self.expense_data(description="First edit", version=0)
        self.assertEqual(self.client.post(url, values).status_code, 302)
        values["description"] = "Stale edit"
        response = self.client.post(url, values)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(response.context["form"]["description"].value(), "Stale edit")
        expense.refresh_from_db()
        self.assertEqual(expense.description, "First edit")
        self.assertEqual(expense.version, 1)
        del values["version"]
        response = self.client.post(url, values)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)

    def test_invalid_edit_does_not_change_saved_information(self):
        expense = self.expense()
        response = self.client.post(reverse("edit_expense", args=[expense.pk]),
                                    self.expense_data(description="Changed", amount="0", version=0))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"]["description"].value(), "Changed")
        expense.refresh_from_db()
        self.assertEqual(expense.description, "Lunch")
        self.assertEqual(expense.version, 0)

    def test_other_users_records_are_never_read_edited_or_deleted(self):
        other = self.expense(user=self.bob, description="Private record")
        response = self.client.get(self.history_url())
        self.assertNotContains(response, "Private record")
        self.assertNotIn(other, list(response.context["expenses"]))
        for name in ("edit_expense", "delete_expense"):
            with self.subTest(name=name):
                url = reverse(name, args=[other.pk])
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url, self.expense_data(version=0)).status_code, 404)
        self.assertTrue(Expense.objects.filter(pk=other.pk).exists())

    def test_delete_requires_confirmation_and_repeated_delete_is_safe(self):
        expense = self.expense()
        url = reverse("delete_expense", args=[expense.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(Expense.objects.filter(pk=expense.pk).exists())
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(Expense.objects.filter(pk=expense.pk).exists())
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(self.client.get(reverse("edit_expense", args=[expense.pk])).status_code, 404)

    def test_wallet_pages_are_separate_and_unknown_wallet_is_rejected(self):
        usd = self.expense(description="Dollar lunch")
        lbp = self.expense(description="Lira taxi", currency="LBP")
        self.assertEqual(list(self.client.get(self.history_url("usd")).context["expenses"]), [usd])
        self.assertEqual(list(self.client.get(self.history_url("lbp")).context["expenses"]), [lbp])
        self.assertEqual(self.client.get(self.history_url("eur")).status_code, 404)
        self.assertEqual(self.client.get(self.add_url("eur")).status_code, 404)

    def test_descriptions_are_escaped_in_rendered_pages(self):
        description = "<script>alert('test')</script>"
        self.expense(description=description)
        for url in (self.history_url(), reverse("dashboard")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotContains(response, description)
                self.assertContains(response, "&lt;script&gt;")


class DashboardTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.alice)

    def test_totals_never_mix_wallets_or_users(self):
        today = self.expense(amount=Decimal("12.50"))
        self.expense(amount=Decimal("7.50"), category="Transport", date=date(2026, 10, 1))
        self.expense(amount=Decimal("4"), date=date(2026, 9, 30))
        self.expense(amount=Decimal("500000"), currency="LBP")
        self.expense(amount=Decimal("1000"), user=self.bob)
        response = self.client.get(reverse("dashboard"), {"wallet": "usd"})
        self.assertEqual(response.context["total_spending"], Decimal("20"))
        self.assertIn(today, response.context["recent_expenses"])
        categories = {row["name"]: row["total"] for row in response.context["spending_by_category"]}
        self.assertEqual(len(categories), 6)
        self.assertEqual(categories["Food"], Decimal("12.50"))
        self.assertEqual(categories["Transport"], Decimal("7.50"))
        self.assertEqual(categories["Bills"], Decimal("0"))
        summaries = list(response.context["monthly_summary"])
        self.assertEqual(sum(row["total"] for row in summaries), Decimal("24"))
        self.assertEqual(sum(row["count"] for row in summaries), 3)
        response = self.client.get(reverse("dashboard"), {"wallet": "lbp"})
        self.assertEqual(response.context["total_spending"], Decimal("500000"))

    def test_recent_expenses_are_limited_to_five_records(self):
        records = [self.expense(description=f"Expense {day}", date=date(2026, 10, day)) for day in range(1, 8)]
        response = self.client.get(reverse("dashboard"), {"wallet": "usd"})
        self.assertEqual(list(response.context["recent_expenses"]), list(reversed(records))[:5])

    def test_monthly_summary_keeps_year_boundaries_distinct(self):
        self.expense(amount=Decimal("10"), date=date(2025, 12, 31))
        self.expense(amount=Decimal("20"), date=date(2026, 1, 1))
        self.expense(amount=Decimal("30"), date=date(2026, 10, 1))
        response = self.client.get(reverse("dashboard"))
        rows = list(response.context["monthly_summary"])
        self.assertEqual([(row["month"].year, row["month"].month, row["total"]) for row in rows],
                         [(2026, 10, Decimal("30")), (2026, 1, Decimal("20")), (2025, 12, Decimal("10"))])

    def test_empty_dashboard_has_zero_totals_and_six_categories(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_spending"], Decimal("0"))
        self.assertEqual(len(response.context["spending_by_category"]), 6)
        self.assertEqual(list(response.context["monthly_summary"]), [])
        self.assertEqual(list(response.context["recent_expenses"]), [])

    def test_selected_wallet_is_remembered_and_invalid_selection_is_rejected(self):
        self.expense(amount=Decimal("10"), currency="USD")
        self.expense(amount=Decimal("1000"), currency="LBP")
        self.client.get(self.history_url("lbp"))
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["total_spending"], Decimal("1000"))
        self.assertEqual(self.client.get(reverse("dashboard"), {"wallet": "eur"}).status_code, 404)


class BudgetTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.alice)

    def save_url(self, currency="usd"):
        return reverse("save_budget", kwargs={"currency": currency})

    def overall_save_url(self, currency="usd"):
        return reverse("save_overall_budget", kwargs={"currency": currency})

    def test_save_updates_current_category_month_wallet_without_duplicates(self):
        for amount in ("100", "150"):
            response = self.client.post(self.save_url(), {"category": "Food", "amount": amount})
            self.assertEqual(response.status_code, 302)
        budget = MonthlyBudget.objects.get(user=self.alice, currency="USD", category="Food")
        self.assertEqual(budget.month, date(2026, 10, 1))
        self.assertEqual(budget.amount, Decimal("150"))
        self.assertEqual(MonthlyBudget.objects.count(), 1)
        self.client.post(self.save_url("lbp"), {"category": "Food", "amount": "1000000", "currency": "USD"})
        self.assertEqual(MonthlyBudget.objects.count(), 2)
        self.assertEqual(MonthlyBudget.objects.get(currency="LBP").amount, Decimal("1000000"))

    def test_invalid_budget_does_not_save_and_shows_errors(self):
        for values in ({"category": "Food", "amount": "0"}, {"category": "Food", "amount": "-1"},
                       {"category": "Food", "amount": "1.001"}, {"category": "Food", "amount": "NaN"},
                       {"category": "Invalid", "amount": "100"}):
            with self.subTest(values=values):
                response = self.client.post(self.save_url(), values)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["budget_form"].errors)
                self.assertEqual(MonthlyBudget.objects.count(), 0)

    def test_dashboard_budget_uses_spending_in_matching_month_and_wallet(self):
        MonthlyBudget.objects.create(user=self.alice, currency="USD", category="Food", month=date(2026, 10, 1), amount="10")
        MonthlyBudget.objects.create(user=self.alice, currency="LBP", category="Food", month=date(2026, 10, 1), amount="1000000")
        MonthlyBudget.objects.create(user=self.alice, currency="USD", category="Food", month=date(2026, 9, 1), amount="500")
        self.expense(amount=Decimal("12"))
        response = self.client.get(reverse("dashboard"), {"wallet": "usd"})
        food = next(row for row in response.context["spending_by_category"] if row["name"] == "Food")
        self.assertEqual(food["budget"], Decimal("10"))
        self.assertEqual(food["remaining"], Decimal("-2"))
        self.assertTrue(food["over_budget"])

    def test_budget_delete_is_post_only_and_owner_restricted(self):
        own = MonthlyBudget.objects.create(user=self.alice, currency="USD", category="Food", month=date(2026, 10, 1), amount="50")
        other = MonthlyBudget.objects.create(user=self.bob, currency="USD", category="Food", month=date(2026, 10, 1), amount="75")
        own_url = reverse("delete_budget", args=[own.pk])
        self.assertEqual(self.client.get(own_url).status_code, 405)
        self.assertTrue(MonthlyBudget.objects.filter(pk=own.pk).exists())
        self.assertEqual(self.client.post(reverse("delete_budget", args=[other.pk])).status_code, 404)
        self.assertTrue(MonthlyBudget.objects.filter(pk=other.pk).exists())
        self.assertEqual(self.client.post(own_url).status_code, 302)
        self.assertFalse(MonthlyBudget.objects.filter(pk=own.pk).exists())
        self.assertEqual(self.client.get(self.save_url()).status_code, 405)

    def test_database_rejects_duplicate_category_budgets_and_nonpositive_amounts(self):
        values = {"user": self.alice, "currency": "USD", "category": "Food", "month": date(2026, 10, 1), "amount": "10"}
        MonthlyBudget.objects.create(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MonthlyBudget.objects.create(**values)
        for amount in ("0", "-1"):
            with self.subTest(amount=amount):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    MonthlyBudget.objects.create(**{**values, "category": "Bills", "amount": amount})

    def test_database_rejects_budget_months_that_are_not_first_of_month(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            MonthlyBudget.objects.create(user=self.alice, currency="USD", category="Food", month=TODAY, amount="50")

    def test_overall_month_and_year_budgets_use_only_the_current_period(self):
        self.client.post(self.overall_save_url(), {"period": "month", "amount": "100"})
        self.client.post(self.overall_save_url(), {"period": "year", "amount": "1000"})
        self.client.post(self.overall_save_url(), {"period": "overall", "amount": "2000"})
        OverallBudget.objects.create(
            user=self.alice, currency="USD", period="month", period_start=date(2026, 9, 1), amount="999",
        )
        OverallBudget.objects.create(
            user=self.alice, currency="USD", period="year", period_start=date(2025, 1, 1), amount="9999",
        )
        self.expense(amount=Decimal("40"))
        self.expense(amount=Decimal("50"), date=date(2026, 1, 5))
        self.expense(amount=Decimal("60"), date=date(2025, 12, 31))
        response = self.client.get(reverse("dashboard"), {"wallet": "usd"})
        rows = {row["period"]: row for row in response.context["overall_budgets"]}
        self.assertEqual(rows["month"]["amount"], Decimal("100"))
        self.assertEqual(rows["month"]["spent"], Decimal("40"))
        self.assertEqual(rows["month"]["remaining"], Decimal("60"))
        self.assertEqual(rows["year"]["amount"], Decimal("1000"))
        self.assertEqual(rows["year"]["spent"], Decimal("90"))
        self.assertEqual(rows["year"]["remaining"], Decimal("910"))
        self.assertEqual(rows["overall"]["amount"], Decimal("2000"))
        self.assertEqual(rows["overall"]["spent"], Decimal("150"))
        self.assertEqual(rows["overall"]["remaining"], Decimal("1850"))

    def test_overall_budget_updates_without_duplicates_and_validates_amount(self):
        for amount in ("100", "150"):
            self.assertEqual(
                self.client.post(self.overall_save_url(), {"period": "month", "amount": amount}).status_code,
                302,
            )
        budget = OverallBudget.objects.get()
        self.assertEqual(budget.period_start, date(2026, 10, 1))
        self.assertEqual(budget.amount, Decimal("150"))
        for values in ({"period": "month", "amount": "0"}, {"period": "old", "amount": "100"}):
            response = self.client.post(self.overall_save_url(), values)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["overall_budget_form"].errors)
        self.assertEqual(OverallBudget.objects.count(), 1)

    def test_overall_budget_delete_is_post_only_and_owner_restricted(self):
        own = OverallBudget.objects.create(
            user=self.alice, currency="USD", period="month", period_start=date(2026, 10, 1), amount="100",
        )
        other = OverallBudget.objects.create(
            user=self.bob, currency="USD", period="month", period_start=date(2026, 10, 1), amount="200",
        )
        own_url = reverse("delete_overall_budget", args=[own.pk])
        self.assertEqual(self.client.get(own_url).status_code, 405)
        self.assertEqual(self.client.post(reverse("delete_overall_budget", args=[other.pk])).status_code, 404)
        self.assertEqual(self.client.post(own_url).status_code, 302)
        self.assertFalse(OverallBudget.objects.filter(pk=own.pk).exists())


class RequestSecurityTests(AppTestCase):
    @override_settings(AUTH_ATTEMPT_LIMIT=2)
    def test_repeated_failed_logins_and_registrations_are_limited(self):
        for attempt in range(2):
            self.assertEqual(self.client.post(reverse("login"), {"username": "Alice", "password": "wrong"}).status_code, 200)
        response = self.client.post(reverse("login"), {"username": "Alice", "password": PASSWORD})
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.context["error_message"])
        self.assertNotIn("_auth_user_id", self.client.session)
        # Registration has its own limit and cannot be used to bypass its own failures.
        for attempt in range(2):
            self.assertEqual(self.client.post(reverse("register"), self.registration_data(username="Alice")).status_code, 200)
        response = self.client.post(reverse("register"), self.registration_data())
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.context["error_message"])
        self.assertEqual(User.objects.count(), 2)

    @override_settings(AUTH_ATTEMPT_LIMIT=1)
    def test_blocked_login_never_calls_authentication_or_retains_a_password(self):
        self.client.post(reverse("login"), {"username": "Alice", "password": "wrong"})
        with patch("django.contrib.auth.forms.authenticate") as authenticate:
            response = self.client.post(reverse("login"), {"username": "Alice", "password": PASSWORD})
        authenticate.assert_not_called()
        self.assertEqual(response.status_code, 429)
        self.assertFalse(response.context["form"].is_bound)
        self.assertEqual(response.context["form"]["username"].value(), "Alice")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotContains(response, PASSWORD, status_code=429)

    @override_settings(AUTH_ATTEMPT_LIMIT=1)
    def test_blocked_registration_never_runs_validation_or_creates_an_account(self):
        self.client.post(reverse("register"), self.registration_data(username="Alice"))
        with patch("app1.views.RegisterForm.is_valid", side_effect=AssertionError("blocked request validated")) as validate:
            response = self.client.post(reverse("register"), self.registration_data())
        validate.assert_not_called()
        self.assertEqual(response.status_code, 429)
        self.assertFalse(response.context["form"].is_bound)
        self.assertEqual(response.context["form"]["username"].value(), "Charlie")
        self.assertEqual(User.objects.count(), 2)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotContains(response, PASSWORD, status_code=429)

    @override_settings(AUTH_ATTEMPT_LIMIT=2)
    def test_successful_login_resets_failed_attempts(self):
        self.client.post(reverse("login"), {"username": "Alice", "password": "wrong"})
        response = self.client.post(reverse("login"), {"username": "Alice", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.client.post(reverse("logout"))
        for attempt in range(2):
            response = self.client.post(reverse("login"), {"username": "Alice", "password": "wrong"})
            self.assertEqual(response.status_code, 200)

    def test_login_next_redirect_allows_local_pages_but_rejects_external_urls(self):
        for next_page in ("https://evil.example/path", "//evil.example/path", "javascript:alert(1)"):
            with self.subTest(next_page=next_page):
                response = self.client.post(reverse("login") + "?next=" + next_page,
                                            {"username": "Alice", "password": PASSWORD})
                self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
                self.client.post(reverse("logout"))
        response = self.client.post(reverse("login") + "?next=" + self.history_url("lbp"),
                                    {"username": "Alice", "password": PASSWORD})
        self.assertRedirects(response, self.history_url("lbp"), fetch_redirect_response=False)

    def test_csrf_is_required_for_account_and_expense_mutations(self):
        browser = Client(enforce_csrf_checks=True)
        self.assertEqual(browser.post(reverse("register"), self.registration_data()).status_code, 403)
        self.assertEqual(browser.post(reverse("login"), {"username": "Alice", "password": PASSWORD}).status_code, 403)
        browser.force_login(self.alice)
        expense = self.expense()
        urls = [self.add_url(), reverse("edit_expense", args=[expense.pk]),
                reverse("delete_expense", args=[expense.pk]), reverse("logout"),
                reverse("save_budget", kwargs={"currency": "usd"})]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(browser.post(url, self.expense_data(version=0)).status_code, 403)
        self.assertTrue(Expense.objects.filter(pk=expense.pk).exists())
        self.assertEqual(MonthlyBudget.objects.count(), 0)
