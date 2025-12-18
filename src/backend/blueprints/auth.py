from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.validators import DataRequired
from datetime import datetime, timedelta
from models.models import db, User, UserActivity
from utils.security_utils import SecurityValidator, log_security_event
from utils.utils import generate_activity_log

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    class LoginForm(FlaskForm):
        username = StringField('Username', validators=[DataRequired()])
        password = PasswordField('Password', validators=[DataRequired()])
        remember = BooleanField('Remember Me')
    
    form = LoginForm()
    
    if request.method == 'POST':
        if form.validate_on_submit():
            username = SecurityValidator.sanitize_input(
                form.username.data, max_length=50
            ).strip()
            password = form.password.data
            remember = form.remember.data
            
            user = User.query.filter_by(username=username).first()
            
            if user and user.check_password(password) and user.is_active:
                otp_enabled = str(current_app.config.get('OTP_ENABLED', True)).lower() in ['true', '1', 'yes']

                if otp_enabled and user.first_login:
                    session['first_login_user_id'] = user.id
                    session['first_login_remember'] = remember
                    session['first_login_next'] = request.args.get('next')

                    from utils.utils import generate_otp
                    otp_code = generate_otp()
                    session['first_login_otp'] = otp_code
                    session['first_login_otp_expires'] = (datetime.utcnow() + timedelta(minutes=current_app.config['OTP_EXPIRY_MINUTES'])).isoformat()

                    from services.email_service import email_service
                    success, error_message = email_service.send_first_login_otp(user, otp_code)

                    if success:
                        flash('This is your first login. Please check your email for further instructions.', 'info')
                        return redirect(url_for('otp.verify_first_login_otp'))
                    else:
                        current_app.logger.error(f"Failed to send first login OTP email: {error_message}")
                        # Show specific error if related to configuration
                        if "configuration" in str(error_message).lower() or "credentials" in str(error_message).lower():
                            flash(f'Email Error: {error_message}', 'error')
                        else:
                            flash('Failed to send OTP email. Please contact administrator or try again later.', 'error')
                        
                        session.pop('first_login_user_id', None)
                        session.pop('first_login_otp', None)
                        session.pop('first_login_otp_expires', None)
                        session.pop('first_login_remember', None)
                        session.pop('first_login_next', None)
                        return redirect(url_for('auth.login'))

                user.last_login = datetime.utcnow()
                db.session.commit()

                login_user(user, remember=remember)

                log_security_event(
                    "LOGIN_SUCCESS", 
                    f"Successful login for user: {user.username}",
                    user_id=user.id,
                    ip_address=request.remote_addr
                )

                generate_activity_log(
                    action='login',
                    description=f'Login successful for user: {user.username}',
                    user_id=user.id,
                    icon='fas fa-sign-in-alt',
                    color='success'
                )

                next_page = request.args.get('next')
                flash('Login successful!', 'success')
                return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))
            
            else:
                log_security_event(
                    "LOGIN_FAILED", 
                    f"Failed login attempt for username: {form.username.data if form.username.data else 'unknown'}",
                    ip_address=request.remote_addr
                )
                flash('Incorrect username or password!', 'error')
    else:
        if form.errors:
            current_app.logger.warning(f"Form validation errors: {form.errors}")
            flash('There are errors in the form. Please try again.', 'error')
    
    return render_template('auth/login.html', form=form)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('otp.register_request'))

@auth_bp.route('/logout')
@login_required
def logout():
    generate_activity_log(
        action='logout',
        description=f'Logout for user: {current_user.username}',
        user_id=current_user.id,
        icon='fas fa-sign-out-alt',
        color='warning'
    )
    
    logout_user()
    flash('Logout successful!', 'info')
    return redirect(url_for('auth.login'))
