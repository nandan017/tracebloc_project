from django.urls import path
from . import views

urlpatterns = [
    path('', views.product_list, name='product_list'),
    # The <uuid:product_id> part captures the ID from the URL and passes it to the view
    path('product/<uuid:product_id>/', views.product_detail, name='product_detail'),
     # New URL for adding a step
    path('product/<uuid:product_id>/add_step/', views.add_supply_chain_step, name='add_supply_chain_step'),
    # New URL for the public tracking page
    path('track/<uuid:product_id>/', views.public_tracking_view, name='public_tracking_page'),
    # New URL for generating the QR code image
    path('product/<uuid:product_id>/qr_code/', views.product_qr_code_view, name='product_qr_code'),
    # New URL for product creation
    path('product/create/', views.create_product, name='create_product'),
]
