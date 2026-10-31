"""Explicit purchased project-lot cost attribution, never inferred FIFO allocation."""

from decimal import Decimal

from app.modules.ifrs.schemas import InventoryItem, StockIssue, StockReceipt


class ProjectCostLayers:
    def __init__(self, item: InventoryItem):
        self.item = item
        self.layers: dict[str, dict] = {}
        self.allocations: list[dict] = []
        if item.opening_unit_cost or item.opening_cost_evidence.strip():
            raise ValueError("Project lots require opening layers, not a pooled opening unit cost")
        if (
            sum((layer.quantity for layer in item.opening_layers), Decimal(0))
            != item.opening_quantity
        ):
            raise ValueError("Project opening layers must reconcile to opening quantity")
        references = [layer.reference for layer in item.opening_layers]
        references += [m.reference for m in item.receipts]
        references += [m.reference for m in item.issues]
        if len(references) != len(set(references)):
            raise ValueError("Project layer and movement references must be distinct")
        for layer in item.opening_layers:
            self.add(
                layer.reference, layer.quantity, layer.quantity * layer.unit_cost, layer.evidence
            )

    @property
    def cost(self):
        return sum((layer["remaining_cost"] for layer in self.layers.values()), Decimal(0))

    @property
    def quantity(self):
        return sum((layer["remaining_quantity"] for layer in self.layers.values()), Decimal(0))

    def add(self, reference: str, quantity: Decimal, cost: Decimal, evidence: str):
        if not reference.strip() or not evidence.strip():
            raise ValueError("Project cost layers require explicit reference and evidence")
        if reference in self.layers:
            raise ValueError("Duplicate project cost layer")
        self.layers[reference] = {
            "item": self.item.reference,
            "identification_reference": self.item.identification_reference.strip(),
            "layer_reference": reference,
            "original_quantity": quantity,
            "original_cost": cost,
            "remaining_quantity": quantity,
            "remaining_cost": cost,
            "source_evidence": evidence,
        }

    def receipt(self, receipt: StockReceipt, cost: Decimal):
        self.add(receipt.reference, receipt.quantity, cost, receipt.evidence)

    def issue(self, issue: StockIssue):
        allocations = issue.cost_allocations
        if not allocations or sum((a.quantity for a in allocations), Decimal(0)) != issue.quantity:
            raise ValueError(
                "Project issue requires explicit cost allocations for its entire quantity"
            )
        refs = [a.layer_reference for a in allocations]
        if len(refs) != len(set(refs)):
            raise ValueError("Duplicate project issue allocation target")
        total = Decimal(0)
        for allocation in allocations:
            if not allocation.evidence.strip():
                raise ValueError("Project issue allocation requires evidence")
            layer = self.layers.get(allocation.layer_reference)
            if layer is None:
                raise ValueError("Project issue targets a missing or future cost layer")
            quantity = allocation.quantity
            if quantity > layer["remaining_quantity"]:
                raise ValueError("Project issue exceeds the selected layer quantity")
            # Exhaustion consumes the original layer's entire residual, avoiding
            # cumulative division drift. No cost is borrowed from another layer.
            cost = (
                layer["remaining_cost"]
                if quantity == layer["remaining_quantity"]
                else layer["remaining_cost"] * quantity / layer["remaining_quantity"]
            )
            layer["remaining_quantity"] -= quantity
            layer["remaining_cost"] -= cost
            total += cost
            self.allocations.append(
                {
                    "item": self.item.reference,
                    "identification_reference": self.item.identification_reference.strip(),
                    "issue_reference": issue.reference,
                    "layer_reference": allocation.layer_reference,
                    "quantity": quantity,
                    "cost": cost,
                    "remaining_quantity": layer["remaining_quantity"],
                    "remaining_cost": layer["remaining_cost"],
                    "source_evidence": layer["source_evidence"],
                    "allocation_evidence": allocation.evidence,
                }
            )
        return total
