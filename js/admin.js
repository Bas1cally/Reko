// ===========================================
// Admin - Teilnehmerverwaltung
// ===========================================

const CATEGORY_LABELS = {
  aerzte: 'Aerzte',
  sozialberatung: 'Sozialberatung',
  bgf: 'Betriebliche Gesundheitsfoerderung',
  wd_orga: 'WD-Organisation',
  sanitaeter: 'Notfall-/Rettungssanitaeter',
  betriebsrat: 'Betriebsratsmitglied',
};

const ADMIN_PIN = '0054';

const Admin = {
  supabase: null,

  async init() {
    this.supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

    const user = Auth.requireAuth();
    if (!user) return;

    // PIN-Eingabe: Enter-Taste
    const pinInput = document.getElementById('pin-input');
    pinInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.checkPin();
    });
    pinInput.focus();
  },

  checkPin() {
    const input = document.getElementById('pin-input');
    const error = document.getElementById('pin-error');

    if (input.value === ADMIN_PIN) {
      document.getElementById('pin-gate').style.display = 'none';
      document.getElementById('admin-main').style.display = 'block';
      this.loadParticipants();
      this.loadConfirmations();
    } else {
      error.style.display = 'block';
      input.value = '';
      input.focus();
    }
  },

  async loadConfirmations() {
    // Alle Bestaetigungen laden, gruppiert nach KW
    const { data: confirmations } = await this.supabase
      .from('read_confirmations')
      .select('*, participants(name)')
      .order('year', { ascending: false })
      .order('calendar_week', { ascending: false });

    if (!confirmations || confirmations.length === 0) return;

    const container = document.getElementById('confirmations-admin-list');
    container.innerHTML = '';

    // Nach KW gruppieren
    const groups = {};
    for (const c of confirmations) {
      const key = `${c.year}-${c.calendar_week}`;
      if (!groups[key]) groups[key] = { year: c.year, cw: c.calendar_week, items: [] };
      groups[key].items.push(c);
    }

    for (const key of Object.keys(groups)) {
      const group = groups[key];
      const confirmed = group.items.filter(i => i.confirmed).length;
      const total = group.items.length;

      const section = document.createElement('div');
      section.style.marginBottom = '16px';

      const header = document.createElement('div');
      header.style.cssText = 'font-weight:700;font-size:14px;margin-bottom:8px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:8px';

      const headerLeft = document.createElement('span');
      headerLeft.textContent = `KW ${group.cw} / ${group.year}`;

      const headerRight = document.createElement('span');
      headerRight.style.cssText = 'display:flex;align-items:center;gap:8px';
      headerRight.innerHTML = `<span style="font-size:12px;color:var(--mb-gray-500)">${confirmed} / ${total} bestaetigt</span>`;

      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'btn btn-danger btn-sm';
      deleteBtn.textContent = 'Entfernen';
      deleteBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!confirm(`Lesebestaetigungen fuer KW ${group.cw}/${group.year} wirklich loeschen?`)) return;
        const { error } = await this.supabase
          .from('read_confirmations')
          .delete()
          .eq('calendar_week', group.cw)
          .eq('year', group.year);
        if (error) {
          alert('Fehler beim Loeschen: ' + error.message);
          return;
        }
        section.remove();
        // Prüfen ob noch Bestaetigungen da sind
        if (container.children.length === 0) {
          document.getElementById('confirmations-overview').style.display = 'none';
        }
      });
      headerRight.appendChild(deleteBtn);

      header.appendChild(headerLeft);
      header.appendChild(headerRight);

      const list = document.createElement('div');
      list.className = 'confirmation-status';
      list.style.display = 'none';

      header.addEventListener('click', (e) => {
        if (e.target.closest('button')) return;
        list.style.display = list.style.display === 'none' ? 'flex' : 'none';
      });

      for (const item of group.items) {
        const row = document.createElement('div');
        row.className = 'confirmation-status-row';
        row.innerHTML = `
          <span>${item.participants ? item.participants.name : 'Unbekannt'}</span>
          <span class="${item.confirmed ? 'badge-confirmed' : 'badge-pending'}">${item.confirmed ? 'Gelesen' : 'Offen'}</span>
        `;
        list.appendChild(row);
      }

      section.appendChild(header);
      section.appendChild(list);
      container.appendChild(section);
    }

    document.getElementById('confirmations-overview').style.display = 'block';
  },

  async loadParticipants() {
    const { data: all } = await this.supabase
      .from('participants')
      .select('*')
      .order('sort_order');

    const activeList = document.getElementById('active-list');
    activeList.innerHTML = '';

    const participants = all || [];
    const categories = [...new Set(participants.map(p => p.category))];
    for (const cat of categories) {
      const catParts = participants.filter(p => p.category === cat);
      const label = CATEGORY_LABELS[cat] || cat;

      const group = document.createElement('div');
      group.className = 'category-section';
      group.innerHTML = `<div class="category-header">${label}</div>`;

      for (const p of catParts) {
        group.appendChild(this.createParticipantRow(p));
      }
      activeList.appendChild(group);
    }

    document.getElementById('admin-loading').style.display = 'none';
    document.getElementById('admin-content').style.display = 'block';
  },

  createParticipantRow(participant) {
    const row = document.createElement('div');
    row.className = 'admin-row';

    const nameSpan = document.createElement('span');
    nameSpan.className = 'admin-row-name';
    nameSpan.textContent = participant.name;

    const actions = document.createElement('div');
    actions.className = 'admin-row-actions';

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn btn-danger btn-sm';
    deleteBtn.textContent = 'Loeschen';
    deleteBtn.addEventListener('click', async () => {
      if (!confirm(`${participant.name} wirklich loeschen?`)) return;
      await this.supabase.from('participants').delete().eq('id', participant.id);
      await this.loadParticipants();
    });
    actions.appendChild(deleteBtn);

    row.appendChild(nameSpan);
    row.appendChild(actions);
    return row;
  },

  async addParticipant() {
    const nameInput = document.getElementById('add-name');
    const catSelect = document.getElementById('add-category');

    const name = nameInput.value.trim();
    const category = catSelect.value;

    if (!name || !category) {
      alert('Bitte Name und Kategorie angeben.');
      return;
    }

    // sort_order: letzter in der Kategorie + 1
    const { data: existing } = await this.supabase
      .from('participants')
      .select('sort_order')
      .eq('category', category)
      .order('sort_order', { ascending: false })
      .limit(1);

    const sortOrder = existing && existing.length > 0 ? existing[0].sort_order + 1 : 0;

    await this.supabase
      .from('participants')
      .insert({ name, category, sort_order: sortOrder, active: true });

    nameInput.value = '';
    catSelect.value = '';
    await this.loadParticipants();
  },
};
