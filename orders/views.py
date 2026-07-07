from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone

from cart.models import CartItem
from products.models import Product
from .models import Order, OrderItem, Payment
from .serializers import (
    OrderListSerializer,
    OrderDetailSerializer,
    CheckoutSerializer,
    PaymentSerializer,
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
        order = self.get_object()
        # BUSINESS LOGIC: can only cancel before it ships
        if order.order_status not in ('Pending', 'Processing'):
            return Response(
                {"detail": f"Cannot cancel an order that is already '{order.order_status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            order.order_status = 'Cancelled'
            order.save()
            # restock items
            for item in order.items.select_related('product'):
                if item.product:
                    Product.objects.filter(pk=item.product_id).update(
                        stock_count=item.product.stock_count + item.quantity
                    )
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
            product = locked_products[item.product_id]
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

        subtotal = sum(item.product.price * item.quantity for item in cart_items)
        shipping_cost = data.get('shipping_cost') or 0
        total = subtotal + shipping_cost

        order = Order.objects.create(
            user=request.user,
            subtotal_amount=subtotal,
            shipping_cost=shipping_cost,
            total_amount=total,
            order_status='Pending',
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


class PaymentWebhookView(APIView):
    """
    POST /api/orders/payment-webhook/
    Called by your payment gateway (Stripe, SSLCommerz, etc.) — NOT by the
    frontend directly. In production, verify the gateway's signature header
    here before trusting the payload.

    Body: { "order_id": "...", "transaction_id": "...", "status": "Completed" }
    """
    permission_classes = [permissions.AllowAny]  # gateway calls this, not a logged-in user

    def post(self, request):
        order_id = request.data.get('order_id')
        transaction_id = request.data.get('transaction_id')
        new_status = request.data.get('status')

        if new_status not in dict(Payment.PAYMENT_STATUS):
            return Response({"detail": "Invalid status."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = Payment.objects.select_related('order').get(order_id=order_id)
        except Payment.DoesNotExist:
            return Response({"detail": "Order/payment not found."}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            payment.transaction_id = transaction_id
            payment.payment_status = new_status
            if new_status == 'Completed':
                payment.paid_at = timezone.now()
                payment.order.order_status = 'Processing'
                payment.order.save()
            elif new_status == 'Failed':
                # BUSINESS LOGIC: restock items if payment fails
                payment.order.order_status = 'Cancelled'
                payment.order.save()
                for item in payment.order.items.select_related('product'):
                    if item.product:
                        Product.objects.filter(pk=item.product_id).update(
                            stock_count=item.product.stock_count + item.quantity
                        )
            payment.save()

        return Response(PaymentSerializer(payment).data, status=status.HTTP_200_OK)
