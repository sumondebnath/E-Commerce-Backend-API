from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from rest_framework.pagination import PageNumberPagination
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta

from accounts.models import User
from products.models import Product, Category
from orders.models import Order, OrderItem, Payment
from cart.models import CartItem


class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_staff


# ── Dashboard ──────────────────────────────────────────────────────────────────

class DashboardStatsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        total_orders = Order.objects.count()
        total_users = User.objects.filter(is_staff=False).count()
        total_revenue = (
            Payment.objects.filter(payment_status='Completed')
            .aggregate(total=Sum('amount'))['total'] or 0
        )

        return Response({
            'orders': {'total': total_orders},
            'users': {'total': total_users},
            'revenue': {'total': str(total_revenue)},
        })


# ── Admin Orders ───────────────────────────────────────────────────────────────

class AdminOrderPagination(PageNumberPagination):
    page_size = 20


class AdminOrderListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        orders = Order.objects.select_related('user').prefetch_related('items').all()

        paginator = AdminOrderPagination()
        page = paginator.paginate_queryset(orders, request)

        results = []
        for order in page:
            results.append({
                'id': str(order.id),
                'user': {'email': order.user.email if order.user else None},
                'order_status': order.order_status,
                'total_amount': str(order.total_amount),
                'item_count': order.items.count(),
                'created_at': order.created_at.isoformat(),
            })

        return paginator.get_paginated_response(results)


class OrderManagementView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, order_id):
        new_status = request.data.get('status')
        valid = [s[0] for s in Order.STATUS_CHOICES]

        if new_status not in valid:
            return Response(
                {'detail': f'Invalid status. Must be one of: {valid}'},
                status=400
            )

        try:
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist:
            return Response({'detail': 'Order not found.'}, status=404)

        order.order_status = new_status
        order.save()
        return Response({'id': str(order.id), 'order_status': order.order_status})


# ── Admin Products ─────────────────────────────────────────────────────────────

class AdminProductPagination(PageNumberPagination):
    page_size = 20


class AdminProductListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        products = Product.objects.select_related('category').all()
        search = request.query_params.get('search')
        if search:
            products = products.filter(name__icontains=search)

        paginator = AdminProductPagination()
        page = paginator.paginate_queryset(products, request)

        results = []
        for p in page:
            results.append({
                'id': p.id,
                'name': p.name,
                'price': str(p.price),
                'stock_count': p.stock_count,
                'category_id': p.category_id,
                'category_name': p.category.name if p.category else None,
                'description': p.description,
                'is_active': p.is_active,
                'created_at': p.created_at.isoformat(),
            })

        return paginator.get_paginated_response(results)

    def post(self, request):
        name = request.data.get('name')
        price = request.data.get('price')
        stock_count = request.data.get('stock_count', 0)
        category_id = request.data.get('category_id')
        description = request.data.get('description', '')
        is_active = request.data.get('is_active', True)

        if not name or price is None:
            return Response({'detail': 'name and price are required.'}, status=400)

        product = Product.objects.create(
            name=name,
            price=price,
            stock_count=stock_count,
            category_id=category_id,
            description=description,
            is_active=is_active,
        )

        return Response({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'stock_count': product.stock_count,
            'category_id': product.category_id,
            'description': product.description,
            'is_active': product.is_active,
        }, status=201)


class AdminProductDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, product_id):
        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            return Response({'detail': 'Product not found.'}, status=404)

        for field in ['name', 'price', 'stock_count', 'category_id', 'description', 'is_active']:
            if field in request.data:
                setattr(product, field, request.data[field])
        product.save()

        return Response({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'stock_count': product.stock_count,
            'category_id': product.category_id,
            'description': product.description,
            'is_active': product.is_active,
        })

    def delete(self, request, product_id):
        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            return Response({'detail': 'Product not found.'}, status=404)

        product.delete()
        return Response(status=204)


class ProductStockUpdateView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, product_id):
        stock = request.data.get('stock_count')
        if stock is None or int(stock) < 0:
            return Response({'detail': 'stock_count must be a non-negative integer.'}, status=400)

        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            return Response({'detail': 'Product not found.'}, status=404)

        product.stock_count = int(stock)
        product.save()
        return Response({'id': product.id, 'name': product.name, 'stock_count': product.stock_count})


# ── Admin Categories ───────────────────────────────────────────────────────────

class AdminCategoryPagination(PageNumberPagination):
    page_size = 20


class AdminCategoryListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        categories = Category.objects.all()

        paginator = AdminCategoryPagination()
        page = paginator.paginate_queryset(categories, request)

        results = []
        for cat in page:
            results.append({
                'id': cat.id,
                'name': cat.name,
                'slug': cat.slug,
                'description': getattr(cat, 'description', ''),
            })

        return paginator.get_paginated_response(results)

    def post(self, request):
        name = request.data.get('name')
        description = request.data.get('description', '')

        if not name:
            return Response({'detail': 'name is required.'}, status=400)

        from django.utils.text import slugify
        slug = slugify(name)

        if Category.objects.filter(slug=slug).exists():
            return Response({'detail': 'A category with this name already exists.'}, status=400)

        category = Category.objects.create(name=name, slug=slug)
        return Response({
            'id': category.id,
            'name': category.name,
            'slug': category.slug,
            'description': description,
        }, status=201)


class AdminCategoryDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, category_id):
        try:
            cat = Category.objects.get(pk=category_id)
        except Category.DoesNotExist:
            return Response({'detail': 'Category not found.'}, status=404)

        return Response({
            'id': cat.id,
            'name': cat.name,
            'slug': cat.slug,
            'description': getattr(cat, 'description', ''),
        })

    def patch(self, request, category_id):
        try:
            cat = Category.objects.get(pk=category_id)
        except Category.DoesNotExist:
            return Response({'detail': 'Category not found.'}, status=404)

        if 'name' in request.data:
            cat.name = request.data['name']
        if 'description' in request.data:
            pass  # Category model doesn't have description field yet
        cat.save()

        return Response({
            'id': cat.id,
            'name': cat.name,
            'slug': cat.slug,
        })

    def delete(self, request, category_id):
        try:
            cat = Category.objects.get(pk=category_id)
        except Category.DoesNotExist:
            return Response({'detail': 'Category not found.'}, status=404)

        cat.delete()
        return Response(status=204)
