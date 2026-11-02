import hashlib
import hmac
from django.conf import settings
from rest_framework.exceptions import PermissionDenied
from rest_framework import request, viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from decimal import Decimal

from cart.models import CartItem
from orders.pricing import calculate_shipping_cost
from products.models import Product
from .models import Order, OrderItem, Payment
from .services import restock_order_items, settle_cancelled_payment
from .serializers import (
    OrderListSerializer,
    OrderDetailSerializer,
    CheckoutSerializer,
    PaymentSerializer,
    PaymentWebhookSerializer,
)


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/orders/          -> list current user's past orders
    GET /api/orders/{id}/     -> order detail with items + payment

    Orders are created only through the /checkout/ endpoint below —
    never exposed as a plain POST here, because creating an order is a
    multi-step transaction (stock check, deduction, payment record, cart
    clear), not a simple model write.
    """
    serializer_class = OrderDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Order.objects.filter(user=self.request.user).prefetch_related('items', 'payment')
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return OrderListSerializer
        return OrderDetailSerializer

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            order = get_object_or_404(Order.objects.select_for_update(), pk=pk, user=request.user)
            if order.order_status not in ('PENDING', 'PROCESSING'):
                return Response({"detail": f"Cannot cancel an order that is already '{order.order_status}'."}, status=status.HTTP_400_BAD_REQUEST,)
            restock_order_items(order)
            settle_cancelled_payment(order)
            order.order_status = 'CANCELLED'
            order.save(update_fields=['order_status', 'updated_at'])
        return Response(OrderDetailSerializer(order).data)


class CheckoutView(APIView):
    """
    POST /api/orders/checkout/

    Body:
    {
      "address_id": 4,                  // OR shipping_* fields directly
      "payment_method": "stripe",
      "shipping_cost": "5.00"
    }

    This is the single most important business-logic endpoint in the system.
    It must be atomic: either the whole order succeeds, or nothing changes
    (no partial stock deduction, no order created without items, etc).
    """
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = CheckoutSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Lock the user's cart items + underlying products for the duration of
        # this transaction so two simultaneous checkouts (e.g. two browser tabs,
        # or the classic "last item in stock" race condition) can't both
        # succeed and oversell stock.
        cart_items = (
            CartItem.objects.filter(user=request.user)
            .select_related('product')
            .select_for_update(of=('self',))
        )

        if not cart_items.exists():
            return Response({"detail": "Your cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

        product_ids = [item.product_id for item in cart_items]
        # Lock the actual Product rows too — this is the row that stock_count
        # lives on, so this is what prevents oversell under concurrency.
        locked_products = {
            p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids)
        }

        # Validate stock for every line BEFORE writing anything
        insufficient = []
        for item in cart_items:
            product = locked_products.get(item.product_id)
            if product is None:
                insufficient.append("A product in your cart is no longer available.")
                continue
            if not product.is_active:
                insufficient.append(f"'{product.name}' is no longer available.")
            elif item.quantity > product.stock_count:
                insufficient.append(f"Only {product.stock_count} unit(s) of '{product.name}' left.")
        if insufficient:
            return Response({"detail": insufficient}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve shipping address (saved address vs one-off fields)
        address = data.get('address')
        if address:
            shipping_fields = {
                'shipping_full_name': request.user.full_name or request.user.email,
                'shipping_street_address': address.street_address,
                'shipping_city': address.city,
                'shipping_state': address.state,
                'shipping_postal_code': address.postal_code,
                'shipping_country': address.country,
            }
        else:
            shipping_fields = {k: data[k] for k in [
                'shipping_full_name', 'shipping_street_address', 'shipping_city',
                'shipping_state', 'shipping_postal_code', 'shipping_country',
            ]}

        subtotal = sum((item.product.price * item.quantity for item in cart_items), Decimal('0.00'),)
        shipping_cost = calculate_shipping_cost(subtotal)
        total = subtotal + shipping_cost

        order = Order.objects.create(
            user=request.user,
            subtotal_cost=subtotal,
            shipping_cost=shipping_cost,
            total_amount=total,
            order_status='PENDING',
            **shipping_fields,
        )

        order_items = []
        for item in cart_items:
            product = locked_products[item.product_id]
            order_items.append(OrderItem(
                order=order,
                product=product,
                product_name_snapshot=product.name,
                quantity=item.quantity,
                price_at_purchase=product.price,
            ))
            # Deduct stock — safe because the row is locked above
            product.stock_count -= item.quantity
        OrderItem.objects.bulk_create(order_items)
        Product.objects.bulk_update(locked_products.values(), ['stock_count'])

        Payment.objects.create(
            order=order,
            payment_method=data['payment_method'],
            amount=total,
            payment_status='Pending',
        )

        # Empty the cart now that it's been converted into an order
        cart_items.delete()

        return Response(OrderDetailSerializer(order).data, status=status.HTTP_201_CREATED)


# class PaymentWebhookView(APIView):
#     """
#     POST /api/orders/payment-webhook/
#     Called by your payment gateway (Stripe, SSLCommerz, etc.) — NOT by the
#     frontend directly. In production, verify the gateway's signature header
#     here before trusting the payload.

#     Body: { "order_id": "...", "transaction_id": "...", "status": "Completed" }
#     """
#     permission_classes = [permissions.AllowAny]  # gateway calls this, not a logged-in user

#     def post(self, request):
#         order_id = request.data.get('order_id')
#         transaction_id = request.data.get('transaction_id')
#         new_status = request.data.get('status')

#         if new_status not in dict(Payment.PAYMENT_STATUS):
#             return Response({"detail": "Invalid status."}, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             payment = Payment.objects.select_related('order').get(order_id=order_id)
#         except Payment.DoesNotExist:
#             return Response({"detail": "Order/payment not found."}, status=status.HTTP_404_NOT_FOUND)

#         with transaction.atomic():
#             payment.transaction_id = transaction_id
#             payment.payment_status = new_status
#             if new_status == 'Completed':
#                 payment.paid_at = timezone.now()
#                 payment.order.order_status = 'PROCESSING'
#                 payment.order.save()
#             elif new_status == 'Failed':
#                 # BUSINESS LOGIC: restock items if payment fails
#                 payment.order.order_status = 'CANCELLED'
#                 payment.order.save()
#                 for item in payment.order.items.select_related('product'):
#                     if item.product:
#                         Product.objects.filter(pk=item.product_id).update(
#                             stock_count=item.product.stock_count + item.quantity
#                         )
#             payment.save()

#         return Response(PaymentSerializer(payment).data, status=status.HTTP_200_OK)





PAYMENT_TRANSITIONS = {
    'Pending': {'Completed', 'Failed'},
    'Completed': {'Refunded'},
    'Failed': set(),
    'Refunded': set(),
}


def verify_webhook_signature(request):
    """
    Generic HMAC-SHA256 verification over the raw request body.
    Header: X-Webhook-Signature: sha256=<hex_digest>
    Configure PAYMENT_WEBHOOK_SECRET in the environment.
    """
    secret = getattr(settings, 'PAYMENT_WEBHOOK_SECRET', '')
    if not secret:
        # Fail closed in production; allow local/test only when DEBUG=True.
        if settings.DEBUG:
            return
        raise PermissionDenied('Payment webhook secret is not configured.')

    received = request.headers.get('X-Webhook-Signature', '')
    expected = 'sha256=' + hmac.new(
        secret.encode('utf-8'), request.body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(received, expected):
        raise PermissionDenied('Invalid webhook signature.')


class PaymentWebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # gateways don't send JWTs

    def post(self, request):
        verify_webhook_signature(request)

        serializer = PaymentWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            payment = (
                Payment.objects.select_for_update()
                .select_related('order')
                .filter(order_id=data['order_id'])
                .first()
            )
            if payment is None:
                return Response(
                    {"detail": "Order/payment not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            order = Order.objects.select_for_update().get(pk=payment.order_id)
            new_status = data['status']

            # Idempotent retries.
            if payment.payment_status == new_status:
                return Response(PaymentSerializer(payment).data, status=status.HTTP_200_OK)

            if data.get('amount') is not None and data['amount'] != payment.amount:
                return Response(
                    {"detail": "Amount does not match the order total."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if new_status not in PAYMENT_TRANSITIONS.get(payment.payment_status, set()):
                return Response(
                    {"detail": (
                        f"Cannot change payment status from "
                        f"'{payment.payment_status}' to '{new_status}'."
                    )},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # A cancelled order has already released its inventory. Allowing a
            # late "Completed" callback would resurrect it without deducting
            # stock again, causing a free order / oversell.
            if new_status == 'Completed' and order.order_status == 'CANCELLED':
                return Response(
                    {"detail": "Order has been cancelled; payment cannot complete."},
                    status=status.HTTP_409_CONFLICT,
                )

            if (
                data.get('transaction_id')
                and Payment.objects.exclude(pk=payment.pk)
                .filter(transaction_id=data['transaction_id']).exists()
            ):
                return Response(
                    {"detail": "transaction_id has already been used."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            payment.transaction_id = data['transaction_id']
            payment.payment_status = new_status

            if new_status == 'Completed':
                payment.paid_at = timezone.now()
                order.order_status = 'PROCESSING'
                order.save(update_fields=['order_status', 'updated_at'])
            elif new_status in ('Failed', 'Refunded'):
                # Only put stock back if the goods never shipped. A refund for
                # a shipped/delivered order must not restock the warehouse.
                if order.order_status not in ('SHIPPED', 'DELIVERED'):
                    # restock_order_items() is idempotent via inventory_released.
                    restock_order_items(order)
                    order.order_status = 'CANCELLED'
                    order.save(update_fields=['order_status', 'updated_at'])

            payment.save()

        return Response(PaymentSerializer(payment).data, status=status.HTTP_200_OK)