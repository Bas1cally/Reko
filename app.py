import os
import uuid
from collections import OrderedDict
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    send_from_directory,
    send_file,
)
from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.utils import secure_filename

from config import Config
from models import db, Protocol, Participant, Attendance, Entry, Attachment, seed_participants
from pdf_generator import generate_pdf

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
scheduler = BackgroundScheduler(daemon=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def get_participants_by_category():
    participants = Participant.query.filter_by(active=True).order_by(Participant.sort_order).all()
    grouped = OrderedDict()
    for p in participants:
        grouped.setdefault(p.category, []).append(p)
    return grouped


def get_or_create_current_protocol():
    protocol = Protocol.query.filter_by(status="active").order_by(Protocol.id.desc()).first()
    if not protocol:
        protocol = Protocol.create_for_current_week()
    return protocol


def archive_protocol(protocol):
    """Archive a protocol: generate PDF, update status."""
    participants_by_cat = get_participants_by_category()

    attendance_map = {}
    for att in Attendance.query.filter_by(protocol_id=protocol.id).all():
        attendance_map[att.participant_id] = att

    entries_map = {}
    for entry in Entry.query.filter_by(protocol_id=protocol.id).all():
        entries_map[entry.participant_id] = entry

    pdf_filename = f"Reko_KW{protocol.calendar_week}_{protocol.year}.pdf"
    pdf_path = os.path.join(Config.ARCHIVE_PATH, pdf_filename)

    generate_pdf(protocol, participants_by_cat, attendance_map, entries_map, pdf_path)

    protocol.status = "archived"
    protocol.archived_at = datetime.utcnow()
    protocol.pdf_path = pdf_path
    db.session.commit()


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------

def scheduled_archive_and_rotate():
    """Archive the current protocol and create a new one."""
    with app.app_context():
        protocol = Protocol.query.filter_by(status="active").first()
        if protocol:
            archive_protocol(protocol)
            Protocol.create_for_current_week()


# ---------------------------------------------------------------------------
# Routes: Auth
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == Config.GROUP_PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("index"))
        flash("Falsches Passwort.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Routes: Main protocol
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def index():
    protocol = get_or_create_current_protocol()
    return redirect(url_for("protocol_view", protocol_id=protocol.id))


@app.route("/protokoll/<int:protocol_id>")
@login_required
def protocol_view(protocol_id):
    protocol = Protocol.query.get_or_404(protocol_id)
    participants_by_cat = get_participants_by_category()

    attendance_map = {}
    for att in Attendance.query.filter_by(protocol_id=protocol.id).all():
        attendance_map[att.participant_id] = att

    entries_map = {}
    for entry in Entry.query.filter_by(protocol_id=protocol.id).all():
        entries_map[entry.participant_id] = entry

    return render_template(
        "protocol.html",
        protocol=protocol,
        participants_by_cat=participants_by_cat,
        attendance_map=attendance_map,
        entries_map=entries_map,
    )


# ---------------------------------------------------------------------------
# Routes: API endpoints
# ---------------------------------------------------------------------------

@app.route("/api/attendance", methods=["POST"])
@login_required
def toggle_attendance():
    data = request.get_json()
    protocol_id = data["protocol_id"]
    participant_id = data["participant_id"]
    present = data["present"]

    protocol = Protocol.query.get_or_404(protocol_id)
    if not protocol.is_editable:
        return jsonify({"error": "Protokoll ist gesperrt."}), 403

    att = Attendance.query.filter_by(
        protocol_id=protocol_id, participant_id=participant_id
    ).first()

    if att:
        att.present = present
        att.checked_at = datetime.utcnow() if present else None
    else:
        att = Attendance(
            protocol_id=protocol_id,
            participant_id=participant_id,
            present=present,
            checked_at=datetime.utcnow() if present else None,
        )
        db.session.add(att)

    db.session.commit()
    return jsonify({
        "ok": True,
        "checked_at": att.checked_at.strftime("%H:%M") if att.checked_at else None,
    })


@app.route("/api/entry", methods=["POST"])
@login_required
def save_entry():
    data = request.get_json()
    protocol_id = data["protocol_id"]
    participant_id = data["participant_id"]
    content = data["content"]

    protocol = Protocol.query.get_or_404(protocol_id)
    if not protocol.is_editable:
        return jsonify({"error": "Protokoll ist gesperrt."}), 403

    entry = Entry.query.filter_by(
        protocol_id=protocol_id, participant_id=participant_id
    ).first()

    if entry:
        entry.content = content
        entry.updated_at = datetime.utcnow()
    else:
        entry = Entry(
            protocol_id=protocol_id,
            participant_id=participant_id,
            content=content,
        )
        db.session.add(entry)

    db.session.commit()
    return jsonify({"ok": True, "updated_at": datetime.utcnow().strftime("%H:%M")})


@app.route("/api/upload", methods=["POST"])
@login_required
def upload_file():
    protocol_id = request.form.get("protocol_id", type=int)
    participant_id = request.form.get("participant_id", type=int)
    file = request.files.get("file")

    if not file or not allowed_file(file.filename):
        return jsonify({"error": "Ungültiger Dateityp."}), 400

    protocol = Protocol.query.get_or_404(protocol_id)
    if not protocol.is_editable:
        return jsonify({"error": "Protokoll ist gesperrt."}), 403

    entry = Entry.query.filter_by(
        protocol_id=protocol_id, participant_id=participant_id
    ).first()
    if not entry:
        entry = Entry(protocol_id=protocol_id, participant_id=participant_id, content="")
        db.session.add(entry)
        db.session.commit()

    original_name = secure_filename(file.filename)
    unique_name = f"{uuid.uuid4().hex}_{original_name}"
    upload_dir = os.path.join(Config.UPLOAD_FOLDER, str(protocol_id))
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, unique_name))

    attachment = Attachment(
        entry_id=entry.id,
        filename=unique_name,
        original_name=file.filename,
    )
    db.session.add(attachment)
    db.session.commit()

    return jsonify({
        "ok": True,
        "id": attachment.id,
        "name": file.filename,
        "url": url_for("get_upload", protocol_id=protocol_id, filename=unique_name),
    })


@app.route("/api/attachment/<int:attachment_id>", methods=["DELETE"])
@login_required
def delete_attachment(attachment_id):
    att = Attachment.query.get_or_404(attachment_id)
    protocol = att.entry.protocol
    if not protocol.is_editable:
        return jsonify({"error": "Protokoll ist gesperrt."}), 403

    filepath = os.path.join(Config.UPLOAD_FOLDER, str(protocol.id), att.filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    db.session.delete(att)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/uploads/<int:protocol_id>/<filename>")
@login_required
def get_upload(protocol_id, filename):
    upload_dir = os.path.join(Config.UPLOAD_FOLDER, str(protocol_id))
    return send_from_directory(upload_dir, filename)


# ---------------------------------------------------------------------------
# Routes: Archive & manual actions
# ---------------------------------------------------------------------------

@app.route("/archiv")
@login_required
def archive_list():
    protocols = (
        Protocol.query
        .filter(Protocol.status == "archived")
        .order_by(Protocol.year.desc(), Protocol.calendar_week.desc())
        .all()
    )
    return render_template("archive.html", protocols=protocols)


@app.route("/archiv/<int:protocol_id>/pdf")
@login_required
def download_pdf(protocol_id):
    protocol = Protocol.query.get_or_404(protocol_id)
    if protocol.pdf_path and os.path.exists(protocol.pdf_path):
        return send_file(protocol.pdf_path, as_attachment=True)
    flash("PDF nicht gefunden.", "error")
    return redirect(url_for("archive_list"))


@app.route("/archiv/<int:protocol_id>")
@login_required
def archive_detail(protocol_id):
    protocol = Protocol.query.get_or_404(protocol_id)
    participants_by_cat = get_participants_by_category()
    attendance_map = {
        a.participant_id: a
        for a in Attendance.query.filter_by(protocol_id=protocol.id).all()
    }
    entries_map = {
        e.participant_id: e
        for e in Entry.query.filter_by(protocol_id=protocol.id).all()
    }
    return render_template(
        "protocol.html",
        protocol=protocol,
        participants_by_cat=participants_by_cat,
        attendance_map=attendance_map,
        entries_map=entries_map,
    )


@app.route("/admin/archive-now", methods=["POST"])
@login_required
def manual_archive():
    protocol = Protocol.query.filter_by(status="active").first()
    if protocol:
        archive_protocol(protocol)
        Protocol.create_for_current_week()
        flash(f"Protokoll {protocol.label} wurde archiviert.", "success")
    else:
        flash("Kein aktives Protokoll gefunden.", "error")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

with app.app_context():
    db.create_all()
    seed_participants()
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(Config.ARCHIVE_PATH, exist_ok=True)

scheduler.add_job(
    scheduled_archive_and_rotate,
    "cron",
    id="archive_and_rotate",
    day_of_week=Config.ARCHIVE_DAY,
    hour=Config.ARCHIVE_HOUR,
    minute=Config.ARCHIVE_MINUTE,
)
scheduler.start()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
