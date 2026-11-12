from app.extensions import db
from app.models.base import BaseModel


class Supplier(BaseModel):
    """Suppliers and vendors providing ingredients and restaurant goods."""
    __tablename__ = 'suppliers'

    name = db.Column(db.String(120), nullable=False, index=True)
    contact_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    address = db.Column(db.Text, nullable=True)
    tax_id = db.Column(db.String(50), nullable=True)

    # Relationships
    inventory_items = db.relationship(
        'InventoryItem',
        back_populates='supplier',
        foreign_keys='InventoryItem.supplier_id',
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<Supplier {self.name}>'


class InventoryItem(BaseModel):
    """Raw materials and supplies tracked in inventory."""
    __tablename__ = 'inventory_items'

    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey('suppliers.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    name = db.Column(db.String(150), nullable=False)
    sku = db.Column(db.String(50), unique=True, nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False, default='General', index=True)
    unit = db.Column(db.String(30), nullable=False)
    current_stock = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    minimum_stock = db.Column(db.Numeric(10, 2), default=5.00, nullable=False)
    reorder_quantity = db.Column(db.Numeric(10, 2), default=10.00, nullable=False)
    unit_cost = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)

    # Relationships
    supplier = db.relationship('Supplier', back_populates='inventory_items', foreign_keys=[supplier_id])
    movements = db.relationship(
        'StockMovement',
        back_populates='inventory_item',
        foreign_keys='StockMovement.inventory_item_id',
        cascade='all, delete-orphan',
        order_by='StockMovement.created_at.desc()'
    )

    @property
    def is_low_stock(self):
        """Returns True if current stock is below or equal to minimum threshold."""
        return self.current_stock <= self.minimum_stock

    def __repr__(self):
        return f'<InventoryItem {self.name} ({self.current_stock} {self.unit})>'


class StockMovement(BaseModel):
    """Audit log of stock movements (IN from purchase, OUT for kitchen, WASTE, ADJUSTMENT)."""
    __tablename__ = 'stock_movements'

    inventory_item_id = db.Column(
        db.Integer,
        db.ForeignKey('inventory_items.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    movement_type = db.Column(
        db.String(20),
        nullable=False,
        index=True
    )  # 'IN', 'OUT', 'ADJUSTMENT', 'WASTE'
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    unit_cost = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    reference_no = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Relationships
    inventory_item = db.relationship(
        'InventoryItem',
        back_populates='movements',
        foreign_keys=[inventory_item_id]
    )

    def __repr__(self):
        return f'<StockMovement {self.movement_type} {self.quantity} for item_id={self.inventory_item_id}>'
