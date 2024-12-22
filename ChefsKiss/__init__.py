from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager
import os

# Declarations to insert before the create_app function:

class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


def create_app(test_config=None):
    app = Flask(__name__)
    

    # A secret for signing session cookies
    app.config["SECRET_KEY"] = "93220d9b340cf9a6c39bac99cce7daf220167498f91fa"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///datingapp.db"
    app.config['UPLOAD_FOLDER'] = os.path.join(
    os.path.dirname(__file__), 'static', 'uploads'
)

    app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # Limit file size to 2MB
    app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
    app.config["TABLES_PER_NIGHT"] = 2
    # Ensure the upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Register blueprints
    from . import main  # Import main blueprint
    from . import auth  # Import auth blueprint
    from . import model

    db.init_app(app)

    # With the other imports at the beginning:

    # Inside create_app:
    login_manager = LoginManager()
    
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(model.User, int(user_id))


    # Register the blueprints
    app.register_blueprint(main.bp)  # Register main blueprint
    app.register_blueprint(auth.bp)  # Register auth blueprint

    return app
