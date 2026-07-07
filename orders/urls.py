from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, CheckoutView, PaymentWebhookView

router = DefaultRouter()
router.register(r'', OrderViewSet, basename='order')

urlpatterns = [
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    path('payment-webhook/', PaymentWebhookView.as_view(), name='payment_webhook'),
    path('', include(router.urls)),
]
