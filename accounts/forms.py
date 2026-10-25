from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import LoginEvent, User
from .security import get_client_ip, get_user_agent, is_locked_out

INPUT_CSS = (
    "w-full rounded-md border border-slate-300 px-3 py-2 "
    "focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
)


class StyledFormMixin:
    # klasy tailwinda dla pol
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", INPUT_CSS)


class RegisterForm(StyledFormMixin, UserCreationForm):
    wants_to_sell = forms.BooleanField(
        label="Chcę też sprzedawać (konto sprzedawcy)",
        required=False,
    )

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Konto z tym adresem e-mail już istnieje.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        # role ustawiamy tutaj, nie z formularza
        user.role = User.Role.SELLER if self.cleaned_data.get("wants_to_sell") else User.Role.CUSTOMER
        if commit:
            user.save()
        return user


class LoginForm(StyledFormMixin, AuthenticationForm):
    # blokada po za duzej liczbie nieudanych prob (login+ip albo samo ip)
    error_messages = {
        **AuthenticationForm.error_messages,
        "locked": "Zbyt wiele nieudanych prób logowania. Spróbuj ponownie za 15 minut.",
    }

    def clean(self):
        username = self.cleaned_data.get("username", "")
        ip = get_client_ip(self.request)
        if username and is_locked_out(username, ip):
            LoginEvent.objects.create(
                username=username[:150],
                kind=LoginEvent.Kind.LOCKED,
                ip_address=ip,
                user_agent=get_user_agent(self.request),
            )
            raise forms.ValidationError(self.error_messages["locked"], code="locked")
        return super().clean()


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ten adres e-mail jest już zajęty.")
        return email
