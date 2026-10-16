from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Expense(models.Model):
    class Category(models.TextChoices):
        FOOD = "food", "Food"
        TRANSPORT = "transport", "Transport"
        BILLS = "bills", "Bills"
        SHOPPING = "shopping", "Shopping"
        ENTERTAINMENT = "entertainment", "Entertainment"
        OTHER = "other", "Other"

    class Currency(models.TextChoices):
        USD = "USD", "USD"
        LBP = "LBP", "LBP"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="expenses"
    )
    description = models.CharField(max_length=120)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    category = models.CharField(max_length=20, choices=Category.choices)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [models.Index(fields=["owner", "currency", "date"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=Decimal("0.01")),
                name="expense_amount_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    category__in=["food", "transport", "bills", "shopping", "entertainment", "other"]
                ),
                name="expense_category_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__in=["USD", "LBP"]),
                name="expense_currency_valid",
            ),
        ]

    def __str__(self):
        return f"{self.description} ({self.currency} {self.amount})"
