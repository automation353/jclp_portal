from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

User = get_user_model()


class StyledAuthenticationForm(AuthenticationForm):
    """Same Django auth logic, just with our own field widgets/classes."""

    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "field-input",
                "placeholder": "Username",
                "autofocus": True,
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "field-input", "placeholder": "Password"}
        )
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "That username and password don't match a JCPL account.",
        "inactive": "This account has been disabled. Contact your Super Admin.",
    }


class AdminAccountForm(forms.ModelForm):
    """Used by a Super Admin to create or edit an Admin / Super Admin account."""

    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"class": "field-input", "placeholder": "Leave blank to keep current password"}),
        help_text=(
            "Required when creating a new account. Passwords are stored as a "
            "one-way hash, so an existing one can never be displayed here — "
            "leave this blank to keep it unchanged, or type a new one (use "
            "the Show button to check it before saving)."
        ),
    )

    class Meta:
        model = User
        # NOTE: "password" is deliberately NOT listed here even though it's a
        # real model field. ModelForm.save(commit=False) copies every listed
        # field straight onto the instance via construct_instance() *before*
        # our save() override runs — for "password" that means the plaintext
        # (or, when the field is left blank on edit, an empty string) would
        # clobber the real hash. "password" stays a declared form field below
        # and is applied by hand in save() instead, only when non-blank.
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "department",
            "role",
        ]
        widgets = {
            "username": forms.TextInput(attrs={"class": "field-input"}),
            "first_name": forms.TextInput(attrs={"class": "field-input"}),
            "last_name": forms.TextInput(attrs={"class": "field-input"}),
            "email": forms.EmailInput(attrs={"class": "field-input"}),
            "department": forms.Select(attrs={"class": "field-input"}),
            "role": forms.Select(attrs={"class": "field-input"}),
        }

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if not self.instance.pk and not password:
            raise forms.ValidationError("A password is required for a new account.")
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user
