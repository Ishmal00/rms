from datetime import datetime
from urllib.parse import urlsplit
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.models.auth import User
from app.blueprints.auth.forms import LoginForm

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def _is_safe_next_url(target):
    if not target or not target.startswith('/') or target.startswith('//'):
        return False
    parsed = urlsplit(target)
    return not parsed.scheme and not parsed.netloc


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = LoginForm()
    if form.validate_on_submit():
        ident = form.identity.data.strip()
        # Search by email or username using ORM (no raw SQL)
        user = User.query.filter(
            (User.email == ident) | (User.username == ident)
        ).first()

        if user and user.check_password(form.password.data):
            if user.status != 'active':
                flash('Your account has been deactivated. Please contact an administrator.', 'danger')
                return render_template('auth/login.html', form=form)

            # Record login timestamp
            user.last_login_at = datetime.utcnow()
            db.session.commit()

            login_user(user, remember=form.remember_me.data)
            flash(f'Welcome back, {user.full_name}!', 'success')

            next_page = request.args.get('next')
            if not _is_safe_next_url(next_page):
                next_page = url_for('dashboard.index')
            return redirect(next_page)
        else:
            flash('Invalid username/email or password.', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html', user=current_user)
