"""
Personal Budget Manager with Plaid Integration
===============================================
Save this entire file as: web_budget_app.py

Installation:
    pip install flask plaid-python

Run:
    python web_budget_app.py

Open: http://localhost:5000
"""

from flask import Flask, render_template_string, request, jsonify
from datetime import datetime
import json
import os
from typing import Dict
import secrets
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Plaid imports
try:
    from plaid.api import plaid_api
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.products import Products
    from plaid.model.country_code import CountryCode
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    from plaid.model.transactions_sync_request import TransactionsSyncRequest
    import plaid
    from plaid.configuration import Configuration
    HAS_PLAID = True
except ImportError:
    HAS_PLAID = False
    print("⚠️ Plaid not installed. Run: pip install plaid-python")

# ==================== FLASK APP CONFIGURATION ====================
app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
DATA_FILE = "budget_data_web.json"

# ==================== PLAID CONFIGURATION ====================
PLAID_CLIENT_ID = os.getenv('PLAID_CLIENT_ID')
PLAID_SANDBOX_SECRET = os.getenv('PLAID_SANDBOX_SECRET')
PLAID_PRODUCTION_SECRET = os.getenv('PLAID_PRODUCTION_SECRET')
PLAID_ENVIRONMENT = os.getenv('PLAID_ENV', 'sandbox')

# Initialize Plaid client
plaid_client = None
if HAS_PLAID:
    secret = PLAID_SANDBOX_SECRET if PLAID_ENVIRONMENT == 'sandbox' else PLAID_PRODUCTION_SECRET
    host = plaid.Environment.Sandbox if PLAID_ENVIRONMENT == 'sandbox' else plaid.Environment.Production
    configuration = Configuration(
        host=host,
        api_key={
            'clientId': PLAID_CLIENT_ID,
            'secret': secret,
        }
    )
    api_client = plaid.ApiClient(configuration)
    plaid_client = plaid_api.PlaidApi(api_client)

# ==================== DATA MANAGEMENT FUNCTIONS ====================
def load_data() -> Dict:
    """Load data from JSON file"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {
        'income': [],
        'bills': [],
        'budget': {'groceries': 0.0, 'savings': 0.0, 'miscellaneous': 0.0},
        'transactions': [],
        'debt': [],
        'plaid_items': [],
        'recurring_patterns': [],  # NEW: Track detected recurring transactions
        'auto_categorized': {},     # NEW: Store auto-categorization rules
        'projected_bills': []       # NEW: Future bill projections
    }

def save_data(data: Dict):
    """Save data to JSON file"""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

def get_dashboard_stats(data: Dict) -> Dict:
    """Calculate dashboard statistics"""
    income = sum(i.get('amount', 0) for i in data.get('income', []))
    bills = sum(b.get('amount', 0) for b in data.get('bills', []))
    debt_min = sum(d.get('min_payment', 0) for d in data.get('debt', []))
    debt = sum(d.get('balance', 0) for d in data.get('debt', []))
    budget = data.get('budget', {})
    groceries = budget.get('groceries', 0)
    savings = budget.get('savings', 0)
    misc = budget.get('miscellaneous', 0)
    total_alloc = bills + debt_min + groceries + savings + misc

    return {
        'income': income,
        'bills': bills,
        'debt_min': debt_min,
        'debt': debt,
        'groceries': groceries,
        'savings': savings,
        'misc': misc,
        'total_alloc': total_alloc,
        'remaining': income - total_alloc
    }

# ==================== PLAID API ROUTES ====================
@app.route('/api/plaid/create_link_token', methods=['POST'])
def create_link_token():
    """Create a Plaid Link token"""
    if not plaid_client:
        return jsonify({'error': 'Plaid not configured'}), 400

    try:
        request_data = LinkTokenCreateRequest(
            products=[Products("transactions")],
            client_name="Personal Budget Manager",
            country_codes=[CountryCode('US')],
            language='en',
            user=LinkTokenCreateRequestUser(
                client_user_id='user-' + secrets.token_hex(8)
            )
        )
        response = plaid_client.link_token_create(request_data)
        return jsonify({'link_token': response['link_token']})
    except Exception as e:
        print(f"Error creating link token: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/plaid/exchange_public_token', methods=['POST'])
def exchange_public_token():
    """Exchange public token for access token"""
    if not plaid_client:
        return jsonify({'error': 'Plaid not configured'}), 400

    try:
        public_token = request.json.get('public_token')
        institution_name = request.json.get('institution_name', 'Bank Account')

        exchange_request = ItemPublicTokenExchangeRequest(
            public_token=public_token
        )
        exchange_response = plaid_client.item_public_token_exchange(exchange_request)
        access_token = exchange_response['access_token']

        data = load_data()
        data['plaid_items'].append({
            'institution_name': institution_name,
            'access_token': access_token,
            'item_id': exchange_response['item_id'],
            'created_at': datetime.now().isoformat(),
            'last_sync': None
        })
        save_data(data)

        return jsonify({'success': True})
    except Exception as e:
        print(f"Error exchanging token: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/plaid/sync_transactions', methods=['POST'])
def sync_transactions():
    """Sync transactions from all connected banks"""
    if not plaid_client:
        return jsonify({'error': 'Plaid not configured'}), 400

    data = load_data()
    total_imported = 0
    errors = []

    for item in data.get('plaid_items', []):
        try:
            access_token = item['access_token']
            cursor = item.get('cursor', None)  # Resume from last cursor
            has_more = True
            iterations = 0
            max_iterations = 20  # Prevent infinite loops

            while has_more and iterations < max_iterations:
                iterations += 1

                if cursor:
                    sync_request = TransactionsSyncRequest(
                        access_token=access_token,
                        cursor=cursor,
                        count=500  # Request more transactions per call
                    )
                else:
                    sync_request = TransactionsSyncRequest(
                        access_token=access_token,
                        count=500
                    )

                sync_response = plaid_client.transactions_sync(sync_request)

                print(f"Syncing batch {iterations}: {len(sync_response['added'])} transactions")

                for trans in sync_response['added']:
                    transaction = {
                        'date': str(trans['date']),
                        'amount': -float(trans['amount']),
                        'description': trans['name'],
                        'category': trans.get('category', ['Uncategorized'])[0] if trans.get('category') else 'Uncategorized',
                        'merchant_name': trans.get('merchant_name', trans['name'])
                    }

                    key = f"{transaction['date']}_{transaction['description']}_{transaction['amount']}"
                    existing_keys = [f"{t['date']}_{t['description']}_{t['amount']}" for t in data['transactions']]

                    if key not in existing_keys:
                        data['transactions'].append(transaction)
                        total_imported += 1

                has_more = sync_response['has_more']
                cursor = sync_response['next_cursor']

            # Save the cursor for next time
            item['cursor'] = cursor
            item['last_sync'] = datetime.now().isoformat()

        except Exception as e:
            errors.append(f"{item.get('institution_name', 'Unknown')}: {str(e)}")
            print(f"Error syncing transactions: {e}")

    save_data(data)

    print(f"Total transactions imported: {total_imported}")

    return jsonify({
        'success': True,
        'imported': total_imported,
        'errors': errors
    })

@app.route('/api/plaid/disconnect', methods=['POST'])
def disconnect_bank():
    """Disconnect a bank account"""
    item_id = request.json.get('item_id')
    data = load_data()
    data['plaid_items'] = [
        item for item in data['plaid_items']
        if item.get('item_id') != item_id
    ]
    save_data(data)
    return jsonify({'success': True})

# ==================== DATA API ROUTES ====================
@app.route('/api/income', methods=['GET', 'POST', 'DELETE'])
def handle_income():
    """Handle income CRUD operations"""
    data = load_data()

    if request.method == 'GET':
        return jsonify(data.get('income', []))

    elif request.method == 'POST':
        income_data = request.json
        data.setdefault('income', []).append({
            'source': income_data['source'],
            'amount': float(income_data['amount']),
            'frequency': income_data['frequency'],
            'date_added': datetime.now().isoformat()
        })
        save_data(data)
        return jsonify({'success': True})

    elif request.method == 'DELETE':
        index = request.json.get('index')
        if 0 <= index < len(data.get('income', [])):
            del data['income'][index]
            save_data(data)
            return jsonify({'success': True})
        return jsonify({'error': 'Invalid index'}), 400

@app.route('/api/bills', methods=['GET', 'POST', 'DELETE'])
def handle_bills():
    """Handle bills CRUD operations"""
    data = load_data()

    if request.method == 'GET':
        return jsonify(data.get('bills', []))

    elif request.method == 'POST':
        bill_data = request.json
        data.setdefault('bills', []).append({
            'name': bill_data['name'],
            'amount': float(bill_data['amount']),
            'due_day': int(bill_data['due_day']),
            'category': bill_data.get('category', 'Other')
        })
        save_data(data)
        return jsonify({'success': True})

    elif request.method == 'DELETE':
        index = request.json.get('index')
        if 0 <= index < len(data.get('bills', [])):
            del data['bills'][index]
            save_data(data)
            return jsonify({'success': True})
        return jsonify({'error': 'Invalid index'}), 400

@app.route('/api/budget', methods=['GET', 'POST'])
def handle_budget():
    """Handle budget operations"""
    data = load_data()

    if request.method == 'GET':
        return jsonify(data.get('budget', {}))

    elif request.method == 'POST':
        budget_data = request.json
        data['budget'] = {
            'groceries': float(budget_data.get('groceries', 0)),
            'savings': float(budget_data.get('savings', 0)),
            'miscellaneous': float(budget_data.get('miscellaneous', 0))
        }
        save_data(data)
        return jsonify({'success': True})

@app.route('/api/transactions', methods=['GET'])
def handle_transactions():
    """Get all transactions"""
    data = load_data()
    return jsonify(data.get('transactions', []))

@app.route('/api/debt', methods=['GET', 'POST', 'DELETE'])
def handle_debt():
    """Handle debt/credit card CRUD operations"""
    data = load_data()

    if request.method == 'GET':
        return jsonify(data.get('debt', []))

    elif request.method == 'POST':
        debt_data = request.json
        data.setdefault('debt', []).append({
            'name': debt_data['name'],
            'balance': float(debt_data['balance']),
            'interest_rate': float(debt_data['interest_rate']),
            'min_payment': float(debt_data['min_payment'])
        })
        save_data(data)
        return jsonify({'success': True})

    elif request.method == 'DELETE':
        index = request.json.get('index')
        if 0 <= index < len(data.get('debt', [])):
            del data['debt'][index]
            save_data(data)
            return jsonify({'success': True})
        return jsonify({'error': 'Invalid index'}), 400
@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    """Get dashboard data"""
    data = load_data()
    stats = get_dashboard_stats(data)

    # Get smart insights
    try:
        recurring = detect_recurring_transactions(data)
        categorized = auto_categorize_spending(data)
        projections = project_future_bills(data)
    except Exception as e:
        print(f"Error in smart insights: {e}")
        recurring = []
        categorized = {}
        projections = []

    return jsonify({
        'stats': stats,
        'plaid_items': data.get('plaid_items', []),
        'recent_transactions': data.get('transactions', [])[-10:][::-1],
        'recurring_bills': recurring,
        'categorized_spending': categorized,
        'projected_bills': projections
    })

# ==================== SMART AUTO-CATEGORIZATION ====================

def detect_recurring_transactions(data: Dict):
    """Detect recurring bills from transaction history"""
    from collections import defaultdict
    from datetime import datetime, timedelta

    transactions = data.get('transactions', [])
    if len(transactions) < 10:
        return []  # Need enough data

    # Group similar transactions by description
    grouped = defaultdict(list)
    for trans in transactions:
        # Normalize description (remove numbers, dates)
        desc = trans.get('description', '').lower()
        # Simple grouping by first few words
        key = ' '.join(desc.split()[:3])
        grouped[key].append(trans)

    recurring = []
    for desc, trans_list in grouped.items():
        if len(trans_list) >= 2:  # Appears at least twice
            # Check if amounts are similar
            amounts = [t['amount'] for t in trans_list]
            avg_amount = sum(amounts) / len(amounts)

            # Check if recurring (similar amount, different dates)
            if all(abs(amt - avg_amount) < avg_amount * 0.1 for amt in amounts):
                # Likely a recurring bill
                dates = [datetime.fromisoformat(t['date']) for t in trans_list]
                dates.sort()

                # Calculate average days between occurrences
                if len(dates) > 1:
                    intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
                    avg_interval = sum(intervals) / len(intervals)

                    # If roughly monthly (25-35 days)
                    if 25 <= avg_interval <= 35:
                        recurring.append({
                            'description': trans_list[0]['description'],
                            'amount': abs(avg_amount),
                            'frequency': 'Monthly',
                            'category': trans_list[0].get('category', 'Uncategorized'),
                            'last_date': str(dates[-1].date()),
                            'occurrences': len(trans_list)
                        })

    return recurring

def auto_categorize_spending(data: Dict):
    """Automatically categorize transactions into budget categories"""
    from datetime import datetime, timedelta

    transactions = data.get('transactions', [])
    now = datetime.now()
    thirty_days_ago = now - timedelta(days=30)  # Look back 30 days

    categorized = {
        'groceries': 0,
        'savings': 0,
        'miscellaneous': 0,
        'bills': 0,
        'income': 0
    }

    # Category mappings
    grocery_keywords = ['grocery', 'market', 'food', 'walmart', 'target', 'costco', 'whole foods', 'aldi', 'kroger', 'publix']
    bill_keywords = ['electric', 'water', 'gas', 'internet', 'phone', 'insurance', 'rent', 'mortgage', 'utilities', 'cable']

    # Income keywords
    income_keywords = ['payroll', 'salary', 'deposit', 'payment', 'direct dep', 'paycheck', 'wages', 'employer']

    # Ignore these (not real income)
    ignore_keywords = ['round-up', 'round up', 'transfer', 'refund', 'reversal', 'credit']

    # Look at last 30 days of transactions
    for trans in transactions:
        try:
            trans_date = datetime.fromisoformat(trans['date'])
            # Skip if older than 30 days
            if trans_date < thirty_days_ago:
                continue
        except:
            pass  # If date parsing fails, include it

        amount = trans.get('amount', 0)
        desc = trans.get('description', '').lower()
        category = trans.get('category', '').lower()

        if amount > 0:  # Positive amount (potential income)
            # Check if it should be ignored (small amounts like round-ups)
            if any(keyword in desc for keyword in ignore_keywords):
                continue  # Skip round-ups, refunds, etc.

            # Count as income if:
            # 1. It's explicitly labeled as income/payroll, OR
            # 2. It's a large deposit (over $100), OR
            # 3. It's a medium amount ($50-$100) that looks like income
            if any(keyword in desc for keyword in income_keywords):
                categorized['income'] += amount
            elif amount > 100:
                # Large deposits are likely income
                categorized['income'] += amount
            elif amount > 50 and 'transfer' not in desc and 'refund' not in desc:
                # Medium amounts that aren't transfers/refunds
                categorized['income'] += amount

        elif amount < 0:  # Expense
            abs_amount = abs(amount)

            # Check if it's a grocery expense
            if any(keyword in desc or keyword in category for keyword in grocery_keywords):
                categorized['groceries'] += abs_amount
            # Check if it's a bill
            elif any(keyword in desc or keyword in category for keyword in bill_keywords):
                categorized['bills'] += abs_amount
            else:
                categorized['miscellaneous'] += abs_amount

    return categorized

def project_future_bills(data: Dict):
    """Project upcoming bills for the next 3 months"""
    from datetime import datetime, timedelta

    bills = data.get('bills', [])
    recurring = detect_recurring_transactions(data)

    projections = []
    today = datetime.now()

    # Project existing bills
    for bill in bills:
        due_day = bill.get('due_day', 1)
        amount = bill.get('amount', 0)
        name = bill.get('name', 'Unknown')

        # Project for next 3 months
        for month_offset in range(3):
            future_date = today + timedelta(days=30 * month_offset)
            try:
                bill_date = future_date.replace(day=due_day)
            except ValueError:
                # Handle months with fewer days
                bill_date = future_date.replace(day=28)

            projections.append({
                'name': name,
                'amount': amount,
                'date': bill_date.strftime('%Y-%m-%d'),
                'type': 'manual_bill'
            })

    # Project detected recurring transactions
    for rec in recurring:
        last_date = datetime.fromisoformat(rec['last_date'])
        for month_offset in range(1, 4):  # Next 3 months
            next_date = last_date + timedelta(days=30 * month_offset)
            projections.append({
                'name': rec['description'],
                'amount': rec['amount'],
                'date': next_date.strftime('%Y-%m-%d'),
                'type': 'detected_recurring'
            })

    # Sort by date
    projections.sort(key=lambda x: x['date'])

    return projections

@app.route('/api/analyze_spending', methods=['GET'])
def analyze_spending():
    """Analyze spending patterns and detect recurring bills"""
    data = load_data()

    recurring = detect_recurring_transactions(data)
    categorized = auto_categorize_spending(data)
    projections = project_future_bills(data)

    return jsonify({
        'recurring_bills': recurring,
        'categorized_spending': categorized,
        'projected_bills': projections
    })

@app.route('/api/convert_to_bill', methods=['POST'])
def convert_to_bill():
    """Convert a detected recurring transaction into a tracked bill"""
    data = load_data()
    recurring_item = request.json

    # Add to bills
    data.setdefault('bills', []).append({
        'name': recurring_item['description'],
        'amount': float(recurring_item['amount']),
        'due_day': int(recurring_item.get('due_day', 1)),
        'category': recurring_item.get('category', 'Other'),
        'auto_detected': True
    })

    save_data(data)
    return jsonify({'success': True})
# ==================== MAIN ROUTE & HTML TEMPLATE ====================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, plaid_env=PLAID_ENVIRONMENT)

HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Personal Budget Manager</title>
    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .header p { opacity: 0.9; font-size: 1.1em; }

        .tabs {
            display: flex;
            background: #f8f9fa;
            border-bottom: 2px solid #e9ecef;
            overflow-x: auto;
        }
        .tab {
            padding: 15px 30px;
            cursor: pointer;
            border: none;
            background: none;
            font-size: 1em;
            font-weight: 500;
            color: #6c757d;
            transition: all 0.3s;
            white-space: nowrap;
        }
        .tab:hover { background: #e9ecef; color: #495057; }
        .tab.active {
            background: white;
            color: #667eea;
            border-bottom: 3px solid #667eea;
        }

        .tab-content { display: none; padding: 30px; }
        .tab-content.active { display: block; }

        .dashboard-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        .card.green { background: linear-gradient(135deg, #56ab2f 0%, #a8e063 100%); }
        .card.red { background: linear-gradient(135deg, #ff512f 0%, #dd2476 100%); }
        .card.blue { background: linear-gradient(135deg, #2196F3 0%, #21cbf3 100%); }
        .card.purple { background: linear-gradient(135deg, #8e2de2 0%, #4a00e0 100%); }
        .card h3 { font-size: 0.9em; opacity: 0.9; margin-bottom: 10px; }
        .card .amount { font-size: 2em; font-weight: bold; }

        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            font-weight: 500;
            transition: transform 0.2s;
            margin: 5px;
        }
        .btn:hover { transform: translateY(-2px); }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .btn-success { background: linear-gradient(135deg, #56ab2f 0%, #a8e063 100%); }
        .btn-danger { background: linear-gradient(135deg, #ff512f 0%, #dd2476 100%); }

        .form-group { margin-bottom: 20px; }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #495057;
        }
        .form-group input, .form-group select {
            width: 100%;
            padding: 12px;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            font-size: 1em;
        }
        .form-group input:focus, .form-group select:focus {
            outline: none;
            border-color: #667eea;
        }

        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        table thead { background: #f8f9fa; }
        table th, table td {
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #e9ecef;
        }
        table tr:hover { background: #f8f9fa; }

        .alert { padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; }
        .alert-info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }

        .plaid-connected {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 15px;
            background: #d4edda;
            border: 1px solid #c3e6cb;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        .plaid-connected .bank-name { font-weight: 600; color: #155724; }
        .plaid-connected .sync-time { color: #155724; font-size: 0.9em; }

        .breakdown {
            background: #f8f9fa;
            padding: 25px;
            border-radius: 10px;
            margin-top: 20px;
            font-family: 'Courier New', monospace;
            white-space: pre-wrap;
            line-height: 1.6;
        }

        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }

        @media (max-width: 768px) {
            .grid-2 { grid-template-columns: 1fr; }
            .dashboard-cards { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>💰 Personal Budget Manager</h1>
            <p>Automatic Bank Syncing with Plaid • Smart Budget Tracking</p>
        </div>

        <div class="tabs">
            <button class="tab active" onclick="showTab('dashboard', this)">📊 Dashboard</button>
            <button class="tab" onclick="showTab('bank', this)">🏦 Bank Connection</button>
            <button class="tab" onclick="showTab('income', this)">💵 Income</button>
            <button class="tab" onclick="showTab('bills', this)">📝 Bills</button>
            <button class="tab" onclick="showTab('budget', this)">🎯 Budget</button>
            <button class="tab" onclick="showTab('transactions', this)">💳 Transactions</button>
            <button class="tab" onclick="showTab('debt', this)">💳 Credit Cards</button>
        </div>

        <!-- DASHBOARD TAB -->
        <div id="dashboard" class="tab-content active">
            <h2>Financial Overview</h2>
            <div class="dashboard-cards">
                <div class="card green">
                    <h3>Monthly Income</h3>
                    <div class="amount" id="dash-income">$0.00</div>
                </div>
                <div class="card red">
                    <h3>Monthly Bills</h3>
                    <div class="amount" id="dash-bills">$0.00</div>
                </div>
                <div class="card purple">
                    <h3>Total Debt</h3>
                    <div class="amount" id="dash-debt">$0.00</div>
                </div>
                <div class="card blue">
                    <h3>Remaining</h3>
                    <div class="amount" id="dash-remaining">$0.00</div>
                </div>
            </div>
            <!-- AI Financial Coach -->
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 25px; border-radius: 15px; margin-top: 30px; box-shadow: 0 4px 15px rgba(0,0,0,0.2);">
                <h3 style="margin-bottom: 20px;">🤖 AI Financial Coach</h3>
                <div id="ai-insights" style="line-height: 1.8;"></div>
            </div>

            <!-- NEW: Smart Insights Section -->
            <div style="margin-top: 40px;">
                <h3>🤖 Smart Insights</h3>

                <!-- Detected Recurring Bills -->
                <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 20px; border-radius: 10px; margin-top: 20px;">
                    <h4 style="color: #856404; margin-bottom: 15px;">💡 Detected Recurring Bills</h4>
                    <div id="recurring-bills-list"></div>
                </div>

                <!-- Auto-Categorized Spending -->
                <div style="background: #d1ecf1; border: 1px solid #bee5eb; padding: 20px; border-radius: 10px; margin-top: 20px;">
                    <h4 style="color: #0c5460; margin-bottom: 15px;">📊 Auto-Categorized Spending (This Month)</h4>
                    <div id="auto-categorized"></div>
                </div>

                <!-- Projected Future Bills -->
                <div style="background: #f8d7da; border: 1px solid #f5c6cb; padding: 20px; border-radius: 10px; margin-top: 20px;">
                    <h4 style="color: #721c24; margin-bottom: 15px;">📅 Upcoming Bills (Next 90 Days)</h4>
                    <div id="projected-bills"></div>
                </div>
            </div>

            <!-- NEW: Smart Insights Section -->
            <div style="margin-top: 40px;">
                <h3>🤖 Smart Insights</h3>

                <!-- Detected Recurring Bills -->
                <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 20px; border-radius: 10px; margin-top: 20px;">
                    <h4 style="color: #856404; margin-bottom: 15px;">💡 Detected Recurring Bills</h4>
                    <div id="recurring-bills-list"></div>
                </div>

                <!-- Auto-Categorized Spending -->
                <div style="background: #d1ecf1; border: 1px solid #bee5eb; padding: 20px; border-radius: 10px; margin-top: 20px;">
                    <h4 style="color: #0c5460; margin-bottom: 15px;">📊 Auto-Categorized Spending (This Month)</h4>
                    <div id="auto-categorized"></div>
                </div>

                <!-- Projected Future Bills -->
                <div style="background: #f8d7da; border: 1px solid #f5c6cb; padding: 20px; border-radius: 10px; margin-top: 20px;">
                    <h4 style="color: #721c24; margin-bottom: 15px;">📅 Upcoming Bills (Next 90 Days)</h4>
                    <div id="projected-bills"></div>
                </div>
            </div>

            <h3 style="margin-top: 30px;">Recent Transactions</h3>

            <table id="recent-transactions">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Description</th>
                        <th>Category</th>
                        <th>Amount</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>

        <!-- BANK CONNECTION TAB -->
        <div id="bank" class="tab-content">
            <h2>🏦 Bank Connection (Plaid)</h2>
            <div class="alert alert-info">
                <strong>Automatic Syncing:</strong> Connect your bank account to automatically import transactions.
                <br>Current mode: <strong id="plaid-env">{{ plaid_env|upper }}</strong>
            </div>
            <div id="plaid-items-list"></div>
            <div style="margin-top: 20px;">
                <button class="btn btn-success" onclick="connectBank()">➕ Connect New Bank</button>
                <button class="btn" id="sync-btn" onclick="syncTransactions()">🔄 Sync All Transactions</button>
            </div>
        </div>

        <!-- INCOME TAB -->
        <div id="income" class="tab-content">
            <h2>💵 Income Sources</h2>
            <div class="grid-2">
                <div>
                    <h3>Add Income</h3>
                    <div class="form-group">
                        <label>Source</label>
                        <input type="text" id="income-source" placeholder="e.g., Salary, Freelance">
                    </div>
                    <div class="form-group">
                        <label>Amount ($)</label>
                        <input type="number" id="income-amount" placeholder="0.00" step="0.01">
                    </div>
                    <div class="form-group">
                        <label>Frequency</label>
                        <select id="income-frequency">
                            <option>Monthly</option>
                            <option>Bi-weekly</option>
                            <option>Weekly</option>
                            <option>One-time</option>
                        </select>
                    </div>
                    <button class="btn btn-success" onclick="addIncome()">Add Income</button>
                </div>
                <div>
                    <h3>Income List</h3>
                    <table id="income-table">
                        <thead>
                            <tr>
                                <th>Source</th>
                                <th>Amount</th>
                                <th>Frequency</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- BILLS TAB -->
        <div id="bills" class="tab-content">
            <h2>📝 Bills & Expenses</h2>
            <div class="grid-2">
                <div>
                    <h3>Add Bill</h3>
                    <div class="form-group">
                        <label>Bill Name</label>
                        <input type="text" id="bill-name" placeholder="e.g., Electric, Rent">
                    </div>
                    <div class="form-group">
                        <label>Amount ($)</label>
                        <input type="number" id="bill-amount" placeholder="0.00" step="0.01">
                    </div>
                    <div class="form-group">
                        <label>Due Day (1-31)</label>
                        <input type="number" id="bill-day" placeholder="15" min="1" max="31">
                    </div>
                    <div class="form-group">
                        <label>Category</label>
                        <select id="bill-category">
                            <option>Utilities</option>
                            <option>Rent/Mortgage</option>
                            <option>Insurance</option>
                            <option>Subscriptions</option>
                            <option>Other</option>
                        </select>
                    </div>
                    <button class="btn btn-success" onclick="addBill()">Add Bill</button>
                </div>
                <div>
                    <h3>Bills List</h3>
                    <table id="bills-table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Amount</th>
                                <th>Due Day</th>
                                <th>Category</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- BUDGET TAB -->
        <div id="budget" class="tab-content">
            <h2>🎯 Budget Categories</h2>
            <div style="max-width: 600px;">
                <div class="form-group">
                    <label>Groceries (Monthly)</label>
                    <input type="number" id="budget-groceries" placeholder="0.00" step="0.01">
                </div>
                <div class="form-group">
                    <label>Savings (Monthly)</label>
                    <input type="number" id="budget-savings" placeholder="0.00" step="0.01">
                </div>
                <div class="form-group">
                    <label>Miscellaneous Spending (Monthly)</label>
                    <input type="number" id="budget-misc" placeholder="0.00" step="0.01">
                </div>
                <button class="btn btn-success" onclick="saveBudget()">Save Budget</button>
            </div>
        </div>

        <!-- TRANSACTIONS TAB -->
        <div id="transactions" class="tab-content">
            <h2>💳 All Transactions</h2>
            <div class="alert alert-info">
                Transactions are automatically imported when you sync your connected bank accounts.
            </div>
            <button class="btn" onclick="loadTransactions()">🔄 Refresh</button>
            <table id="transactions-table" style="margin-top: 20px;">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Description</th>
                        <th>Category</th>
                        <th>Amount</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>

        <!-- DEBT TAB -->
        <div id="debt" class="tab-content">
            <h2>💳 Credit Card Debt</h2>
            <div class="grid-2">
                <div>
                    <h3>Add Credit Card</h3>
                    <div class="form-group">
                        <label>Card Name</label>
                        <input type="text" id="debt-name" placeholder="e.g., Chase Sapphire">
                    </div>
                    <div class="form-group">
                        <label>Balance ($)</label>
                        <input type="number" id="debt-balance" placeholder="0.00" step="0.01">
                    </div>
                    <div class="form-group">
                        <label>APR (%)</label>
                        <input type="number" id="debt-apr" placeholder="18.99" step="0.01">
                    </div>
                    <div class="form-group">
                        <label>Minimum Payment ($)</label>
                        <input type="number" id="debt-min" placeholder="25.00" step="0.01">
                    </div>
                    <button class="btn btn-success" onclick="addDebt()">Add Card</button>
                </div>
                <div>
                    <h3>Credit Cards</h3>
                    <table id="debt-table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Balance</th>
                                <th>APR</th>
                                <th>Min Payment</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script>
// Global variables
const PLAID_ENV = '{{ plaid_env }}';

// Tab switching function
function showTab(tabName, clickedButton) {
    console.log('showTab called with:', tabName);

    // Hide all tab contents
    const allContents = document.querySelectorAll('.tab-content');
    allContents.forEach(function(content) {
        content.style.display = 'none';
        content.classList.remove('active');
    });

    // Remove active from all tab buttons
    const allTabs = document.querySelectorAll('.tab');
    allTabs.forEach(function(tab) {
        tab.classList.remove('active');
    });

    // Show the selected content
    const selectedContent = document.getElementById(tabName);
    if (selectedContent) {
        selectedContent.style.display = 'block';
        selectedContent.classList.add('active');
        console.log('Showing tab:', tabName);
    } else {
        console.error('Tab not found:', tabName);
    }

    // Add active class to the clicked button
    if (clickedButton) {
        clickedButton.classList.add('active');
    }

    // Load data for the selected tab
    if (tabName === 'dashboard') loadDashboard();
    if (tabName === 'bank') loadPlaidItems();
    if (tabName === 'income') loadIncome();
    if (tabName === 'bills') loadBills();
    if (tabName === 'budget') loadBudgetForm();
    if (tabName === 'transactions') loadTransactions();
    if (tabName === 'debt') loadDebt();
}

// Dashboard functions
async function loadDashboard() {
    try {
        const response = await fetch('/api/dashboard');
        const data = await response.json();
        const stats = data.stats;

        // Use auto-categorized data if manual data is empty
        const displayIncome = stats.income > 0 ? stats.income : (data.categorized_spending?.income || 0);
        const displayBills = stats.bills > 0 ? stats.bills : (data.categorized_spending?.bills || 0);

        document.getElementById('dash-income').textContent = '$' + displayIncome.toFixed(2);
        document.getElementById('dash-bills').textContent = '$' + displayBills.toFixed(2);
        document.getElementById('dash-debt').textContent = '$' + stats.debt.toFixed(2);

        const remainingCalc = displayIncome - stats.total_alloc;
        const remainingText = remainingCalc >= 0
            ? '$' + remainingCalc.toFixed(2)
            : '-$' + Math.abs(remainingCalc).toFixed(2);
        document.getElementById('dash-remaining').textContent = remainingText;

        // Generate AI Financial Coach insights
        generateAIInsights(data, displayIncome, stats);

        const tbody = document.querySelector('#recent-transactions tbody');
        tbody.innerHTML = data.recent_transactions.map(t => `
            <tr>
                <td>${t.date}</td>
                <td>${t.description}</td>
                <td>${t.category}</td>
                <td style="color: ${t.amount >= 0 ? 'green' : 'red'}; font-weight: bold;">
                    $${t.amount.toFixed(2)}
                </td>
            </tr>
        `).join('');

        // NEW: Load smart insights
        if (data.recurring_bills && data.recurring_bills.length > 0) {
            const recurringDiv = document.getElementById('recurring-bills-list');
            recurringDiv.innerHTML = data.recurring_bills.map(bill => `
                <div style="background: white; padding: 15px; margin-bottom: 10px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong>${bill.description}</strong>
                        <div style="color: #666; font-size: 0.9em;">
                            $${bill.amount.toFixed(2)} • ${bill.frequency} • Detected ${bill.occurrences} times
                        </div>
                    </div>
                    <button class="btn btn-success" onclick="convertToBill('${bill.description.replace(/'/g, "\\'")}', ${bill.amount})">
                        Add as Bill
                    </button>
                </div>
            `).join('');
        } else {
            document.getElementById('recurring-bills-list').innerHTML =
                '<p style="color: #856404;">No recurring patterns detected yet. Connect your bank and sync more transactions.</p>';
        }

        // Auto-categorized spending
        if (data.categorized_spending) {
            const catDiv = document.getElementById('auto-categorized');
            const cats = data.categorized_spending;
            catDiv.innerHTML = `
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    <div style="background: white; padding: 15px; border-radius: 8px;">
                        <div style="color: #666; font-size: 0.9em;">Groceries</div>
                        <div style="font-size: 1.5em; font-weight: bold; color: #ff6b6b;">$${(cats.groceries || 0).toFixed(2)}</div>
                    </div>
                    <div style="background: white; padding: 15px; border-radius: 8px;">
                        <div style="color: #666; font-size: 0.9em;">Bills</div>
                        <div style="font-size: 1.5em; font-weight: bold; color: #ff6b6b;">$${(cats.bills || 0).toFixed(2)}</div>
                    </div>
                    <div style="background: white; padding: 15px; border-radius: 8px;">
                        <div style="color: #666; font-size: 0.9em;">Miscellaneous</div>
                        <div style="font-size: 1.5em; font-weight: bold; color: #ff6b6b;">$${(cats.miscellaneous || 0).toFixed(2)}</div>
                    </div>
                    <div style="background: white; padding: 15px; border-radius: 8px;">
                        <div style="color: #666; font-size: 0.9em;">Income</div>
                        <div style="font-size: 1.5em; font-weight: bold; color: #51cf66;">$${(cats.income || 0).toFixed(2)}</div>
                    </div>
                </div>
            `;
        }

        // Projected bills
        if (data.projected_bills && data.projected_bills.length > 0) {
            const projDiv = document.getElementById('projected-bills');
            projDiv.innerHTML = data.projected_bills.slice(0, 10).map(bill => `
                <div style="background: white; padding: 12px; margin-bottom: 8px; border-radius: 8px; display: flex; justify-content: space-between;">
                    <div>
                        <strong>${bill.name}</strong>
                        <span style="color: #666; margin-left: 10px;">${bill.date}</span>
                    </div>
                    <div style="font-weight: bold; color: #e03131;">$${bill.amount.toFixed(2)}</div>
                </div>
            `).join('');
        } else {
            document.getElementById('projected-bills').innerHTML =
                '<p style="color: #721c24;">No upcoming bills projected yet.</p>';
        }

    } catch (error) {
        console.error('Error loading dashboard:', error);
        alert('Error loading dashboard data');
    }
}

// Plaid functions
async function connectBank() {
    console.log('connectBank() called');

    try {
        const response = await fetch('/api/plaid/create_link_token', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();
        console.log('Link token response:', data);

        if (data.error) {
            alert('Error: ' + data.error);
            return;
        }

        const handler = Plaid.create({
            token: data.link_token,
            onSuccess: async (public_token, metadata) => {
                console.log('Plaid Link success!', metadata);

                const exchangeResponse = await fetch('/api/plaid/exchange_public_token', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        public_token: public_token,
                        institution_name: metadata.institution.name
                    })
                });

                const exchangeData = await exchangeResponse.json();

                if (exchangeData.success) {
                    alert('Bank connected successfully!');
                    loadPlaidItems();
                } else {
                    alert('Error connecting bank: ' + (exchangeData.error || 'Unknown error'));
                }
            },
            onExit: (err, metadata) => {
                if (err) {
                    console.error('Plaid Link error:', err);
                }
                console.log('Plaid Link exit:', metadata);
            }
        });

        handler.open();

    } catch (error) {
        console.error('Error in connectBank:', error);
        alert('Error: ' + error.message);
    }
}

async function syncTransactions() {
    const btn = document.getElementById('sync-btn');
    btn.disabled = true;
    btn.textContent = '🔄 Syncing...';

    try {
        const response = await fetch('/api/plaid/sync_transactions', {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
    let message = 'Synced ' + data.imported + ' new transaction(s)';
    if (data.errors && data.errors.length > 0) {
        message += '\n\nErrors:\n' + data.errors.join('\n');
    }
            alert(message);
            loadDashboard();
        } else {
            alert('Error syncing transactions');
        }
    } catch (error) {
        console.error('Error syncing transactions:', error);
        alert('Error syncing transactions');
    } finally {
        btn.disabled = false;
        btn.textContent = '🔄 Sync All Transactions';
    }
}

async function loadPlaidItems() {
    try {
        const response = await fetch('/api/dashboard');
        const data = await response.json();

        const listDiv = document.getElementById('plaid-items-list');

        if (data.plaid_items && data.plaid_items.length > 0) {
            listDiv.innerHTML = data.plaid_items.map(item => `
                <div class="plaid-connected">
                    <div>
                        <div class="bank-name">🏦 ${item.institution_name}</div>
                        <div class="sync-time">
                            Connected: ${new Date(item.created_at).toLocaleDateString()}
                            ${item.last_sync ? ' • Last sync: ' + new Date(item.last_sync).toLocaleString() : ''}
                        </div>
                    </div>
                    <button class="btn btn-danger" onclick="disconnectBank('${item.item_id}')">
                        Disconnect
                    </button>
                </div>
            `).join('');
        } else {
            listDiv.innerHTML = '<p style="color: #6c757d;">No banks connected yet.</p>';
        }
    } catch (error) {
        console.error('Error loading Plaid items:', error);
    }
}

async function disconnectBank(itemId) {
    if (!confirm('Are you sure you want to disconnect this bank?')) {
        return;
    }

    try {
        const response = await fetch('/api/plaid/disconnect', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ item_id: itemId })
        });

        const data = await response.json();

        if (data.success) {
            alert('Bank disconnected');
            loadPlaidItems();
        }
    } catch (error) {
        console.error('Error disconnecting bank:', error);
        alert('Error disconnecting bank');
    }
}

// Income functions
async function addIncome() {
    const source = document.getElementById('income-source').value.trim();
    const amount = parseFloat(document.getElementById('income-amount').value);
    const frequency = document.getElementById('income-frequency').value;

    if (!source || !amount || amount <= 0) {
        alert('Please fill in all fields with valid values');
        return;
    }

    try {
        const response = await fetch('/api/income', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ source, amount, frequency })
        });

        const data = await response.json();

        if (data.success) {
            document.getElementById('income-source').value = '';
            document.getElementById('income-amount').value = '';
            loadIncome();
            alert('Income added successfully!');
        }
    } catch (error) {
        console.error('Error adding income:', error);
        alert('Error adding income');
    }
}

async function loadIncome() {
    try {
        const response = await fetch('/api/income');
        const items = await response.json();

        const tbody = document.querySelector('#income-table tbody');
        tbody.innerHTML = items.map((item, index) => `
            <tr>
                <td>${item.source}</td>
                <td>$${item.amount.toFixed(2)}</td>
                <td>${item.frequency}</td>
                <td>
                    <button class="btn btn-danger" onclick="deleteIncome(${index})">
                        Delete
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Error loading income:', error);
    }
}

async function deleteIncome(index) {
    if (!confirm('Are you sure you want to delete this income?')) {
        return;
    }

    try {
        const response = await fetch('/api/income', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ index })
        });

        const data = await response.json();

        if (data.success) {
            loadIncome();
            alert('Income deleted');
        }
    } catch (error) {
        console.error('Error deleting income:', error);
        alert('Error deleting income');
    }
}

// Bills functions
async function addBill() {
    const name = document.getElementById('bill-name').value.trim();
    const amount = parseFloat(document.getElementById('bill-amount').value);
    const due_day = parseInt(document.getElementById('bill-day').value);
    const category = document.getElementById('bill-category').value;

    if (!name || !amount || amount <= 0 || !due_day || due_day < 1 || due_day > 31) {
        alert('Please fill in all fields with valid values');
        return;
    }

    try {
        const response = await fetch('/api/bills', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name, amount, due_day, category })
        });

        const data = await response.json();

        if (data.success) {
            document.getElementById('bill-name').value = '';
            document.getElementById('bill-amount').value = '';
            document.getElementById('bill-day').value = '';
            loadBills();
            alert('Bill added successfully!');
        }
    } catch (error) {
        console.error('Error adding bill:', error);
        alert('Error adding bill');
    }
}

async function loadBills() {
    try {
        const response = await fetch('/api/bills');
        const items = await response.json();

        const tbody = document.querySelector('#bills-table tbody');
        tbody.innerHTML = items.map((item, index) => `
            <tr>
                <td>${item.name}</td>
                <td>$${item.amount.toFixed(2)}</td>
                <td>${item.due_day}</td>
                <td>${item.category}</td>
                <td>
                    <button class="btn btn-danger" onclick="deleteBill(${index})">
                        Delete
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Error loading bills:', error);
    }
}

async function deleteBill(index) {
    if (!confirm('Are you sure you want to delete this bill?')) {
        return;
    }

    try {
        const response = await fetch('/api/bills', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ index })
        });

        const data = await response.json();

        if (data.success) {
            loadBills();
            alert('Bill deleted');
        }
    } catch (error) {
        console.error('Error deleting bill:', error);
        alert('Error deleting bill');
    }
}

// Budget functions
async function saveBudget() {
    const groceries = parseFloat(document.getElementById('budget-groceries').value) || 0;
    const savings = parseFloat(document.getElementById('budget-savings').value) || 0;
    const miscellaneous = parseFloat(document.getElementById('budget-misc').value) || 0;

    try {
        const response = await fetch('/api/budget', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ groceries, savings, miscellaneous })
        });

        const data = await response.json();

        if (data.success) {
            alert('Budget saved successfully!');
            loadDashboard();
        }
    } catch (error) {
        console.error('Error saving budget:', error);
        alert('Error saving budget');
    }
}

async function loadBudgetForm() {
    try {
        const response = await fetch('/api/budget');
        const budget = await response.json();

        document.getElementById('budget-groceries').value = budget.groceries || 0;
        document.getElementById('budget-savings').value = budget.savings || 0;
        document.getElementById('budget-misc').value = budget.miscellaneous || 0;
    } catch (error) {
        console.error('Error loading budget:', error);
    }
}

// Transactions functions
async function loadTransactions() {
    try {
        const response = await fetch('/api/transactions');
        const items = await response.json();

        const tbody = document.querySelector('#transactions-table tbody');
        const recentTransactions = items.reverse(); // Show all transactions

        tbody.innerHTML = recentTransactions.map(t => `
            <tr>
                <td>${t.date}</td>
                <td>${t.description}</td>
                <td>${t.category}</td>
                <td style="color: ${t.amount >= 0 ? 'green' : 'red'}; font-weight: bold;">
                    $${t.amount.toFixed(2)}
                </td>
            </tr>
        `).join('');

        if (recentTransactions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #6c757d;">No transactions yet. Connect your bank to sync transactions.</td></tr>';
        }
    } catch (error) {
        console.error('Error loading transactions:', error);
    }
}

// Debt/Credit Card functions
async function addDebt() {
    const name = document.getElementById('debt-name').value.trim();
    const balance = parseFloat(document.getElementById('debt-balance').value);
    const interest_rate = parseFloat(document.getElementById('debt-apr').value) || 0;
    const min_payment = parseFloat(document.getElementById('debt-min').value) || 0;

    if (!name || !balance || balance <= 0) {
        alert('Please fill in name and balance');
        return;
    }

    try {
        const response = await fetch('/api/debt', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name, balance, interest_rate, min_payment })
        });

        const data = await response.json();

        if (data.success) {
            document.getElementById('debt-name').value = '';
            document.getElementById('debt-balance').value = '';
            document.getElementById('debt-apr').value = '';
            document.getElementById('debt-min').value = '';
            loadDebt();
            alert('Credit card added successfully!');
        }
    } catch (error) {
        console.error('Error adding debt:', error);
        alert('Error adding credit card');
    }
}

async function loadDebt() {
    try {
        const response = await fetch('/api/debt');
        const items = await response.json();

        const tbody = document.querySelector('#debt-table tbody');
        tbody.innerHTML = items.map((item, index) => `
            <tr>
                <td>${item.name}</td>
                <td>$${item.balance.toFixed(2)}</td>
                <td>${item.interest_rate.toFixed(2)}%</td>
                <td>$${item.min_payment.toFixed(2)}</td>
                <td>
                    <button class="btn btn-danger" onclick="deleteDebt(${index})">
                        Delete
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Error loading debt:', error);
    }
}

async function deleteDebt(index) {
    if (!confirm('Are you sure you want to delete this credit card?')) {
        return;
    }

    try {
        const response = await fetch('/api/debt', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ index })
        });

        const data = await response.json();

        if (data.success) {
            loadDebt();
            alert('Credit card deleted');
        }
    } catch (error) {
        console.error('Error deleting debt:', error);
        alert('Error deleting credit card');
    }
}

// Initialize app on page load
// Convert detected recurring transaction to a tracked bill
async function convertToBill(description, amount) {
    const dueDay = prompt('What day of the month is this bill due? (1-31)', '1');
    if (!dueDay) return;

    try {
        const response = await fetch('/api/bills', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: description,
                amount: amount,
                due_day: parseInt(dueDay),
                category: 'Auto-Detected'
            })
        });

        const data = await response.json();

        if (data.success) {
            alert('Bill added successfully!');
            loadDashboard();
        }
    } catch (error) {
        console.error('Error adding bill:', error);
        alert('Error adding bill');
    }
}
// Generate AI-powered financial insights
function generateAIInsights(data, income, stats) {
    const insights = [];
    const cats = data.categorized_spending || {};

    // Calculate totals
    const totalSpending = (cats.bills || 0) + (cats.groceries || 0) + (cats.miscellaneous || 0);
    const netIncome = income - totalSpending;
    const savingsRate = income > 0 ? ((netIncome / income) * 100) : 0;

    // Insight 1: Overall financial health
    if (netIncome > 0) {
        if (savingsRate > 20) {
            insights.push(`💰 <strong>Excellent!</strong> You're saving ${savingsRate.toFixed(0)}% of your income ($${netIncome.toFixed(2)}). You're building wealth!`);
        } else if (savingsRate > 10) {
            insights.push(`✅ <strong>Good job!</strong> You're saving ${savingsRate.toFixed(0)}% of your income ($${netIncome.toFixed(2)}). Try to increase this to 20% for faster wealth building.`);
        } else if (savingsRate > 0) {
            insights.push(`⚠️ You're saving only ${savingsRate.toFixed(0)}% of your income ($${netIncome.toFixed(2)}). Experts recommend saving at least 20%. Look for areas to cut back.`);
        }
    } else {
        insights.push(`🚨 <strong>Warning:</strong> You're spending $${Math.abs(netIncome).toFixed(2)} more than you earn. This is unsustainable - review your expenses immediately.`);
    }

    // Insight 2: Spending categories analysis
    if (totalSpending > 0) {
        const groceryPercent = (cats.groceries / totalSpending) * 100;
        const billsPercent = (cats.bills / totalSpending) * 100;
        const miscPercent = (cats.miscellaneous / totalSpending) * 100;

        if (groceryPercent > 40) {
            insights.push(`🛒 Your grocery spending is ${groceryPercent.toFixed(0)}% of total expenses. Consider meal planning, buying in bulk, or using store brands to reduce this.`);
        }

        if (miscPercent > 50) {
            insights.push(`💸 ${miscPercent.toFixed(0)}% of your spending is miscellaneous ($${cats.miscellaneous.toFixed(2)}). Track where this money goes - you might find easy savings!`);
        }

        if (billsPercent > 50 && cats.bills > income * 0.5) {
            insights.push(`📱 Bills are ${billsPercent.toFixed(0)}% of expenses. Review subscriptions, negotiate rates, or switch providers to lower fixed costs.`);
        }
    }

    // Insight 3: Recurring bills detection
    if (data.recurring_bills && data.recurring_bills.length > 0) {
        insights.push(`🔔 I detected ${data.recurring_bills.length} recurring transaction(s). Click "Add as Bill" below to track them automatically.`);
    }

    // Insight 4: Debt insights
    if (stats.debt > 0) {
        const debtToIncome = income > 0 ? ((stats.debt / income) * 100) : 0;
        if (debtToIncome > 600) {
            insights.push(`💳 Your total debt ($${stats.debt.toFixed(2)}) is ${(debtToIncome / 100).toFixed(1)}x your monthly income. Focus on paying down high-interest debt first.`);
        } else if (stats.debt > 1000) {
            insights.push(`💳 You have $${stats.debt.toFixed(2)} in debt. Consider the avalanche method: pay minimums on all cards, then extra on the highest interest rate.`);
        }
    }

    // Insight 5: Action items
    if (netIncome > 100) {
        insights.push(`💡 <strong>Action:</strong> You have $${netIncome.toFixed(2)} left over. Consider: (1) Add to emergency fund, (2) Pay extra on debt, or (3) Invest for the future.`);
    }

    // Insight 6: No data yet
    if (totalSpending === 0 && income === 0) {
        insights.push(`📊 Connect your bank and sync transactions to get personalized financial insights and recommendations!`);
    }

    // Display insights
    const insightsDiv = document.getElementById('ai-insights');
    if (insights.length > 0) {
        insightsDiv.innerHTML = insights.map(insight =>
            `<div style="background: rgba(255,255,255,0.1); padding: 15px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #FFD700;">
                ${insight}
            </div>`
        ).join('');
    } else {
        insightsDiv.innerHTML = '<p>No insights available yet. Add more transactions!</p>';
    }
}
// Initialize app on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Budget Manager initialized');
    console.log('Plaid environment:', PLAID_ENV);
    loadDashboard();
});
</script>
</body>
</html>
'''

# Auto-open browser on startup
import webbrowser
import threading

def open_browser():
    webbrowser.open("http://localhost:5000")

# Open browser 1 second after server starts
threading.Timer(1, open_browser).start()


# ==================== MAIN EXECUTION ====================
if __name__ == '__main__':
    print('\n' + '='*70)
    print('🚀 PERSONAL BUDGET MANAGER WITH PLAID')
    print('='*70)
    print(f'✓ Plaid SDK installed: {HAS_PLAID}')
    print(f'✓ Environment: {PLAID_ENVIRONMENT.upper()}')
    print('='*70)
    print('\n🌐 Starting server...')
    print('📱 Open your browser to: http://localhost:5000')
    print('\n💡 SANDBOX TEST CREDENTIALS:')
    print('   Username: user_good')
    print('   Password: pass_good')
    print('='*70 + '\n')

    app.run(debug=True, port=5000, host='0.0.0.0')