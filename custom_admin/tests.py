from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from orders.models import Order, OrderItem
from products.models import Category, Product


class AdminApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='user@example.com', password='StrongPass123!'
        )
        self.staff = User.objects.create_user(
            email='admin@example.com', password='StrongPass123!', is_staff=True
        )
        self.category = Category.objects.create(name='Books', slug='books')
        self.product = Product.objects.create(
            category=self.category,
            name='Book',
            description='A book',
            price=Decimal('10.00'),
            stock_count=3,
        )
        self.client = APIClient()

    def test_non_staff_forbidden(self):
        self.client.force_authenticate(self.user)
        res = self.client.get('/api/admin/dashboard/')
        self.assertEqual(res.status_code, 403)

    def test_negative_price_rejected(self):
        self.client.force_authenticate(self.staff)
        res = self.client.post(
            '/api/admin/products/',
            {'name': 'Bad', 'price': '-1.00', 'stock_count': 1},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_invalid_stock_rejected(self):
        self.client.force_authenticate(self.staff)
        res = self.client.patch(
            f'/api/admin/products/{self.product.id}/stock/',
            {'stock_count': 'abc'},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_category_rename_updates_slug(self):
        self.client.force_authenticate(self.staff)
        res = self.client.patch(
            f'/api/admin/categories/{self.category.id}/',
            {'name': 'New Books'},
            format='json',
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, 'New Books')
        self.assertEqual(self.category.slug, 'new-books')

    def test_category_description_round_trips(self):
        self.client.force_authenticate(self.staff)
        res = self.client.post(
            '/api/admin/categories/',
            {'name': 'Fiction', 'description': 'Fiction books'},
            format='json',
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['description'], 'Fiction books')

    def test_admin_cancel_restocks(self):
        order = Order.objects.create(
            user=self.user,
            subtotal_cost=Decimal('20.00'),
            shipping_cost=Decimal('0.00'),
            total_amount=Decimal('20.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name_snapshot='Book',
            quantity=2,
            price_at_purchase=Decimal('10.00'),
        )
        self.product.stock_count = 1
        self.product.save(update_fields=['stock_count'])

        self.client.force_authenticate(self.staff)
        res = self.client.patch(
            f'/api/admin/orders/{order.id}/status/',
            {'status': 'CANCELLED'},
            format='json',
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock_count, 3)
        self.assertTrue(order.inventory_released)

    def test_invalid_order_transition_rejected(self):
        order = Order.objects.create(
            user=self.user,
            subtotal_cost=Decimal('10.00'),
            total_amount=Decimal('10.00'),
            order_status='DELIVERED',
        )
        self.client.force_authenticate(self.staff)
        res = self.client.patch(
            f'/api/admin/orders/{order.id}/status/',
            {'status': 'PENDING'},
            format='json',
        )
        self.assertEqual(res.status_code, 400)