from rest_framework import serializers
from .models import CartItem
from products.models import Product

class CartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(is_active=True), source='product', write_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_price = serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)
    product_image = serializers.ImageField(source='product.image', read_only=True)
    stock_available = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['id', 'product_id', 'product_name', 'product_price', 'product_image', 'stock_available', 'quantity', 'subtotal', "updated_at"]
        read_only_fields = ['id', 'updated_at']

    def get_subtotal(self, obj):
        return obj.subtotal

    def get_stock_available(self, obj):
        return obj.product.stock_count > 0
    
    def validate(self, attrs):
        product = attrs.get('product') or getattr(self.instance, 'product', None)
        quantity = attrs.get('quantity') or getattr(self.instance, 'quantity', 1)

        if product and quantity > product.stock_count:
            raise serializers.ValidationError(
                {
                    'quantity': f"Only {product.stock_count} unit(s) of '{product.name}' are available in stock."
                }
            )
        return attrs
    
    