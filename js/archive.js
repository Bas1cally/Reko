// ===========================================
// Archiv-Seite
// ===========================================

const CATEGORY_LABELS = {
  aerzte: 'Aerzte',
  sozialberatung: 'Sozialberatung',
  bgf: 'Betriebliche Gesundheitsfoerderung',
  wd_orga: 'WD-Organisation',
  sanitaeter: 'Notfall-/Rettungssanitaeter',
  betriebsrat: 'Betriebsratsmitglied',
};

const Archive = {
  supabase: null,
  currentProto: null,
  currentEntries: null,
  currentAttendance: null,

  async init() {
    this.supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

    const user = Auth.requireAuth();
    if (!user) return;

    await this.loadArchive();
  },

  async loadArchive() {
    const { data: protocols } = await this.supabase
      .from('protocols')
      .select('*')
      .eq('status', 'archived')
      .order('year', { ascending: false })
      .order('calendar_week', { ascending: false });

    const container = document.getElementById('archive-list');
    container.innerHTML = '';

    if (!protocols || protocols.length === 0) {
      container.innerHTML = '<p style="color:var(--mb-gray-500);text-align:center;padding:40px;">Noch keine archivierten Protokolle.</p>';
      return;
    }

    for (const proto of protocols) {
      const card = document.createElement('div');
      card.className = 'archive-card';
      card.innerHTML = `
        <div>
          <div class="kw">KW ${proto.calendar_week} / ${proto.year}</div>
          <div class="meta">${this.formatDate(proto.week_start)} - ${this.formatDate(proto.week_end)}</div>
        </div>
        <div class="meta">Archiviert: ${this.formatDate(proto.archived_at)}</div>
      `;
      card.addEventListener('click', () => this.showProtocol(proto));
      container.appendChild(card);
    }
  },

  async showProtocol(proto) {
    const { data: entries } = await this.supabase
      .from('entries')
      .select('*')
      .eq('protocol_id', proto.id)
      .order('sort_order');

    const { data: attendance } = await this.supabase
      .from('attendance')
      .select('*, participants(name, category)')
      .eq('protocol_id', proto.id);

    // Daten fuer PDF-Export merken
    this.currentProto = proto;
    this.currentEntries = entries;
    this.currentAttendance = attendance;

    const modal = document.getElementById('archive-modal');
    const content = document.getElementById('archive-modal-content');

    const present = (attendance || []).filter(a => a.present).map(a => a.participants.name);
    const absent = (attendance || []).filter(a => !a.present).map(a => a.participants.name);

    let html = `
      <h2>KW ${proto.calendar_week} / ${proto.year}</h2>
      <p>${this.formatDate(proto.week_start)} - ${this.formatDate(proto.week_end)}</p>
      <hr style="margin:16px 0;border:none;border-top:1px solid var(--mb-gray-200)">
      <p><strong>Anwesend:</strong> ${present.join(', ') || 'Niemand'}</p>
      <p style="margin-bottom:16px"><strong>Abwesend:</strong> ${absent.join(', ') || '-'}</p>
    `;

    // Bericht Betriebsrat
    const brEntry = (entries || []).find(e => e.section === 'betriebsrat' && e.content.trim());
    if (brEntry) {
      html += `<h3 style="margin-top:20px;font-size:14px;text-transform:uppercase;color:var(--mb-gray-500)">Bericht Betriebsrat</h3>`;
      html += `<div style="background:var(--mb-gray-100);padding:12px;border-radius:4px;margin:8px 0;white-space:pre-wrap">${this.escapeHtml(brEntry.content)}</div>`;
    }

    // Blitzlicht
    const blitzEntries = (entries || []).filter(e => e.section === 'blitzlicht' && e.content.trim());
    if (blitzEntries.length > 0) {
      html += `<h3 style="margin-top:20px;font-size:14px;text-transform:uppercase;color:var(--mb-gray-500)">Berichte / Blitzlicht</h3>`;
      for (const entry of blitzEntries) {
        html += `
          <div style="background:var(--mb-gray-100);padding:12px;border-radius:4px;margin:8px 0">
            <strong>${this.escapeHtml(entry.author_name || 'Unbekannt')}</strong>
            <div style="margin-top:6px;white-space:pre-wrap">${this.escapeHtml(entry.content)}</div>
          </div>
        `;
      }
    }

    // Sonstiges
    const sonstigesEntry = (entries || []).find(e => e.section === 'sonstiges' && e.content.trim());
    if (sonstigesEntry) {
      html += `<h3 style="margin-top:20px;font-size:14px;text-transform:uppercase;color:var(--mb-gray-500)">Sonstiges</h3>`;
      html += `<div style="background:var(--mb-gray-100);padding:12px;border-radius:4px;margin:8px 0;white-space:pre-wrap">${this.escapeHtml(sonstigesEntry.content)}</div>`;
    }

    content.innerHTML = html;

    // PDF-Button binden
    document.getElementById('btn-export-pdf').onclick = () => this.exportPDF();

    modal.classList.add('open');
  },

  // --- PDF Export ---
  exportPDF() {
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ unit: 'mm', format: 'a4' });
    const pageW = doc.internal.pageSize.getWidth();
    const pageH = doc.internal.pageSize.getHeight();
    const margin = 20;
    const maxW = pageW - 2 * margin;
    let y = margin;

    const proto = this.currentProto;
    const entries = this.currentEntries || [];
    const attendance = this.currentAttendance || [];

    // Hilfsfunktionen
    const checkPage = (needed) => {
      if (y + needed > pageH - margin) {
        doc.addPage();
        y = margin;
        addWatermark();
      }
    };

    const addWatermark = () => {
      doc.saveGraphicsState();
      doc.setFontSize(50);
      doc.setTextColor(220, 220, 220);
      doc.text('VERTRAULICH', pageW / 2, pageH / 2, {
        align: 'center',
        angle: 45,
      });
      doc.restoreGraphicsState();
    };

    const addText = (text, size, style, color) => {
      doc.setFontSize(size || 11);
      doc.setFont('helvetica', style || 'normal');
      doc.setTextColor(...(color || [0, 0, 0]));
    };

    const writeWrapped = (text, size, style, color) => {
      addText(text, size, style, color);
      const lines = doc.splitTextToSize(text, maxW);
      const lineH = (size || 11) * 0.5;
      checkPage(lines.length * lineH);
      doc.text(lines, margin, y);
      y += lines.length * lineH + 2;
    };

    // --- PDF Inhalt ---
    addWatermark();

    // Header
    addText('', 18, 'bold');
    doc.text(`ReKo Protokoll - KW ${proto.calendar_week} / ${proto.year}`, margin, y);
    y += 8;

    addText('', 10, 'normal', [100, 100, 100]);
    doc.text(`${this.formatDate(proto.week_start)} - ${this.formatDate(proto.week_end)}`, margin, y);
    y += 4;
    doc.text(`Archiviert: ${this.formatDate(proto.archived_at)}`, margin, y);
    y += 8;

    // Trennlinie
    doc.setDrawColor(200, 200, 200);
    doc.line(margin, y, pageW - margin, y);
    y += 6;

    // Anwesenheit
    const present = attendance.filter(a => a.present).map(a => a.participants.name);
    const absent = attendance.filter(a => !a.present).map(a => a.participants.name);

    writeWrapped('Anwesend: ' + (present.join(', ') || 'Niemand'), 10, 'normal');
    writeWrapped('Abwesend: ' + (absent.join(', ') || '-'), 10, 'normal', [120, 120, 120]);
    y += 4;

    // Bericht Betriebsrat
    const brEntry = entries.find(e => e.section === 'betriebsrat' && e.content.trim());
    if (brEntry) {
      checkPage(12);
      writeWrapped('BERICHT BETRIEBSRAT', 11, 'bold', [100, 100, 100]);
      writeWrapped(brEntry.content, 10, 'normal');
      y += 4;
    }

    // Blitzlicht
    const blitzEntries = entries.filter(e => e.section === 'blitzlicht' && e.content.trim());
    if (blitzEntries.length > 0) {
      checkPage(12);
      writeWrapped('BERICHTE / BLITZLICHT', 11, 'bold', [100, 100, 100]);
      for (const entry of blitzEntries) {
        checkPage(12);
        writeWrapped(entry.author_name || 'Unbekannt', 10, 'bold');
        writeWrapped(entry.content, 10, 'normal');
        y += 2;
      }
      y += 2;
    }

    // Sonstiges
    const sonstigesEntry = entries.find(e => e.section === 'sonstiges' && e.content.trim());
    if (sonstigesEntry) {
      checkPage(12);
      writeWrapped('SONSTIGES', 11, 'bold', [100, 100, 100]);
      writeWrapped(sonstigesEntry.content, 10, 'normal');
    }

    // Footer auf jeder Seite
    const totalPages = doc.internal.getNumberOfPages();
    for (let i = 1; i <= totalPages; i++) {
      doc.setPage(i);
      doc.setFontSize(8);
      doc.setTextColor(180, 180, 180);
      doc.text('VERTRAULICH - Nur fuer internen Gebrauch', pageW / 2, pageH - 10, { align: 'center' });
      doc.text(`Seite ${i} / ${totalPages}`, pageW - margin, pageH - 10, { align: 'right' });
    }

    doc.save(`ReKo_KW${proto.calendar_week}_${proto.year}.pdf`);
  },

  closeModal() {
    document.getElementById('archive-modal').classList.remove('open');
  },

  formatDate(dateStr) {
    if (!dateStr) return '-';
    const d = new Date(dateStr);
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  },

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  },
};
