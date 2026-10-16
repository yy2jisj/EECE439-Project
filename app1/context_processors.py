from .models import Expense


def get_selected_currency(request):
    currency = request.session.get("selected_currency", Expense.Currency.USD)
    if currency not in Expense.Currency.values:
        return Expense.Currency.USD
    return currency


def pocketmanager(request):
    return {
        "app_name": "PocketManager",
        "selected_currency": get_selected_currency(request),
        "currency_choices": Expense.Currency.choices,
    }
