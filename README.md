# Qatarat Payment Flow — Automation Test Suite

End-to-end automation tests for the Qatarat checkout → login → PayTabs payment flow.

## Stack
| Tool | Purpose |
|------|---------|
| [Playwright](https://playwright.dev/python/) | Browser automation |
| [pytest](https://pytest.org) | Test runner |
| Python 3.10+ | Runtime |

---

## Quick Start

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Install Playwright browsers
```bash
playwright install chromium
```

### 3. Run the full suite (headless)
```bash
python3 tests/test_payment_flow.py
```

### 4. Run with a visible browser window
```bash
python3 tests/test_payment_flow.py --headed
```

### 5. Run only one payment method
```bash
python3 tests/test_payment_flow.py --method visa --headed
python3 tests/test_payment_flow.py --method mada --headed
```

### 6. Debug a fresh PayTabs URL directly
PayTabs codes change for every order and expire quickly. Normal checkout runs automatically capture the latest live URL from the redirect. Use direct mode only when you already have a fresh PayTabs URL:
```bash
python3 tests/test_payment_flow.py --paytabs-only --paytabs-url "https://secure.paytabs.sa/payment/page/LATEST_CODE/start"
```

### 7. Run via pytest
```bash
cd tests
pytest test_visa_payment.py -v
pytest test_mada_payment.py -v
pytest .                          # both
```

---

## Test Flow

```
Product Page
    └── Add a low-value package to cart as guest
        └── Checkout Page
            └── Select Visa / Mada
            └── Login when checkout asks (country: Bangladesh +880, phone: 1685220417, OTP: 1234)
            └── Select Payment Method (Visa / Mada)
            └── Place Order → capture latest live PayTabs redirect URL/code
                └── Fill Card Details (fake filler)
                    └── Click Pay Now → assert result
```

## Screenshots

All screenshots are saved to `/tmp/qatarat-payment/` for debugging:

| File | Step |
|------|------|
| `01_checkout.png` | Checkout page |
| `02_logged_in.png` | After OTP verification |
| `03_visa_selected.png` / `03_mada_selected.png` | Payment method selected |
| `04_paytabs_from_checkout.png` | PayTabs payment page from latest redirect |
| `05_payment_form_filled.png` | Card details filled |
| `06_payment_result.png` | Final payment result |

## Test Card Data

| Field | Visa | Mada |
|-------|------|------|
| Name | Qatarat Test User | Qatarat Test User |
| Number | 4111 1111 1111 1111 | 5297 4009 0000 0002 |
| Expiry | 12/2028 | 06/2028 |
| CVV | 123 | 123 |

> **Note:** These are sandbox/test card numbers. Results depend on the PayTabs sandbox environment configuration.

---

## Project Structure

```
Qatarat-web/
├── requirements.txt
├── README.md
└── tests/
    ├── conftest.py              # Shared pytest fixtures
    ├── test_payment_flow.py     # Main script (run standalone or via pytest)
    ├── test_visa_payment.py     # Visa-only pytest test
    └── test_mada_payment.py     # Mada-only pytest test
```
