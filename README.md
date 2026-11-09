# PayAgent AI - Working Hackathon Demo

A local, beginner-friendly prototype based on the 11-slide PayAgent AI pitch deck. It demonstrates the buyer agent and merchant dispute-shield experience in one application. The local mock demo uses only Python standard-library modules; no package installation or API key is required.

> **Important:** This is a hackathon/demo prototype. Mock mode does not move money. PayPal mode uses PayPal's Sandbox, not live payments. Risk scores are explainable demo rules, not a validated fraud model. Do not use this application with real customers or production payment credentials.

## What works in this demo

### 1. Buyer AI Negotiator
- Product catalog with four sample products.
- Natural-language price offers such as `Can you do $110 if I buy today?`.
- A local negotiation engine that extracts the requested price, applies Plus-member and quantity discounts, accepts offers inside a configurable demo range, or returns a counter-offer.
- Quantity changes, negotiated price and savings display, and checkout.
- For this version, the negotiation engine is deterministic Python logic. It does not call an external LLM. That makes the demo repeatable and works without an API key.

### 2. Payment engine
- **Mock mode (default):** completes a simulated checkout, assigns a payment reference, and writes the order to SQLite. No funds are charged or transferred.
- **Optional PayPal Sandbox mode:** server-side OAuth token, Orders v2 create-order, buyer approval redirect, and capture after approval. Sandbox credentials are required. No live-payment mode is implemented.

### 3. Merchant AG Grid Dispute Shield concept
- Interactive transaction grid with search, status filtering, row selection and transaction detail.
- Explainable risk score based on order value, new device, country mismatch, order quantity and recent checkout velocity.
- High-risk transactions enter `REVIEW_REQUIRED`; lower-risk transactions are auto-approved in the demo.
- Evidence snapshot and transaction event timeline.
- Merchant actions to request additional evidence or mark a review resolved.
- Export a JSON evidence packet for the selected transaction.

The merchant screen uses a lightweight local table with grid-like filtering and selection. It is not the licensed AG Grid Enterprise product.

### 4. Audit / lifecycle
- Events for initiation, agreement, payment, risk assessment, shield alert, approval and resolution.
- SQLite persistence: transactions remain after the app is restarted.
- Four sample transactions are inserted the first time the database is created.
- Reset button restores the original sample transactions.

## Run on Windows 10 / 11

### Option A - Python (recommended for the first run)

1. Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/). During setup, enable **Add Python to PATH**.
2. Extract this project folder somewhere simple, for example `C:\Projects\payagent_ai_demo`.
3. Open PowerShell in that folder.
4. No package installation is needed. The app uses Python's built-in modules. You can run it directly in step 6. Creating a virtual environment is optional; to use one:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this once in the same terminal, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

5. Copy the example settings file only if you want to change settings or configure PayPal Sandbox. It is not required for mock mode:

```powershell
Copy-Item .env.example .env
```

6. Start the application:

```powershell
python app.py
```

Keep the terminal window open while using the demo. Open **http://127.0.0.1:5000** in your browser and press `Ctrl+C` to stop the server.

### Option B - Docker

Docker Desktop must be running. From the project folder:

```powershell
docker compose up --build
```

Open **http://127.0.0.1:5000**. The SQLite database is stored in the local `instance` folder and persists across container restarts. Stop it with `Ctrl+C`, then run `docker compose down` when needed.

## 5-minute judge demo walkthrough

1. Open **Buyer agent** and select **Pulse Watch Pro**.
2. Enter `Can you do $115?` and click the up-arrow. The agent should accept the request because it is above the demo minimum price.
3. Change the product or try `Can you do $70?` to see a counter-offer. You can also click **Find best price** to generate a member/quantity offer.
4. Click **Continue to checkout**. In default mock mode, a simulated payment record is created.
5. The app moves to **Merchant shield** and opens the new transaction. Inspect the risk reasons and evidence snapshot.
6. Click **Export evidence** to save a JSON evidence packet.
7. Go back to **Buyer agent**, click **Run a high-risk demo transaction**, then click **Continue to checkout**. It uses a large quantity plus test device/location signals so the merchant shield should route it to `REVIEW_REQUIRED`.
8. Open the flagged transaction, review its reasons, then click **Mark resolved**. The audit timeline records the action.
9. Visit **Audit timeline** to show the recorded lifecycle events.

## Optional: connect PayPal Sandbox

Mock mode is enough to run the full prototype. To test PayPal's external sandbox checkout:

1. Create or sign in to a PayPal Developer account.
2. Open the Developer Dashboard, create a REST app in **Sandbox**, and copy its Sandbox Client ID and Secret.
3. Edit `.env`:

```dotenv
PAYMENT_MODE=paypal
PAYPAL_CLIENT_ID=YOUR_SANDBOX_CLIENT_ID
PAYPAL_CLIENT_SECRET=YOUR_SANDBOX_SECRET
SECRET_KEY=use-a-long-random-local-secret
```

4. Restart `python app.py`. The app creates an Orders v2 order on the server, redirects the buyer to PayPal Sandbox for approval, and captures the order after PayPal returns to the local app.
5. Use a PayPal **Sandbox personal test account** at the approval page, not your real PayPal account.

PayPal references:
- [PayPal Orders API integration guide](https://developer.paypal.com/api/rest/integration/orders-api)
- [Create Order API](https://developer.paypal.com/sdk/orders/v2/orders-create/)
- [Create PayPal REST API credentials](https://developer.paypal.com/tools/sandbox/apps-and-credentials/)

The server calls PayPal using Python's built-in HTTPS client; credentials are read from `.env` and are never sent to the browser. Never commit `.env` or publish your Client Secret.

## Run the automated tests

```powershell
python -m unittest -v test_app
```

## Project structure

```text
payagent_ai_demo/
├── app.py                  # Python standard-library server and API logic
├── index.html              # Main application screens
├── app.js                  # UI interactions and API calls
├── style.css               # Responsive dashboard styling
├── test_app.py             # Automated tests
├── .env.example            # Optional local configuration
├── Dockerfile
├── docker-compose.yml
├── instance/               # SQLite database created at runtime
└── README.md
```

## API routes

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/state` | Dashboard statistics, products and transactions |
| POST | `/api/negotiate` | Generate an offer / acceptance / counter-offer |
| POST | `/api/checkout` | Simulate checkout or start PayPal Sandbox checkout |
| GET | `/api/transactions/<id>` | Transaction and audit detail |
| POST | `/api/transactions/<id>/action` | Request evidence or resolve a review |
| GET | `/api/transactions/<id>/evidence` | Build the JSON evidence packet |
| POST | `/api/reset-demo` | Restore the sample data |

## What is intentionally not production-ready

- No actual LLM, agent-to-agent protocol, real merchant integrations or live customer accounts.
- No live payment mode, refunds, settlement, subscriptions or webhooks.
- No production fraud/chargeback model, model training or guaranteed dispute win-rate.
- No authentication, role-based access control, CSRF protection, multi-tenant isolation or hardened deployment.
- Local demo evidence is an exportable record, not a tamper-proof or legally certified evidence chain.
- The sample dataset, product catalog, membership profile and rules are illustrative.

A production build would need security review, authentication and authorization, audited payment/webhook handling, merchant-specific policies, a proper fraud dataset and validation, privacy controls, observability, and legal/compliance review.
