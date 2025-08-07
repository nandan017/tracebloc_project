from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group
from .models import Product, SupplyChainStep

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'sku', 'description']

class SupplyChainStepForm(forms.ModelForm):
    class Meta:
        model = SupplyChainStep
        # We only want the user to fill out these two fields
        fields = ['stage', 'location']

    def __init__(self, *args, **kwargs):
        allowed_choices = kwargs.pop('allowed_choices', None)
        super().__init__(*args, **kwargs)
        if allowed_choices is not None:
            self.fields['stage'].choices = allowed_choices

class CustomUserCreationForm(UserCreationForm):
    ROLE_CHOICES = (
        ('Supplier', 'Supplier'),
        ('Distributor', 'Distributor'),
        ('Retailer', 'Retailer'),
    )
    role = forms.ChoiceField(choices=ROLE_CHOICES)