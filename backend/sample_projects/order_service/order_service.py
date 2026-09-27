"""
Order Service — sample project for DevProof AI.

Bug (intentional): the coupon discount is subtracted from the subtotal
*before* tax is applied, so the customer's coupon inadvertently reduces
the taxable base and they end up paying less tax than intended.

Buggy formula:
    total = round((subtotal - coupon_discount) * tax_rate, 2)
    # discount reduces the pre-tax base → customer saves tax on the coupon amount

Correct formula:
    total = round(subtotal * tax_rate - coupon_discount, 2)
    # tax is computed on the full pre-discount subtotal; coupon comes off post-tax

Concrete example:
    subtotal=100, tax_rate=1.1, coupon_discount=10
    Buggy:   (100 - 10) * 1.1 = 90 * 1.1 = 99.0
    Correct: 100 * 1.1 - 10   = 110 - 10  = 100.0
"""


def calculate_order_total(subtotal: float, tax_rate: float, coupon_discount: float) -> float:
    """
    Calculate the final order total after tax and a flat-dollar coupon discount.

    Args:
        subtotal:        Pre-tax item total in dollars.
        tax_rate:        Multiplier e.g. 1.10 for 10% tax.
        coupon_discount: Flat dollar amount to discount e.g. 10.0 for $10 off.

    Returns:
        Rounded total in dollars.

    BUG: coupon_discount is subtracted from the subtotal *before* tax is applied.
    It should be subtracted *after* tax so that the full pre-discount subtotal
    is used as the taxable base.
    """
    total = round((subtotal - coupon_discount) * tax_rate, 2)  # BUG: discount before tax
    return total


def create_order(items: list[dict]) -> dict:
    """
    Create an order from a list of items.

    Each item: {"name": str, "price": float, "quantity": int}
    Tax rate is fixed at 10%. A $10 coupon applies when there are 3 or more items.
    """
    subtotal = sum(item["price"] * item["quantity"] for item in items)
    tax_rate = 1.10
    coupon_discount = 10.0 if len(items) >= 3 else 0.0

    total = calculate_order_total(subtotal, tax_rate, coupon_discount)

    return {
        "items": items,
        "subtotal": round(subtotal, 2),
        "tax_rate": tax_rate,
        "coupon_discount": coupon_discount,
        "total": total,
    }
