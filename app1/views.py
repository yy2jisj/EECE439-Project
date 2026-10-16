from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .context_processors import get_selected_currency
from .forms import ExpenseFilterForm, ExpenseForm, LoginForm, RegistrationForm
from .models import Expense


def safe_next_url(request, candidate):
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return None


def selected_expenses(request):
    # Every page starts from the signed-in user's rows and one currency.
    return Expense.objects.filter(owner=request.user, currency=get_selected_currency(request))


def expense_total(expenses):
    return expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        auth_login(request, user)
        messages.success(request, "Your PocketManager account is ready.")
        return redirect("dashboard")
    return render(request, "register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login(request):
    next_url = request.POST.get("next") or request.GET.get("next", "")
    next_url = safe_next_url(request, next_url) or ""
    if request.user.is_authenticated:
        return redirect(next_url or "dashboard")
    form = LoginForm(request, data=request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        auth_login(request, form.get_user())
        messages.success(request, "Welcome back to PocketManager.")
        return redirect(next_url or "dashboard")
    return render(request, "login.html", {"form": form, "next": next_url})


@login_required
@require_POST
def logout(request):
    auth_logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("login")


@login_required
@require_GET
def profile(request):
    return render(request, "profile.html")


@login_required
@require_POST
def switch_currency(request):
    currency = request.POST.get("currency")
    if currency in Expense.Currency.values:
        request.session["selected_currency"] = currency
    else:
        messages.error(request, "Choose USD or LBP.")
    next_url = safe_next_url(request, request.POST.get("next"))
    return redirect(next_url or "dashboard")


@login_required
@require_GET
def dashboard(request):
    today = timezone.localdate()
    current_month = today.replace(day=1)
    if today.month == 12:
        next_month = date(today.year + 1, 1, 1)
    else:
        next_month = date(today.year, today.month + 1, 1)

    expenses = selected_expenses(request)
    month_expenses = expenses.filter(date__gte=current_month, date__lt=next_month)
    monthly_total = expense_total(month_expenses)
    category_rows = month_expenses.values("category").annotate(total=Sum("amount"))
    totals_by_category = {row["category"]: row["total"] for row in category_rows}
    category_totals = []
    for category, name in Expense.Category.choices:
        total = totals_by_category.get(category, Decimal("0.00"))
        percent = total * 100 / monthly_total if monthly_total else Decimal("0.00")
        category_totals.append({"name": name, "total": total, "percent": percent})

    monthly_summary = list(
        expenses.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-month")
    )
    if not any(row["month"] == current_month for row in monthly_summary):
        monthly_summary.append({"month": current_month, "total": Decimal("0.00"), "count": 0})
        monthly_summary.sort(key=lambda row: row["month"], reverse=True)

    context = {
        "current_month": current_month,
        "monthly_total": monthly_total,
        "expense_count": month_expenses.count(),
        "category_totals": category_totals,
        "recent_expenses": expenses[:5],
        "monthly_summary": monthly_summary,
    }
    return render(request, "dashboard.html", context)


@login_required
@require_GET
def expense_list(request):
    form = ExpenseFilterForm(request.GET)
    expenses = selected_expenses(request)
    if form.is_valid():
        filters = form.cleaned_data
        if filters.get("category"):
            expenses = expenses.filter(category=filters["category"])
        if filters.get("start_date"):
            expenses = expenses.filter(date__gte=filters["start_date"])
        if filters.get("end_date"):
            expenses = expenses.filter(date__lte=filters["end_date"])
        if filters.get("min_amount") is not None:
            expenses = expenses.filter(amount__gte=filters["min_amount"])
        if filters.get("max_amount") is not None:
            expenses = expenses.filter(amount__lte=filters["max_amount"])
    else:
        # Invalid filters show their errors instead of silently broadening the history.
        expenses = expenses.none()
    return render(
        request,
        "expense_list.html",
        {"expenses": expenses, "filter_form": form, "filtered_total": expense_total(expenses)},
    )


@login_required
@require_http_methods(["GET", "POST"])
def expense_add(request):
    form = ExpenseForm(
        request.POST if request.method == "POST" else None,
        initial={"currency": get_selected_currency(request)},
    )
    if request.method == "POST" and form.is_valid():
        expense = form.save(commit=False)
        expense.owner = request.user
        expense.save()
        request.session["selected_currency"] = expense.currency
        messages.success(request, "Expense added.")
        return redirect("expense_list")
    return render(
        request,
        "expense_form.html",
        {"form": form, "is_edit": False, "heading": "Add an expense", "button_label": "Save expense"},
    )


@login_required
@require_http_methods(["GET", "POST"])
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk, owner=request.user)
    form = ExpenseForm(request.POST if request.method == "POST" else None, instance=expense)
    if request.method == "POST" and form.is_valid():
        expense = form.save()
        request.session["selected_currency"] = expense.currency
        messages.success(request, "Expense updated.")
        return redirect("expense_list")
    return render(
        request,
        "expense_form.html",
        {"form": form, "expense": expense, "is_edit": True, "heading": "Edit expense", "button_label": "Save changes"},
    )


@login_required
@require_http_methods(["GET", "POST"])
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk, owner=request.user)
    if request.method == "POST":
        expense.delete()
        messages.success(request, "Expense deleted.")
        return redirect("expense_list")
    return render(request, "expense_confirm_delete.html", {"expense": expense})
