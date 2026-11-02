from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from products.models import Category, Product, Review, SaveProduct


class ProductApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='buyer@example.com', password='StrongPass123!'
        )
        self.other = User.objects.create_user(
            email='other@example.com', password='StrongPass123!'
        )
        self.staff = User.objects.create_user(
            email='staff@example.com', password='StrongPass123!', is_staff=True
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

    def test_save_to_watchlist_works(self):
        self.client.force_authenticate(self.user)
        res = self.client.post(f'/api/products/{self.product.id}/save_to_watchlist/')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertIn('average_rating', res.data['product_detail'])
        self.assertEqual(SaveProduct.objects.count(), 1)

    def test_save_to_watchlist_is_idempotent_per_user(self):
        self.client.force_authenticate(self.user)
        self.client.post(f'/api/products/{self.product.id}/save_to_watchlist/')
        res = self.client.post(f'/api/products/{self.product.id}/save_to_watchlist/')
        self.assertEqual(res.status_code, 400)

    def test_cannot_update_other_users_review(self):
        review = Review.objects.create(
            user=self.other, product=self.product, rating=5, comment='great'
        )
        self.client.force_authenticate(self.user)
        res = self.client.patch(
            f'/api/products/reviews/{review.id}/?product={self.product.id}',
            {'rating': 1},
            format='json',
        )
        self.assertEqual(res.status_code, 403)

    def test_cannot_delete_other_users_review(self):
        review = Review.objects.create(
            user=self.other, product=self.product, rating=5, comment='great'
        )
        self.client.force_authenticate(self.user)
        res = self.client.delete(
            f'/api/products/reviews/{review.id}/?product={self.product.id}'
        )
        self.assertEqual(res.status_code, 403)

    def test_staff_can_create_product_with_json(self):
        self.client.force_authenticate(self.staff)
        res = self.client.post(
            '/api/products/',
            {
                'name': 'New Book',
                'description': 'desc',
                'price': '12.50',
                'stock_count': 4,
                'category_id': self.category.id,
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201, res.data)

    def test_non_staff_cannot_create_product(self):
        self.client.force_authenticate(self.user)
        res = self.client.post(
            '/api/products/',
            {'name': 'X', 'description': 'd', 'price': '1.00'},
            format='json',
        )
        self.assertEqual(res.status_code, 403)