# tests/test_sdl_facet_money.py
"""SDL Phase 2 — Money & Commerce family facets."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from imperal_sdk.sdl.entity import Entity, roles_of
from imperal_sdk.sdl.facets.money import (
    Monetary, Priced, Discountable, Subscribable, Balanced, Invoiced,
)


class PriceDoc(Entity, Monetary, Priced, Discountable):
    pass


def test_money_facets_compose_and_are_optional():
    d = PriceDoc(id=1, title="x")
    assert d.amount is None
    assert d.unit_price is None
    assert d.sale_price is None


def test_monetary_accept_values():
    d = PriceDoc(
        id=1, title="x",
        amount=Decimal("9.99"), currency="USD",
        unit_price=Decimal("19.99"), list_price=Decimal("24.99"),
        price_currency="USD", price_includes_tax=False,
        sale_price=Decimal("14.99"), discount_pct=Decimal("25"), is_on_sale=True,
    )
    assert d.amount == Decimal("9.99")
    assert d.currency == "USD"
    assert d.unit_price == Decimal("19.99")
    assert d.price_currency == "USD"
    assert d.sale_price == Decimal("14.99")
    assert d.is_on_sale is True


def test_money_roles_present():
    roles = roles_of(PriceDoc)
    assert roles["amount"] == "money.amount"
    assert roles["currency"] == "money.currency"
    assert roles["unit_price"] == "money.unit_price"
    assert roles["price_currency"] == "money.price_currency"
    assert roles["sale_price"] == "money.sale_price"
    assert roles["discount_pct"] == "money.discount_pct"


def test_subscribable_roles():
    class SubDoc(Entity, Subscribable):
        pass

    roles = roles_of(SubDoc)
    assert roles["subscription_status"] == "money.subscription_status"
    assert roles["billing_interval"] == "money.billing_interval"
    assert roles["recurring_amount"] == "money.recurring_amount"


def test_balanced_roles():
    class BalDoc(Entity, Balanced):
        pass

    roles = roles_of(BalDoc)
    assert roles["balance"] == "money.balance"
    assert roles["balance_currency"] == "money.balance_currency"
    assert roles["credit_limit"] == "money.credit_limit"


def test_invoiced_roles():
    class InvDoc(Entity, Invoiced):
        pass

    now = datetime(2026, 5, 31, 12, 0, 0)
    d = InvDoc(id=1, title="x", invoice_number="INV-001", total=Decimal("100.00"),
               tax=Decimal("20.00"), payment_status="unpaid", paid_at=None, invoice_due_at=now)
    assert d.invoice_number == "INV-001"
    assert d.total == Decimal("100.00")
    assert d.payment_status == "unpaid"

    roles = roles_of(InvDoc)
    assert roles["invoice_number"] == "money.invoice_number"
    assert roles["total"] == "money.total"
    assert roles["payment_status"] == "money.payment_status"
    assert roles["invoice_due_at"] == "money.invoice_due_at"
