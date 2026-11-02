from django.db import transaction
from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action 
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from decimal import Decimal
from products.models import Product
from .serializers import CartAddSerializer, CartItemSerializer
from .models import CartItem

# Create your views here.


class CartItemViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CartItem.objects.filter(user=self.request.user).select_related('product')
    
    def create(self, request, *args, **kwargs):
        payload = CartAddSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        product_id = payload.validated_data['product_id']
        quantity_to_add = payload.validated_data['quantity']

        # Keep the lock, the read-modify-write, and the save in one transaction
        # so two concurrent adds cannot lose an increment.
        with transaction.atomic():
            product = get_object_or_404(
                Product.objects.select_for_update(),
                id=product_id,
                is_active=True,
            )

            cart_item, created = CartItem.objects.select_for_update().get_or_create(
                user=request.user,
                product=product,
                defaults={'quantity': 0},
            )
            new_quantity = cart_item.quantity + quantity_to_add

            if new_quantity > product.stock_count:
                raise ValidationError({
                    'quantity': (
                        f"Only {product.stock_count} unit(s) of "
                        f"'{product.name}' are available in stock."
                    )
                })

            cart_item.quantity = new_quantity
            cart_item.save(update_fields=['quantity', 'updated_at'])

        serializer = self.get_serializer(cart_item)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'])
    def clear(self, request):
        deleted_count, _ = self.get_queryset().delete()
        return Response({"detail" : f"Removed {deleted_count} item(s) from the cart."}, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        items = self.get_queryset()
        subtotal = sum(item.subtotal for item in items)

        return Response(
            {
                "total_count": items.count(),
                "total_quantity": sum(item.quantity for item in items),
                "subtotal": subtotal,
            }
        )