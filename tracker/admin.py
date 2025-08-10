# tracker/admin.py
from django.contrib import admin
from .models import Product, SupplyChainStep, Batch

class ProductInline(admin.TabularInline):
    model = Product
    extra = 0  # Don't show any empty extra forms
    fields = ('name', 'sku')
    readonly_fields = ('name', 'sku')
    can_delete = False
    show_change_link = True

@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('name', 'batch_id', 'created_at')
    search_fields = ('name', 'batch_id')
    inlines = [ProductInline]

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'batch', 'created_at')
    search_fields = ('name', 'sku')
    list_filter = ('batch',)
    readonly_fields = ('id', 'created_at')
    filter_horizontal = ('authorized_users',)


@admin.register(SupplyChainStep)
class SupplyChainStepAdmin(admin.ModelAdmin):
    list_display = ('product', 'stage', 'location', 'timestamp')
    list_filter = ('stage',)
    search_fields = ('product__name', 'location')