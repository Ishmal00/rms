from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models.base import BaseModel


class Role(BaseModel):
    """Roles for role-based access control (RBAC)."""
    __tablename__ = 'roles'

    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)

    # Explicit foreign_keys to resolve ambiguity with BaseModel audit columns
    users = db.relationship(
        'User',
        back_populates='role',
        foreign_keys='User.role_id',
        lazy='dynamic'
    )
    role_permissions = db.relationship(
        'RolePermission',
        back_populates='role',
        foreign_keys='RolePermission.role_id',
        cascade='all, delete-orphan',
        lazy='joined'
    )

    def __repr__(self):
        return f'<Role {self.name}>'


class Permission(BaseModel):
    """System permissions mapped to modules and actions."""
    __tablename__ = 'permissions'

    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    module = db.Column(db.String(50), nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)

    # Relationships
    role_permissions = db.relationship(
        'RolePermission',
        back_populates='permission',
        foreign_keys='RolePermission.permission_id',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<Permission {self.slug}>'


class RolePermission(BaseModel):
    """Association model linking Roles and Permissions."""
    __tablename__ = 'role_permissions'

    role_id = db.Column(
        db.Integer,
        db.ForeignKey('roles.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    permission_id = db.Column(
        db.Integer,
        db.ForeignKey('permissions.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Relationships
    role = db.relationship('Role', back_populates='role_permissions', foreign_keys=[role_id])
    permission = db.relationship('Permission', back_populates='role_permissions', foreign_keys=[permission_id])

    __table_args__ = (
        db.UniqueConstraint('role_id', 'permission_id', name='uq_role_permission'),
    )

    def __repr__(self):
        return f'<RolePermission role_id={self.role_id} permission_id={self.permission_id}>'


class User(UserMixin, BaseModel):
    """Application users with authentication and RBAC."""
    __tablename__ = 'users'

    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    role_id = db.Column(
        db.Integer,
        db.ForeignKey('roles.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    last_login_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    role = db.relationship('Role', back_populates='users', foreign_keys=[role_id], lazy='joined')

    def set_password(self, password):
        """Generates and sets the salted password hash."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verifies given password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    def has_role(self, role_slug):
        """Checks if user has a specific role."""
        return self.role is not None and self.role.slug == role_slug

    def has_permission(self, permission_slug):
        """Checks if user's role grants a specific permission."""
        if not self.role:
            return False
        # Super admin has all permissions
        if self.role.slug == 'admin':
            return True
        for rp in self.role.role_permissions:
            if rp.permission and rp.permission.slug == permission_slug:
                return True
        return False

    def __repr__(self):
        return f'<User {self.username} ({self.email})>'
