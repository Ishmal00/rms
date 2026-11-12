import os
from flask import Flask, render_template
from app.config import config
from app.extensions import db, migrate, login_manager, csrf
from app.services.cache_service import cache
from app.models.base import register_base_model_events
from app.models.auth import User


def create_app(config_name=None):
    """Application factory for the Restaurant Management System."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config['default']))

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Initialize Redis caching
    cache.init_app(app.config.get('REDIS_URL'))

    # Setup user loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Register BaseModel audit and soft-delete event listeners
    with app.app_context():
        register_base_model_events(app, db.session)

    # Register Blueprints
    from app.blueprints.auth import auth_bp
    from app.blueprints.dashboard import dashboard_bp
    from app.blueprints.menu import menu_bp
    from app.blueprints.inventory import inventory_bp
    from app.blueprints.tables import tables_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.orders import orders_bp
    from app.blueprints.kitchen import kitchen_bp
    from app.blueprints.billing import billing_bp
    from app.blueprints.staff.routes import staff_bp
    from app.blueprints.delivery.routes import delivery_bp
    from app.blueprints.expenses.routes import expenses_bp
    from app.blueprints.loyalty.routes import loyalty_bp
    from app.blueprints.feedback.routes import feedback_bp
    from app.blueprints.reports.routes import reports_bp
    from app.blueprints.settings.routes import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(menu_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(tables_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(kitchen_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(delivery_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(loyalty_bp)
    app.register_blueprint(feedback_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)

    # Error handlers
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500

    # Shell context for CLI
    @app.shell_context_processor
    def make_shell_context():
        import app.models as models
        return {'db': db, **{k: getattr(models, k) for k in models.__all__}}

    # CLI command to initialize database tables and seed
    @app.cli.command('init-db')
    def init_db_command():
        """Creates tables from code via db.create_all() and runs seed."""
        db.create_all()
        from app.seeds.seed_data import seed_database
        seed_database()
        print("Database initialized and seeded successfully.")

    return app
