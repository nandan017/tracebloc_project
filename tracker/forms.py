from django import forms
from .models import SupplyChainStep

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