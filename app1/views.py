from decimal import Decimal

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ExpenseFilterForm, ExpenseForm, RegisterForm
from .models import Expense


def register(request):
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("dashboard")
    return render(request, "register.html", {"form": form})


def login_user(request):
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect("dashboard")
    return render(request, "login.html", {"form": form})


@login_required
def logout_user(request):
    if request.method == "POST":
        logout(request)
        return redirect("login")
    return redirect("dashboard")


@login_required
def profile(request):
    return render(request, "profile.html")


@login_required
def dashboard(request):
    expenses = Expense.objects.filter(user=request.user)
    today = timezone.localdate()
    this_month = expenses.filter(date__year=today.year, date__month=today.month)

    total_spending = this_month.aggregate(Sum("amount"))["amount__sum"] or Decimal("0")

    spending_by_category = []
    for category, name in Expense.CATEGORY_CHOICES:
        total = this_month.filter(category=category).aggregate(Sum("amount"))["amount__sum"]
        spending_by_category.append({"name": name, "total": total or Decimal("0")})

    monthly_summary = (
        expenses.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-month")
    )

    return render(
        request,
        "dashboard.html",
        {
            "total_spending": total_spending,
            "spending_by_category": spending_by_category,
            "recent_expenses": expenses[:5],
            "monthly_summary": monthly_summary,
        },
    )


@login_required
def expense_history(request):
    expenses = Expense.objects.filter(user=request.user)
    form = ExpenseFilterForm(request.GET or None)

    if form.is_valid():
        category = form.cleaned_data.get("category")
        start_date = form.cleaned_data.get("start_date")
        end_date = form.cleaned_data.get("end_date")
        minimum_amount = form.cleaned_data.get("minimum_amount")
        maximum_amount = form.cleaned_data.get("maximum_amount")

        if category:
            expenses = expenses.filter(category=category)
        if start_date:
            expenses = expenses.filter(date__gte=start_date)
        if end_date:
            expenses = expenses.filter(date__lte=end_date)
        if minimum_amount is not None:
            expenses = expenses.filter(amount__gte=minimum_amount)
        if maximum_amount is not None:
            expenses = expenses.filter(amount__lte=maximum_amount)

    return render(request, "expense_history.html", {"expenses": expenses, "form": form})


@login_required
def add_expense(request):
    form = ExpenseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        expense = form.save(commit=False)
        expense.user = request.user
        expense.save()
        return redirect("expense_history")
    return render(request, "expense_form.html", {"form": form, "title": "Add Expense"})


@login_required
def edit_expense(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, user=request.user)
    form = ExpenseForm(request.POST or None, instance=expense)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("expense_history")
    return render(request, "expense_form.html", {"form": form, "title": "Edit Expense"})


@login_required
def delete_expense(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, user=request.user)
    if request.method == "POST":
        expense.delete()
        return redirect("expense_history")
    return render(request, "expense_confirm_delete.html", {"expense": expense})
