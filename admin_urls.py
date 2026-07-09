from django.urls import path
from admin_views import (
    DashboardStatsView,
    OrderManagementView,
    AdminOrderListView,
    AdminProductListView,
    AdminProductDetailView,
    ProductStockUpdateView,
    AdminCategoryListView,
    AdminCategoryDetailView,
)

urlpatterns = [
    path('dashboard/', DashboardStatsView.as_view(), name='admin_dashboard'),

    path('orders/', AdminOrderListView.as_view(), name='admin_order_list'),
    path('orders/<uuid:order_id>/status/', OrderManagementView.as_view(), name='admin_order_status'),

    path('products/', AdminProductListView.as_view(), name='admin_product_list'),
    path('products/<int:product_id>/', AdminProductDetailView.as_view(), name='admin_product_detail'),
    path('products/<int:product_id>/stock/', ProductStockUpdateView.as_view(), name='admin_product_stock'),

    path('categories/', AdminCategoryListView.as_view(), name='admin_category_list'),
    path('categories/<int:category_id>/', AdminCategoryDetailView.as_view(), name='admin_category_detail'),
]
