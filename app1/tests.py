from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Expense


User = get_user_model()
PASSWORD = "StudyBudget!4826"


class ExpenseTestCase(TestCase):
    """Shared fixtures for access, validation, and spending tests."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="budget_student", password=PASSWORD, first_name="Maya",
            last_name="Haddad", email="maya@example.com"
        )
        cls.other_user = User.objects.create_user(username="another_student", password=PASSWORD)

    def setUp(self):
        self.client.force_login(self.user)

    def make_expense(self, **changes):
        values = {
            "owner": self.user, "description": "Lunch on campus", "amount": Decimal("8.50"),
            "category": "food", "currency": "USD", "date": timezone.localdate(),
        }
        values.update(changes)
        return Expense.objects.create(**values)

    def expense_data(self, **changes):
        values = {
            "description": "Campus lunch", "amount": "8.50", "category": "food",
            "currency": "USD", "date": timezone.localdate().isoformat(),
        }
        values.update(changes)
        return values

    def list_ids(self, response):
        return {expense.pk for expense in response.context["expenses"]}


class AuthenticationTests(ExpenseTestCase):
    def test_anonymous_users_are_redirected_to_login(self):
        expense = self.make_expense()
        self.client.logout()
        pages = [
            ("dashboard", ()), ("profile", ()), ("expense_list", ()), ("expense_add", ()),
            ("expense_edit", (expense.pk,)), ("expense_delete", (expense.pk,)),
        ]
        for name, args in pages:
            with self.subTest(page=name):
                response = self.client.get(reverse(name, args=args))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("login")))

    def test_registration_creates_user_with_hashed_password(self):
        self.client.logout()
        response = self.client.post(reverse("register"), {
            "username": "new_student", "first_name": "Nour", "last_name": "Saleh",
            "email": "nour@example.com", "password1": PASSWORD, "password2": PASSWORD,
        })
        self.assertEqual(response.status_code, 302)
        registered = User.objects.get(username="new_student")
        self.assertTrue(registered.check_password(PASSWORD))
        self.assertNotEqual(registered.password, PASSWORD)
        self.assertEqual(registered.first_name, "Nour")
        self.assertEqual(registered.email, "nour@example.com")

    def test_registration_rejects_existing_username(self):
        self.client.logout()
        response = self.client.post(reverse("register"), {
            "username": self.user.username, "password1": PASSWORD, "password2": PASSWORD,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 2)

    def test_registration_rejects_mismatched_and_weak_passwords(self):
        self.client.logout()
        for first, second in [(PASSWORD, "DifferentPass!82"), ("123", "123")]:
            with self.subTest(password=first):
                response = self.client.post(reverse("register"), {
                    "username": "new_student", "password1": first, "password2": second,
                })
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertFalse(User.objects.filter(username="new_student").exists())

    def test_login_accepts_valid_credentials_and_local_next(self):
        self.client.logout()
        response = self.client.post(reverse("login"), {
            "username": self.user.username, "password": PASSWORD, "next": reverse("profile"),
        })
        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_rejects_invalid_credentials(self):
        self.client.logout()
        response = self.client.post(reverse("login"), {
            "username": self.user.username, "password": "WrongPassword!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_does_not_redirect_to_an_external_host(self):
        self.client.logout()
        response = self.client.post(reverse("login"), {
            "username": self.user.username, "password": PASSWORD, "next": "https://example.com/phish",
        })
        self.assertRedirects(response, reverse("dashboard"))

    def test_logout_requires_post_and_ends_the_session(self):
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_profile_displays_the_current_account(self):
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)
        self.assertContains(response, self.user.email)
        self.assertNotContains(response, self.other_user.username)


class ExpenseCrudTests(ExpenseTestCase):
    def test_add_assigns_current_user_and_preserves_decimal_amount(self):
        response = self.client.post(reverse("expense_add"), self.expense_data(
            amount="1234.56", owner=self.other_user.pk
        ))
        self.assertEqual(response.status_code, 302)
        expense = Expense.objects.get()
        self.assertEqual(expense.owner, self.user)
        self.assertEqual(expense.amount, Decimal("1234.56"))

    def test_minimum_positive_amount_can_be_saved(self):
        response = self.client.post(reverse("expense_add"), self.expense_data(amount="0.01"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Expense.objects.get().amount, Decimal("0.01"))

    def test_invalid_amounts_do_not_create_an_expense(self):
        for amount in ["0", "-0.01", "abc", "1.001", "1000000000000.00", "", "NaN", "Infinity"]:
            with self.subTest(amount=amount):
                response = self.client.post(reverse("expense_add"), self.expense_data(amount=amount))
                self.assertEqual(response.status_code, 200)
                self.assertIn("amount", response.context["form"].errors)
                self.assertEqual(Expense.objects.count(), 0)

    def test_invalid_category_currency_date_and_description_are_rejected(self):
        invalid_fields = [
            ("category", "unknown"), ("currency", "EUR"), ("date", "2026-02-30"),
            ("date", "not-a-date"), ("description", "   "),
        ]
        for field, value in invalid_fields:
            with self.subTest(field=field, value=value):
                response = self.client.post(reverse("expense_add"), self.expense_data(**{field: value}))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
                self.assertEqual(Expense.objects.count(), 0)

    def test_each_category_and_both_currencies_can_be_saved(self):
        categories = ["food", "transport", "bills", "shopping", "entertainment", "other"]
        for index, category in enumerate(categories):
            with self.subTest(category=category):
                response = self.client.post(reverse("expense_add"), self.expense_data(
                    category=category, currency="USD" if index % 2 == 0 else "LBP"
                ))
                self.assertEqual(response.status_code, 302)
        self.assertEqual(Expense.objects.count(), 6)

    def test_model_validation_rejects_nonpositive_amount(self):
        expense = Expense(owner=self.user, **self.expense_data(amount=Decimal("0.00")))
        with self.assertRaises(ValidationError):
            expense.full_clean()

    def test_model_default_date_is_today(self):
        expense = Expense(
            owner=self.user, description="Notebook", amount=Decimal("2.50"),
            category="shopping", currency="USD"
        )
        self.assertEqual(expense.date, timezone.localdate())

    def test_owner_can_edit_all_expense_fields(self):
        expense = self.make_expense()
        response = self.client.post(reverse("expense_edit", args=[expense.pk]), self.expense_data(
            description="Bus to campus", amount="3.20", category="transport",
            currency="LBP", date="2026-01-15", owner=self.other_user.pk
        ))
        self.assertEqual(response.status_code, 302)
        expense.refresh_from_db()
        self.assertEqual(expense.description, "Bus to campus")
        self.assertEqual(expense.amount, Decimal("3.20"))
        self.assertEqual(expense.category, "transport")
        self.assertEqual(expense.currency, "LBP")
        self.assertEqual(expense.date, date(2026, 1, 15))
        self.assertEqual(expense.owner, self.user)

    def test_invalid_edit_keeps_the_original_expense(self):
        expense = self.make_expense()
        response = self.client.post(
            reverse("expense_edit", args=[expense.pk]), self.expense_data(amount="-9")
        )
        self.assertEqual(response.status_code, 200)
        expense.refresh_from_db()
        self.assertEqual(expense.amount, Decimal("8.50"))

    def test_delete_get_is_confirmation_and_post_deletes(self):
        expense = self.make_expense()
        url = reverse("expense_delete", args=[expense.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(Expense.objects.filter(pk=expense.pk).exists())
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(Expense.objects.filter(pk=expense.pk).exists())

    def test_other_users_cannot_view_or_modify_an_expense(self):
        expense = self.make_expense(owner=self.other_user, description="Private purchase")
        for page in ["expense_edit", "expense_delete"]:
            url = reverse(page, args=[expense.pk])
            for method in ["get", "post"]:
                with self.subTest(page=page, method=method):
                    response = getattr(self.client, method)(url, self.expense_data(amount="999.00"))
                    self.assertEqual(response.status_code, 404)
        expense.refresh_from_db()
        self.assertEqual(expense.amount, Decimal("8.50"))
        self.assertEqual(expense.description, "Private purchase")

    def test_missing_expenses_return_404(self):
        for page in ["expense_edit", "expense_delete"]:
            with self.subTest(page=page):
                self.assertEqual(self.client.get(reverse(page, args=[99999])).status_code, 404)

    def test_descriptions_are_html_escaped_in_list(self):
        self.make_expense(description="<script>alert('expense')</script>")
        response = self.client.get(reverse("expense_list"))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert('expense')</script>")


class ExpenseFilterTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.low = self.make_expense(amount=Decimal("5.00"), date=date(2026, 1, 10))
        self.middle = self.make_expense(amount=Decimal("10.00"), date=date(2026, 1, 15))
        self.high = self.make_expense(amount=Decimal("20.00"), date=date(2026, 1, 20))
        self.bus = self.make_expense(category="transport", amount=Decimal("10.00"), date=date(2026, 1, 15))
        self.lbp = self.make_expense(currency="LBP", amount=Decimal("10.00"), date=date(2026, 1, 15))
        self.private = self.make_expense(owner=self.other_user, amount=Decimal("10.00"), date=date(2026, 1, 15))

    def test_default_listing_contains_only_owned_usd_expenses(self):
        response = self.client.get(reverse("expense_list"))
        self.assertEqual(self.list_ids(response), {self.low.pk, self.middle.pk, self.high.pk, self.bus.pk})
        self.assertEqual(response.context["filtered_total"], Decimal("45.00"))

    def test_category_filter(self):
        response = self.client.get(reverse("expense_list"), {"category": "transport"})
        self.assertEqual(self.list_ids(response), {self.bus.pk})

    def test_date_boundaries_are_inclusive(self):
        response = self.client.get(reverse("expense_list"), {
            "start_date": "2026-01-10", "end_date": "2026-01-20",
        })
        self.assertEqual(self.list_ids(response), {self.low.pk, self.middle.pk, self.high.pk, self.bus.pk})

    def test_amount_boundaries_are_inclusive(self):
        response = self.client.get(reverse("expense_list"), {"min_amount": "5.00", "max_amount": "20.00"})
        self.assertEqual(self.list_ids(response), {self.low.pk, self.middle.pk, self.high.pk, self.bus.pk})

    def test_all_filters_combine(self):
        response = self.client.get(reverse("expense_list"), {
            "category": "food", "start_date": "2026-01-15", "end_date": "2026-01-20",
            "min_amount": "10.00", "max_amount": "10.00",
        })
        self.assertEqual(self.list_ids(response), {self.middle.pk})
        self.assertEqual(response.context["filtered_total"], Decimal("10.00"))

    def test_single_sided_ranges(self):
        cases = [
            ({"start_date": "2026-01-20"}, {self.high.pk}),
            ({"end_date": "2026-01-10"}, {self.low.pk}),
            ({"min_amount": "20.00"}, {self.high.pk}),
            ({"max_amount": "5.00"}, {self.low.pk}),
        ]
        for filters, expected in cases:
            with self.subTest(filters=filters):
                response = self.client.get(reverse("expense_list"), filters)
                self.assertEqual(self.list_ids(response), expected)

    def test_invalid_filters_show_errors_and_no_results(self):
        cases = [
            {"start_date": "bad-date"}, {"category": "invalid"}, {"min_amount": "not-money"},
            {"start_date": "2026-01-20", "end_date": "2026-01-10"},
            {"min_amount": "20", "max_amount": "5"},
        ]
        for filters in cases:
            with self.subTest(filters=filters):
                response = self.client.get(reverse("expense_list"), filters)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["filter_form"].errors)
                self.assertEqual(self.list_ids(response), set())
                self.assertEqual(response.context["filtered_total"], Decimal("0.00"))

    def test_empty_filter_result_has_zero_total(self):
        response = self.client.get(reverse("expense_list"), {"category": "bills"})
        self.assertEqual(self.list_ids(response), set())
        self.assertEqual(response.context["filtered_total"], Decimal("0.00"))

    def test_selected_lbp_currency_is_used_with_filters(self):
        self.client.post(reverse("switch_currency"), {"currency": "LBP"})
        response = self.client.get(reverse("expense_list"), {"category": "food", "min_amount": "5"})
        self.assertEqual(self.list_ids(response), {self.lbp.pk})
        self.assertEqual(response.context["filtered_total"], Decimal("10.00"))


class DashboardTests(ExpenseTestCase):
    def test_monthly_totals_use_decimal_and_current_month_only(self):
        today = timezone.localdate()
        first_day = today.replace(day=1)
        next_month = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1)
        self.make_expense(amount=Decimal("0.10"), date=first_day)
        self.make_expense(amount=Decimal("0.20"), date=next_month - timedelta(days=1))
        self.make_expense(amount=Decimal("999.00"), date=first_day - timedelta(days=1))
        self.make_expense(amount=Decimal("999.00"), date=next_month)
        self.make_expense(amount=Decimal("999.00"), currency="LBP", date=today)
        self.make_expense(owner=self.other_user, amount=Decimal("999.00"), date=today)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["monthly_total"], Decimal("0.30"))
        self.assertEqual(response.context["expense_count"], 2)

    def test_category_totals_and_percentages_match_the_month(self):
        self.make_expense(amount=Decimal("10.00"), category="food")
        self.make_expense(amount=Decimal("30.00"), category="transport")
        previous_month = timezone.localdate().replace(day=1) - timedelta(days=1)
        self.make_expense(amount=Decimal("1000.00"), date=previous_month)
        response = self.client.get(reverse("dashboard"))
        categories = response.context["category_totals"]
        self.assertEqual(len(categories), 6)
        self.assertEqual(sum((row["total"] for row in categories), Decimal("0.00")), Decimal("40.00"))
        self.assertAlmostEqual(sum(float(row["percent"]) for row in categories), 100.0)
        self.assertEqual(
            sorted(row["total"] for row in categories),
            [Decimal("0.00")] * 4 + [Decimal("10.00"), Decimal("30.00")]
        )

    def test_recent_expenses_show_five_latest_owned_records_in_selected_currency(self):
        today = timezone.localdate()
        owned = [self.make_expense(date=today - timedelta(days=index)) for index in range(7)]
        self.make_expense(owner=self.other_user, date=today + timedelta(days=1))
        self.make_expense(currency="LBP", date=today + timedelta(days=1))
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(
            [expense.pk for expense in response.context["recent_expenses"]],
            [expense.pk for expense in owned[:5]]
        )

    def test_monthly_summary_keeps_december_and_january_separate(self):
        self.make_expense(amount=Decimal("12.34"), date=date(2024, 12, 31))
        self.make_expense(amount=Decimal("5.00"), date=date(2025, 1, 1))
        self.make_expense(amount=Decimal("7.00"), date=date(2025, 1, 31))
        self.make_expense(owner=self.other_user, amount=Decimal("500.00"), date=date(2024, 12, 31))
        self.make_expense(currency="LBP", amount=Decimal("500.00"), date=date(2025, 1, 1))
        response = self.client.get(reverse("dashboard"))
        months = {row["month"]: row for row in response.context["monthly_summary"]}
        self.assertEqual(months[date(2024, 12, 1)]["total"], Decimal("12.34"))
        self.assertEqual(months[date(2025, 1, 1)]["total"], Decimal("12.00"))
        self.assertEqual(months[date(2025, 1, 1)]["count"], 2)
        self.assertIn(timezone.localdate().replace(day=1), months)

    def test_empty_dashboard_has_zero_totals_and_a_current_month_row(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["monthly_total"], Decimal("0.00"))
        self.assertEqual(response.context["expense_count"], 0)
        self.assertEqual(len(response.context["category_totals"]), 6)
        self.assertTrue(all(row["total"] == 0 and row["percent"] == 0 for row in response.context["category_totals"]))
        self.assertEqual(list(response.context["recent_expenses"]), [])
        summary = response.context["monthly_summary"]
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["month"], timezone.localdate().replace(day=1))
        self.assertEqual(summary[0]["total"], Decimal("0.00"))
        self.assertEqual(summary[0]["count"], 0)

    def test_currency_switch_changes_dashboard_totals_without_conversion(self):
        self.make_expense(amount=Decimal("10.00"))
        self.make_expense(amount=Decimal("450000.00"), currency="LBP")
        self.client.post(reverse("switch_currency"), {"currency": "LBP"})
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["monthly_total"], Decimal("450000.00"))
        self.assertEqual(response.context["expense_count"], 1)


class CurrencySwitchTests(ExpenseTestCase):
    def test_post_sets_currency_and_redirects_to_a_local_page(self):
        response = self.client.post(reverse("switch_currency"), {
            "currency": "LBP", "next": reverse("expense_list"),
        })
        self.assertRedirects(response, reverse("expense_list"))
        self.assertEqual(self.client.session["selected_currency"], "LBP")

    def test_get_cannot_change_currency(self):
        response = self.client.get(reverse("switch_currency"), {"currency": "LBP"})
        self.assertEqual(response.status_code, 405)
        self.assertNotEqual(self.client.session.get("selected_currency"), "LBP")

    def test_invalid_currency_preserves_selection(self):
        self.client.post(reverse("switch_currency"), {"currency": "LBP"})
        response = self.client.post(reverse("switch_currency"), {"currency": "EUR"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["selected_currency"], "LBP")

    def test_external_next_targets_are_rejected(self):
        for target in ["https://example.com/phish", "//example.com/phish"]:
            with self.subTest(target=target):
                response = self.client.post(reverse("switch_currency"), {"currency": "LBP", "next": target})
                self.assertRedirects(response, reverse("dashboard"))

    def test_anonymous_post_cannot_set_currency(self):
        self.client.logout()
        response = self.client.post(reverse("switch_currency"), {"currency": "LBP"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))
        self.assertNotIn("selected_currency", self.client.session)


class CsrfProtectionTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.csrf_client = Client(enforce_csrf_checks=True)
        self.csrf_client.force_login(self.user)

    def test_create_rejects_post_without_csrf_token(self):
        response = self.csrf_client.post(reverse("expense_add"), self.expense_data())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Expense.objects.count(), 0)

    def test_delete_rejects_post_without_csrf_token(self):
        expense = self.make_expense()
        response = self.csrf_client.post(reverse("expense_delete", args=[expense.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Expense.objects.filter(pk=expense.pk).exists())

    def test_logout_rejects_post_without_csrf_token(self):
        response = self.csrf_client.post(reverse("logout"))
        self.assertEqual(response.status_code, 403)
        self.assertIn("_auth_user_id", self.csrf_client.session)

    def test_currency_switch_rejects_post_without_csrf_token(self):
        response = self.csrf_client.post(reverse("switch_currency"), {"currency": "LBP"})
        self.assertEqual(response.status_code, 403)
        self.assertNotEqual(self.csrf_client.session.get("selected_currency"), "LBP")

    def test_create_accepts_a_valid_csrf_token_from_the_form(self):
        response = self.csrf_client.get(reverse("expense_add"))
        self.assertEqual(response.status_code, 200)
        token = self.csrf_client.cookies["csrftoken"].value
        response = self.csrf_client.post(
            reverse("expense_add"), self.expense_data(csrfmiddlewaretoken=token)
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Expense.objects.count(), 1)


class DemoDataTests(ExpenseTestCase):
    def test_demo_data_is_owned_idempotent_and_contains_both_currencies(self):
        original_password = self.user.password
        call_command("seed_demo", username=self.user.username, stdout=StringIO())
        first_count = Expense.objects.filter(owner=self.user).count()
        self.assertGreater(first_count, 0)
        self.assertEqual(Expense.objects.filter(owner=self.other_user).count(), 0)
        self.assertEqual(set(Expense.objects.values_list("category", flat=True)), {
            "food", "transport", "bills", "shopping", "entertainment", "other",
        })
        self.assertEqual(set(Expense.objects.values_list("currency", flat=True)), {"USD", "LBP"})
        call_command("seed_demo", username=self.user.username, stdout=StringIO())
        self.assertEqual(Expense.objects.filter(owner=self.user).count(), first_count)
        self.assertEqual(User.objects.count(), 2)
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, original_password)

    def test_demo_data_requires_an_existing_account(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", username="account_does_not_exist", stdout=StringIO())
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(Expense.objects.count(), 0)


class AdminOwnershipTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])

    def test_admin_list_is_confined_to_owned_expenses(self):
        owned = self.make_expense(description="Admin own expense")
        self.make_expense(owner=self.other_user, description="Other account private expense")
        response = self.client.get(reverse("admin:app1_expense_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([expense.pk for expense in response.context["cl"].result_list], [owned.pk])

    def test_admin_create_ignores_a_forged_owner(self):
        response = self.client.post(
            reverse("admin:app1_expense_add"), self.expense_data(owner=self.other_user.pk, _save="Save")
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Expense.objects.get().owner, self.user)

    def test_admin_cannot_open_edit_or_delete_another_accounts_expense(self):
        expense = self.make_expense(owner=self.other_user, description="Private admin record")
        for action in ["change", "delete"]:
            url = reverse(f"admin:app1_expense_{action}", args=[expense.pk])
            with self.subTest(action=action):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                data = self.expense_data(amount="999.00", _save="Save") if action == "change" else {"post": "yes"}
                response = self.client.post(url, data)
                self.assertEqual(response.status_code, 302)
                expense.refresh_from_db()
                self.assertEqual(expense.owner, self.other_user)
                self.assertEqual(expense.amount, Decimal("8.50"))
