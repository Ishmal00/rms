from app.extensions import db
from app.models.base import BaseModel


class Category(BaseModel):
    """Primary menu categories (e.g., Appetizers, Main Course, Drinks, Desserts)."""
    __tablename__ = 'categories'

    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    image_url = db.Column(db.String(255), nullable=True)

    # Relationships with explicit foreign_keys
    subcategories = db.relationship(
        'SubCategory',
        back_populates='category',
        foreign_keys='SubCategory.category_id',
        cascade='all, delete-orphan',
        order_by='SubCategory.display_order'
    )
    menu_items = db.relationship(
        'MenuItem',
        back_populates='category',
        foreign_keys='MenuItem.category_id',
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<Category {self.name}>'


class SubCategory(BaseModel):
    """Subcategories nested under a primary category (e.g., Pasta, Burgers, Cocktails)."""
    __tablename__ = 'subcategories'

    category_id = db.Column(
        db.Integer,
        db.ForeignKey('categories.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    # Relationships
    category = db.relationship(
        'Category',
        back_populates='subcategories',
        foreign_keys=[category_id]
    )
    menu_items = db.relationship(
        'MenuItem',
        back_populates='subcategory',
        foreign_keys='MenuItem.subcategory_id',
        lazy='dynamic'
    )

    __table_args__ = (
        db.UniqueConstraint('category_id', 'slug', name='uq_category_subcategory_slug'),
    )

    def __repr__(self):
        return f'<SubCategory {self.name}>'


class MenuItem(BaseModel):
    """Menu items available for ordering."""
    __tablename__ = 'menu_items'

    category_id = db.Column(
        db.Integer,
        db.ForeignKey('categories.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    subcategory_id = db.Column(
        db.Integer,
        db.ForeignKey('subcategories.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(150), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    base_price = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    prep_time_minutes = db.Column(db.Integer, default=15, nullable=False)
    is_vegetarian = db.Column(db.Boolean, default=False, nullable=False)
    is_spicy = db.Column(db.Boolean, default=False, nullable=False)
    image_url = db.Column(db.String(255), nullable=True)

    # Relationships
    category = db.relationship('Category', back_populates='menu_items', foreign_keys=[category_id])
    subcategory = db.relationship('SubCategory', back_populates='menu_items', foreign_keys=[subcategory_id])
    variants = db.relationship(
        'ItemVariant',
        back_populates='menu_item',
        foreign_keys='ItemVariant.menu_item_id',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<MenuItem {self.name} - ${self.base_price}>'


class ItemVariant(BaseModel):
    """Portion sizes and variants for menu items (e.g. Small, Medium, Large, Spicy)."""
    __tablename__ = 'item_variants'

    menu_item_id = db.Column(
        db.Integer,
        db.ForeignKey('menu_items.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    name = db.Column(db.String(80), nullable=False)
    additional_price = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    sku = db.Column(db.String(50), nullable=True, index=True)

    # Relationships
    menu_item = db.relationship('MenuItem', back_populates='variants', foreign_keys=[menu_item_id])

    def __repr__(self):
        return f'<ItemVariant {self.name} (+${self.additional_price})>'


class Ingredient(BaseModel):
    """Raw ingredients and allergens tracking for menu recipes."""
    __tablename__ = 'ingredients'

    name = db.Column(db.String(100), unique=True, nullable=False)
    unit = db.Column(db.String(30), nullable=False)
    cost_per_unit = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    allergen_info = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<Ingredient {self.name} ({self.unit})>'
