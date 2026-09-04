"""Inventory for the smoke fixture."""

from .orders import compute_order_total


class Inventory:
    def __init__(self) -> None:
        self.stock: dict[str, int] = {}

    def reserve(self, sku: str, qty: int) -> bool:
        have = self.stock.get(sku, 0)
        if have < qty:
            return False
        self.stock[sku] = have - qty
        return True

    def order_value(self, prices: list[int]) -> int:
        return compute_order_total(prices)
