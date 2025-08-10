# tracker/views.py
import os
import json
from dotenv import load_dotenv
from web3 import Web3
from django.db.models import Count
from collections import defaultdict
from django.db.models import Q
from django.core.paginator import Paginator
from web3.middleware import ExtraDataToPOAMiddleware
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.models import Group
from django.contrib import messages
from .models import Product, SupplyChainStep, Batch
from .forms import SupplyChainStepForm, ProductForm, CustomUserCreationForm
import qrcode
from io import BytesIO
from django.http import HttpResponse
from django.urls import reverse
from django.conf import settings

# Load environment variables from .env file
load_dotenv()

# --- Blockchain Connection Setup ---
RPC_URL = os.getenv("POLYGON_AMOY_RPC_URL")
PRIVATE_KEY = os.getenv("SIGNER_PRIVATE_KEY")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")

if not all([RPC_URL, PRIVATE_KEY, CONTRACT_ADDRESS]):
    raise Exception("Please ensure POLYGON_AMOY_RPC_URL, SIGNER_PRIVATE_KEY, and CONTRACT_ADDRESS are set in your .env file")

w3 = Web3(Web3.HTTPProvider(RPC_URL))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
account = w3.eth.account.from_key(PRIVATE_KEY)

abi_path = os.path.join(settings.BASE_DIR, 'tracker/contract_abi.json')
try:
    with open(abi_path, 'r') as f:
        contract_abi = json.load(f)
except FileNotFoundError:
    raise Exception(f"contract_abi.json not found at {abi_path}. Please create it.")

checksum_address = w3.to_checksum_address(CONTRACT_ADDRESS)
contract = w3.eth.contract(address=checksum_address, abi=contract_abi)
# --- End of Blockchain Setup ---


def product_list(request):
    # Start with all products
    queryset = Product.objects.all().order_by('-created_at')

    # Get search and filter parameters from the URL
    search_query = request.GET.get('q', '')
    stage_filter = request.GET.get('stage', '')

    # Apply search filter if a query is provided
    if search_query:
        queryset = queryset.filter(
            Q(name__icontains=search_query) |
            Q(sku__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Apply stage filter if a stage is selected
    if stage_filter:
        queryset = queryset.filter(steps__stage=stage_filter).distinct()

    # Apply pagination
    paginator = Paginator(queryset, 9) # Show 9 products per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get all possible stages for the filter dropdown
    stage_choices = SupplyChainStep.STAGE_CHOICES

    context = {
        'page_obj': page_obj,
        'is_customer': request.user.is_authenticated and request.user.groups.filter(name='Customer').exists(),
        'stage_choices': stage_choices,
        'search_query': search_query,
        'stage_filter': stage_filter,
    }
    return render(request, 'tracker/product_list.html', context)


def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    available_stages = []
    is_manager = False # Default to False

    if request.user.is_authenticated and request.user in product.authorized_users.all():
        user_groups = request.user.groups.values_list('name', flat=True)

        # Check if user is a manager
        if 'Manager' in user_groups:
            is_manager = True

        # Determine available stages based on roles
        for group in user_groups:
            available_stages.extend(settings.ROLE_PERMISSIONS.get(group, []))

    available_stages = sorted(list(set(available_stages)))
    allowed_choices = [(stage, dict(SupplyChainStep.STAGE_CHOICES).get(stage)) for stage in available_stages]
    form = SupplyChainStepForm(allowed_choices=allowed_choices)

    context = {
        'product': product,
        'form': form,
        'is_manager': is_manager, # Pass the manager flag to the template
    }
    return render(request, 'tracker/product_detail.html', context)


@login_required
@require_POST
def add_supply_chain_step(request, product_id):
    product = get_object_or_404(Product, id=product_id)

     # New permission check
    if request.user not in product.authorized_users.all():
        # Return an error if the user is not authorized for this product
        error_message = "You do not have permission to add an update to this product."
        response = render(request, 'tracker/partials/_error_toast.html', {'message': error_message})
        response['HX-Retarget'] = '#error-container'
        return response
    
     # --- New Granular Role-Based Permission Check ---
    stage = request.POST.get('stage')
    user_groups = request.user.groups.values_list('name', flat=True)

    # Check if the submitted stage is allowed for any of the user's roles
    is_authorized_for_stage = False
    for group in user_groups:
        if stage in settings.ROLE_PERMISSIONS.get(group, []):
            is_authorized_for_stage = True
            break

    if not is_authorized_for_stage:
        error_message = f"Your role does not have permission to add a '{stage}' update."
        response = render(request, 'tracker/partials/_error_toast.html', {'message': error_message})
        response['HX-Retarget'] = '#error-container'
        return response
    # --- End of New Check ---

    form = SupplyChainStepForm(request.POST)

    if form.is_valid():
        new_step = form.save(commit=False)
        new_step.product = product

        try:
            tx = contract.functions.addUpdate(
                str(product.id),
                new_step.get_stage_display(),
                new_step.location
            ).build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address),
            })
            signed_tx = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            w3.eth.wait_for_transaction_receipt(tx_hash)
            new_step.tx_hash = tx_hash.hex()
            new_step.save()
            context = {'step': new_step}
            return render(request, 'tracker/partials/_history_item.html', context)
        except Exception as e:
            print(f"An error occurred during the blockchain transaction: {e}")
            error_message = "Transaction failed. Please check your connection and try again."
            response = render(request, 'tracker/partials/_error_toast.html', {'message': error_message})
            response['HX-Retarget'] = '#error-container'
            return response
        
    # We must also re-calculate the allowed_choices for the form to render correctly
    available_stages = []
    if request.user.groups.filter(name='Supplier').exists():
        available_stages.extend(['sourcing', 'packing'])
    if request.user.groups.filter(name='Manufacturer').exists(): 
        available_stages.append('manufacturing')
    if request.user.groups.filter(name='Distributor').exists():
        available_stages.extend(['shipping', 'delivery'])
    if request.user.groups.filter(name='Retailer').exists():
        available_stages.append('shipping', 'delivery','retail') 
    allowed_choices = [(stage, dict(SupplyChainStep.STAGE_CHOICES).get(stage)) for stage in available_stages]
    form.fields['stage'].choices = allowed_choices
            
    return render(request, 'tracker/partials/_add_update_form.html', {'product': product, 'form': form})


def public_tracking_view(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    context = {
        'product': product
    }
    return render(request, 'tracker/public_tracking_page.html', context)

def product_qr_code_view(request, product_id):
    """Generates and serves a QR code image for a product's public tracking page."""
    # Construct the full, absolute URL for the public tracking page
    public_url = request.build_absolute_uri(
        reverse('public_tracking_page', args=[str(product_id)])
    )

    # Generate the QR code in memory
    qr_image = qrcode.make(public_url, box_size=10, border=4)

    # Create an in-memory buffer to save the image
    buffer = BytesIO()
    qr_image.save(buffer, format='PNG')

    # Return the buffer's content as an HTTP response with the correct content type
    return HttpResponse(buffer.getvalue(), content_type="image/png")

@login_required
def create_product(request):

    # New permission check: Deny access if user is in the 'Customer' group
    if request.user.groups.filter(name='Customer').exists():
        return redirect('product_list') # Or show a permission denied page

    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.save()
            # Automatically authorize the creator for this product
            product.authorized_users.add(request.user)
            return redirect('product_detail', product_id=product.id)
    else:
        form = ProductForm()

    return render(request, 'tracker/create_product.html', {'form': form})

def register_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Get the role from the form
            role_name = form.cleaned_data.get('role')
            # Find the group with that name and add the user to it
            role_group = Group.objects.get(name=role_name)
            user.groups.add(role_group)
            # Log the user in automatically
            login(request, user)
            return redirect('product_list')
    else:
        form = CustomUserCreationForm()

    return render(request, 'registration/register.html', {'form': form})

@login_required
def delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    # Check for high-level permission to delete
    is_manager = request.user.groups.filter(name='Manager').exists()
    if request.user.is_superuser or is_manager:
        if request.method == 'POST':
            product.delete()
            return redirect('product_list')

    # If not a manager/superuser or not a POST request, redirect
    return redirect('product_detail', product_id=product.id)


@login_required
def profile_view(request):
    # Get the current user
    user = request.user
    # Get all groups the user belongs to
    user_groups = user.groups.all()
    # Get all products this user is authorized to manage
    associated_products = Product.objects.filter(authorized_users=user).order_by('name')

    context = {
        'user_groups': user_groups,
        'associated_products': associated_products,
    }
    return render(request, 'registration/profile.html', context)

@login_required
def analytics_view(request):
    # Metric 1: Activity by Stage
    stage_counts = SupplyChainStep.objects.values('stage').annotate(count=Count('id')).order_by('stage')
    stage_labels = [dict(SupplyChainStep.STAGE_CHOICES).get(item['stage'], 'Unknown') for item in stage_counts]
    stage_data = [item['count'] for item in stage_counts]

    # Metric 2: Average Time Per Stage
    products = Product.objects.prefetch_related('steps').all()
    time_diffs = defaultdict(list)
    for product in products:
        steps = sorted(list(product.steps.all()), key=lambda x: x.timestamp)
        for i in range(len(steps) - 1):
            current_step = steps[i]
            next_step = steps[i+1]
            duration = next_step.timestamp - current_step.timestamp
            time_diffs[current_step.stage].append(duration.total_seconds())

    avg_times = {}
    for stage, durations in time_diffs.items():
        avg_seconds = sum(durations) / len(durations)
        avg_days = avg_seconds / (60 * 60 * 24)
        avg_times[dict(SupplyChainStep.STAGE_CHOICES).get(stage)] = round(avg_days, 2)

    # New KPI Card Data
    total_products = Product.objects.count()
    slowest_stage = max(avg_times, key=avg_times.get, default="N/A")

    avg_time_labels = list(avg_times.keys())
    avg_time_data = list(avg_times.values())

    context = {
        'stage_labels': stage_labels,
        'stage_data': stage_data,
        'avg_time_labels': avg_time_labels,
        'avg_time_data': avg_time_data,
        'total_products': total_products,
        'slowest_stage_name': slowest_stage,
        'slowest_stage_time': avg_times.get(slowest_stage, 0),
        'total_updates': sum(stage_data),
    }
    return render(request, 'tracker/analytics.html', context)

@login_required
def batch_list(request):
    batches = Batch.objects.all().order_by('-created_at')
    paginator = Paginator(batches, 10) # Show 10 batches per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'tracker/batch_list.html', {'page_obj': page_obj})


@login_required
def batch_detail(request, batch_id):
    batch = get_object_or_404(Batch, id=batch_id)

    # This is the same logic from product_detail to get available stages
    available_stages = []
    if request.user.is_authenticated:
        user_groups = request.user.groups.values_list('name', flat=True)
        for group in user_groups:
            available_stages.extend(settings.ROLE_PERMISSIONS.get(group, []))

    available_stages = sorted(list(set(available_stages)))
    allowed_choices = [(stage, dict(SupplyChainStep.STAGE_CHOICES).get(stage)) for stage in available_stages]
    form = SupplyChainStepForm(allowed_choices=allowed_choices)

    context = {
        'batch': batch,
        'form': form,
    }
    return render(request, 'tracker/batch_detail.html', context)


@login_required
@require_POST
def add_batch_step(request, batch_id):
    batch = get_object_or_404(Batch, id=batch_id)
    form = SupplyChainStepForm(request.POST) # We don't need choices here, just for validation

    if form.is_valid():
        stage = form.cleaned_data['stage']
        location = form.cleaned_data['location']

        products_in_batch = batch.products.all()
        for product in products_in_batch:
            # Create a new step for each product in the batch
            new_step = SupplyChainStep.objects.create(
                product=product,
                stage=stage,
                location=location
            )
            # Note: Blockchain transaction logic would go here for each step.
            # This can be very slow for large batches.

        messages.success(request, f"Successfully added '{dict(SupplyChainStep.STAGE_CHOICES).get(stage)}' update to {products_in_batch.count()} products in the batch.")
    else:
        messages.error(request, "There was an error with your submission.")

    return redirect('batch_detail', batch_id=batch.id)