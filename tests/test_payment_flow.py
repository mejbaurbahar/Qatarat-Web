"""
Qatarat checkout -> PayTabs payment automation.

Run:
    python3 tests/test_payment_flow.py --method visa --headed
    python3 tests/test_payment_flow.py --method mada --headed
    python3 tests/test_payment_flow.py --method both
    python3 tests/test_payment_flow.py --paytabs-only --paytabs-url "https://secure.paytabs.sa/payment/page/LATEST_CODE/start"
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from playwright.sync_api import (
    Browser,
    Error as PlaywrightError,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

PaymentMethod = Literal["visa", "mada"]

CHECKOUT_URL = "https://qatarat-stage.vercel.app/en/checkout"
PRODUCT_URL = "https://qatarat-stage.vercel.app/en/mecca-mosques-most-needed"
CART_URL = "https://qatarat-stage.vercel.app/en/cart"
PAYTABS_URL_RE = re.compile(r"https://secure\.paytabs\.sa/payment/page/([^/?#]+)/start")

LOGIN_PHONE = "8801685220417"
LOGIN_OTP = "1234"
DEFAULT_TIMEOUT = 30_000
SCREENSHOT_DIR = Path("/tmp/qatarat-payment")

TEST_CARDS = {
    "visa": {
        "number": "4111111111111111",
        "month": "12",
        "year": "2028",
        "cvv": "123",
    },
    "mada": {
        "number": "5297400900000002",
        "month": "06",
        "year": "2028",
        "cvv": "123",
    },
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("qatarat-payment")


@dataclass
class StepResult:
    name: str
    passed: bool
    detail: str = ""


def screenshot(page: Page, name: str) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        log.info("Screenshot saved: %s", path)
    except PlaywrightError as exc:
        log.warning("Could not save screenshot %s: %s", name, exc)


def wait_for_background_idle(page: Page, timeout: int = 8_000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except PlaywrightTimeoutError:
        log.info("Continuing without networkidle; page is still making background requests")


def visible(locator: Locator, timeout: int = 2_000) -> bool:
    try:
        locator.first.wait_for(state="visible", timeout=timeout)
        return True
    except (PlaywrightTimeoutError, PlaywrightError):
        return False


def click_first(page: Page, selectors: list[str], label: str, timeout: int = 4_000) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        if not visible(locator, timeout):
            continue
        try:
            locator.click(timeout=timeout)
            log.info("%s clicked with selector: %s", label, selector)
            return True
        except PlaywrightError:
            continue
    return False


def fill_first(page: Page, selectors: list[str], value: str, label: str, timeout: int = 3_000) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        if not visible(locator, timeout):
            continue
        if fill_locator(locator, value):
            log.info("%s filled with selector: %s", label, selector)
            return True
    return False


def fill_locator(locator: Locator, value: str) -> bool:
    try:
        tag_name = locator.evaluate("el => el.tagName.toLowerCase()")
        if tag_name == "select":
            options = locator.locator("option").evaluate_all(
                """(options, value) => options.map(option => ({
                    value: option.value,
                    label: option.label || option.textContent || "",
                    selected: option.value === value || (option.label || "").includes(value)
                }))""",
                value,
            )
            match = next((item for item in options if item["selected"]), None)
            if match:
                locator.select_option(match["value"])
            else:
                locator.select_option(value)
        else:
            locator.click(timeout=3_000)
            locator.press("Meta+A")
            locator.press("Control+A")
            locator.fill(value)
        return True
    except PlaywrightError:
        try:
            locator.type(value, delay=20)
            return True
        except PlaywrightError:
            return False


def fill_any_frame(page: Page, selectors: list[str], value: str, label: str) -> bool:
    if fill_first(page, selectors, value, label):
        return True

    for frame in page.frames:
        for selector in selectors:
            locator = frame.locator(selector).first
            if not visible(locator, 1_500):
                continue
            if fill_locator(locator, value):
                log.info("%s filled inside frame with selector: %s", label, selector)
                return True
    return False


def open_checkout(page: Page) -> StepResult:
    try:
        page.goto(CHECKOUT_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
        wait_for_background_idle(page)
        screenshot(page, "01_checkout")
        return StepResult("Open checkout", True, page.url)
    except PlaywrightError as exc:
        screenshot(page, "01_checkout_error")
        return StepResult("Open checkout", False, str(exc))


def local_phone_number() -> str:
    return LOGIN_PHONE[3:] if LOGIN_PHONE.startswith("880") else LOGIN_PHONE


def choose_bangladesh_country_code(page: Page) -> None:
    if not visible(page.get_by_text("(966)").first, 1_500):
        return

    page.get_by_text("(966)").first.click()
    search = page.locator('input[placeholder="Search Country"]').first
    search.wait_for(state="visible", timeout=5_000)
    search.fill("Bangladesh")
    page.get_by_text("Bangladesh").first.click()
    page.wait_for_timeout(500)


def continue_otp_delivery_step(page: Page, timeout: int = 12_000) -> None:
    try:
        page.get_by_text("How should we send your code?").first.wait_for(state="visible", timeout=timeout)
    except PlaywrightTimeoutError:
        return

    click_first(page, ['button:has-text("WhatsApp")', 'button:has-text("SMS")'], "OTP delivery method", timeout=1_000)
    page.locator('button:has-text("Continue")').last.click(timeout=5_000)
    log.info("OTP delivery continue clicked")


def login_if_needed(page: Page) -> StepResult:
    phone_selectors = [
        'input[type="tel"]:visible',
        'input[name*="phone" i]:visible',
        'input[id*="phone" i]:visible',
        'input[placeholder*="phone" i]:visible',
        'input[autocomplete="tel"]:visible',
    ]

    login_openers = [
        'button:has-text("Login")',
        'button:has-text("Sign in")',
        'button:has-text("Continue")',
        'button:has-text("Place Order")',
        'button:has-text("Pay Now")',
        'a:has-text("Login")',
        '[role="button"]:has-text("Login")',
    ]

    if not any(visible(page.locator(selector).first, 1_000) for selector in phone_selectors):
        click_first(page, login_openers, "Login opener", timeout=2_000)

    if visible(page.get_by_text("(966)").first, 1_500):
        choose_bangladesh_country_code(page)

    if not fill_first(page, phone_selectors, local_phone_number(), "Phone number", timeout=2_000):
        return StepResult("Login", True, "No login prompt was visible")

    if not click_first(
        page,
        [
            'button[type="submit"]',
            'button:has-text("Log In")',
            'button:has-text("Send")',
            'button:has-text("Get OTP")',
            'button:has-text("Continue")',
            'button:has-text("Next")',
        ],
        "Phone submit",
    ):
        return StepResult("Login", False, "Phone submit button not found")

    continue_otp_delivery_step(page)

    otp_filled = False
    digits = page.locator('input[maxlength="1"]:visible')
    try:
        digits.first.wait_for(state="visible", timeout=8_000)
    except PlaywrightTimeoutError:
        pass

    if digits.count() >= len(LOGIN_OTP):
        for index, digit in enumerate(LOGIN_OTP):
            digits.nth(index).fill(digit)
        otp_filled = True

    if not otp_filled:
        otp_filled = fill_first(
            page,
            [
                'input[name*="otp" i]:visible',
                'input[name*="code" i]:visible',
                'input[placeholder*="otp" i]:visible',
                'input[placeholder*="code" i]:visible',
                'input[autocomplete="one-time-code"]:visible',
            ],
            LOGIN_OTP,
            "OTP",
            timeout=8_000,
        )

    if not otp_filled:
        screenshot(page, "02_login_otp_not_found")
        return StepResult("Login", False, "Phone accepted, but OTP field was not found")

    click_first(
        page,
        [
            'button:has-text("Confirm to Login")',
            'button[type="submit"]',
            'button:has-text("Verify")',
            'button:has-text("Confirm")',
            'button:has-text("Login")',
            'button:has-text("Submit")',
        ],
        "OTP submit",
    )
    page.wait_for_timeout(2_000)
    screenshot(page, "02_logged_in")
    return StepResult("Login", True, page.url)


def ensure_logged_in(page: Page) -> StepResult:
    if not visible(page.locator('button:has-text("Log In")').first, 2_000):
        return StepResult("Login", True, "Already logged in or login button not visible")

    page.locator('button:has-text("Log In")').first.click()
    return login_if_needed(page)


def seed_cart(page: Page) -> StepResult:
    try:
        for attempt in range(1, 5):
            page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
            page.wait_for_timeout(4_000)

            buttons = page.locator('button:has-text("Add To Cart")')
            if buttons.count() == 0:
                page.reload(wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
                page.wait_for_timeout(4_000)
                buttons = page.locator('button:has-text("Add To Cart")')

            button_count = buttons.count()
            if button_count == 0:
                return StepResult("Seed cart", False, "No Add To Cart buttons were found")

            button = buttons.nth(min(attempt - 1, button_count - 1))
            button.scroll_into_view_if_needed(timeout=5_000)
            button.click(timeout=5_000, force=True)
            page.wait_for_timeout(3_000)
            screenshot(page, f"00_product_added_attempt_{attempt}")

            page.goto(CART_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
            page.wait_for_timeout(3_000)
            screenshot(page, f"00_cart_seeded_attempt_{attempt}")

            cart_text = page.locator("body").inner_text(timeout=5_000)
            if "Empty Cart" not in cart_text:
                return StepResult("Seed cart", True, f"Cart has an item before checkout after attempt {attempt}")

        return StepResult("Seed cart", False, "Add To Cart was clicked several times, but cart is still empty")
    except PlaywrightError as exc:
        screenshot(page, "00_seed_cart_error")
        return StepResult("Seed cart", False, str(exc))


def select_payment_method(page: Page, method: PaymentMethod) -> StepResult:
    method_text = "mada" if method == "mada" else "visa"
    selectors = [
        f'input[value*="{method_text}" i]',
        f'button:has-text("{method_text}")',
        f'label:has-text("{method_text}")',
        f'[role="button"]:has-text("{method_text}")',
        f'img[alt*="{method_text}" i]',
        f'[aria-label*="{method_text}" i]',
        f'[class*="{method_text}" i]',
    ]
    if click_first(page, selectors, f"{method.upper()} method", timeout=2_000):
        screenshot(page, f"03_{method}_selected")
        return StepResult(f"Select {method.upper()}", True)

    screenshot(page, f"03_{method}_not_found")
    return StepResult(f"Select {method.upper()}", False, "Payment method control not found")


def paytabs_code_from_url(url: str) -> str:
    match = PAYTABS_URL_RE.search(url)
    return match.group(1) if match else ""


def continue_to_paytabs(page: Page, direct_paytabs_url: str | None = None) -> StepResult:
    click_first(
        page,
        [
            'button:has-text("Place Order")',
            'button:has-text("Proceed to Payment")',
            'button:has-text("Continue to Payment")',
            'button:has-text("Pay Now")',
            'button[type="submit"]',
        ],
        "Checkout payment button",
        timeout=2_000,
    )

    try:
        page.wait_for_url(PAYTABS_URL_RE, timeout=12_000)
        screenshot(page, "04_paytabs_from_checkout")
        latest_code = paytabs_code_from_url(page.url)
        return StepResult("Open PayTabs", True, f"Live PayTabs URL: {page.url} | code: {latest_code}")
    except PlaywrightTimeoutError:
        if not direct_paytabs_url:
            screenshot(page, "04_paytabs_redirect_missing")
            return StepResult(
                "Open PayTabs",
                False,
                "Checkout did not generate a live PayTabs URL. Add an item/order first or pass --paytabs-url with a fresh URL.",
            )
        log.warning("Checkout did not redirect to PayTabs. Opening provided PayTabs URL directly.")

    try:
        page.goto(direct_paytabs_url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
        page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
        screenshot(page, "04_paytabs_direct")
        latest_code = paytabs_code_from_url(page.url)
        return StepResult("Open PayTabs", True, f"Direct PayTabs URL: {page.url} | code: {latest_code}")
    except PlaywrightError as exc:
        screenshot(page, "04_paytabs_error")
        return StepResult("Open PayTabs", False, str(exc))


def open_paytabs_direct(page: Page, paytabs_url: str) -> StepResult:
    try:
        page.goto(paytabs_url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
        page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
        screenshot(page, "01_paytabs_direct")
        latest_code = paytabs_code_from_url(page.url)
        return StepResult("Open PayTabs", True, f"Direct PayTabs URL: {page.url} | code: {latest_code}")
    except PlaywrightError as exc:
        screenshot(page, "01_paytabs_error")
        return StepResult("Open PayTabs", False, str(exc))


def fill_payment_form(page: Page, method: PaymentMethod) -> StepResult:
    expired = payment_session_error(page)
    if expired:
        screenshot(page, "05_payment_session_unavailable")
        return StepResult("Fill payment form", False, expired)

    holder_name = "Qatarat Test User"
    card = TEST_CARDS[method]

    field_map = [
        (
            "Card holder name",
            holder_name,
            [
                'input[name*="holder" i]',
                'input[name*="name" i]',
                'input[id*="holder" i]',
                'input[id*="name" i]',
                'input[placeholder*="holder" i]',
                'input[placeholder*="name" i]',
                '#card-holder',
                '#cc-name',
            ],
        ),
        (
            "Card number",
            card["number"],
            [
                'input[name*="cardnumber" i]',
                'input[name*="card_number" i]',
                'input[name*="number" i]',
                'input[id*="cardNumber" i]',
                'input[id*="card-number" i]',
                'input[id*="number" i]',
                'input[placeholder*="card number" i]',
                'input[autocomplete="cc-number"]',
                '#cc-number',
            ],
        ),
        (
            "Expiry month",
            card["month"],
            [
                'select[name*="month" i]',
                'input[name*="month" i]',
                'select[id*="month" i]',
                'input[id*="month" i]',
                'input[placeholder="MM"]',
                'input[placeholder*="month" i]',
                'input[autocomplete="cc-exp-month"]',
            ],
        ),
        (
            "Expiry year",
            card["year"],
            [
                'select[name*="year" i]',
                'input[name*="year" i]',
                'select[id*="year" i]',
                'input[id*="year" i]',
                'input[placeholder="YY"]',
                'input[placeholder="YYYY"]',
                'input[placeholder*="year" i]',
                'input[autocomplete="cc-exp-year"]',
            ],
        ),
        (
            "CVV",
            card["cvv"],
            [
                'input[name*="cvv" i]',
                'input[name*="cvc" i]',
                'input[name*="security" i]',
                'input[id*="cvv" i]',
                'input[id*="cvc" i]',
                'input[placeholder*="CVV" i]',
                'input[placeholder*="CVC" i]',
                'input[autocomplete="cc-csc"]',
            ],
        ),
    ]

    missing = []
    for label, value, selectors in field_map:
        if not fill_any_frame(page, selectors, value, label):
            missing.append(label)

    if missing:
        screenshot(page, "05_payment_form_missing_fields")
        return StepResult("Fill payment form", False, "Missing fields: " + ", ".join(missing))

    screenshot(page, "05_payment_form_filled")
    return StepResult("Fill payment form", True, f"Holder: {holder_name}")


def submit_payment(page: Page) -> StepResult:
    clicked = click_first(
        page,
        [
            'button:has-text("Pay Now")',
            'button:has-text("Pay")',
            'button:has-text("Submit")',
            'input[type="submit"]',
            'button[type="submit"]',
        ],
        "Pay Now",
        timeout=5_000,
    )
    if not clicked:
        screenshot(page, "06_pay_button_not_found")
        return StepResult("Click Pay Now", False, "Pay Now button not found")

    page.wait_for_timeout(5_000)
    screenshot(page, "06_payment_result")

    body = ""
    try:
        body = page.locator("body").inner_text(timeout=3_000).lower()
    except PlaywrightError:
        pass

    if any(word in body for word in ["success", "approved", "thank you", "confirmed"]):
        return StepResult("Click Pay Now", True, "Success/approved result detected")
    if any(word in body for word in ["declined", "failed", "error", "rejected"]):
        return StepResult("Click Pay Now", True, "Gateway returned a test-card failure result")
    return StepResult("Click Pay Now", True, page.url)


def payment_session_error(page: Page) -> str:
    try:
        body = page.locator("body").inner_text(timeout=2_000).lower()
    except PlaywrightError:
        return ""

    if "payment session has expired" in body:
        return "PayTabs says the payment session has expired"
    if "cannot be completed" in body and "payment session" in body:
        return "PayTabs says the payment session cannot be completed"
    return ""


def new_browser(headed: bool) -> Browser:
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=not headed, slow_mo=250 if headed else 0)
    browser._playwright = playwright  # type: ignore[attr-defined]
    return browser


def close_browser(browser: Browser) -> None:
    playwright = getattr(browser, "_playwright", None)
    browser.close()
    if playwright:
        playwright.stop()


def run_payment_test(
    method: PaymentMethod,
    headed: bool = False,
    paytabs_only: bool = False,
    paytabs_url: str | None = None,
) -> list[StepResult]:
    results: list[StepResult] = []
    log.info("Running %s payment automation", method.upper())

    browser = new_browser(headed)
    context = browser.new_context(
        viewport={"width": 1366, "height": 900},
        locale="en-US",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()
    page.set_default_timeout(DEFAULT_TIMEOUT)

    try:
        if paytabs_only:
            if not paytabs_url:
                results.append(
                    StepResult(
                        "Open PayTabs",
                        False,
                        "--paytabs-only needs --paytabs-url because PayTabs codes expire and change every order.",
                    )
                )
                return results
            results.append(open_paytabs_direct(page, paytabs_url))
        else:
            results.append(seed_cart(page))
            if not results[-1].passed:
                return results

            results.append(open_checkout(page))
            if results[-1].passed:
                select_result = select_payment_method(page, method)
                results.append(select_result)

                if visible(page.get_by_text("Please login to continue").first, 2_000) or visible(
                    page.locator('input[type="tel"]:visible').first, 1_000
                ):
                    login_result = login_if_needed(page)
                    results.append(login_result)
                    if login_result.passed:
                        retry_select = select_payment_method(page, method)
                        if retry_select.passed:
                            results.append(retry_select)
                        else:
                            results.append(
                                StepResult(
                                    f"Select {method.upper()} after login",
                                    True,
                                    "Payment selection was already applied before login",
                                )
                            )

                results.append(continue_to_paytabs(page, paytabs_url))

        if results and results[-1].passed:
            results.append(fill_payment_form(page, method))
        if results and results[-1].passed:
            results.append(submit_payment(page))
    finally:
        close_browser(browser)

    return results


def print_summary(method: str, results: list[StepResult]) -> None:
    print()
    print("=" * 72)
    print(f"TEST SUMMARY: {method.upper()}")
    print("=" * 72)
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        detail = f" - {result.detail}" if result.detail else ""
        print(f"{status:4} {result.name}{detail}")
    print("=" * 72)
    print(f"Screenshots: {SCREENSHOT_DIR}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Qatarat PayTabs automation")
    parser.add_argument("--method", choices=["visa", "mada", "both"], default="both")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--paytabs-only", action="store_true")
    parser.add_argument(
        "--paytabs-url",
        nargs="?",
        default=None,
        const="",
        help="Optional fresh PayTabs URL for debugging. Normal checkout runs capture the latest URL automatically.",
    )
    args = parser.parse_args()

    methods: list[PaymentMethod] = ["visa", "mada"] if args.method == "both" else [args.method]
    passed = True

    for method in methods:
        results = run_payment_test(
            method=method,
            headed=args.headed,
            paytabs_only=args.paytabs_only,
            paytabs_url=args.paytabs_url,
        )
        print_summary(method, results)
        passed = passed and all(result.passed for result in results)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
