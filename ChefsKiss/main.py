import datetime
import flask_login
from flask import Blueprint, render_template, request, redirect, url_for, abort, flash, current_app, \
    send_from_directory, jsonify, session
from flask_login import current_user
from . import model, db
import pathlib
from sqlalchemy import or_
from sqlalchemy.sql import func
import os
from pathlib import Path
import dateutil.tz

bp = Blueprint("main", __name__)


# Main page where users scroll through profiles
@bp.route("/index")
@flask_login.login_required
def index():
    user = flask_login.current_user

    if not user:
        abort(404,
              description="An error ocurred when retrieving the user logged in. Please, refresh the page and log in again.")  # Handle case where user is not found

    preferences = user.matching_preferences

    if not preferences:
        flash("Please update your matching preferences in the settings.", "info")
        return redirect(url_for("main.settings"))

    # Current user characteristics
    lower_year = preferences.lower_year_preference
    upper_year = preferences.upper_year_preference
    gender_preference = preferences.gender_preference
    user_born = user.year_of_birth

    # Exclude blocked users and users who have blocked the current user
    blocked_user_ids = [blocked.id for blocked in user.blocking]
    blockers_ids = [blocker.id for blocker in user.blockers]

    # Filter by age first
    profiles_query = model.Profile.query.join(
        model.User, model.User.id == model.Profile.user_id
    ).outerjoin(
        model.Photo, model.Profile.photo_id == model.Photo.id
    ).join(
        model.MatchingPreference, model.MatchingPreference.user_id == model.User.id
    ).where(
        ~model.User.id.in_(blocked_user_ids),  # Exclude users blocked by the current user
        ~model.User.id.in_(blockers_ids),  # Exclude users blocking the current user
        ~model.User.id.in_(
            db.session.query(model.LikingAssociation.liked_id).filter_by(liker_id=user.id)
        ),
        model.User.id != user.id  # Exclude the current user's own profile
    ).where(
        # Ensure the profile's age is within the user's preference range
        model.Profile.year_of_birth <= lower_year,
        model.Profile.year_of_birth >= upper_year,
        # Ensure the current user's age is within the profile's preference range
        model.MatchingPreference.lower_year_preference >= user_born,
        model.MatchingPreference.upper_year_preference <= user_born
    )

    # Filtering by gender
    # Check that the user whose profile is shown could like the user logged in base on gender preference
    # First option: the user is a male
    if user.gender == 'Male':
        if gender_preference == model.GenderPreference.male:
            profiles_query = (profiles_query.where(model.User.gender == 'Male').where(
                or_(
                    model.MatchingPreference.gender_preference == model.GenderPreference.male,
                    model.MatchingPreference.gender_preference == model.GenderPreference.both)
            ))
        elif gender_preference == model.GenderPreference.female:
            profiles_query = (profiles_query.where(model.User.gender == 'Female').where(
                or_(
                    model.MatchingPreference.gender_preference == model.GenderPreference.male,
                    model.MatchingPreference.gender_preference == model.GenderPreference.both)
            ))
        elif gender_preference == model.GenderPreference.both:
            profiles_query = (profiles_query.where(
                or_(
                    model.MatchingPreference.gender_preference == model.GenderPreference.male,
                    model.MatchingPreference.gender_preference == model.GenderPreference.both)
            ))

    # Second option: the user is a female
    elif user.gender == 'Female':
        if gender_preference == model.GenderPreference.male:
            profiles_query = (profiles_query.where(model.User.gender == 'Male').where(
                or_(
                    model.MatchingPreference.gender_preference == model.GenderPreference.female,
                    model.MatchingPreference.gender_preference == model.GenderPreference.both)
            ))
        elif gender_preference == model.GenderPreference.female:
            profiles_query = (profiles_query.where(model.User.gender == 'Female').where(
                or_(
                    model.MatchingPreference.gender_preference == model.GenderPreference.female,
                    model.MatchingPreference.gender_preference == model.GenderPreference.both)
            ))
        elif gender_preference == model.GenderPreference.both:
            profiles_query = (
                profiles_query.where(
                    or_(
                        model.MatchingPreference.gender_preference == model.GenderPreference.female,
                        model.MatchingPreference.gender_preference == model.GenderPreference.both)
                ))

    # All profiles satisfying the criteria must be included
    profiles = profiles_query.all()

    # Render the index page with the filtered profiles
    return render_template("main/index.html", user=user, profiles=profiles)


# My own user profile
@bp.route("/myprofile")
@flask_login.login_required
def my_profile():
    user = flask_login.current_user  # Get the currently logged-in user

    if not user:
        abort(404,
              description="An error ocurred when retrieving the user logged in. Please, refresh the page and log in again.")  # Handle case where user is not found

    photo = user.profile.photo

    if not photo:
        flash("Please update your photo in the settings, it is mandatory to have a profile picture.", "info")
        return redirect(url_for("main.settings"))

    # Pass user information to the template
    return render_template("main/myprofile.html", user=user, photo=photo)


# The profile of each user when you click on the View Profile button
@bp.route("/profile/<int:profile_id>")
@flask_login.login_required
def profile_detail(profile_id):
    # Fetch the profile by profile_id from the database
    user_id = current_user.id
    profile = model.Profile.query.get(profile_id)

    my_blocked_user_ids = db.session.query(model.User.id).join(
        model.BlockingAssociation, model.BlockingAssociation.blocked_id == model.User.id
    ).filter(model.BlockingAssociation.blocker_id == user_id).all()

    my_blocked_user_ids = [user_id[0] for user_id in my_blocked_user_ids]

    # This will never occur unless there is a major error with the network and profiles cannot be retreived from the database
    if not profile:
        abort(404,
              description="An error ocurred when retrieving the profile. Please, go back to the main menu and try again.")  # Handle case where profile is not found

    photo = profile.photo
    return render_template("main/profile_detail.html", profile=profile, photo=photo,
                           my_blocked_user_ids=my_blocked_user_ids)


# This function retrieves the path of the profile picture, as shown in the statement
def photo_filename(photo):
    path = (
            pathlib.Path(current_app.root_path)
            / "static"
            / "photos"
            / f"photo-{photo.id}.{photo.file_extension}"
    )
    return path


# Settings page for user to update preferences
@bp.route('/settings', methods=['GET', 'POST'])
@flask_login.login_required
def settings():
    user = flask_login.current_user
    if not user:
        abort(404,
              description="An error ocurred when retrieving the user logged in. Please, refresh the page and log in again.")  # Handle case where user is not found

    if request.method == 'POST':

        # Update basic information
        user.name = request.form.get('name')
        user.lastname = request.form.get('lastname')
        user.gender = request.form.get('gender')
        user.year_of_birth = int(request.form.get('year_of_birth'))

        uploaded_file = request.files['photo']
        file_extension = None

        if uploaded_file.filename != '':
            content_type = uploaded_file.content_type
            if content_type == "image/png":
                file_extension = "png"
            elif content_type == "image/jpeg":
                file_extension = "jpg"
            else:
                abort(400, f"Unsupported file type {content_type}")

            photo = model.Photo(
                file_extension=file_extension
            )
            db.session.add(photo)

            # Remove old photo if it exists
            old_photo = flask_login.current_user.profile.photo
            if old_photo is not None:
                path = photo_filename(old_photo)
                path.unlink()
                db.session.delete(old_photo)

            # Save the new photo
            flask_login.current_user.profile.photo = photo
            path = photo_filename(photo)
            uploaded_file.save(path)

        # Update matching preferences
        matching_preferences = user.matching_preferences
        matching_preferences.gender_preference = request.form.get('gender_preference')
        matching_preferences.lower_year_preference = user.year_of_birth + int(request.form.get('min_age_difference'))
        matching_preferences.upper_year_preference = user.year_of_birth - int(request.form.get('max_age_difference'))

        # Update profile bio
        profile = user.profile
        profile.bio = request.form.get('bio')
        profile.interests = request.form.get('interests')
        profile.name = user.name
        profile.year_of_birth = user.year_of_birth
        profile.gender = user.gender

        if not isinstance(user.name, str) or user.name.strip() == "":
            flash("Name must be a valid text string.", "error")
            return redirect(url_for("main.settings"))

        if not isinstance(user.lastname, str) or user.lastname.strip() == "":
            flash("Last name must be a valid text string.", "error")
            return redirect(url_for("main.settings"))

        if not isinstance(profile.bio, str) or profile.bio.strip() == "" or len(profile.bio) > 2000:
            flash("Bio must be a valid text string less than 2000 characters.", "error")
            return redirect(url_for("main.settings"))

        if not isinstance(profile.interests, str) or profile.interests.strip() == "" or len(profile.interests) > 2000:
            flash("Interests must be a valid text string less than 2000 characters.", "error")
            return redirect(url_for("main.settings"))

        # Save changes to the database
        db.session.commit()
        flash("Settings updated successfully!", "success")
        return redirect(url_for('main.settings'))

    photo = user.profile.photo if user.profile else None  # Ensure that the user can update the preferences without updating the profile picture

    return render_template('main/settings.html', user=user, photo=photo)


# The following 2 routes trigger when you click the propose date button, first get and then post
# This retrieves the form
@bp.route("/propose_date_form/<int:recipient_id>", methods=["GET"])
@flask_login.login_required
def propose_date_form(recipient_id):
    recipient = model.User.query.get_or_404(recipient_id)

    # Blocked users cannot send proposals
    if recipient in flask_login.current_user.blocking:
        flash("You cannot send a proposal to a user you have blocked.", "danger")
        return redirect(url_for("main.index"))
    if flask_login.current_user in recipient.blocking:
        flash("This user has blocked you. You cannot send a date proposal.", "danger")
        return redirect(url_for("main.index"))

    # Fetch all restaurants for the user to select
    restaurants = model.Restaurant.query.all()

    if not restaurants:
        flash("There are no restaurants in the database. Please try again later or contact support.", "error")
        return redirect(url_for('main.index'))  # Redirect to a relevant page

    # Render the proposal date form
    return render_template("main/propose_date_form.html", profile=recipient, restaurants=restaurants)


# Posting the proposal date
@bp.route("/propose_date/<int:recipient_id>", methods=["POST"])
@flask_login.login_required
def propose_date(recipient_id):
    recipient = model.User.query.get_or_404(recipient_id)
    proposer = flask_login.current_user

    # Get form data
    proposal_date_str = request.form.get("proposal_date")
    proposal_message = request.form.get("proposal_message", "").strip()
    restaurant_id = request.form.get("restaurant_id")

    restaurant = model.Restaurant.query.get(restaurant_id)

    # Validate restaurant
    if not restaurant:
        flash("Invalid restaurant selected.", "danger")
        return redirect(url_for("main.propose_date_form", recipient_id=recipient_id))

    # Validate proposal date
    if not proposal_date_str:
        flash("Please, provide a valid proposal date.", "danger")
        return redirect(url_for("main.propose_date_form", recipient_id=recipient_id))

    # Ensure we store the correct data type for the date
    try:
        proposal_date = datetime.datetime.strptime(proposal_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("An error ocurred. The date format is invalid. Please try again.", "danger")
        return redirect(url_for("main.propose_date_form", recipient_id=recipient_id))

    # Validate proposal message
    if len(proposal_message) > 600:
        flash("Proposal message cannot exceed 600 characters.", "danger")
        return redirect(url_for("main.propose_date_form", recipient_id=recipient_id))

    # Check for blocked users
    if proposer in recipient.blocking:
        # Automatically mark the proposal as ignored
        proposal_status = model.ProposalStatus.ignored
        flash("The recipient has blocked you. Your proposal will be ignored.", "warning")
    else:

        proposal_status = model.ProposalStatus.proposed

        # Check table availability only if not blocked
        occupied_tables = (
            model.DateProposal.query.filter_by(proposal_date=proposal_date, restaurant_id=restaurant.id)
            .filter(model.DateProposal.status.in_([model.ProposalStatus.proposed, model.ProposalStatus.accepted]))
            .count()
        )

        # Check that the proposed restaurant has enough tables on that date
        if occupied_tables >= restaurant.tables_available:
            flash(
                f"{restaurant.name} is fully booked on {proposal_date}. Please choose a different date or restaurant.",
                "warning")
            return redirect(url_for("main.propose_date_form", recipient_id=recipient_id))

        # Check that the date is in the future
        if proposal_date <= datetime.datetime.now().date():
            flash("You cannot book a date for today or in the past.", "warning")
            return redirect(url_for("main.propose_date_form", recipient_id=recipient_id))

    # Create a new proposal
    proposal = model.DateProposal(
        proposer=proposer,
        recipient=recipient,
        proposal_date=proposal_date,
        proposal_message=proposal_message,
        restaurant_id=restaurant.id,
        status=proposal_status,
    )

    db.session.add(proposal)
    db.session.commit()

    flash("Date proposal sent successfully.", "success")
    return redirect(url_for("main.index"))


@bp.route("/respond_to_proposal/<int:proposal_id>", methods=["POST"])
@flask_login.login_required
def respond_to_proposal(proposal_id):
    proposal = model.DateProposal.query.get_or_404(proposal_id)

    # Only the recipient can respond
    if proposal.recipient != flask_login.current_user:
        abort(403)

    # Ensure proposal is still pending
    if proposal.status != model.ProposalStatus.proposed:
        flash("This proposal has already been handled.", "warning")
        return redirect(url_for("main.index"))

    # Get and validate response status
    response_status = request.form.get("status")
    valid_statuses = {"accept", "reject", "reschedule", "ignore"}

    if response_status not in valid_statuses:
        flash("Invalid response status.", "danger")
        return redirect(request.referrer or url_for("main.index"))

    # Update proposal status
    response_message = request.form.get("response_message", "").strip()

    if response_status == "accept":
        proposal.status = model.ProposalStatus.accepted

        proposer_event = model.Event(
            user_id=proposal.proposer.id,
            date=proposal.proposal_date,
            description=f"Date with {proposal.recipient.name}"
        )
        recipient_event = model.Event(
            user_id=proposal.recipient.id,
            date=proposal.proposal_date,
            description=f"Date with {proposal.proposer.name}"
        )
        db.session.add(proposer_event)
        db.session.add(recipient_event)

    elif response_status == "reject":
        proposal.status = model.ProposalStatus.rejected

    elif response_status == "reschedule":
        proposal.status = model.ProposalStatus.reschedule

    elif response_status == "ignore":
        proposal.status = model.ProposalStatus.ignored

    # Update timestamps and optional message
    proposal.timestamp_answered = datetime.datetime.utcnow()
    proposal.response_message = response_message[:500]  # Limit message length

    db.session.commit()
    flash("Your response has been recorded.", "success")
    return redirect(request.referrer or url_for("main.index"))


@bp.route("/proposal_inbox", methods=["GET"])
@flask_login.login_required
def proposal_inbox():
    user = flask_login.current_user

    if not user:
        abort(404,
              description="An error ocurred when retrieving the user logged in. Please, refresh the page and log in again.")  # Handle case where user is not found

    # Fetch proposals where the current user is the recipient
    proposals = (
        model.DateProposal.query
        .filter_by(recipient=user)
        .join(model.Restaurant)  # Join with Restaurant to include details
        .options(db.joinedload(model.DateProposal.restaurant))  # Load the Restaurant relationship
        .all()
    )

    return render_template("main/proposal_inbox.html", proposals=proposals)


# Liking route, it doesn't render any templates
@bp.route("/like/<int:user_id>", methods=["POST"])
@flask_login.login_required
def like_user(user_id):
    # Ensure the user is not liking themselves, not really possible but just in case
    if user_id == current_user.id:
        flash("You cannot like yourself!", "warning")
        return redirect(url_for("main.index"))

    # Check if the user exists
    liked_user = model.User.query.get(user_id)
    if not liked_user:
        abort(404, description="User not found.")

    # Check if the like already exists
    existing_like = db.session.query(model.LikingAssociation).filter_by(
        liker_id=current_user.id, liked_id=user_id
    ).first()

    if existing_like:
        flash("You already liked this user.", "info")
    else:
        # Add the like
        like = model.LikingAssociation(liker_id=current_user.id, liked_id=user_id)
        db.session.add(like)
        db.session.commit()
        flash(f"You liked {liked_user.name}.", "success")

    return redirect(url_for("main.index"))


# Blocking now
@bp.route("/block/<int:user_id>", methods=["POST"])
@flask_login.login_required
def block_user(user_id):
    # Ensure the user is not blocking themselves
    if user_id == current_user.id:
        flash("You cannot block yourself!", "warning")
        return redirect(url_for("main.index"))

    # Check if the user exists
    blocked_user = model.User.query.get(user_id)
    if not blocked_user:
        abort(404, description="User not found.")

    # Check if the block already exists
    existing_block = db.session.query(model.BlockingAssociation).filter_by(
        blocker_id=current_user.id, blocked_id=user_id
    ).first()

    if existing_block:
        flash("You already blocked this user.", "info")
    else:
        # Add the block
        block = model.BlockingAssociation(blocker_id=current_user.id, blocked_id=user_id)
        db.session.add(block)
        # Remove the "like" relationship if it exists
        existing_like = db.session.query(model.LikingAssociation).filter_by(
            liker_id=current_user.id, liked_id=user_id
        ).first()

        if existing_like:
            db.session.delete(existing_like)  # Remove the like relationship
            flash(f"You unliked {blocked_user.name} due to blocking.", "info")

        db.session.commit()
        flash(f"You blocked {blocked_user.name}.", "success")

    return redirect(url_for("main.index"))


# To show in your profile the blocked users:
@bp.route("/blocked", methods=["GET"])
@flask_login.login_required
def blocked_users():
    user_id = current_user.id

    # To retrieve the blocked users
    my_blocked_users = db.session.query(model.User).join(
        model.BlockingAssociation, model.BlockingAssociation.blocked_id == model.User.id
    ).filter(model.BlockingAssociation.blocker_id == user_id).all()

    # Pass the blocked users to the template
    return render_template("main/blocked.html", my_blocked_users=my_blocked_users)


# To unblock the user
@bp.route("/unblock/<int:user_id>", methods=["POST"])
@flask_login.login_required
def unblock_user(user_id):
    if user_id == current_user.id:
        flash("You cannot unblock yourself!", "warning")
        return redirect(url_for("main.index"))

    blocked_user = model.User.query.get(user_id)
    if not blocked_user:
        abort(404, description="User not found.")

    existing_block = db.session.query(model.BlockingAssociation).filter_by(
        blocker_id=current_user.id, blocked_id=user_id
    ).first()

    db.session.delete(existing_block)
    db.session.commit()

    flash(f"You have unblocked {blocked_user.name}.", "success")

    return redirect(url_for("main.blocked_users"))


# Likes template rendering
@bp.route("/liked_and_liking", methods=["GET"])
@flask_login.login_required
def liked_and_liking():
    user = flask_login.current_user
    if not user:
        abort(404,
              description="An error ocurred when retrieving the user logged in. Please, refresh the page and log in again.")  # Handle case where user is not found

    # Get the list of users who liked the current user (likers)
    blocked_user_ids = [blocked.id for blocked in user.blocking]
    liked_by_users = [u for u in user.likers if u.id not in blocked_user_ids]

    # Get the list of users the current user has liked (liking)
    # There cannot appear blocked users since it is handled in the blocking association
    liking_users = user.liking

    return render_template("main/liked_and_liking.html", liked_by_users=liked_by_users, liking_users=liking_users,
                           current_user=user)


# Unlike button
@bp.route("/unlike/<int:user_id>", methods=["POST"])
@flask_login.login_required
def unlike_user(user_id):
    user = flask_login.current_user
    if not user:
        abort(404,
              description="An error ocurred when retrieving the user logged in. Please, refresh the page and log in again.")  # Handle case where user is not found

    # Check if the user exists
    liked_user = model.User.query.get(user_id)
    if not liked_user:
        abort(404, description="There was an error. Liked user not found. Refresh the page")

    # Check if the "like" exists
    existing_like = db.session.query(model.LikingAssociation).filter_by(
        liker_id=user.id, liked_id=user_id
    ).first()

    if existing_like:
        db.session.delete(existing_like)
        db.session.commit()
        flash(f"You unliked {liked_user.name}.", "success")
    else:
        flash("You haven't liked this user yet.", "info")

    return redirect(url_for("main.liked_and_liking"))


# Render map template
@bp.route('/map')
def get_map():
    return render_template("main/map.html")


# The following two methods are for the API. The user is not able to access them with any button in the web page.
# Retrieve the restaurant characteristics for map
@bp.route('/api/restaurants', methods=['GET'])
def get_restaurants():
    restaurants = model.Restaurant.query.all()
    return jsonify([{
        'id': r.id,
        'name': r.name,
        'latitude': r.latitude,
        'longitude': r.longitude
    } for r in restaurants])


# Characteristics of the restaurant
@bp.route('/api/restaurants/<int:restaurant_id>', methods=['GET'])
def get_restaurant_details(restaurant_id):
    restaurant = model.Restaurant.query.get_or_404(restaurant_id)
    return jsonify({
        'id': restaurant.id,
        'name': restaurant.name,
        'latitude': restaurant.latitude,
        'longitude': restaurant.longitude,
        'description': restaurant.description
    })


# Characteristics of each restaurant
@bp.route('/restaurant/<int:restaurant_id>', methods=['GET'])
def restaurant_page(restaurant_id):
    restaurant = model.Restaurant.query.get_or_404(restaurant_id)
    return render_template('main/restaurant.html', restaurant=restaurant)


# To show the proposals the user logged in sent
@bp.route("/sent_proposals", methods=["GET"])
@flask_login.login_required
def sent_proposals():
    user = flask_login.current_user

    # Here we retreieve proposals where the current user is the proposer
    proposals = (
        model.DateProposal.query.filter_by(proposer=user)
        .join(model.Restaurant)  # Include restaurant details
        .add_columns(model.Restaurant.name.label("restaurant_name"))
        .all()
    )

    return render_template("main/sent_proposals.html", proposals=proposals)


# Route for javascript to retrieve the table availability
@bp.route("/get_table_availability", methods=["GET"])
@flask_login.login_required
def get_table_availability():
    date_str = request.args.get("proposal_date")
    restaurant_id = request.args.get("restaurant_id")

    if not date_str or not restaurant_id:
        return jsonify({"error": "Invalid data provided."}), 400

    # Validate date format (as we did also in propose date)
    try:
        proposal_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format."}), 400

    # Here we get the restaurant
    restaurant = model.Restaurant.query.get(restaurant_id)
    if not restaurant:
        return jsonify({"error": "Restaurant not found."}), 404

    # Count occupied tables for the given date and restaurant
    occupied_tables = (
        model.DateProposal.query.filter_by(proposal_date=proposal_date, restaurant_id=restaurant.id)
        .filter(model.DateProposal.status.in_([model.ProposalStatus.proposed, model.ProposalStatus.accepted]))
        .count()
    )
    available_tables = max(0, restaurant.tables_available - occupied_tables)

    return jsonify({"available_tables": available_tables})


# Route to fetch analytics with the graph
@bp.route("/analytics")
@flask_login.login_required
def analytics():
    user_id = flask_login.current_user.id

    total_proposals = model.DateProposal.query.filter_by(proposer_id=user_id).count()
    accepted_proposals = model.DateProposal.query.filter_by(proposer_id=user_id,
                                                            status=model.ProposalStatus.accepted).count()
    rejected_proposals = model.DateProposal.query.filter_by(proposer_id=user_id,
                                                            status=model.ProposalStatus.rejected).count()
    ignored_proposals = model.DateProposal.query.filter_by(proposer_id=user_id,
                                                           status=model.ProposalStatus.ignored).count()
    rescheduled_proposals = model.DateProposal.query.filter_by(proposer_id=user_id,
                                                               status=model.ProposalStatus.reschedule).count()

    popular_restaurants = (
        db.session.query(model.Restaurant.name, func.count(model.DateProposal.id).label("proposal_count"))
        .join(model.DateProposal, model.Restaurant.id == model.DateProposal.restaurant_id)
        .filter(model.DateProposal.proposer_id == user_id)
        .group_by(model.Restaurant.name)
        .order_by(func.count(model.DateProposal.id).desc())
        .limit(5)
        .all()
    )

    analytics_data = {
        "total_proposals": total_proposals,
        "accepted_proposals": accepted_proposals,
        "rejected_proposals": rejected_proposals,
        "ignored_proposals": ignored_proposals,
        "rescheduled_proposals": rescheduled_proposals,
        "popular_restaurants": popular_restaurants,
    }

    return render_template("main/analytics.html", analytics=analytics_data)


# Interactive quiz the users have to do when they accept a date
@bp.route("/interactive_quiz/<int:proposal_id>", methods=["GET"])
@flask_login.login_required
def interactive_quiz(proposal_id):
    # Here we store proposal_id in the session to associate quiz results later
    session["current_proposal_id"] = proposal_id
    return render_template("main/interactive_quiz.html")


# Route to submit the interactive quiz answers
@bp.route("/submit_quiz_answers", methods=["POST"])
@flask_login.login_required
def submit_quiz_answers():
    data = request.json
    if not data:
        return jsonify({"error": "Invalid data"}), 400

    # Getting the correct session id that corresponds to the proposal
    proposal_id = session.get("current_proposal_id")
    if not proposal_id:
        return jsonify({"error": "No active proposal"}), 400

    proposal = model.DateProposal.query.get_or_404(proposal_id)
    user_id = flask_login.current_user.id

    # Assigning the correct proposer and proposed id's
    if user_id == proposal.proposer.id:
        proposal.quiz_results_proposer = data
    elif user_id == proposal.recipient.id:
        proposal.quiz_results_recipient = data
    else:
        return jsonify({"error": "Unauthorized user."}), 403

    db.session.commit()

    return jsonify({"message": "Quiz responses saved successfully"}), 200


# Render template to see the quiz results with both of the answers (proposer and proposed)
@bp.route("/view_quiz_results/<int:proposal_id>")
@flask_login.login_required
def view_quiz_results(proposal_id):
    proposal = model.DateProposal.query.get_or_404(proposal_id)

    # Check if the current user is either the proposer or recipient
    if flask_login.current_user.id not in [proposal.proposer.id, proposal.recipient.id]:
        flash("You are not authorized to view this proposal's quiz results.", "danger")
        return redirect(url_for("main.index"))

    # Get both users' quiz results
    quiz_results_proposer = proposal.quiz_results_proposer
    quiz_results_recipient = proposal.quiz_results_recipient

    return render_template("main/view_quiz_results.html", proposal=proposal,
                           quiz_results_proposer=quiz_results_proposer, quiz_results_recipient=quiz_results_recipient)


# Render the upcoming dates template. These are just the dates that have been accepted.
@bp.route("/upcoming_dates", methods=["GET"])
@flask_login.login_required
def upcoming_dates():
    user = flask_login.current_user

    # Fetch accepted proposals where the user is either proposer or recipient
    accepted_dates = model.DateProposal.query.filter(
        (model.DateProposal.recipient_id == user.id) | (model.DateProposal.proposer_id == user.id),
        model.DateProposal.status == model.ProposalStatus.accepted
    ).join(model.Restaurant).all()

    return render_template("main/upcoming_dates.html", accepted_dates=accepted_dates)


# Calendar: Retrieving the user events
@bp.route('/get_user_events')
@flask_login.login_required
def get_user_events():
    # Get the events currently accepted
    events = model.Event.query.filter_by(user_id=flask_login.current_user.id).all()

    # Retrieve calendar data in the correct formats
    event_data = []
    for event in events:
        event_data.append({
            'title': event.description,
            'start': event.date.isoformat(),
            'end': event.date.isoformat(),
            'description': event.description,
        })

    return jsonify(event_data)


# Calendar template retrieval
@bp.route('/calendar')
@flask_login.login_required
def calendar():
    return render_template('main/calendar.html')