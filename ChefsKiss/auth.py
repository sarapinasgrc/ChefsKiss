from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, abort
from werkzeug.security import generate_password_hash, check_password_hash
from . import db
from . import model
import flask_login
from flask_login import current_user
from flask import redirect, url_for
from flask_login import logout_user, login_required
import os
from datetime import datetime
import pathlib


bp = Blueprint("auth", __name__)

# Home Page
@bp.route("/")
def home():
    return render_template("auth/home.html")

@bp.route("/signup", methods=["GET"])
def signup():
    return render_template("auth/signup.html")

@bp.route("/signup", methods=["POST"])
def signup_post():
    email = request.form.get("email")
    password_repeat = request.form.get("password_repeat")
    password = request.form.get("password")
    name = request.form.get("name")
    lastname = request.form.get("lastname")
    gender = request.form.get("gender")
    year_of_birth = int(request.form.get("year_of_birth"))
    gender_preference_str = request.form.get("gender_preference")
    lower_year_difference = int(request.form.get("min_age_difference"))
    upper_year_difference = int(request.form.get("max_age_difference"))
    bio_text = request.form.get("bio")
    interests = request.form.get("interests")
    uploaded_file = request.files["photo"]

    # Most of the validations are already checked with the html form default settings and also using javascript
    # The verifications can be seen in signup.html

    if not email or "@" not in email or "." not in email.split("@")[-1]:
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("auth.signup"))

    if not isinstance(name, str) or name.strip() == "":
        flash("Name must be a valid text string.", "error")
        return redirect(url_for("auth.signup"))

    if not isinstance(lastname, str) or lastname.strip() == "":
        flash("Last name must be a valid text string.", "error")
        return redirect(url_for("auth.signup"))

    if not isinstance(bio_text, str) or bio_text.strip() == "" or len(bio_text) > 2000:
        flash("Bio must be a valid text string less than 2000 characters.", "error")
        return redirect(url_for("auth.signup"))

    if not isinstance(interests, str) or interests.strip() == "" or len(interests) > 2000:
        flash("Interests must be a valid text string less than 2000 characters.", "error")
        return redirect(url_for("auth.signup"))

    # Validate passwords
    if not password or len(password) < 3:
        flash("Password must be at least 3 characters long.", "error")
        return redirect(url_for("auth.signup"))
    if password != password_repeat:
        flash("Passwords do not match.", "error")
        return redirect(url_for("auth.signup"))

    # Hash password
    password_hash = generate_password_hash(password)

    # Calculate age
    current_year = datetime.now().year
    age = current_year - year_of_birth

    # Validate age ranges
    if age - lower_year_difference < 18:
        flash("Minimum age difference not valid.", "error")
        return redirect(url_for("auth.signup"))

    if age + upper_year_difference > 100:
        flash("Maximum age difference not valid.", "error")
        return redirect(url_for("auth.signup"))

    # Verify email is unique
    query = db.select(model.User).where(model.User.email == email)
    existing_user = db.session.execute(query).scalar_one_or_none()
    if existing_user:
        flash("Email is already registered.", "error")
        return redirect(url_for("auth.signup"))

    # Handle photo upload
    if uploaded_file.filename != "":
        content_type = uploaded_file.content_type
        if content_type == "image/png":
            file_extension = "png"
        elif content_type == "image/jpeg":
            file_extension = "jpg"
        else:
            abort(400, f"Unsupported file type {content_type}")

        photo = model.Photo(file_extension=file_extension)
        db.session.add(photo)
        db.session.commit()
        path = (
            pathlib.Path(current_app.root_path)
            / "static"
            / "photos"
            / f"photo-{photo.id}.{file_extension}"
        )
        uploaded_file.save(path)




    # Convert gender preference string to enum
    try:
        gender_preference = model.GenderPreference[gender_preference_str.lower()]
    except KeyError:
        flash("Invalid gender preference selected.", "error")
        return redirect(url_for("auth.signup"))

    # Create new user
    new_user = model.User(
        email=email,
        name=name,
        lastname=lastname,
        password=password_hash,
        gender=gender,
        year_of_birth=year_of_birth,

    )

    # Create matching preferences
    matching_preferences = model.MatchingPreference(
        gender_preference=gender_preference,
        lower_year_preference=year_of_birth + lower_year_difference,
        upper_year_preference=year_of_birth - upper_year_difference,
        user=new_user,
    )

    # Create new profile
    new_profile = model.Profile(
        name=name,
        email=email,
        year_of_birth=year_of_birth,
        gender=gender,
        user=new_user,
        interests=interests,
        bio = bio_text,
        photo_id=photo.id if uploaded_file.filename != "" else None,
    )

    db.session.add(new_user)
    db.session.add(matching_preferences)
    db.session.add(new_profile)

    db.session.commit()

    flash("Account created successfully! Please log in.", "success")
    return redirect(url_for("auth.login"))


@bp.errorhandler(413)
def file_too_large(error):
    flash("File size is too large.")
    return redirect(url_for("auth.signup"))

# Route to render the login form
@bp.route("/login", methods=["GET"])
def login():
    return render_template("auth/login.html")


# Route to process login form submission
@bp.route("/login", methods=["POST"])
def login_post():
    email = request.form.get("email")
    password = request.form.get("password")

    # Get the user with that email from the database
    query = db.select(model.User).where(model.User.email == email)
    user = db.session.execute(query).scalar_one_or_none()


    if user and check_password_hash(user.password, password):
        flash("Login successful!", "success")
        flask_login.login_user(user)
        return redirect(url_for("main.index"))
    else:
        # Wrong email and/or password
        flash("Invalid email or password. Please try again.", "error")
        return redirect(url_for("auth.login"))


@bp.route("/logout")
@login_required
def logout():
    logout_user()  # Log out the user
    return redirect(url_for("auth.home"))

