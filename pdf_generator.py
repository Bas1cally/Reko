import os
from datetime import datetime

try:
    from weasyprint import HTML
    HAS_WEASYPRINT = True
except ImportError:
    HAS_WEASYPRINT = False

DASH = "\u2014"
NO_ENTRIES = '<p style="color:#999;">Keine Eintr\u00e4ge vorhanden.</p>'


def generate_pdf(protocol, participants_by_category, attendance_map, entries_map, output_path):
    """Generate a PDF for an archived protocol. Falls back to HTML if weasyprint is unavailable."""

    attendance_rows = ""
    for category, participants in participants_by_category.items():
        for p in participants:
            att = attendance_map.get(p.id)
            status = "Anwesend" if att and att.present else DASH
            css_class = "present" if att and att.present else "absent"
            timestamp = att.checked_at.strftime("%H:%M") if att and att.checked_at else ""
            attendance_rows += f"""
            <tr>
                <td>{p.name}</td>
                <td>{category}</td>
                <td class="{css_class}">{status}</td>
                <td>{timestamp}</td>
            </tr>"""

    entry_sections = ""
    for category, participants in participants_by_category.items():
        for p in participants:
            entry = entries_map.get(p.id)
            if entry and entry.content.strip():
                attachment_html = ""
                if entry.attachments:
                    names = ", ".join(a.original_name for a in entry.attachments)
                    attachment_html = f"<p class='attachments'>Anh\u00e4nge: {names}</p>"

                entry_sections += f"""
                <div class="entry">
                    <h3>{p.name} <span class="cat">({category})</span></h3>
                    <div class="entry-content">{entry.content}</div>
                    {attachment_html}
                </div>"""

    berichte = entry_sections if entry_sections else NO_ENTRIES
    week_range = f"{protocol.week_start.strftime('%d.%m.%Y')} {DASH} {protocol.week_end.strftime('%d.%m.%Y')}"
    archived_date = datetime.now().strftime("%d.%m.%Y %H:%M")

    html_content = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<style>
    body {{ font-family: Arial, sans-serif; font-size: 11pt; color: #222; margin: 2cm; }}
    h1 {{ color: #1a237e; border-bottom: 3px solid #1a237e; padding-bottom: 8px; }}
    h2 {{ color: #283593; margin-top: 24px; }}
    h3 {{ margin-bottom: 4px; }}
    .cat {{ color: #666; font-weight: normal; font-size: 0.9em; }}
    .meta {{ color: #555; margin-bottom: 20px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
    th {{ background: #e8eaf6; color: #1a237e; }}
    .present {{ color: #2e7d32; font-weight: bold; }}
    .absent {{ color: #999; }}
    .entry {{ margin: 12px 0; padding: 10px; background: #f5f5f5; border-left: 4px solid #1a237e; }}
    .entry-content {{ white-space: pre-wrap; }}
    .attachments {{ font-size: 0.9em; color: #555; margin-top: 6px; }}
    .footer {{ margin-top: 30px; border-top: 1px solid #ccc; padding-top: 8px; font-size: 0.85em; color: #888; }}
</style>
</head>
<body>
    <h1>Reko-Protokoll {protocol.label}</h1>
    <p class="meta">
        Woche: {week_range}<br>
        Archiviert am: {archived_date}
    </p>

    <h2>Anwesenheit</h2>
    <table>
        <thead>
            <tr><th>Name</th><th>Bereich</th><th>Status</th><th>Uhrzeit</th></tr>
        </thead>
        <tbody>{attendance_rows}</tbody>
    </table>

    <h2>Berichte</h2>
    {berichte}

    <div class="footer">
        Automatisch generiert {DASH} Reko-Protokoll-System
    </div>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if HAS_WEASYPRINT:
        HTML(string=html_content).write_pdf(output_path)
    else:
        html_path = output_path.rsplit(".", 1)[0] + ".html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        output_path = html_path

    return output_path
