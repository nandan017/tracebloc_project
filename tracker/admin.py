from django.contrib import admin
from .models import Product, SupplyChainStep

# Register your models here.

# This tells Django to show the Product model in the admin interface
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'created_at')
    search_fields = ('name', 'sku')
    readonly_fields = ('id', 'created_at')
    filter_horizontal = ('authorized_users',)

@admin.register(SupplyChainStep)
class SupplyChainStepAdmin(admin.ModelAdmin):
    list_display = ('product', 'stage', 'location', 'timestamp')
    list_filter = ('stage',)
    search_fields = ('product__name', 'location')
