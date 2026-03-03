// ===========================================
// Archiv-Seite
// ===========================================

const Archive = {
  supabase: null,

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
    // Lade Eintraege mit Teilnehmer-Info
    const { data: entries } = await this.supabase
      .from('entries')
      .select('*, participants(name, category)')
      .eq('protocol_id', proto.id)
      .order('created_at');

    const { data: attendance } = await this.supabase
      .from('attendance')
      .select('*, participants(name)')
      .eq('protocol_id', proto.id);

    // Modal mit Inhalt anzeigen
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

    const categories = { meister: 'Meister', pitstop: 'Pitstop / Instandhaltung', logistik: 'Logistik' };
    for (const [catKey, catLabel] of Object.entries(categories)) {
      const catEntries = (entries || []).filter(e => e.participants.category === catKey && e.content.trim());
      if (catEntries.length === 0) continue;
      html += `<h3 style="margin-top:20px;font-size:14px;text-transform:uppercase;color:var(--mb-gray-500)">${catLabel}</h3>`;
      for (const entry of catEntries) {
        html += `
          <div style="background:var(--mb-gray-100);padding:12px;border-radius:4px;margin:8px 0">
            <strong>${entry.participants.name}</strong>
            <div style="margin-top:6px;white-space:pre-wrap">${this.escapeHtml(entry.content)}</div>
          </div>
        `;
      }
    }

    content.innerHTML = html;
    modal.classList.add('open');
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
