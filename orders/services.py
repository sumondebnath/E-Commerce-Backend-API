from django.db.models import F

from products.models import Product
from .models import Payment



ORDER_TRANSITIONS = {
    'PENDING': {'PROCESSING', 'CANCELLED'},
    'PROCESSING': {'SHIPPED', 'CANCELLED'},
    'SHIPPED': {'DELIVERED'},
    'DELIVERED': set(),
    'CANCELLED': set(),
}


def restock_order_items(order) -> bool:
    """
    Returns True if stock was released now, False if it was already released.
    Safe to call from cancel, webhook, and admin endpoints.
    """
    if order.inventory_released:
        return False

    for item in order.items.only('product_id', 'quantity'):
        if item.product_id:
            # F() prevents lost updates under concurrency.
            Product.objects.filter(pk=item.product_id).update(
                stock_count=F('stock_count') + item.quantity
            )

    order.inventory_released = True
    order.save(update_fields=['inventory_released'])
    return True


def settle_cancelled_payment(order):
    """Mark a completed payment as refunded when the order is cancelled."""
    payment = Payment.objects.filter(order=order).first()
    if payment and payment.payment_status == 'Completed':
        payment.payment_status = 'Refunded'
        payment.save(update_fields=['payment_status'])
    return payment