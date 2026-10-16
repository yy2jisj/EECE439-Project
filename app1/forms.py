from decimal import Decimal

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Expense


def describe_form_fields(form):
    # Connect each input to the help and error text rendered by the shared partial.
    for name, field in form.fields.items():
        description_ids = []
        if field.help_text:
            description_ids.append(f"id_{name}_help")
        if form.is_bound and name in form.errors:
            description_ids.append(f"id_{name}_errors")
            field.widget.attrs["aria-invalid"] = "true"
        if description_ids:
            field.widget.attrs["aria-describedby"] = " ".join(description_ids)


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=False, help_text="Optional. Used only on your profile.")

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs["autocomplete"] = "username"
        self.fields["first_name"].widget.attrs["autocomplete"] = "given-name"
        self.fields["last_name"].widget.attrs["autocomplete"] = "family-name"
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        describe_form_fields(self)


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        describe_form_fields(self)


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["description", "amount", "category", "currency", "date"]
        widgets = {
            "description": forms.TextInput(attrs={"placeholder": "e.g. Lunch or a ride"}),
            "amount": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
            "date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }
        help_texts = {
            "amount": "Enter a positive amount with up to two decimal places.",
            "currency": "USD and LBP are tracked separately. No currency conversion is applied.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        describe_form_fields(self)


class ExpenseFilterForm(forms.Form):
    category = forms.ChoiceField(
        required=False, choices=[("", "All categories"), *Expense.Category.choices]
    )
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    min_amount = forms.DecimalField(
        required=False,
        min_value=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
    )
    max_amount = forms.DecimalField(
        required=False,
        min_value=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        describe_form_fields(self)

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and start_date > end_date:
            self.add_error("end_date", "End date must be on or after the start date.")

        min_amount = cleaned_data.get("min_amount")
        max_amount = cleaned_data.get("max_amount")
        if min_amount is not None and max_amount is not None and min_amount > max_amount:
            self.add_error("max_amount", "Maximum amount must be at least the minimum amount.")
        return cleaned_data
