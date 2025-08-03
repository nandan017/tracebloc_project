from django import forms
from .models import SupplyChainStep

class SupplyChainStepForm(forms.ModelForm):
    class Meta:
        model = SupplyChainStep
        # We only want the user to fill out these two fields
        fields = ['stage', 'location']