"""
Visa Payment Test — pytest style
Run: pytest tests/test_visa_payment.py -v --headed
"""
import pytest
from test_payment_flow import run_payment_test


def test_visa_checkout_flow():
    """Full end-to-end Visa payment flow."""
    results = run_payment_test("visa", headed=False)
    failed = [r for r in results if not r.passed]
    assert not failed, (
        f"The following steps FAILED:\n" +
        "\n".join(f"  ✗ {r.name}: {r.detail}" for r in failed)
    )
