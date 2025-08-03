# tracker/views.py
import os
import json
from dotenv import load_dotenv
from web3 import Web3
from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST
from .models import Product
from .forms import SupplyChainStepForm

# Load environment variables from .env file
load_dotenv()

# --- Blockchain Connection Setup ---
RPC_URL = os.getenv("POLYGON_AMOY_RPC_URL")
PRIVATE_KEY = os.getenv("SIGNER_PRIVATE_KEY")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")

# Check if required environment variables are set
if not all([RPC_URL, PRIVATE_KEY, CONTRACT_ADDRESS]):
    raise Exception("Please ensure POLYGON_AMOY_RPC_URL, SIGNER_PRIVATE_KEY, and CONTRACT_ADDRESS are set in your .env file")

w3 = Web3(Web3.HTTPProvider(RPC_URL))
account = w3.eth.account.from_key(PRIVATE_KEY)

# Load contract ABI from the JSON file
abi_path = os.path.join(settings.BASE_DIR, 'tracker/contract_abi.json')
try:
    with open(abi_path, 'r') as f:
        contract_abi = json.load(f)
except FileNotFoundError:
    raise Exception(f"contract_abi.json not found at {abi_path}. Please create it.")

# --- THIS IS THE CORRECTED PART ---
# Convert the address to a checksum address before creating the contract object
checksum_address = w3.to_checksum_address(CONTRACT_ADDRESS)
contract = w3.eth.contract(address=checksum_address, abi=contract_abi)
# --- End of Correction ---

def product_list(request):
    """A view to display a list of all products."""
    products = Product.objects.all().order_by('-created_at')
    context = {
        'products': products
    }
    return render(request, 'tracker/product_list.html', context)


def product_detail(request, product_id):
    """A view to display the details of a single product."""
    product = get_object_or_404(Product, id=product_id)
    form = SupplyChainStepForm()
    context = {
        'product': product,
        'form': form,
    }
    return render(request, 'tracker/product_detail.html', context)


@require_POST # This view only accepts POST requests
def add_supply_chain_step(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    form = SupplyChainStepForm(request.POST)

    if form.is_valid():
        new_step = form.save(commit=False)
        new_step.product = product

        # --- Call the Smart Contract ---
        try:
            # Build Transaction
            tx = contract.functions.addUpdate(
                str(product.id),
                new_step.get_stage_display(),
                new_step.location
            ).build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address),
            })
            # Sign and send
            signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)

            # Wait for receipt and save the hash
            w3.eth.wait_for_transaction_receipt(tx_hash)
            new_step.tx_hash = tx_hash.hex()

            new_step.save() # Save the new step to the database

            context = {'step': new_step}
            return render(request, 'tracker/partials/_history_item.html', context)

        except Exception as e:
            # --- THIS IS THE NEW ERROR HANDLING LOGIC ---
            print(f"An error occurred during the blockchain transaction: {e}")

            # Create a response containing the error message
            error_message = "Transaction failed. Please check your connection and try again."
            response = render(request, 'tracker/partials/_error_toast.html', {'message': error_message})

            # Use a special HTMX header to retarget this response to the error container
            response['HX-Retarget'] = '#error-container'
            return response

    # This part handles an invalid form
    return render(request, 'tracker/product_detail.html', {'product': product, 'form': form})


def public_tracking_view(request, product_id):
    """A public, read-only view to display the full history of a product."""
    product = get_object_or_404(Product, id=product_id)
    context = {
        'product': product
    }
    return render(request, 'tracker/public_tracking_page.html', context)