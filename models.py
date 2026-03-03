from datetime import datetime, date, timedelta

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Protocol(db.Model):
    __tablename__ = "protocols"

    id = db.Column(db.Integer, primary_key=True)
    calendar_week = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    week_start = db.Column(db.Date, nullable=False)  # Monday
    week_end = db.Column(db.Date, nullable=False)  # Friday (Reko day)
    status = db.Column(
        db.String(20), default="active"
    )  # active, locked, archived
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    archived_at = db.Column(db.DateTime, nullable=True)
    pdf_path = db.Column(db.String(500), nullable=True)

    entries = db.relationship(
        "Entry", backref="protocol", cascade="all, delete-orphan", lazy=True
    )
    attendance_records = db.relationship(
        "Attendance", backref="protocol", cascade="all, delete-orphan", lazy=True
    )

    @property
    def label(self):
        return f"KW {self.calendar_week} / {self.year}"

    @property
    def is_editable(self):
        return self.status == "active"

    @staticmethod
    def create_for_current_week():
        today = date.today()
        # ISO calendar: Monday = 1, Sunday = 7
        monday = today - timedelta(days=today.weekday())
        friday = monday + timedelta(days=4)
        iso = today.isocalendar()

        existing = Protocol.query.filter_by(
            calendar_week=iso[1], year=iso[0]
        ).first()
        if existing:
            return existing

        protocol = Protocol(
            calendar_week=iso[1],
            year=iso[0],
            week_start=monday,
            week_end=friday,
            status="active",
        )
        db.session.add(protocol)
        db.session.commit()

        return protocol


class Participant(db.Model):
    __tablename__ = "participants"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)

    entries = db.relationship("Entry", backref="participant", lazy=True)
    attendance_records = db.relationship("Attendance", backref="participant", lazy=True)


class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    protocol_id = db.Column(
        db.Integer, db.ForeignKey("protocols.id"), nullable=False
    )
    participant_id = db.Column(
        db.Integer, db.ForeignKey("participants.id"), nullable=False
    )
    present = db.Column(db.Boolean, default=False)
    checked_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("protocol_id", "participant_id"),
    )


class Entry(db.Model):
    __tablename__ = "entries"

    id = db.Column(db.Integer, primary_key=True)
    protocol_id = db.Column(
        db.Integer, db.ForeignKey("protocols.id"), nullable=False
    )
    participant_id = db.Column(
        db.Integer, db.ForeignKey("participants.id"), nullable=False
    )
    content = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    attachments = db.relationship(
        "Attachment", backref="entry", cascade="all, delete-orphan", lazy=True
    )


class Attachment(db.Model):
    __tablename__ = "attachments"

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(
        db.Integer, db.ForeignKey("entries.id"), nullable=False
    )
    filename = db.Column(db.String(300), nullable=False)
    original_name = db.Column(db.String(300), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


def seed_participants():
    """Seed the default participants from the Word template."""
    if Participant.query.count() > 0:
        return

    participants = [
        # Ärzte
        ("Dr. Frei, Markus", "Ärzte", 1),
        ("Dr. Schmidt, Sabine", "Ärzte", 2),
        ("Dr. Vitez, Lilla", "Ärzte", 3),
        # Sozialberatung
        ("Walther, Katja", "Sozialberatung", 10),
        ("Völkering, Katharina", "Sozialberatung", 11),
        ("Gürsel, Helin", "Sozialberatung", 12),
        # BGF
        ("Zieger-Buchta, Katrin", "Betriebliche Gesundheitsförderung", 20),
        ("Müller-Horn, Susanne", "Betriebliche Gesundheitsförderung", 21),
        ("Krempl, Lara", "Betriebliche Gesundheitsförderung", 22),
        # WD-Organisation
        ("Schmidt, Emily-Kim", "WD-Organisation", 30),
        ("Radimersky, Larissa", "WD-Organisation", 31),
        # Sanitäter
        ("Putschler, Walter", "Notfall-/Rettungssanitäter", 40),
        ("Krempl, Elke", "Notfall-/Rettungssanitäter", 41),
        ("Breig, Bernd", "Notfall-/Rettungssanitäter", 42),
        ("Kunz, Lia", "Notfall-/Rettungssanitäter", 43),
        ("Zeller, Tobias", "Notfall-/Rettungssanitäter", 44),
        ("Jochim, Benjamin", "Notfall-/Rettungssanitäter", 45),
        ("Siebert, Emanuel", "Notfall-/Rettungssanitäter", 46),
        ("Wunsch, Fabian", "Notfall-/Rettungssanitäter", 47),
        ("Goepfrich, Markus", "Notfall-/Rettungssanitäter", 48),
    ]

    for name, category, order in participants:
        db.session.add(
            Participant(name=name, category=category, sort_order=order)
        )
    db.session.commit()
