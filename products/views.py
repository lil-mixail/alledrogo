from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg, Count, ProtectedError, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from accounts.permissions import seller_required

from .forms import MAX_IMAGES_PER_PRODUCT, CommentForm, MessageForm, ProductForm, ProductImageForm
from .models import Comment, Conversation, Message, Product, ProductImage
from .purchases import has_bought

PER_PAGE = 12


def _can_manage(user, product):
    return user.is_authenticated and (product.seller_id == user.pk or user.is_admin_role)


def _get_managed_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if not _can_manage(request.user, product):
        raise PermissionDenied
    return product


# --- produkty ---

@require_http_methods(["GET"])
def product_list(request):
    q = request.GET.get("q", "").strip()[:100]
    products = Product.objects.filter(is_active=True).select_related("seller").prefetch_related("images")
    if q:
        products = products.filter(Q(title__icontains=q) | Q(description__icontains=q))
    page = Paginator(products, PER_PAGE).get_page(request.GET.get("page"))
    return render(request, "products/product_list.html", {"page": page, "q": q})


@require_http_methods(["GET"])
def product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related("seller"), pk=pk)
    if not product.is_active and not _can_manage(request.user, product):
        raise Http404
    comments = product.comments.select_related("author")
    user = request.user
    my_comment = comments.filter(author=user).first() if user.is_authenticated else None
    can_comment = (
        user.is_authenticated and my_comment is None
        and product.seller_id != user.pk and has_bought(user, product)
    )
    return render(request, "products/product_detail.html", {
        "product": product,
        "images": product.images.all(),
        "comments": comments,
        "stats": comments.aggregate(avg=Avg("rating"), count=Count("id")),
        "my_comment": my_comment,
        "comment_form": CommentForm() if can_comment else None,
        "can_manage": _can_manage(user, product),
    })


@seller_required
@require_http_methods(["GET"])
def my_products(request):
    products = Product.objects.filter(seller=request.user)
    return render(request, "products/my_products.html", {"products": products})


@seller_required
@require_http_methods(["GET", "POST"])
def product_create(request):
    form = ProductForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        product = form.save(commit=False)
        product.seller = request.user  # sprzedawca z sesji, nie z formularza
        product.save()
        messages.success(request, "Produkt dodany. Teraz dodaj zdjęcia.")
        return redirect("products:edit", pk=product.pk)
    return render(request, "products/product_form.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def product_edit(request, pk):
    product = _get_managed_product(request, pk)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Zmiany zapisane.")
        return redirect(product)
    return render(request, "products/product_form.html", {
        "form": form,
        "product": product,
        "images": product.images.all(),
        "image_form": ProductImageForm(),
        "max_images": MAX_IMAGES_PER_PRODUCT,
    })


@login_required
@require_POST
def product_delete(request, pk):
    product = _get_managed_product(request, pk)
    try:
        product.delete()
        messages.success(request, "Produkt usunięty.")
    except ProtectedError:
        # produkt jest w zamowieniach - nie kasujemy historii, tylko ukrywamy
        product.is_active = False
        product.save(update_fields=["is_active", "updated_at"])
        messages.info(request, "Produkt ma zamówienia, więc został tylko ukryty.")
    return redirect("products:mine")


# --- zdjecia ---

@login_required
@require_POST
def image_add(request, pk):
    product = _get_managed_product(request, pk)
    if product.images.count() >= MAX_IMAGES_PER_PRODUCT:
        messages.error(request, f"Produkt może mieć maksymalnie {MAX_IMAGES_PER_PRODUCT} zdjęć.")
        return redirect("products:edit", pk=product.pk)
    form = ProductImageForm(request.POST, request.FILES)
    if form.is_valid():
        image = form.save(commit=False)
        image.product = product
        image.save()
        messages.success(request, "Zdjęcie dodane.")
    else:
        for error in form.errors.get("image", []):
            messages.error(request, error)
    return redirect("products:edit", pk=product.pk)


@login_required
@require_POST
def image_delete(request, pk):
    image = get_object_or_404(ProductImage.objects.select_related("product"), pk=pk)
    if not _can_manage(request.user, image.product):
        raise PermissionDenied
    image.delete()
    messages.success(request, "Zdjęcie usunięte.")
    return redirect("products:edit", pk=image.product_id)


# --- opinie ---

@login_required
@require_POST
def comment_add(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    # sprawdzamy na serwerze, nie tylko chowamy formularz w szablonie
    if product.seller_id == request.user.pk or not has_bought(request.user, product):
        raise PermissionDenied
    if Comment.objects.filter(product=product, author=request.user).exists():
        messages.error(request, "Ten produkt ma już Twoją opinię.")
        return redirect(product)
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.product = product
        comment.author = request.user
        comment.save()
        messages.success(request, "Dziękujemy za opinię!")
    else:
        messages.error(request, "Opinia nie została zapisana – sprawdź ocenę i treść.")
    return redirect(product)


@login_required
@require_POST
def comment_delete(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    if comment.author_id != request.user.pk and not request.user.is_moderator:
        raise PermissionDenied
    comment.delete()
    messages.success(request, "Opinia usunięta.")
    return redirect("products:detail", pk=comment.product_id)


# --- czat ---

def _get_conversation(request, pk):
    conversation = get_object_or_404(
        Conversation.objects.select_related("product", "buyer", "seller"), pk=pk
    )
    # obcy dostaje 404, zeby nie zdradzac, ze rozmowa istnieje
    if not conversation.has_participant(request.user):
        raise Http404
    return conversation


def _recent_messages(conversation, limit=100):
    recent = conversation.messages.select_related("sender").order_by("-created_at")[:limit]
    return list(reversed(recent))


@login_required
@require_POST
def conversation_start(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    if product.seller_id == request.user.pk:
        messages.error(request, "To Twój produkt – nie można pisać do siebie.")
        return redirect(product)
    conversation, _ = Conversation.objects.get_or_create(
        product=product, buyer=request.user, defaults={"seller": product.seller}
    )
    return redirect("products:conversation", pk=conversation.pk)


@login_required
@require_http_methods(["GET"])
def conversation_list(request):
    conversations = Conversation.objects.filter(
        Q(buyer=request.user) | Q(seller=request.user)
    ).select_related("product", "buyer", "seller")
    return render(request, "products/conversation_list.html", {"conversations": conversations})


@login_required
@require_http_methods(["GET", "POST"])
def conversation_detail(request, pk):
    conversation = _get_conversation(request, pk)
    form = MessageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        Message.objects.create(conversation=conversation, sender=request.user, body=form.cleaned_data["body"])
        conversation.save(update_fields=["updated_at"])
        return redirect("products:conversation", pk=conversation.pk)
    return render(request, "products/conversation_detail.html", {
        "conversation": conversation,
        "other": conversation.other_party(request.user),
        "chat_messages": _recent_messages(conversation),
        "form": form,
    })


@login_required
@require_http_methods(["GET"])
def conversation_messages(request, pk):
    # fragment HTML pobierany co kilka sekund przez chat.js
    conversation = _get_conversation(request, pk)
    return render(request, "products/_chat_messages.html", {"chat_messages": _recent_messages(conversation)})

