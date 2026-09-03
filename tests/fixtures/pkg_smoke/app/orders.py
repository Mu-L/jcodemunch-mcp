"""Order handling for the smoke fixture."""

from dataclasses import dataclass


@dataclass
class Order:
    order_id: int
    total_cents: int


def compute_order_total(items: list[int]) -> int:
    """Sum line totals; the symbol the smoke test looks up by name."""
    return sum(items)


def apply_discount(total: int, pct: int) -> int:
    return total - (total * pct) // 100
