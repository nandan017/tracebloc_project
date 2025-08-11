# tracker/forms.py
from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group
from .models import Product, SupplyChainStep, Batch

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'sku', 'description']

class SupplyChainStepForm(forms.ModelForm):
    class Meta:
        model = SupplyChainStep
        fields = ['stage', 'location', 'document']

    def __init__(self, *args, **kwargs):
        allowed_choices = kwargs.pop('allowed_choices', None)
        super().__init__(*args, **kwargs)
        if allowed_choices is not None:
            self.fields['stage'].choices = [('', '---------')] + allowed_choices
        else:
            self.fields['stage'].choices = [('', '---------')] + self.Meta.model.STAGE_CHOICES

class CustomUserCreationForm(UserCreationForm):
    role = forms.ChoiceField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        role_choices = [(role, role) for role in settings.ROLE_PERMISSIONS.keys()]
        self.fields['role'].choices = role_choices

class BatchCreationForm(forms.ModelForm):
    products = forms.ModelMultipleChoiceField(
        queryset=None,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = Batch
        fields = ['name', 'batch_id', 'description']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['products'].queryset = Product.objects.filter(
                authorized_users=user,
                batch__isnull=True
            )