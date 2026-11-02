from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from django.db.models import Sum

from accounts.models import User
from orders.models import Order, Payment
from orders.services import restock_order_items, settle_cancelled_payment, ORDER_TRANSITIONS
from products.models import Product, Category
from .serializers import (
    AdminProductSerializer,
    StockUpdateSerializer,
    AdminCategorySerializer,
    OrderStatusSerializer,
)




def product_payload(product):
    return {
        'id': product.id,
        'name': product.name,
        'price': str(product.price),
        'stock_count': product.stock_count,
        'category_id': product.category_id,
        'category_name': product.category.name if product.category else None,
        'description': product.description,
        'is_active': product.is_active,
        'created_at': product.created_at.isoformat(),
    }

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
            Payment.objects.filter(payment_status='Completed', order__order_status__in=['PROCESSING', 'SHIPPED', 'DELIVERED'],).aggregate(total=Sum('amount'))['total'] or 0)

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
        payload = OrderStatusSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        new_status = payload.validated_data['status']

        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .filter(pk=order_id)
                .first()
            )
            if order is None:
                return Response({'detail': 'Order not found.'}, status=404)

            if order.order_status == new_status:
                return Response({'id': str(order.id), 'order_status': order.order_status})

            if new_status not in ORDER_TRANSITIONS.get(order.order_status, set()):
                return Response(
                    {'detail': (
                        f"Cannot change order status from "
                        f"'{order.order_status}' to '{new_status}'."
                    )},
                    status=400,
                )

            if new_status == 'CANCELLED':
                restock_order_items(order)
                settle_cancelled_payment(order)

            order.order_status = new_status
            order.save(update_fields=['order_status', 'updated_at'])

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
        return paginator.get_paginated_response([product_payload(p) for p in page])

    def post(self, request):
        serializer = AdminProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(product_payload(product), status=201)



class AdminProductDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        serializer = AdminProductSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(product_payload(product))

    def delete(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        product.delete()
        return Response(status=204)


class ProductStockUpdateView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, product_id):
        payload = StockUpdateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        product = get_object_or_404(Product, pk=product_id)
        product.stock_count = payload.validated_data['stock_count']
        product.save(update_fields=['stock_count', 'updated_at'])

        return Response({
            'id': product.id,
            'name': product.name,
            'stock_count': product.stock_count,
        })

# ── Admin Categories ───────────────────────────────────────────────────────────

class AdminCategoryPagination(PageNumberPagination):
    page_size = 20


class AdminCategoryListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        categories = Category.objects.all()
        paginator = AdminCategoryPagination()
        page = paginator.paginate_queryset(categories, request)
        return paginator.get_paginated_response([
            AdminCategorySerializer(c).data for c in page
        ])

    def post(self, request):
        serializer = AdminCategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(AdminCategorySerializer(category).data, status=201)



class AdminCategoryDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, category_id):
        category = get_object_or_404(Category, pk=category_id)
        return Response(AdminCategorySerializer(category).data)

    def patch(self, request, category_id):
        category = get_object_or_404(Category, pk=category_id)
        serializer = AdminCategorySerializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(AdminCategorySerializer(category).data)

    def delete(self, request, category_id):
        category = get_object_or_404(Category, pk=category_id)
        category.delete()
        return Response(status=204)