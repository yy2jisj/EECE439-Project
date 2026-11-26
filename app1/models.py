from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models


class AccountIdentity(models.Model):
    # Separate normalized keys enforce case-insensitive uniqueness without replacing Django User.
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    username_key = models.CharField(max_length=150, unique=True)
    email_key = models.EmailField(max_length=254, null=True, blank=True, unique=True)


class Expense(models.Model):
    CURRENCY_CHOICES = [("USD", "US dollar"), ("LBP", "Lebanese pound")]
    CATEGORY_CHOICES = [
        ("Food", "Food"),
        ("Transport", "Transport"),
        ("Bills", "Bills"),
        ("Shopping", "Shopping"),
        ("Entertainment", "Entertainment"),
        ("Other", "Other"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    date = models.DateField()
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="USD")
    submission_key = models.UUIDField(null=True, unique=True, editable=False)
    version = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-date", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="expense_amount_positive"),
            models.CheckConstraint(condition=models.Q(currency__in=["USD", "LBP"]), name="expense_valid_currency"),
            models.CheckConstraint(condition=models.Q(category__in=["Food", "Transport", "Bills", "Shopping", "Entertainment", "Other"]), name="expense_valid_category"),
        ]

    def __str__(self):
        return self.description


class ExpenseSubmission(models.Model):
    # A receipt survives expense deletion so replaying an old form cannot recreate it.
    key = models.UUIDField(primary_key=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    currency = models.CharField(max_length=3, choices=Expense.CURRENCY_CHOICES)
    expense = models.OneToOneField(Expense, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(currency__in=["USD", "LBP"]), name="submission_valid_currency"),
        ]


class MonthlyBudget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    currency = models.CharField(max_length=3, choices=Expense.CURRENCY_CHOICES, default="USD")
    category = models.CharField(max_length=20, choices=Expense.CATEGORY_CHOICES)
    month = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])

    class Meta:
        ordering = ["category"]
        constraints = [
            models.UniqueConstraint(fields=["user", "currency", "category", "month"], name="unique_monthly_category_budget"),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="budget_amount_positive"),
            models.CheckConstraint(condition=models.Q(currency__in=["USD", "LBP"]), name="budget_valid_currency"),
            models.CheckConstraint(condition=models.Q(category__in=["Food", "Transport", "Bills", "Shopping", "Entertainment", "Other"]), name="budget_valid_category"),
            models.CheckConstraint(condition=models.Q(month__day=1), name="budget_month_first_day"),
        ]

    def __str__(self):
        return f"{self.category}: {self.amount} {self.currency} ({self.month:%Y-%m})"


class OverallBudget(models.Model):
    PERIOD_CHOICES = [("month", "This month"), ("year", "This year"), ("overall", "Overall")]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    currency = models.CharField(max_length=3, choices=Expense.CURRENCY_CHOICES, default="USD")
    period = models.CharField(max_length=7, choices=PERIOD_CHOICES)
    period_start = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])

    class Meta:
        ordering = ["period"]
        constraints = [
            models.UniqueConstraint(fields=["user", "currency", "period", "period_start"], name="unique_overall_budget"),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="overall_budget_amount_positive"),
            models.CheckConstraint(condition=models.Q(currency__in=["USD", "LBP"]), name="overall_budget_valid_currency"),
            models.CheckConstraint(condition=models.Q(period__in=["month", "year", "overall"]), name="overall_budget_valid_period"),
            models.CheckConstraint(
                condition=models.Q(period="month", period_start__day=1)
                | models.Q(period="year", period_start__month=1, period_start__day=1)
                | models.Q(period="overall", period_start=date.min),
                name="overall_budget_valid_start",
            ),
        ]

    def __str__(self):
        return f"{self.get_period_display()}: {self.amount} {self.currency}"
