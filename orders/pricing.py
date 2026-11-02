from decimal import Decimal

from django.conf import settings


def calculate_shipping_cost(subtotal) -> Decimal:
    """
    Server-authoritative shipping. Never trust a client-supplied shipping cost.
    Defaults: free over 100.00, otherwise 5.00. Override via settings/env.
    """
    subtotal = Decimal(str(subtotal))
    if subtotal <= 0:
        return Decimal('0.00')

    threshold = Decimal(str(getattr(settings, 'FREE_SHIPPING_THRESHOLD', '100.00')))
    flat = Decimal(str(getattr(settings, 'FLAT_SHIPPING_COST', '5.00')))

    if subtotal >= threshold:
        return Decimal('0.00')
    return flat