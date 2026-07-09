from rest_framework import serializers
from accounts.models import Address
from .models import Order, OrderItem, Payment


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name_snapshot', 'quantity', 'price_at_purchase', 'line_total']
        read_only_fields = fields

    line_total = serializers.SerializerMethodField()

    def get_line_total(self, obj):
        return obj.line_total


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'payment_method', 'transaction_id', 'payment_status', 'amount', 'paid_at']
        read_only_fields = ['id', 'payment_status', 'paid_at']


class OrderListSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(source='items.count', read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'order_status', 'total_amount', 'item_count', 'created_at']


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    payment = PaymentSerializer(read_only=True)
    item_count = serializers.IntegerField(source='items.count', read_only=True)
    user = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_status', 'subtotal_cost', 'shipping_cost', 'total_amount',
            'shipping_full_name', 'shipping_street_address', 'shipping_city',
            'shipping_state', 'shipping_postal_code', 'shipping_country',
            'items', 'item_count', 'user', 'payment', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_user(self, obj):
        if obj.user:
            return {'email': obj.user.email}
        return None


class CheckoutSerializer(serializers.Serializer):
    """
    Input serializer for the checkout endpoint.
    Either pass `address_id` to use a saved address, or pass the
    shipping fields directly for a one-off address.
    """
    address_id = serializers.PrimaryKeyRelatedField(
        queryset=Address.objects.all(), source='address', required=False, allow_null=True
    )
    shipping_full_name = serializers.CharField(required=False)
    shipping_street_address = serializers.CharField(required=False)
    shipping_city = serializers.CharField(required=False)
    shipping_state = serializers.CharField(required=False)
    shipping_postal_code = serializers.CharField(required=False)
    shipping_country = serializers.CharField(required=False)

    payment_method = serializers.CharField(required=True)
    shipping_cost = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)

    def validate(self, attrs):
        request = self.context['request']
        address = attrs.get('address')

        if address:
            # BUSINESS LOGIC: a user can never check out using someone else's address
            if address.user_id != request.user.id:
                raise serializers.ValidationError({"address_id": "This address does not belong to you."})
        else:
            required_fields = [
                'shipping_full_name', 'shipping_street_address', 'shipping_city',
                'shipping_state', 'shipping_postal_code', 'shipping_country',
            ]
            missing = [f for f in required_fields if not attrs.get(f)]
            if missing:
                raise serializers.ValidationError(
                    {"address_id": f"Provide address_id or all of: {', '.join(missing)}"}
                )
        return attrs
