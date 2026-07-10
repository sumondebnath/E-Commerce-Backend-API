from django.shortcuts import render
from rest_framework import viewsets, permissions, status, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Avg
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import Category, Product, Review, SaveProduct
from .serializers import CategorySerializer, ProductListSerializer, ProductDetailSerializer, ReviewSerializer, SaveProductSerializer

# Create your views here.

class IsStaffOrReadOnly(permissions.BasePermission):
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.is_staff
    

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsStaffOrReadOnly]
    # filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    # search_fields = ['name']
    # filterset_fields = ['name', 'slug']
    lookup_field = 'slug'


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductListSerializer
    permission_classes = [IsStaffOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ['name', 'description']
    filterset_fields = ['category', 'is_active']
    ordering_fields = ['price', 'stock_count', 'created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = Product.objects.select_related('category').prefetch_related('reviews')
        qs = qs.annotate(average_rating=Avg('reviews__rating'))

        if not (self.request.user.is_authenticated and self.request.user.is_staff):
            qs = qs.filter(is_active=True)
        return qs
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        return ProductDetailSerializer
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def save_to_watchlist(self, request, pk=None):
        product = self.get_object()
        serializer = SavedProductSerializer(data={'product' : product.id}, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    

class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product']

    def get_queryset(self):
        qs = Review.objects.select_related('user', 'product').all()
        product_id = self.request.query_params.get('product')
        if product_id:
            qs = qs.filter(product_id=product_id)
        elif self.request.user.is_authenticated:
            qs = qs.filter(user=self.request.user)
        return qs
    
    def perform_update(self, serializer):
        if serializer.instance.user != self.request.user:
            raise permissions.permissionDenied("You can only update your own reviews.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.user != self.request.user and not self.request.user.is_staff:
            raise permissions.permissionDenied("You can only delete your own reviews.")
        instance.delete()



class WishlistViewSet(viewsets.ModelViewSet):
    serializer_class = SaveProductSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        return SaveProduct.objects.filter(user=self.request.user).select_related('product')