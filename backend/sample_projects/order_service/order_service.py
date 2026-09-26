"""
Order Service — sample project for DevProof AI.

Bug (intentional): discount_amount is computed from the pre-tax subtotal,
but it should be computed from the post-tax total.

Buggy formula:
    discount_amount = subtotal * discount_rate          # computed on pre-tax
    total = (subtotal - discount_amount) * tax_rate     # wrong: discount eats pre-tax base

Correct formula:
    post_tax = subtotal * tax_rate
    discount_amount = post_tax * discount_rate          # computed on post-tax
    total = post_tax - discount_amount
          = subtotal * tax_rate * (1 - discount_rate)
"""


def calculate_order_total(subtotal: float, tax_rate: float, discount_rate: float) -> float:
    """
    Calculate the final order total.

    Args:
        subtotal:      Pre-tax item total in dollars.
        tax_rate:      Multiplier e.g. 1.10 for 10% tax.
        discount_rate: Fraction to discount e.g. 0.20 for 20% off.

    Returns:
        Rounded total in dollars.

    BUG: discount_amount is derived from the pre-tax subtotal instead of the
    post-tax total, so customers receive a smaller discount than advertised.
    """
    discount_amount = subtotal * discount_rate          # BUG: should use subtotal * tax_rate
    total = (subtotal - discount_amount) * tax_rate
    return round(total, 2)


def create_order(items: list[dict]) -> dict:
    """
    Create an order from a list of items.

    Each item: {"name": str, "price": float, "quantity": int}
    Tax rate is fixed at 10%. Discount applies when there are 3 or more items.
    """
    subtotal = sum(item["price"] * item["quantity"] for item in items)
    tax_rate = 1.10
    discount_rate = 0.10 if len(items) >= 3 else 0.0

    total = calculate_order_total(subtotal, tax_rate, discount_rate)

    return {
        "items": items,
        "subtotal": round(subtotal, 2),
        "tax_rate": tax_rate,
        "discount_rate": discount_rate,
        "total": total,
    }
