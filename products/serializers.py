from rest_framework import serializers
from django.db import transaction
from .models import Category, Product, Review, SaveProduct

class CategorySerializer(serializers.ModelSerializer):
    products_count = serializers.IntegerField(source='products.count', read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'products_count']


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'user', 'user_name', 'product', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']

    def validate(self, attrs):
        request = self.context['request']
        product = attrs.get('product')
        if self.instance is None and Review.objects.filter(user=request.user, product=product).exists():
            raise serializers.ValidationError("You have already reviewed this product.")
        return attrs
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
    

class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'category_name', 'price', 'stock_count', 'image_url', 'is_active', 'average_rating', 'in_stock']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image:
            return request.build_absolute_uri(obj.image.url) if request else obj.image.url
        return None



class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), source='category', write_only=True, required=False, allow_null=True)
    image = serializers.ImageField(required=False,allow_null=True, write_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    review_count = serializers.IntegerField(source='reviews.count', read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'price', 'stock_count', 'image', 'image_url', 'is_active', 'category', 'category_id', 'reviews', 'average_rating', 'in_stock', 'review_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'image_url', 'created_at', 'updated_at']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image:
            return request.build_absolute_uri(obj.image.url) if request else obj.image.url
        return None

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Price must be a non-negative value.")
        return value
    

class SaveProductSerializer(serializers.ModelSerializer):
    product_detail = ProductListSerializer(source='product', read_only=True)

    class Meta:
        model = SaveProduct
        fields = ['id', 'product', 'product_detail', 'saved_at']
        read_only_fields = ['id', 'saved_at']

    def validate(self, attrs):
        request = self.context['request']
        product = attrs.get('product')
        if self.instance is None and SaveProduct.objects.filter(user=request.user, product=product).exists():
            raise serializers.ValidationError("You have already saved this product.")
        return attrs
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
    
    