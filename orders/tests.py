import hashlib
import hmac
import json
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from cart.models import CartItem
from orders.models import Order, OrderItem, Payment
from products.models import Category, Product


class CheckoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='user@example.com', password='StrongPass123!'
        )
        self.category = Category.objects.create(name='Books', slug='books')
        self.product = Product.objects.create(
            category=self.category,
            name='Book',
            description='A book',
            price=Decimal('10.00'),
            stock_count=5,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _shipping(self, **overrides):
        body = {
            'shipping_full_name': 'Test User',
            'shipping_street_address': '1 Main St',
            'shipping_city': 'Dhaka',
            'shipping_state': 'DH',
            'shipping_postal_code': '1200',
            'shipping_country': 'BD',
            'payment_method': 'stripe',
        }
        body.update(overrides)
        return body

    def test_empty_cart_rejected(self):
        res = self.client.post('/api/orders/checkout/', self._shipping(), format='json')
        self.assertEqual(res.status_code, 400)

    def test_checkout_decrements_stock_and_clears_cart(self):
        CartItem.objects.create(user=self.user, product=self.product, quantity=2)
        res = self.client.post('/api/orders/checkout/', self._shipping(), format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_count, 3)
        self.assertEqual(CartItem.objects.filter(user=self.user).count(), 0)
        self.assertEqual(Order.objects.count(), 1)

    def test_client_shipping_cost_is_ignored(self):
        CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        res = self.client.post(
            '/api/orders/checkout/',
            self._shipping(shipping_cost='-100.00'),
            format='json',
        )
        self.assertEqual(res.status_code, 201, res.data)
        order = Order.objects.get()
        self.assertEqual(order.shipping_cost, Decimal('5.00'))
        self.assertEqual(order.total_amount, Decimal('15.00'))

    def test_insufficient_stock_rolls_back(self):
        CartItem.objects.create(user=self.user, product=self.product, quantity=99)
        res = self.client.post('/api/orders/checkout/', self._shipping(), format='json')
        self.assertEqual(res.status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_count, 5)

    def test_cancel_restocks_once_and_refunds(self):
        CartItem.objects.create(user=self.user, product=self.product, quantity=2)
        res = self.client.post('/api/orders/checkout/', self._shipping(), format='json')
        order_id = res.data['id']

        payment = Payment.objects.get(order_id=order_id)
        payment.payment_status = 'Completed'
        payment.save(update_fields=['payment_status'])

        first = self.client.post(f'/api/orders/{order_id}/cancel/')
        self.assertEqual(first.status_code, 200, first.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_count, 5)
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, 'Refunded')

        second = self.client.post(f'/api/orders/{order_id}/cancel/')
        self.assertEqual(second.status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_count, 5)


@override_settings(PAYMENT_WEBHOOK_SECRET='testsecret')
class PaymentWebhookTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='webhook@example.com', password='StrongPass123!'
        )
        self.category = Category.objects.create(name='Books', slug='books')
        self.product = Product.objects.create(
            category=self.category,
            name='Book',
            description='A book',
            price=Decimal('10.00'),
            stock_count=3,
        )
        self.order = Order.objects.create(
            user=self.user,
            subtotal_cost=Decimal('20.00'),
            shipping_cost=Decimal('0.00'),
            total_amount=Decimal('20.00'),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name_snapshot='Book',
            quantity=2,
            price_at_purchase=Decimal('10.00'),
        )
        self.payment = Payment.objects.create(
            order=self.order,
            payment_method='stripe',
            amount=Decimal('20.00'),
            payment_status='Pending',
        )
        self.client = APIClient()

    def _post(self, payload, secret='testsecret'):
        body = json.dumps(payload).encode()
        signature = 'sha256=' + hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()
        return self.client.post(
            '/api/orders/payment-webhook/',
            data=body,
            content_type='application/json',
            HTTP_X_WEBHOOK_SIGNATURE=signature,
        )

    def _payload(self, **overrides):
        body = {
            'order_id': str(self.order.id),
            'transaction_id': 'txn-1',
            'status': 'Completed',
        }
        body.update(overrides)
        return body

    def test_invalid_signature_is_403(self):
        res = self._post(self._payload(), secret='wrong')
        self.assertEqual(res.status_code, 403)

    def test_invalid_uuid_is_400(self):
        res = self._post(self._payload(order_id='not-a-uuid'))
        self.assertEqual(res.status_code, 400)

    def test_amount_mismatch_is_400(self):
        res = self._post(self._payload(amount='999.00'))
        self.assertEqual(res.status_code, 400)

    def test_completed_moves_order_to_processing(self):
        res = self._post(self._payload())
        self.assertEqual(res.status_code, 200, res.data)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.payment_status, 'Completed')
        self.assertEqual(self.order.order_status, 'PROCESSING')

    def test_failed_restock_is_idempotent(self):
        payload = self._payload(status='Failed')
        first = self._post(payload)
        self.assertEqual(first.status_code, 200, first.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_count, 5)

        second = self._post(payload)
        self.assertEqual(second.status_code, 200, second.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_count, 5)

    def test_refund_after_completed(self):
        self.assertEqual(self._post(self._payload()).status_code, 200)
        self.assertEqual(
            self._post(self._payload(status='Refunded')).status_code, 200
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_count, 5)