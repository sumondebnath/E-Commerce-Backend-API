from django.utils.text import slugify
from rest_framework import serializers

from orders.models import Order
from products.models import Category, Product


def unique_category_slug(name, instance_pk=None):
    base = (slugify(name) or 'category')[:120]
    slug = base
    qs = Category.objects.exclude(pk=instance_pk)
    index = 2
    while qs.filter(slug=slug).exists():
        suffix = f'-{index}'
        slug = f"{base[:120 - len(suffix)]}{suffix}"
        index += 1
    return slug


class AdminProductSerializer(serializers.ModelSerializer):
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source='category',
        allow_null=True,
        required=False,
    )
    category_name = serializers.CharField(source='category.name', read_only=True)
    description = serializers.CharField(required=False, allow_blank=True, default='')

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'price', 'stock_count', 'image',
            'category_id', 'category_name', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'category_name', 'created_at', 'updated_at']

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError('Price must be non-negative.')
        return value

    def validate_stock_count(self, value):
        if value < 0:
            raise serializers.ValidationError('Stock must be non-negative.')
        return value


class StockUpdateSerializer(serializers.Serializer):
    stock_count = serializers.IntegerField(min_value=0)


class AdminCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description']
        read_only_fields = ['id', 'slug']

    def create(self, validated_data):
        validated_data['slug'] = unique_category_slug(validated_data['name'])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'name' in validated_data:
            validated_data['slug'] = unique_category_slug(
                validated_data['name'], instance.pk
            )
        return super().update(instance, validated_data)


class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[c[0] for c in Order.STATUS_CHOICES])

