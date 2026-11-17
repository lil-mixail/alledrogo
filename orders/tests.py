from datetime import timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from products.models import Product

from . import payments
from .models import Order
from .services import cancel_expired_orders
from .shipping import shipping_total

P = "Bardzo-Dobre-Haslo-123"


class DeliveryCheckoutTests(TestCase):
    def setUp(self):
        self.s = User.objects.create_user("s", "s@e.com", P, role="seller")
        self.c = User.objects.create_user("c", "c@e.com", P)
        self.p = Product.objects.create(seller=self.s, title="Kubek", description="d", price=10, stock=5)
        self.client.force_login(self.c)
        self.client.post(reverse("orders:cart_add", args=[self.p.pk]), {"quantity": 2})

    def checkout(self, **data):
        return self.client.post(reverse("orders:checkout"), data)

    def test_inpost_order_saved_and_shown(self):
        r = self.checkout(delivery_method="inpost", full_name="Jan Kowalski", phone="+48 600-123-456",
                          parcel_locker="kra01m", street="ignorowana 1")
        order = Order.objects.get()
        self.assertRedirects(r, reverse("orders:detail", args=[order.pk]))
        self.assertEqual((order.phone, order.parcel_locker, order.street), ("600123456", "KRA01M", ""))
        self.client.get(reverse("orders:detail", args=[order.pk]))  # zjada komunikat
        page = self.client.get(reverse("orders:detail", args=[order.pk]))
        self.assertContains(page, "Paczkomat InPost")
        self.assertContains(page, "KRA01M")
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 3)

    def test_courier_order_saved(self):
        self.checkout(delivery_method="courier", full_name="Jan Kowalski", phone="600123456",
                      street="Długa 5/3", postal_code="30-001", city="Kraków", parcel_locker="XX")
        order = Order.objects.get()
        self.assertEqual((order.city, order.postal_code, order.parcel_locker), ("Kraków", "30-001", ""))
        self.assertContains(self.client.get(reverse("orders:detail", args=[order.pk])), "Długa 5/3, 30-001 Kraków")

    def test_missing_fields_reject_order(self):
        r = self.checkout(delivery_method="courier", full_name="Jan", phone="123", postal_code="30001")
        self.assertEqual(r.status_code, 400)
        form = r.context["delivery_form"]
        self.assertEqual(set(form.errors), {"phone", "street", "postal_code", "city"})
        self.assertFalse(Order.objects.exists())
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 5)

    def test_inpost_requires_locker(self):
        r = self.checkout(delivery_method="inpost", full_name="Jan", phone="600123456")
        self.assertIn("parcel_locker", r.context["delivery_form"].errors)
        self.assertFalse(Order.objects.exists())


class SellerPanelTests(TestCase):
    def setUp(self):
        self.s = User.objects.create_user("s", "s@e.com", P, role="seller")
        self.s2 = User.objects.create_user("s2", "s2@e.com", P, role="seller")
        self.c = User.objects.create_user("c", "c@e.com", P)
        self.p = Product.objects.create(seller=self.s, title="Kubek", description="d", price=10, stock=5)
        self.p2 = Product.objects.create(seller=self.s2, title="Talerz", description="d", price=20, stock=5)
        self.order = Order.objects.create(
            buyer=self.c, status=Order.Status.PAID, delivery_method="courier", full_name="Jan Kowalski",
            phone="600123456", street="Długa 5/3", postal_code="30-001", city="Kraków",
        )
        for p in (self.p, self.p2):
            self.order.items.create(product=p, seller=p.seller, title=p.title, unit_price=p.price, quantity=1)

    def test_checkout_copies_seller(self):
        self.client.force_login(self.c)
        self.client.post(reverse("orders:cart_add", args=[self.p.pk]), {"quantity": 1})
        self.client.post(reverse("orders:checkout"), {
            "delivery_method": "inpost", "full_name": "Jan", "phone": "600123456", "parcel_locker": "KRA01M",
        })
        self.assertEqual(Order.objects.latest("pk").items.get().seller, self.s)

    def test_seller_sees_only_own_items_and_address(self):
        self.client.force_login(self.s)
        r = self.client.get(reverse("orders:seller_orders"))
        self.assertContains(r, "Długa 5/3, 30-001 Kraków")
        self.assertContains(r, "Kubek")
        self.assertNotContains(r, "Talerz")
        self.assertContains(r, "Oznacz jako wysłane")

    def test_unpaid_orders_hidden(self):
        self.order.status = Order.Status.NEW
        self.order.save()
        self.client.force_login(self.s)
        self.assertNotContains(self.client.get(reverse("orders:seller_orders")), "Długa 5/3")

    def test_mark_shipped_only_own_items(self):
        self.client.force_login(self.s)
        r = self.client.post(reverse("orders:seller_mark_shipped", args=[self.order.pk]))
        self.assertRedirects(r, reverse("orders:seller_orders"))
        shipped = {i.title: i.shipped_at is not None for i in self.order.items.all()}
        self.assertEqual(shipped, {"Kubek": True, "Talerz": False})
        self.assertNotContains(self.client.get(reverse("orders:seller_orders")), "Oznacz jako wysłane")

    def test_permissions(self):
        self.client.force_login(self.c)
        self.assertEqual(self.client.get(reverse("orders:seller_orders")).status_code, 403)
        self.assertEqual(self.client.post(reverse("orders:seller_mark_shipped", args=[self.order.pk])).status_code, 403)
        other = User.objects.create_user("s3", "s3@e.com", P, role="seller")
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse("orders:seller_mark_shipped", args=[self.order.pk])).status_code, 404)
        self.client.force_login(self.s)
        self.assertEqual(self.client.get(reverse("orders:seller_mark_shipped", args=[self.order.pk])).status_code, 405)


class ShippingCostTests(TestCase):
    def setUp(self):
        self.s = User.objects.create_user("s", "s@e.com", P, role="seller")
        self.s2 = User.objects.create_user("s2", "s2@e.com", P, role="seller")
        self.c = User.objects.create_user("c", "c@e.com", P)
        mk = lambda seller, title, ship: Product.objects.create(
            seller=seller, title=title, description="d", price=10, stock=5, shipping_cost=Decimal(ship)
        )
        self.a, self.b, self.d = mk(self.s, "A", "12.99"), mk(self.s, "B", "9.99"), mk(self.s2, "D", "0")
        self.client.force_login(self.c)

    def add(self, product, qty=1):
        self.client.post(reverse("orders:cart_add", args=[product.pk]), {"quantity": qty})

    def checkout(self):
        self.client.post(reverse("orders:checkout"), {
            "delivery_method": "inpost", "full_name": "Jan", "phone": "600123456", "parcel_locker": "KRA01M",
        })
        return Order.objects.latest("pk")

    def test_rule_max_per_seller(self):
        self.assertEqual(shipping_total([(1, Decimal("5")), (1, Decimal("8")), (2, Decimal("3"))]), Decimal("11"))
        self.assertEqual(shipping_total([]), Decimal("0"))

    def test_order_total_includes_shipping_once_per_seller(self):
        self.add(self.a, 2)
        self.add(self.b)
        self.add(self.d)
        cart_page = self.client.get(reverse("orders:cart"))
        self.assertContains(cart_page, "Do zapłaty: 52,99 zł")
        order = self.checkout()
        self.assertEqual(order.items_total, Decimal("40.00"))
        self.assertEqual(order.shipping_total, Decimal("12.99"))
        self.assertEqual(order.total, Decimal("52.99"))
        # zmiana kosztu po zakupie nie zmienia zamówienia
        Product.objects.update(shipping_cost=Decimal("50"))
        self.assertEqual(Order.objects.get(pk=order.pk).total, Decimal("52.99"))

    @patch("orders.payments.stripe.checkout.Session.create")
    def test_stripe_gets_shipping_line(self, create):
        create.return_value = SimpleNamespace(id="cs_test_1", url="https://stripe.test/pay")
        self.add(self.a)
        order = self.checkout()
        with self.settings(STRIPE_SECRET_KEY="sk_test_x"):
            r = self.client.post(reverse("orders:pay", args=[order.pk]))
        self.assertRedirects(r, "https://stripe.test/pay", fetch_redirect_response=False)
        lines = create.call_args.kwargs["line_items"]
        self.assertEqual(sum(l["price_data"]["unit_amount"] * l["quantity"] for l in lines), 2299)
        self.assertEqual(lines[-1]["price_data"]["product_data"]["name"], "Wysyłka")

    def test_mark_paid_accepts_amount_with_shipping(self):
        self.add(self.a)
        order = self.checkout()
        session = SimpleNamespace(payment_status="paid", client_reference_id=str(order.pk), amount_total=2299)
        self.assertTrue(payments.mark_paid(session))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_free_shipping_adds_no_stripe_line(self):
        self.add(self.d)
        order = self.checkout()
        self.assertEqual(order.shipping_total, Decimal("0"))
        self.assertContains(self.client.get(reverse("orders:detail", args=[order.pk])), "Wysyłka: darmowa")


class ExpiredOrderTests(TestCase):
    def setUp(self):
        self.s = User.objects.create_user("s", "s@e.com", P, role="seller")
        self.c = User.objects.create_user("c", "c@e.com", P)
        self.p = Product.objects.create(seller=self.s, title="Kubek", description="d", price=10, stock=3)
        self.order = self.make_order(minutes_ago=61)

    def make_order(self, minutes_ago, **kwargs):
        order = Order.objects.create(buyer=self.c, **kwargs)
        order.items.create(product=self.p, seller=self.s, title="Kubek", unit_price=10, quantity=2)
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_ago))
        return order

    def assertStatus(self, order, status):
        order.refresh_from_db()
        self.assertEqual(order.status, status)

    def test_overdue_cancelled_and_stock_returned(self):
        fresh = self.make_order(minutes_ago=59)
        paid = self.make_order(minutes_ago=120, status=Order.Status.PAID)
        self.assertEqual(cancel_expired_orders(), 1)
        self.assertStatus(self.order, Order.Status.CANCELLED)
        self.assertStatus(fresh, Order.Status.NEW)
        self.assertStatus(paid, Order.Status.PAID)
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 5)
        self.assertEqual(cancel_expired_orders(), 0)  # drugi raz nie oddaje towaru ponownie

    @patch("orders.payments.stripe.checkout.Session.expire")
    def test_open_stripe_session_is_expired(self, expire):
        Order.objects.filter(pk=self.order.pk).update(stripe_session_id="cs_1")
        cancel_expired_orders()
        expire.assert_called_once_with("cs_1")
        self.assertStatus(self.order, Order.Status.CANCELLED)

    @patch("orders.payments.stripe.checkout.Session.retrieve")
    @patch("orders.payments.stripe.checkout.Session.expire", side_effect=stripe.InvalidRequestError("done", None))
    def test_paid_in_last_moment_is_not_cancelled(self, expire, retrieve):
        Order.objects.filter(pk=self.order.pk).update(stripe_session_id="cs_1")
        retrieve.return_value = SimpleNamespace(
            payment_status="paid", client_reference_id=str(self.order.pk), amount_total=2000
        )
        self.assertEqual(cancel_expired_orders(), 0)
        self.assertStatus(self.order, Order.Status.PAID)
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 3)

    @patch("orders.payments.stripe.checkout.Session.retrieve", side_effect=stripe.APIConnectionError("down"))
    @patch("orders.payments.stripe.checkout.Session.expire", side_effect=stripe.APIConnectionError("down"))
    def test_stripe_down_postpones_cancel(self, expire, retrieve):
        Order.objects.filter(pk=self.order.pk).update(stripe_session_id="cs_1")
        self.assertEqual(cancel_expired_orders(), 0)
        self.assertStatus(self.order, Order.Status.NEW)

    def test_management_command(self):
        out = StringIO()
        call_command("cancel_expired_orders", stdout=out)
        self.assertIn("Anulowano zamówień: 1", out.getvalue())
        self.assertStatus(self.order, Order.Status.CANCELLED)

    def test_middleware_runs_on_request(self):
        cache.clear()
        self.client.get(reverse("products:list"))
        self.assertStatus(self.order, Order.Status.CANCELLED)

    def test_cannot_pay_after_deadline(self):
        cache.set("orders:expired-check", True)  # wyłączamy middleware, żeby sprawdzić sam widok
        self.client.force_login(self.c)
        with self.settings(STRIPE_SECRET_KEY="sk_test_x"):
            r = self.client.post(reverse("orders:pay", args=[self.order.pk]))
        self.assertRedirects(r, reverse("orders:detail", args=[self.order.pk]))
        self.assertStatus(self.order, Order.Status.NEW)
