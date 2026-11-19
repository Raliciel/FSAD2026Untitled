from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db import transaction

from .models import Seller, Staff, User
from .security import Action, audit, client_ip, is_locked_out


class LoginForm(AuthenticationForm):
    """UC04-01. Wrong username and wrong password share Django's generic error message."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "locked_out": "Too many failed attempts. Please try again in a few minutes.",
    }

    def clean(self):
        username = self.cleaned_data.get("username", "")
        # Checked before authenticate() so a correct password cannot bypass the lock.
        if is_locked_out(username, client_ip(self.request)):
            audit(Action.LOGIN_LOCKED, self.request, username=username)
            raise forms.ValidationError(self.error_messages["locked_out"], code="locked_out")
        return super().clean()


class SellerRegistrationForm(UserCreationForm):
    seller_name = forms.CharField(max_length=100)
    seller_profile_picture = forms.ImageField(required=False)

    class Meta:
        model = User
        fields = ("username", "email")

    def clean_seller_profile_picture(self):
        picture = self.cleaned_data.get("seller_profile_picture")
        if picture:
            Seller._meta.get_field("seller_profile_picture").run_validators(picture)
        return picture

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.SELLER  # role is decided by the server, never by the form
        if commit:
            with transaction.atomic():
                user.save()
                Seller.objects.create(
                    user=user,
                    seller_name=self.cleaned_data["seller_name"],
                    seller_profile_picture=self.cleaned_data.get("seller_profile_picture") or "",
                )
        return user


class StaffCreationForm(UserCreationForm):
    """UC01-01 ext. b: only reachable by logged-in staff (see views.staff_create_account)."""

    staff_name = forms.CharField(max_length=100)

    class Meta:
        model = User
        fields = ("username", "email")

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.STAFF
        user.save()
        Staff.objects.create(user=user, staff_name=self.cleaned_data["staff_name"])
        return user


class AccountForm(forms.ModelForm):
    """UC01-02: the login name itself (profile details live on Seller/Staff)."""

    class Meta:
        model = User
        fields = ("username", "email")


class SellerProfileForm(forms.ModelForm):
    class Meta:
        model = Seller
        fields = ("seller_name", "seller_profile_picture")


class StaffProfileForm(forms.ModelForm):
    class Meta:
        model = Staff
        fields = ("staff_name", "staff_profile_picture")


PROFILE_FORMS = {"seller": SellerProfileForm, "staff": StaffProfileForm}
