from django.urls import path
from admin_views import DashboardStatsView, OrderManagementView, ProductStockUpdateView

urlpatterns = [
    path('dashboard/', DashboardStatsView.as_view(), name='admin_dashboard'),
    path('orders/<uuid:order_id>/status/', OrderManagementView.as_view(), name='admin_order_status'),
    path('products/<int:product_id>/stock/', ProductStockUpdateView.as_view(), name='admin_product_stock'),
]
