from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

from accounts.forms import StyledFormMixin

from .models import Comment, Product, ProductImage

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_IMAGES_PER_PRODUCT = 8
ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def validate_image(file):
    if file.size > MAX_IMAGE_SIZE:
        raise ValidationError("Zdjęcie może mieć maksymalnie 5 MB.")
    # ImageField juz otworzyl plik Pillowem; sprawdzamy prawdziwy format, nie rozszerzenie
    fmt = getattr(getattr(file, "image", None), "format", None)
    if fmt not in ALLOWED_FORMATS:
        raise ValidationError("Dozwolone formaty: JPG, PNG, WEBP.")


class ProductForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = ("title", "description", "price", "shipping_cost", "stock", "is_active")
        widgets = {"description": forms.Textarea(attrs={"rows": 6})}


class ProductImageForm(StyledFormMixin, forms.ModelForm):
    image = forms.ImageField(
        label="Zdjęcie",
        validators=[FileExtensionValidator(ALLOWED_EXTENSIONS), validate_image],
    )

    class Meta:
        model = ProductImage
        fields = ("image",)


class CommentForm(StyledFormMixin, forms.ModelForm):
    rating = forms.TypedChoiceField(
        label="Ocena", choices=[(i, f"{i} / 5") for i in range(5, 0, -1)], coerce=int
    )

    class Meta:
        model = Comment
        fields = ("rating", "body")
        labels = {"body": "Twoja opinia"}
        widgets = {"body": forms. Textarea(attrs={"rows": 4})}


class MessageForm(StyledFormMixin, forms.Form):
    body = forms.CharField(
        label="", max_length=2000,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Napisz wiadomość..."}),
    )

