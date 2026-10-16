from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from app1.models import Expense


class Command(BaseCommand):
    help = "Add optional fictional USD/LBP expenses to an existing account."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True, help="An existing account's username")

    def handle(self, *args, **options):
        try:
            owner = get_user_model().objects.get(username=options["username"])
        except get_user_model().DoesNotExist as error:
            raise CommandError("Account not found. Register an account before adding demo data.") from error

        today = timezone.localdate()
        first_date = today.replace(day=1)
        second_date = today.replace(day=10)
        previous_date = (first_date - timedelta(days=1)).replace(day=5)

        # These amounts are invented examples, not real prices or exchange rates.
        demo_rows = [
            ("Mloukhiye lunch", "8.50", "food", "USD", first_date),
            ("Kebbe lunch", "9.00", "food", "USD", second_date),
            ("Fahitta lunch", "400000.00", "food", "LBP", second_date),
            ("Van 4 ride", "1.50", "transport", "USD", first_date),
            ("Van 1 ride", "90000.00", "transport", "LBP", first_date),
            ("Uber ride", "6.25", "transport", "USD", second_date),
            ("inDrive ride", "500000.00", "transport", "LBP", second_date),
            ("Spinneys groceries", "22.75", "shopping", "USD", second_date),
            ("Spinneys groceries", "1800000.00", "shopping", "LBP", previous_date),
            ("Claude subscription", "12.00", "bills", "USD", first_date),
            ("Water bill", "250000.00", "bills", "LBP", first_date),
            ("Netflix subscription", "7.50", "entertainment", "USD", previous_date),
            ("Cinema ticket", "300000.00", "entertainment", "LBP", second_date),
            ("Notebook", "4.00", "other", "USD", previous_date),
            ("Small gift", "150000.00", "other", "LBP", previous_date),
        ]
        added_count = 0
        for description, amount, category, currency, expense_date in demo_rows:
            expense, created = Expense.objects.get_or_create(
                owner=owner,
                description=f"Demo: {description}",
                amount=Decimal(amount),
                category=category,
                currency=currency,
                date=expense_date,
            )
            if created:
                added_count += 1

        self.stdout.write("Fictional demo data: all amounts are invented; no conversion or real prices are implied.")
        self.stdout.write(self.style.SUCCESS(f"Added {added_count} demo expenses for {owner.username}."))
