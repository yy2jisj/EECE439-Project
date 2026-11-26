from datetime import date
from decimal import Decimal
import unicodedata

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import AccountIdentity, Expense, MonthlyBudget, OverallBudget


def normalize_username(value):
    return unicodedata.normalize("NFKC", value.strip())


def username_key(value):
    return normalize_username(value).casefold()


def normalize_email(value):
    return value.strip().casefold()


def username_in_use(value):
    key = username_key(value)
    return AccountIdentity.objects.filter(username_key=key).exists() or any(
        username_key(name) == key for name in User.objects.values_list("username", flat=True)
    )


def email_in_use(value):
    email = normalize_email(value)
    return AccountIdentity.objects.filter(email_key=email).exists() or any(
        normalize_email(address) == email for address in User.objects.values_list("email", flat=True)
    )


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, max_length=254)

    class Meta(UserCreationForm.Meta):
        fields = ["username", "first_name", "last_name", "email", "password1", "password2"]

    def clean_username(self):
        username = normalize_username(self.cleaned_data["username"])
        key = username_key(username)
        if len(key) > 150:
            raise ValidationError("Choose a shorter username.")
        if username_in_use(username):
            raise ValidationError("This username is already in use.")
        return username

    def clean_email(self):
        email = normalize_email(self.cleaned_data["email"])
        if len(email) > 254:
            raise ValidationError("Choose a shorter email address.")
        if email_in_use(email):
            raise ValidationError("This email address is already in use.")
        return email

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        if not password.strip():
            raise ValidationError("Your password cannot contain only spaces.")
        return password


class LoginForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Incorrect username or password.",
        "inactive": "Incorrect username or password.",
    }

    def clean_username(self):
        username = normalize_username(self.cleaned_data["username"])
        key = username_key(username)
        identity = AccountIdentity.objects.select_related("user").filter(username_key=key).first()
        if identity:
            return identity.user.username
        for name in User.objects.values_list("username", flat=True):
            if username_key(name) == key:
                return name
        return username


class SimpleDateWidget(forms.MultiWidget):
    """Ordinary day/month/year controls avoid browser calendar popup glitches."""

    def __init__(self, attrs=None):
        widgets = {
            "day": forms.NumberInput(attrs={"min": 1, "max": 31, "placeholder": "Day", "aria-label": "Day"}),
            "month": forms.Select(choices=[("", "Month")] + [(month, str(month)) for month in range(1, 13)], attrs={"aria-label": "Month"}),
            "year": forms.NumberInput(attrs={"min": 1, "max": 9999, "placeholder": "Year", "aria-label": "Year"}),
        }
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if isinstance(value, str):
            try:
                value = date.fromisoformat(value)
            except ValueError:
                return [None, None, value]
        return [value.day, value.month, value.year] if value else [None, None, None]

    def value_from_datadict(self, data, files, name):
        if not any(name + suffix in data for suffix in self.widgets_names) and data.get(name):
            return self.decompress(data[name])
        return super().value_from_datadict(data, files, name)


class SimpleDateField(forms.MultiValueField):
    widget = SimpleDateWidget

    def __init__(self, *args, **kwargs):
        fields = [
            forms.IntegerField(min_value=1, max_value=31),
            forms.IntegerField(min_value=1, max_value=12),
            forms.IntegerField(min_value=1, max_value=9999),
        ]
        kwargs.setdefault("error_messages", {"required": "Enter a complete date (day, month and year)."})
        super().__init__(fields=fields, *args, **kwargs)

    def compress(self, values):
        if not values:
            return None
        try:
            return date(values[2], values[1], values[0])
        except (ValueError, TypeError):
            raise ValidationError("Enter a valid date.")


class ExpenseForm(forms.ModelForm):
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2)
    date = SimpleDateField(help_text="Day / month / year. Future dates are not allowed.")
    submission_token = forms.CharField(required=False, max_length=512, widget=forms.HiddenInput)
    version = forms.IntegerField(required=False, min_value=0, widget=forms.HiddenInput)

    class Meta:
        model = Expense
        fields = ["category", "description", "amount", "date"]
        widgets = {"description": forms.TextInput(attrs={"placeholder": "What was the expense for?"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = [("", "Choose a category")] + Expense.CATEGORY_CHOICES
        if self.instance.pk:
            self.initial.setdefault("version", self.instance.version)
        else:
            self.initial.setdefault("date", timezone.localdate())

    def clean_date(self):
        expense_date = self.cleaned_data["date"]
        if expense_date > timezone.localdate():
            raise ValidationError("Expense date cannot be in the future.")
        return expense_date


class BudgetForm(forms.ModelForm):
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2)

    class Meta:
        model = MonthlyBudget
        fields = ["category", "amount"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = [("", "Choose a category")] + Expense.CATEGORY_CHOICES


class OverallBudgetForm(forms.ModelForm):
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2)

    class Meta:
        model = OverallBudget
        fields = ["period", "amount"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["period"].choices = [("", "Choose a period")] + OverallBudget.PERIOD_CHOICES


class ExpenseFilterForm(forms.Form):
    category = forms.ChoiceField(choices=[("", "All categories")] + Expense.CATEGORY_CHOICES, required=False)
    start_date = SimpleDateField(required=False)
    end_date = SimpleDateField(required=False)
    minimum_amount = forms.DecimalField(required=False, min_value=Decimal("0"), max_digits=10, decimal_places=2)
    maximum_amount = forms.DecimalField(required=False, min_value=Decimal("0"), max_digits=10, decimal_places=2)

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        minimum, maximum = cleaned.get("minimum_amount"), cleaned.get("maximum_amount")
        if start is not None and end is not None and start > end:
            self.add_error("end_date", "End date must be on or after start date.")
        if minimum is not None and maximum is not None and minimum > maximum:
            self.add_error("maximum_amount", "Maximum amount must be at least the minimum amount.")
        return cleaned
