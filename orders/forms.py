import re

from django import forms

from accounts.forms import StyledFormMixin

from .models import Order

# pola wymagane zależnie od sposobu dostawy
REQUIRED_BY_METHOD = {
    Order.Delivery.INPOST: ("parcel_locker",),
    Order.Delivery.COURIER: ("street", "postal_code", "city"),
}


class DeliveryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Order
        fields = ("delivery_method", "full_name", "phone", "parcel_locker", "street", "postal_code", "city")
        widgets = {
            "delivery_method": forms.RadioSelect(attrs={"class": "accent-orange-600"}),
            "phone": forms.TextInput(attrs={"placeholder": "np. 600 123 456", "autocomplete": "tel"}),
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "parcel_locker": forms.TextInput(attrs={"placeholder": "np. KRA01M"}),
            "postal_code": forms.TextInput(attrs={"placeholder": "00-000", "autocomplete": "postal-code"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["delivery_method"].required = True
        self.fields["delivery_method"].choices = Order.Delivery.choices  # bez pustej opcji "---------"
        self.fields["full_name"].required = True
        self.fields["phone"].required = True

    def clean_phone(self):
        digits = re.sub(r"[\s-]", "", self.cleaned_data["phone"])
        if digits.startswith("+48"):
            digits = digits[3:]
        if not re.fullmatch(r"\d{9}", digits):
            raise forms.ValidationError("Podaj 9-cyfrowy numer telefonu.")
        return digits

    def clean_parcel_locker(self):
        code = self.cleaned_data["parcel_locker"].strip().upper()
        if code and not re.fullmatch(r"[A-Z0-9]{4,12}", code):
            raise forms.ValidationError("Nieprawidłowy kod paczkomatu (np. KRA01M).")
        return code

    def clean_postal_code(self):
        code = self.cleaned_data["postal_code"].strip()
        if code and not re.fullmatch(r"\d{2}-\d{3}", code):
            raise forms.ValidationError("Kod pocztowy w formacie 00-000.")
        return code

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("delivery_method")
        for name in REQUIRED_BY_METHOD.get(method, ()):
            if not cleaned.get(name) and name not in self.errors:
                self.add_error(name, "To pole jest wymagane.")
        # czyścimy dane drugiego sposobu dostawy, żeby nie zapisać śmieci
        for other, names in REQUIRED_BY_METHOD.items():
            if other != method:
                for name in names:
                    cleaned[name] = ""
                    self.errors.pop(name, None)
        return cleaned
