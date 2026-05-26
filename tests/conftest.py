"""
conftest.py — shared fixtures for Qatarat payment tests
"""
import pytest
from playwright.sync_api import Page, BrowserContext


# ── Browser settings ──────────────────────────────────────────────────────────

def pytest_addoption(parser):
    parser.addoption("--payment-method", default="both",
                     choices=["visa", "mada", "both"],
                     help="Payment method to test")


@pytest.fixture(scope="session")
def payment_method(request):
    return request.config.getoption("--payment-method")


@pytest.fixture(scope="function")
def checkout_page(page: Page) -> Page:
    """Navigate to checkout and return the page object."""
    page.set_default_timeout(30_000)
    page.goto("https://qatarat-stage.vercel.app/en/checkout",
               wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    return page
