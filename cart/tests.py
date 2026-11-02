from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from products.models import Category, Product
from cart.models import CartItem


class CartTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='cart@example.com', password='StrongPass123!'
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

    def test_invalid_quantity_is_400(self):
        res = self.client.post(
            '/api/cart/',
            {'product_id': self.product.id, 'quantity': 'abc'},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_null_quantity_is_400(self):
        res = self.client.post(
            '/api/cart/',
            {'product_id': self.product.id, 'quantity': None},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_zero_quantity_is_400(self):
        res = self.client.post(
            '/api/cart/',
            {'product_id': self.product.id, 'quantity': 0},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_negative_quantity_is_400(self):
        res = self.client.post(
            '/api/cart/',
            {'product_id': self.product.id, 'quantity': -2},
            format='json',
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_over_stock_is_400(self):
        res = self.client.post(
            '/api/cart/',
            {'product_id': self.product.id, 'quantity': 6},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_additive_quantity(self):
        first = self.client.post(
            '/api/cart/',
            {'product_id': self.product.id, 'quantity': 2},
            format='json',
        )
        self.assertEqual(first.status_code, 201, first.data)

        second = self.client.post(
            '/api/cart/',
            {'product_id': self.product.id, 'quantity': 1},
            format='json',
        )
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data['quantity'], 3)

    def test_patch_quantity_zero_is_rejected(self):
        item = CartItem.objects.create(
            user=self.user, product=self.product, quantity=2
        )
        res = self.client.patch(
            f'/api/cart/{item.id}/', {'quantity': 0}, format='json'
        )
        self.assertEqual(res.status_code, 400)