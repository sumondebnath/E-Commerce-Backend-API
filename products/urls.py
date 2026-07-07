from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, ProductViewSet, ReviewViewSet, WishlistViewSet

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r"reviews", ReviewViewSet, basename="review")
router.register(r"watchlist", WishlistViewSet, basename="watchlist")
router.register(r'', ProductViewSet, basename='product')

urlpatterns = [
    path("", include(router.urls)),
]