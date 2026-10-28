import io
import tempfile

from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from accounts.models import User
from products.models import Product, Conversation, Message, ProductImage

P = "Bardzo-Dobre-Haslo-123"

def png():
    b = io.BytesIO(); Image.new("RGB", (10, 10), "red").save(b, "PNG"); return b.getvalue()

@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProductSecurityTests(TestCase):
    def setUp(self):
        self.s = User.objects.create_user("s", "s@e.com", P, role="seller")
        self.s2 = User.objects.create_user("s2", "s2@e.com", P, role="seller")
        self.c = User.objects.create_user("c", "c@e.com", P)
        self.x = User.objects.create_user("x", "x@e.com", P)
        self.p = Product.objects.create(seller=self.s, title="<script>alert(1)</script>", description="d", price=10)

    def test_customer_cannot_create(self):
        self.client.force_login(self.c)
        self.assertEqual(self.client.post(reverse("products:create"), {}).status_code, 403)

    def test_other_seller_cannot_edit_delete(self):
        self.client.force_login(self.s2)
        self.assertEqual(self.client.get(reverse("products:edit", args=[self.p.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("products:delete", args=[self.p.pk])).status_code, 403)
        self.assertTrue(Product.objects.filter(pk=self.p.pk).exists())

    def test_delete_get_not_allowed(self):
        self.client.force_login(self.s)
        self.assertEqual(self.client.get(reverse("products:delete", args=[self.p.pk])).status_code, 405)

    def test_xss_escaped(self):
        html = self.client.get(reverse("products:detail", args=[self.p.pk])).content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_upload_valid_and_fake(self):
        self.client.force_login(self.s)
        url = reverse("products:image_add", args=[self.p.pk])
        self.client.post(url, {"image": SimpleUploadedFile("a.png", png(), "image/png")})
        self.assertEqual(ProductImage.objects.count(), 1)
        self.client.post(url, {"image": SimpleUploadedFile("b.png", b"<?php echo 1; ?>", "image/png")})
        self.client.post(url, {"image": SimpleUploadedFile("c.svg", b"<svg onload=alert(1)>", "image/svg+xml")})
        self.assertEqual(ProductImage.objects.count(), 1)
        name = ProductImage.objects.first().image.name
        self.assertNotIn("a.png", name)

    def test_other_seller_cannot_upload(self):
        self.client.force_login(self.s2)
        r = self.client.post(reverse("products:image_add", args=[self.p.pk]), {"image": SimpleUploadedFile("a.png", png(), "image/png")})
        self.assertEqual(r.status_code, 403)

    def test_comment_without_purchase(self):
        self.client.force_login(self.c)
        r = self.client.post(reverse("products:comment_add", args=[self.p.pk]), {"rating": 5, "body": "ok"})
        self.assertEqual(r.status_code, 403)

    def test_chat_outsider_404(self):
        conv = Conversation.objects.create(product=self.p, buyer=self.c, seller=self.s)
        Message.objects.create(conversation=conv, sender=self.c, body="tajne")
        self.client.force_login(self.x)
        self.assertEqual(self.client.get(reverse("products:conversation", args=[conv.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("products:conversation_messages", args=[conv.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("products:conversation", args=[conv.pk]), {"body": "hej"}).status_code, 404)
        self.client.force_login(self.s)
        self.assertIn("tajne", self.client.get(reverse("products:conversation_messages", args=[conv.pk])).content.decode())

    def test_hidden_product_404(self):
        self.p.is_active = False; self.p.save()
        self.assertEqual(self.client.get(reverse("products:detail", args=[self.p.pk])).status_code, 404)

    def test_pages_render(self):
        self.client.force_login(self.s)
        for u in [reverse("products:list"), reverse("products:mine"), reverse("products:create"), reverse("products:conversations"), reverse("products:edit", args=[self.p.pk])]:
            self.assertEqual(self.client.get(u).status_code, 200, u)
