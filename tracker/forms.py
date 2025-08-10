from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group
from .models import Product, SupplyChainStep, Batch
from django.conf import settings

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
    # Define the field without choices initially
    role = forms.ChoiceField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the choices dynamically here, inside the __init__ method
        role_choices = [(role, role) for role in settings.ROLE_PERMISSIONS.keys()]
        self.fields['role'].choices = role_choices

class BatchCreationForm(forms.ModelForm):
    # This field will let us select products to add to the batch
    products = forms.ModelMultipleChoiceField(
        queryset=None, # We will set this in the view
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = Batch
        fields = ['name', 'batch_id', 'description']

    def __init__(self, *args, **kwargs):
        # We need the user to know which products to show
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            # Show only products that the user is authorized for AND are not already in a batch
            self.fields['products'].queryset = Product.objects.filter(
                authorized_users=user,
                batch__isnull=True
            )