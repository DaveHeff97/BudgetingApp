Budgeting App (Work in Progress)

⚠️ Status: This project is currently a work in progress. Features, structure, and configuration may change.

This budgeting app connects securely to your bank account using Plaid to fetch transaction and account data, allowing you to track spending and manage your finances in one place.

🔐 Plaid Integration (Required)

This application uses Plaid to connect to user bank accounts.

To run this app, you must have:

A Plaid account

Plaid API credentials:

PLAID_CLIENT_ID

PLAID_SECRET

PLAID_ENV (environment)

Without valid Plaid credentials, the app will not function.

👉 You can sign up for Plaid here:
https://plaid.com

🧪 Sandbox vs 🚀 Production Modes

Plaid provides two main environments:

Sandbox Mode (Testing)

Used for development and testing

Does not connect to real bank accounts

Uses fake institutions and test credentials

Safe for experimenting without real money

Production Mode (Live Use)

Used for real users and real bank accounts

Requires Plaid production approval

Must be handled securely

⚙️ Configuration Location

You can configure the Plaid environment and credentials in the source code at:

Lines 44–47

These lines control:

Which Plaid environment is used (sandbox or production)

Which API credentials are loaded

Make sure the environment matches your Plaid keys.


📌 Planned Improvements

UI polish

Better error handling

Expanded budgeting categories

Improved analytics and charts