from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    """User login form with validation."""
    identity = StringField(
        'Email or Username',
        validators=[DataRequired(), Length(min=3, max=120)],
        render_kw={'placeholder': 'Enter email or username', 'class': 'form-control', 'autofocus': True}
    )
    password = PasswordField(
        'Password',
        validators=[DataRequired(), Length(min=6, max=100)],
        render_kw={'placeholder': 'Enter your password', 'class': 'form-control'}
    )
    remember_me = BooleanField('Remember me on this device', default=False)
    submit = SubmitField('Sign In', render_kw={'class': 'btn btn-primary w-100 py-2 fw-semibold'})
