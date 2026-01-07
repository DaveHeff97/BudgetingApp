
# 💰 Personal Budget Manager with Plaid Integration

A Flask-based web application that automatically syncs bank transactions using Plaid API and provides smart financial insights with AI-powered budgeting recommendations.

![Budget Manager Dashboard](https://img.shields.io/badge/Python-3.7+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)
![Plaid](https://img.shields.io/badge/Plaid-API-00d4ff.svg)

## ✨ Features

- 🏦 **Automatic Bank Syncing** - Connect real bank accounts via Plaid API
- 📊 **Smart Transaction Categorization** - Auto-detects groceries, bills, and income
- 🤖 **AI Financial Coach** - Personalized insights and recommendations
- 💡 **Recurring Bill Detection** - Automatically identifies subscription payments
- 📅 **Future Bill Projections** - See upcoming expenses for next 90 days
- 💳 **Credit Card Debt Tracking** - Monitor balances, APR, and minimum payments
- 📈 **Dashboard Overview** - Real-time financial health snapshot
- 🎯 **Budget Categories** - Track groceries, savings, and miscellaneous spending

## 🚀 Quick Start

### Prerequisites

- Python 3.7 or higher
- Plaid account (free at [plaid.com](https://plaid.com))
- Git (optional, for cloning)

### Installation

1. **Clone or download this repository**
   ```bash
   git clone <your-repo-url>
   cd BudgetingApp
   ```

2. **Install dependencies**
   ```bash
   pip install flask plaid-python python-dotenv
   ```

3. **Set up Plaid API keys**
   - Sign up at [Plaid Dashboard](https://dashboard.plaid.com)
   - Get your `client_id`, `sandbox_secret`, and `production_secret`

4. **Create `.env` file**

   Create a file named `.env` in the project root:
   ```
   PLAID_CLIENT_ID=your_client_id_here
   PLAID_SANDBOX_SECRET=your_sandbox_secret_here
   PLAID_PRODUCTION_SECRET=your_production_secret_here
   PLAID_ENV=sandbox
   ```

   **⚠️ IMPORTANT:** Change `PLAID_ENV=production` when ready to use real bank data

5. **Run the application**

   **Windows:**
   ```bash
   start_budget_app.bat
   ```

   **Mac/Linux:**
   ```bash
   python web_budget_app.py
   ```

6. **Open in browser**
   ```
   http://localhost:5000
   ```

## 🔐 Security

- ✅ API keys are stored in `.env` file (not committed to Git)
- ✅ `.gitignore` prevents sensitive data from being pushed
- ✅ Personal budget data stays local (`budget_data_web.json`)
- ✅ Plaid uses bank-level encryption for all transactions

### Files Protected by `.gitignore`

```
.env                    # Your API keys
budget_data_web.json    # Your financial data
backups/                # Backup files
```

## 📖 Usage Guide

### 1. Connect Your Bank
- Click **"🏦 Bank Connection"** tab
- Click **"Connect New Bank"**
- Follow Plaid Link to authenticate

**Test Credentials (Sandbox Mode):**
- Username: `user_good`
- Password: `pass_good`

### 2. Sync Transactions
- Click **"🔄 Sync All Transactions"** to import transactions
- Transactions are auto-categorized into groceries, bills, etc.

### 3. Add Income (Optional)
- Go to **"💵 Income"** tab
- Add your paycheck details
- Note: Large deposits are auto-detected as income

### 4. Track Bills
- Go to **"📝 Bills"** tab
- Add recurring bills manually
- Or convert auto-detected recurring transactions

### 5. Set Budget
- Go to **"🎯 Budget"** tab
- Set monthly limits for groceries, savings, and miscellaneous

### 6. Monitor Dashboard
- View financial overview
- Get AI-powered insights
- See upcoming bill projections

## 🤖 Smart Features Explained

### Auto-Categorization (Last 30 Days)
Transactions are automatically categorized:
- **Income:** Paychecks, deposits >$100
- **Groceries:** Walmart, Target, Kroger, etc.
- **Bills:** Electric, internet, insurance, etc.
- **Miscellaneous:** Everything else

### Recurring Bill Detection
The app analyzes transaction history to detect:
- Monthly subscriptions (Netflix, Spotify, etc.)
- Utility bills with similar amounts
- Recurring charges appearing 2+ times

### AI Financial Coach
Get personalized insights:
- Savings rate analysis (20%+ is excellent)
- Spending pattern warnings
- Debt payoff recommendations
- Action items for unused funds

## 📁 Project Structure

```
BudgetingApp/
├── web_budget_app.py           # Main Flask application
├── start_budget_app.bat        # Windows launcher script
├── .env                        # API keys (YOU CREATE THIS)
├── .env.example                # Template for .env
├── .gitignore                  # Git ignore rules
├── README.md                   # This file
├── budget_data_web.json        # Your data (auto-created)
└── backups/                    # Automatic backups (auto-created)
```

## 🛠️ Development

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `PLAID_CLIENT_ID` | Your Plaid client ID | Yes |
| `PLAID_SANDBOX_SECRET` | Sandbox API secret | Yes (for testing) |
| `PLAID_PRODUCTION_SECRET` | Production API secret | Yes (for real banks) |
| `PLAID_ENV` | `sandbox` or `production` | Yes |

### API Endpoints

- `GET /api/dashboard` - Dashboard statistics
- `POST /api/plaid/create_link_token` - Initialize Plaid Link
- `POST /api/plaid/exchange_public_token` - Connect bank
- `POST /api/plaid/sync_transactions` - Sync transactions
- `GET/POST/DELETE /api/income` - Manage income sources
- `GET/POST/DELETE /api/bills` - Manage bills
- `GET/POST /api/budget` - Manage budget categories
- `GET/POST/DELETE /api/debt` - Manage credit cards

### Data Storage

Data is stored in `budget_data_web.json`:
```json
{
  "income": [],
  "bills": [],
  "budget": {},
  "transactions": [],
  "debt": [],
  "plaid_items": []
}
```

## 🐛 Troubleshooting

### "Plaid not configured" error
- Check that `.env` file exists
- Verify API keys are correct
- Make sure `python-dotenv` is installed

### Transactions not importing
- Verify bank is connected in "Bank Connection" tab
- Click "Sync All Transactions" button
- Check console for error messages
- For sandbox: Use `user_good` / `pass_good` credentials

### Income showing $0.00
- Large deposits (>$100) are auto-detected
- Or manually add income in "Income" tab
- Income detection looks at last 30 days

### "Module not found" errors
```bash
pip install flask plaid-python python-dotenv
```

## 📝 Roadmap

Future features planned:
- [ ] Budget vs Actual progress bars
- [ ] Export transactions to CSV
- [ ] Bill payment reminders
- [ ] Debt payoff calculator (snowball/avalanche)
- [ ] Spending trend charts
- [ ] Savings goals tracker
- [ ] Multi-user support with authentication

## 🤝 Contributing

This is a personal project, but feel free to:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## ⚖️ License

MIT License - Use freely for personal or commercial projects

## 🔗 Resources

- [Plaid API Documentation](https://plaid.com/docs/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Plaid Dashboard](https://dashboard.plaid.com/)

## 💬 Support

For issues or questions:
- Check the Troubleshooting section above
- Review Plaid API documentation
- Check Flask error logs in console

---

**⚠️ Important Reminders:**
- Never commit `.env` file to Git
- Switch to `PLAID_ENV=production` when using real banks
- Keep your API keys secure
- Budget data is stored locally - back it up regularly