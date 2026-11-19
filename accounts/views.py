from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy

from .forms import (
    PROFILE_FORMS, AccountForm, LoginForm, SellerProfileForm, SellerRegistrationForm,
    StaffCreationForm,
)
from .models import Seller
from .permissions import staff_required
from .security import Action, audit, client_ip, registration_rate_exceeded


class LoginView(auth_views.LoginView):
    """UC04-01. Django rotates the session id on login."""

    form_class = LoginForm
    redirect_authenticated_user = True


class PasswordChangeView(auth_views.PasswordChangeView):
    """UC01-02: changing the password requires the current one."""

    template_name = "form.html"
    extra_context = {"title": "Change password", "submit": "Change password"}
    success_url = reverse_lazy("accounts:profile")

    def form_valid(self, form):
        response = super().form_valid(form)  # keeps the user logged in
        audit(Action.PASSWORD_CHANGED, self.request)
        messages.success(self.request, "Password changed.")
        return response


def register(request):
    """Use case: Register user (sellers self-register; staff are created by staff)."""
    if request.user.is_authenticated:
        return redirect("catalog:goods_list")
    if request.method == "POST":
        if registration_rate_exceeded(client_ip(request)):
            messages.error(request, "Too many registrations from this network. Try again later.")
            return redirect("accounts:register")
        form = SellerRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            audit(Action.REGISTER, request, user=user)
            login(request, user)
            messages.success(request, "Welcome! Now register your booth.")
            return redirect("booths:register")
    else:
        form = SellerRegistrationForm()
    return render(request, "form.html", {"title": "Register as a seller", "form": form, "submit": "Register"})


@staff_required
def staff_create_account(request):
    """UC01-01 ext. b: never public, otherwise anyone could give themselves staff rights."""
    if request.method == "POST":
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            audit(Action.STAFF_CREATED, request, target=f"user:{user.pk}")
            messages.success(request, f"Staff account '{user.username}' created.")
            return redirect("accounts:staff_create")
    else:
        form = StaffCreationForm()
    return render(request, "form.html", {"title": "Create staff account", "form": form, "submit": "Create"})


@login_required
def profile_edit(request):
    """Use case: Edit user's information (own account only; id comes from the session)."""
    profile = request.user.profile
    if profile is None:
        messages.error(request, "This account has no seller or staff profile.")
        return redirect("catalog:goods_list")
    profile_form_class = PROFILE_FORMS[request.user.role]
    if request.method == "POST":
        account_form = AccountForm(request.POST, instance=request.user)
        profile_form = profile_form_class(request.POST, request.FILES, instance=profile)
        if account_form.is_valid() and profile_form.is_valid():
            with transaction.atomic():
                account_form.save()
                profile_form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    else:
        account_form = AccountForm(instance=request.user)
        profile_form = profile_form_class(instance=profile)
    return render(
        request, "accounts/profile.html",
        {"account_form": account_form, "profile_form": profile_form},
    )


@staff_required
def user_list(request):
    sellers = Seller.objects.select_related("user").order_by("seller_name")
    return render(request, "accounts/user_list.html", {"sellers": sellers})


@staff_required
def user_edit(request, pk):
    """Use case: Edit user's information (staff editing a seller)."""
    seller = get_object_or_404(Seller, pk=pk)
    if request.method == "POST":
        form = SellerProfileForm(request.POST, request.FILES, instance=seller)
        if form.is_valid():
            form.save()
            messages.success(request, "Seller updated.")
            return redirect("accounts:user_list")
    else:
        form = SellerProfileForm(instance=seller)
    return render(request, "form.html", {"title": f"Edit seller: {seller}", "form": form, "submit": "Save"})
