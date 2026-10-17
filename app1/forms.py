from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Expense


class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "password1", "password2"]


class ExpenseForm(forms.ModelForm):
    amount = forms.DecimalField(min_value=0.01, max_digits=10, decimal_places=2)

    class Meta:
        model = Expense
        fields = ["description", "amount", "category", "date"]
        widgets = {
            "date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }


class ExpenseFilterForm(forms.Form):
    category = forms.ChoiceField(
        choices=[("", "All categories")] + Expense.CATEGORY_CHOICES,
        required=False,
    )
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    minimum_amount = forms.DecimalField(required=False, min_value=0)
    maximum_amount = forms.DecimalField(required=False, min_value=0)
