# tracker/views.py
import os
import json
from collections import defaultdict
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.models import Group
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.http import HttpResponse
from io import BytesIO
import qrcode
from django.urls import reverse
from django.contrib import messages
from .models import Product, SupplyChainStep, Batch
from .forms import (
    SupplyChainStepForm, ProductForm, CustomUserCreationForm, BatchCreationForm
)

# Load environment variables and set up Blockchain connection...
load_dotenv()
RPC_URL = os.getenv("POLYGON_AMOY_RPC_URL")
PRIVATE_KEY = os.getenv("SIGNER_PRIVATE_KEY")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")
if not all([RPC_URL, PRIVATE_KEY, CONTRACT_ADDRESS]):
    raise Exception("Please ensure blockchain environment variables are set.")
w3 = Web3(Web3.HTTPProvider(RPC_URL))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
account = w3.eth.account.from_key(PRIVATE_KEY)
abi_path = os.path.join(settings.BASE_DIR, 'tracker/contract_abi.json')
try:
    with open(abi_path, 'r') as f:
        contract_abi = json.load(f)
except FileNotFoundError:
    raise Exception(f"contract_abi.json not found.")
checksum_address = w3.to_checksum_address(CONTRACT_ADDRESS)
contract = w3.eth.contract(address=checksum_address, abi=contract_abi)

# --- HELPER FUNCTION ---
def get_available_stages_for_user(user):
    available_stages = []
    user_groups = user.groups.values_list('name', flat=True)
    for group in user_groups:
        available_stages.extend(settings.ROLE_PERMISSIONS.get(group, []))
    return sorted(list(set(available_stages)))

# --- VIEWS ---
def product_list(request):
    # ... (product_list view logic)
    queryset = Product.objects.all().order_by('-created_at')
    search_query = request.GET.get('q', '')
    stage_filter = request.GET.get('stage', '')
    if search_query:
        queryset = queryset.filter(Q(name__icontains=search_query) | Q(sku__icontains=search_query) | Q(description__icontains=search_query))
    if stage_filter:
        queryset = queryset.filter(steps__stage=stage_filter).distinct()
    paginator = Paginator(queryset, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    is_customer = request.user.is_authenticated and request.user.groups.filter(name='Customer').exists()
    context = {'page_obj': page_obj, 'is_customer': is_customer, 'stage_choices': SupplyChainStep.STAGE_CHOICES, 'search_query': search_query, 'stage_filter': stage_filter}
    return render(request, 'tracker/product_list.html', context)

def product_detail(request, product_id):
    # ... (product_detail view logic)
    product = get_object_or_404(Product, id=product_id)
    is_manager = False
    available_stages = []
    if request.user.is_authenticated and request.user in product.authorized_users.all():
        is_manager = request.user.groups.filter(name='Manager').exists()
        available_stages = get_available_stages_for_user(request.user)
    allowed_choices = [(stage, dict(SupplyChainStep.STAGE_CHOICES).get(stage)) for stage in available_stages]
    form = SupplyChainStepForm(allowed_choices=allowed_choices)
    context = {'product': product, 'form': form, 'is_manager': is_manager, 'available_stages': available_stages}
    return render(request, 'tracker/product_detail.html', context)

@login_required
@require_POST
def add_supply_chain_step(request, product_id):
    # ... (add_supply_chain_step view logic)
    product = get_object_or_404(Product, id=product_id)
    if request.user not in product.authorized_users.all():
        error_message = "You are not an authorized user for this product."
        response = render(request, 'tracker/partials/_error_toast.html', {'message': error_message})
        response['HX-Retarget'] = '#error-container'
        return response
    available_stages = get_available_stages_for_user(request.user)
    allowed_choices = [(stage, dict(SupplyChainStep.STAGE_CHOICES).get(stage)) for stage in available_stages]
    form = SupplyChainStepForm(request.POST, request.FILES, allowed_choices=allowed_choices)
    if form.is_valid():
        stage = form.cleaned_data['stage']
        if stage not in available_stages:
            error_message = f"Your role does not have permission to add a '{stage}' update."
            response = render(request, 'tracker/partials/_error_toast.html', {'message': error_message})
            response['HX-Retarget'] = '#error-container'
            return response
        try:
            new_step = form.save(commit=False)
            new_step.product = product
            tx = contract.functions.addUpdate(str(product.id), new_step.get_stage_display(), new_step.location).build_transaction({'from': account.address, 'nonce': w3.eth.get_transaction_count(account.address)})
            signed_tx = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
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
    else:
        return render(request, 'tracker/partials/_add_update_form.html', {'product': product, 'form': form})

def public_tracking_view(request, product_id):
    # ... (public_tracking_view logic)
    product = get_object_or_404(Product, id=product_id)
    return render(request, 'tracker/public_tracking_page.html', {'product': product})

@login_required
def create_product(request):
    # ... (create_product view logic)
    if request.user.groups.filter(name='Customer').exists():
        return redirect('product_list')
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.save()
            product.authorized_users.add(request.user)
            return redirect('product_detail', product_id=product.id)
    else:
        form = ProductForm()
    return render(request, 'tracker/create_product.html', {'form': form})

@login_required
def delete_product(request, product_id):
    # ... (delete_product view logic)
    product = get_object_or_404(Product, id=product_id)
    is_manager = request.user.groups.filter(name='Manager').exists()
    if request.user.is_superuser or is_manager:
        if request.method == 'POST':
            product.delete()
            return redirect('product_list')
    return redirect('product_detail', product_id=product.id)

@login_required
def profile_view(request):
    # ... (profile_view logic)
    user = request.user
    user_groups = user.groups.all()
    associated_products = Product.objects.filter(authorized_users=user).order_by('name')
    context = {'user_groups': user_groups, 'associated_products': associated_products}
    return render(request, 'registration/profile.html', context)

def register_view(request):
    # ... (register_view logic)
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            role_name = form.cleaned_data.get('role')
            role_group = Group.objects.get(name=role_name)
            user.groups.add(role_group)
            login(request, user)
            return redirect('product_list')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

def product_qr_code_view(request, product_id):
    # ... (product_qr_code_view logic)
    public_url = request.build_absolute_uri(reverse('public_tracking_page', args=[str(product_id)]))
    qr_image = qrcode.make(public_url, box_size=10, border=4)
    buffer = BytesIO()
    qr_image.save(buffer, format='PNG')
    return HttpResponse(buffer.getvalue(), content_type="image/png")

@login_required
def batch_list(request):
    # ... (batch_list view logic)
    batches = Batch.objects.all().order_by('-created_at')
    paginator = Paginator(batches, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    is_customer = request.user.groups.filter(name='Customer').exists()
    context = {'page_obj': page_obj, 'is_customer': is_customer}
    return render(request, 'tracker/batch_list.html', context)

@login_required
def batch_detail(request, batch_id):
    # ... (batch_detail view logic)
    batch = get_object_or_404(Batch, id=batch_id)
    available_stages = get_available_stages_for_user(request.user)
    allowed_choices = [(stage, dict(SupplyChainStep.STAGE_CHOICES).get(stage)) for stage in available_stages]
    form = SupplyChainStepForm(allowed_choices=allowed_choices)
    context = {'batch': batch, 'form': form}
    return render(request, 'tracker/batch_detail.html', context)

@login_required
@require_POST
def add_batch_step(request, batch_id):
    batch = get_object_or_404(Batch, id=batch_id)
    
    available_stages = get_available_stages_for_user(request.user)
    allowed_choices = [(stage, dict(SupplyChainStep.STAGE_CHOICES).get(stage)) for stage in available_stages]
    form = SupplyChainStepForm(request.POST, request.FILES, allowed_choices=allowed_choices)

    if form.is_valid():
        stage = form.cleaned_data['stage']
        location = form.cleaned_data['location']
        document = form.cleaned_data.get('document')

        if stage not in available_stages:
            error_message = f"Your role does not have permission to add a '{stage}' update."
            response = render(request, 'tracker/partials/_error_toast.html', {'message': error_message})
            response['HX-Retarget'] = '#error-container'
            return response

        products_in_batch = batch.products.all()
        successful_updates = 0
        
        try:
            # --- THIS IS THE CORRECTED NONCE LOGIC ---
            # Get the starting nonce BEFORE the loop
            current_nonce = w3.eth.get_transaction_count(account.address)

            for product in products_in_batch:
                new_step = SupplyChainStep(
                    product=product, stage=stage, location=location, document=document
                )
                
                # Build the transaction using the current nonce
                tx = contract.functions.addUpdate(
                    str(product.id), new_step.get_stage_display(), new_step.location
                ).build_transaction({
                    'from': account.address,
                    'nonce': current_nonce, # Use the correct, incrementing nonce
                })
                
                signed_tx = account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                w3.eth.wait_for_transaction_receipt(tx_hash)
                
                new_step.tx_hash = tx_hash.hex()
                new_step.save()
                successful_updates += 1
                
                # Increment the nonce for the next transaction in the loop
                current_nonce += 1
        
        except Exception as e:
            print(f"An error occurred during the batch blockchain transaction: {e}")
            error_message = f"An error occurred after {successful_updates} successful updates. Please check the logs."
            response = render(request, 'tracker/partials/_error_toast.html', {'message': error_message})
            response['HX-Retarget'] = '#error-container'
            return response
        # --- END OF CORRECTED LOGIC ---

        success_message = f"Update successfully added to {successful_updates} of {products_in_batch.count()} products."
        return render(request, 'tracker/partials/_success_toast.html', {'message': success_message})
    else:
        # Re-calculate choices for rendering the form with errors
        available_stages = get_available_stages_for_user(request.user)
        allowed_choices = [(stage, dict(SupplyChainStep.STAGE_CHOICES).get(stage)) for stage in available_stages]
        form.fields['stage'].choices = allowed_choices
        return render(request, 'tracker/partials/_add_update_form.html', {'batch': batch, 'form': form, 'object_id': batch.id, 'form_url': 'add_batch_step'})


@login_required
def create_batch(request):
    # ... (create_batch view logic)
    if request.method == 'POST':
        form = BatchCreationForm(request.POST, user=request.user)
        if form.is_valid():
            batch = form.save()
            selected_products = form.cleaned_data['products']
            selected_products.update(batch=batch)
            return redirect('batch_detail', batch_id=batch.id)
    else:
        form = BatchCreationForm(user=request.user)
    return render(request, 'tracker/batch_form.html', {'form': form})

@login_required
def edit_batch(request, batch_id):
    # ... (edit_batch view logic)
    batch = get_object_or_404(Batch, id=batch_id)
    if request.method == 'POST':
        form = BatchCreationForm(request.POST, user=request.user, instance=batch)
        if form.is_valid():
            current_products = set(batch.products.all())
            selected_products = set(form.cleaned_data['products'])
            products_to_add = selected_products - current_products
            for product in products_to_add:
                product.batch = batch
                product.save()
            products_to_remove = current_products - selected_products
            for product in products_to_remove:
                product.batch = None
                product.save()
            form.save()
            return redirect('batch_detail', batch_id=batch.id)
    else:
        form = BatchCreationForm(user=request.user, instance=batch, initial={'products': batch.products.all()})
    return render(request, 'tracker/batch_form.html', {'form': form, 'batch': batch})

def public_batch_view(request, batch_id):
    # ... (public_batch_view logic)
    batch = get_object_or_404(Batch, id=batch_id)
    return render(request, 'tracker/public_batch_page.html', {'batch': batch})

def batch_qr_code_view(request, batch_id):
    # ... (batch_qr_code_view logic)
    public_url = request.build_absolute_uri(reverse('public_batch_page', args=[str(batch_id)]))
    qr_image = qrcode.make(public_url, box_size=10, border=4)
    buffer = BytesIO()
    qr_image.save(buffer, format='PNG')
    return HttpResponse(buffer.getvalue(), content_type="image/png")

# --- THIS IS THE MISSING VIEW ---
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