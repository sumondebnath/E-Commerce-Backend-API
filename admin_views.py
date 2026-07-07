from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from django.db.models import Sum, Count, Avg
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta

from accounts.models import User
from products.models import Product, Category
from orders.models import Order, Payment
from cart.models import CartItem


class IsAdminUser(permissions.BasePermission):
    """Only staff/superusers can access admin stats."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_staff


class DashboardStatsView(APIView):
    """
    GET /api/admin/dashboard/
    Returns all key metrics for the admin dashboard in one call.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        last_30_days = now - timedelta(days=30)
        last_7_days  = now - timedelta(days=7)

        # ── Orders ────────────────────────────────────────────────────────────
        total_orders    = Order.objects.count()
        orders_today    = Order.objects.filter(created_at__date=now.date()).count()
        orders_30_days  = Order.objects.filter(created_at__gte=last_30_days).count()
        pending_orders  = Order.objects.filter(order_status='Pending').count()
        orders_by_status = (
            Order.objects.values('order_status')
            .annotate(count=Count('id'))
            .order_by('order_status')
        )

        # ── Revenue ───────────────────────────────────────────────────────────
        total_revenue = (
            Payment.objects.filter(payment_status='Completed')
            .aggregate(total=Sum('amount'))['total'] or 0
        )
        revenue_30_days = (
            Payment.objects.filter(payment_status='Completed', paid_at__gte=last_30_days)
            .aggregate(total=Sum('amount'))['total'] or 0
        )
        revenue_7_days = (
            Payment.objects.filter(payment_status='Completed', paid_at__gte=last_7_days)
            .aggregate(total=Sum('amount'))['total'] or 0
        )

        # Revenue per day for last 30 days (for chart)
        daily_revenue = list(
            Payment.objects.filter(payment_status='Completed', paid_at__gte=last_30_days)
            .annotate(date=TruncDate('paid_at'))
            .values('date')
            .annotate(revenue=Sum('amount'))
            .order_by('date')
        )

        # ── Products ──────────────────────────────────────────────────────────
        total_products  = Product.objects.count()
        active_products = Product.objects.filter(is_active=True).count()
        # Low stock = active products with stock <= 5
        low_stock = list(
            Product.objects.filter(is_active=True, stock_count__lte=5)
            .values('id', 'name', 'stock_count')
            .order_by('stock_count')[:10]
        )
        out_of_stock = Product.objects.filter(is_active=True, stock_count=0).count()
        top_products = list(
            Product.objects.annotate(
                order_count=Count('order_items'),
                revenue=Sum('order_items__price_at_purchase')
            )
            .filter(order_count__gt=0)
            .values('id', 'name', 'order_count', 'revenue')
            .order_by('-order_count')[:5]
        )

        # ── Users ─────────────────────────────────────────────────────────────
        total_users     = User.objects.filter(is_staff=False).count()
        new_users_30    = User.objects.filter(is_staff=False, created_at__gte=last_30_days).count()
        active_carts    = CartItem.objects.values('user').distinct().count()

        return Response({
            'orders': {
                'total':      total_orders,
                'today':      orders_today,
                'last_30_days': orders_30_days,
                'pending':    pending_orders,
                'by_status':  list(orders_by_status),
            },
            'revenue': {
                'total':        float(total_revenue),
                'last_30_days': float(revenue_30_days),
                'last_7_days':  float(revenue_7_days),
                'daily_chart':  [
                    {'date': str(r['date']), 'revenue': float(r['revenue'])}
                    for r in daily_revenue
                ],
            },
            'products': {
                'total':        total_products,
                'active':       active_products,
                'out_of_stock': out_of_stock,
                'low_stock':    low_stock,
                'top_selling':  top_products,
            },
            'users': {
                'total':          total_users,
                'new_last_30_days': new_users_30,
                'active_carts':   active_carts,
            },
        })


class OrderManagementView(APIView):
    """
    PATCH /api/admin/orders/{order_id}/status/
    Body: { "status": "Shipped" }
    Staff-only endpoint to update order status.
    """
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


class ProductStockUpdateView(APIView):
    """
    PATCH /api/admin/products/{product_id}/stock/
    Body: { "stock_count": 50 }
    Quick stock update without going through the full product serializer.
    """
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
