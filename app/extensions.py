"""Flask extension instances. Initialised in create_app()."""
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"
