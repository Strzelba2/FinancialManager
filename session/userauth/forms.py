from django import forms
from django.contrib.auth import forms as admin_forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserChangeForm as BaseUserChangeForm
from django.contrib.admin.forms import AdminAuthenticationForm
from django_recaptcha.fields import ReCaptchaField

User = get_user_model()


class UserChangeForm(BaseUserChangeForm):
    """
    A custom form for updating user information.

    Inherits fields and behaviors from `BaseUserChangeForm`, but restricts the fields to
    those relevant for user updates, like first name, last name, username, and email.
    """
    class Meta(BaseUserChangeForm.Meta):
        model = User
        fields = ["first_name", "last_name", "username", "email"]


class UserCreationForm(admin_forms.UserCreationForm):
    """
    A custom form for creating new users, extending Django's built-in UserCreationForm.

    Additional validation checks are added for unique email and username constraints.
    """

    class Meta(admin_forms.UserCreationForm.Meta):
        model = User
        fields = ["first_name", "last_name", "username", "email"]

    error_messages = {
        "duplicate_username": "A user with that username already exists.",
        "duplicate_email": "A user with that email already exists.",
    }

    def clean_email(self) -> str:
        """
        Validates that the email is unique for new user creation.

        Checks if an email already exists in the database; raises a ValidationError
        if a duplicate email is found.

        Returns:
            str: The validated email.

        Raises:
            forms.ValidationError: If the email is already associated with another user.
        """
        email = self.cleaned_data["email"]
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(self.error_messages["duplicate_email"])
        return email

    def clean_username(self) -> str:
        """
        Validates that the username is unique for new user creation.

        Checks if a username already exists in the database; raises a ValidationError
        if a duplicate username is found.

        Returns:
            str: The validated username.

        Raises:
            forms.ValidationError: If the username is already associated with another user.
        """
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError(self.error_messages["duplicate_username"])
        return username
  
    
class CustomAdminAuthenticationForm(AdminAuthenticationForm):
    def __init__(self, *args, **kwargs):
        super(CustomAdminAuthenticationForm, self).__init__(*args, **kwargs)
        self.fields['captcha'] = ReCaptchaField()
