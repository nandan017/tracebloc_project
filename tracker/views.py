from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST
from .models import Product, SupplyChainStep
from .forms import SupplyChainStepForm

# Create your views here.

def product_list(request):
    """A view to display a list of all products."""
    products = Product.objects.all().order_by('-created_at') # Get all products, newest first
    context = {
        'products': products
    }
    return render(request, 'tracker/product_list.html', context)

def product_detail(request, product_id):
    """A view to display the details of a single product."""
    product = get_object_or_404(Product, id=product_id) # Get the product or show a 404 error
    context = {
        'product': product
    }
    return render(request, 'tracker/product_detail.html', context)

@require_POST # This view only accepts POST requests
def add_supply_chain_step(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    form = SupplyChainStepForm(request.POST)
    if form.is_valid():
        # Create the object but don't save to DB yet
        new_step = form.save(commit=False)
        new_step.product = product # Assign the correct product
        new_step.save()

        # This is the key HTMX part: return just a piece of HTML
        context = {'step': new_step}
        return render(request, 'tracker/partials/_history_item.html', context)

    # Handle invalid form if necessary, though less likely with this simple form
    return # You could return an error message here