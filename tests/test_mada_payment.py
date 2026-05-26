"""
Mada Payment Test — pytest style
Run: pytest tests/test_mada_payment.py -v --headed
"""
import pytest
from test_payment_flow import run_payment_test


def test_mada_checkout_flow():
    """Full end-to-end Mada payment flow."""
    results = run_payment_test("mada", headed=False)
    failed = [r for r in results if not r.passed]
    assert not failed, (
        f"The following steps FAILED:\n" +
        "\n".join(f"  ✗ {r.name}: {r.detail}" for r in failed)
    )
