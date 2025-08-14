from django.db import models
from django.contrib.auth.models import User
import uuid

# Create your models here.

class Batch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch_id = models.CharField(max_length=100, unique=True, help_text="A unique identifier for this batch")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Batches"

    def __str__(self):
        return f"{self.name} ({self.batch_id})"

class Product(models.Model):
    # A unique ID for each product, easier to handle than the default 1, 2, 3...
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=100, unique=True, help_text="Stock Keeping Unit")
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    authorized_users = models.ManyToManyField(User, related_name='tracked_products', blank=True)

    # New field to link a Product to a Batch
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')

    def __str__(self):
        return f"{self.name} ({self.sku})"
    
class SupplyChainStep(models.Model):
    STAGE_CHOICES = [
        ('sourcing', 'Sourcing'),
        ('manufacturing', 'Manufacturing'),
        ('processing', 'Processing'),
        ('packing', 'Packing'),
        ('shipping', 'Shipping'),
        ('delivery', 'Delivery'),
        ('retail', 'In Retail'),
    ]

    # Link to the product this step belongs to
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='steps')
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES)
    location = models.CharField(max_length=200)
    # New fields for coordinates
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    document = models.FileField(upload_to='step_documents/', blank=True, null=True)
    # We'll populate this later with the blockchain transaction hash
    tx_hash = models.CharField(max_length=66, blank=True, null=True)

    class Meta:
        ordering = ['timestamp'] # Order steps by when they happened

    def __str__(self):
        return f"{self.product.name} - {self.get_stage_display()}"
