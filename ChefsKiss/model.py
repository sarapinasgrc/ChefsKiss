import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, ForeignKey, func, Enum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
import flask_login
from flask_login import current_user
from . import db
import enum


class LikingAssociation(db.Model):
    __tablename__ = "liking_association"

    liker_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)
    liked_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)


class BlockingAssociation(db.Model):
    __tablename__ = "blocking_association"

    blocker_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)
    blocked_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)


class User(flask_login.UserMixin, db.Model):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(128), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    lastname: Mapped[str] = mapped_column(String(64))
    gender: Mapped[str] = mapped_column(String(10))
    year_of_birth: Mapped[int] = mapped_column(Integer)
    password: Mapped[str] = mapped_column(String(256))

    # Relationships:
    matching_preferences: Mapped[Optional["MatchingPreference"]] = relationship(back_populates="user", uselist=False)
    profile: Mapped[Optional["Profile"]] = relationship(back_populates="user", uselist=False)
    proposals_made: Mapped[List["DateProposal"]] = relationship(
        "DateProposal", foreign_keys="DateProposal.proposer_id", back_populates="proposer", lazy="dynamic"
    )
    proposals_received: Mapped[List["DateProposal"]] = relationship(
        "DateProposal", foreign_keys="DateProposal.recipient_id", back_populates="recipient", lazy="dynamic"
    )
    liking: Mapped[List["User"]] = relationship(
        secondary=LikingAssociation.__table__,
        primaryjoin=id == LikingAssociation.liker_id,
        secondaryjoin=id == LikingAssociation.liked_id,
        back_populates="likers",
    )
    likers: Mapped[List["User"]] = relationship(
        secondary=LikingAssociation.__table__,
        primaryjoin=id == LikingAssociation.liked_id,
        secondaryjoin=id == LikingAssociation.liker_id,
        back_populates="liking",
    )

    # Blocking relationship
    blocking: Mapped[List["User"]] = relationship(
        secondary=BlockingAssociation.__table__,
        primaryjoin=id == BlockingAssociation.blocker_id,
        secondaryjoin=id == BlockingAssociation.blocked_id,
        back_populates="blockers",
    )
    blockers: Mapped[List["User"]] = relationship(
        secondary=BlockingAssociation.__table__,
        primaryjoin=id == BlockingAssociation.blocked_id,
        secondaryjoin=id == BlockingAssociation.blocker_id,
        back_populates="blocking",
    )
    events: Mapped[List["Event"]] = relationship("Event", back_populates="user")


class Photo(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    profile: Mapped["Profile"] = relationship(back_populates="photo")
    file_extension: Mapped[str] = mapped_column(String(8))


class Profile(db.Model):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    year_of_birth: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(16), nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    interests: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship(back_populates="profile")
    photo_id: Mapped[int] = mapped_column(ForeignKey("photo.id"))
    photo: Mapped[Optional["Photo"]] = relationship(back_populates="profile")

class GenderPreference(enum.Enum):
    male = 1
    female = 2
    both = 3

class MatchingPreference(db.Model):
    __tablename__ = "matching_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    gender_preference: Mapped[GenderPreference] = mapped_column(Enum(GenderPreference), nullable=False)
    lower_year_preference: Mapped[int] = mapped_column(Integer, nullable=False)
    upper_year_preference: Mapped[int] = mapped_column(Integer, nullable=False)

    # Foreign key to link MatchingPreference with User
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship(back_populates="matching_preferences")


# Enumerated type for proposal statuses
class ProposalStatus(enum.Enum):
    proposed = 1
    accepted = 2
    rejected = 3
    ignored = 4
    reschedule = 5


class DateProposal(db.Model):
    __tablename__ = "date_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Relationships
    proposer_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False)
    recipient_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False)
    proposer: Mapped["User"] = relationship("User", foreign_keys=[proposer_id], back_populates="proposals_made")
    recipient: Mapped["User"] = relationship("User", foreign_keys=[recipient_id], back_populates="proposals_received")

    # Separate fields for quiz results for proposer and recipient
    quiz_results_proposer: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Store proposer quiz answers
    quiz_results_recipient: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Store recipient quiz answers

    # Proposal details
    proposal_date: Mapped[datetime.date] = mapped_column(db.Date, nullable=False)  # Date of the proposed meeting
    timestamp_proposed: Mapped[datetime.datetime] = mapped_column(db.DateTime, default=func.now())  # Auto-generated
    timestamp_answered: Mapped[Optional[datetime.datetime]] = mapped_column(db.DateTime, nullable=True)
    status: Mapped[ProposalStatus] = mapped_column(Enum(ProposalStatus), default=ProposalStatus.proposed, nullable=False)

    # Messages
    proposal_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Optional, limited to 500 chars
    response_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Optional, limited to 500 chars

    # Restaurant foreign key
    restaurant_id: Mapped[int] = mapped_column(Integer, ForeignKey("restaurants.id"), nullable=False)
    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="date_proposals")


# Restaurant model
class Restaurant(db.Model):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(256), nullable=True)  # Detailed description of the restaurant
    food_type: Mapped[str] = mapped_column(String(64), nullable=False)  # Type of food (e.g., Italian, Chinese)
    tables_available: Mapped[int] = mapped_column(Integer, nullable=False)  # Number of tables available each night
    latitude: Mapped[float] = mapped_column(db.Float, nullable=False)
    longitude: Mapped[float] = mapped_column(db.Float, nullable=False)
    # Relationships
    date_proposals: Mapped[List["DateProposal"]] = relationship(
        "DateProposal", back_populates="restaurant"
    )
# For calendar events
class Event(db.Model):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("user.id"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(db.Date, nullable=False)  # Event date
    description: Mapped[str] = mapped_column(String(256), nullable=False)  # Event description

    user: Mapped["User"] = relationship("User", back_populates="events")