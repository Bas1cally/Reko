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
    } else {
      error.style.display = 'block';
      input.value = '';
      input.focus();
    }
  },

  async loadParticipants() {
    const { data: all } = await this.supabase
      .from('participants')
      .select('*')
      .order('sort_order');

    const active = (all || []).filter(p => p.active);
    const inactive = (all || []).filter(p => !p.active);

    // Aktive nach Kategorie
    const activeList = document.getElementById('active-list');
    activeList.innerHTML = '';

    const categories = [...new Set(active.map(p => p.category))];
    for (const cat of categories) {
      const catParts = active.filter(p => p.category === cat);
      const label = CATEGORY_LABELS[cat] || cat;

      const group = document.createElement('div');
      group.className = 'category-section';
      group.innerHTML = `<div class="category-header">${label}</div>`;

      for (const p of catParts) {
        group.appendChild(this.createParticipantRow(p, true));
      }
      activeList.appendChild(group);
    }

    // Inaktive
    const inactiveSection = document.getElementById('inactive-section');
    const inactiveList = document.getElementById('inactive-list');
    inactiveList.innerHTML = '';

    if (inactive.length > 0) {
      inactiveSection.style.display = 'block';
      for (const p of inactive) {
        inactiveList.appendChild(this.createParticipantRow(p, false));
      }
    } else {
      inactiveSection.style.display = 'none';
    }

    document.getElementById('admin-loading').style.display = 'none';
    document.getElementById('admin-content').style.display = 'block';
  },

  createParticipantRow(participant, isActive) {
    const row = document.createElement('div');
    row.className = 'admin-row';

    const nameSpan = document.createElement('span');
    nameSpan.className = 'admin-row-name';
    nameSpan.textContent = participant.name;
    if (!isActive) nameSpan.style.opacity = '0.5';

    const actions = document.createElement('div');
    actions.className = 'admin-row-actions';

    if (isActive) {
      const deactivateBtn = document.createElement('button');
      deactivateBtn.className = 'btn btn-secondary btn-sm';
      deactivateBtn.textContent = 'Deaktivieren';
      deactivateBtn.addEventListener('click', () => this.toggleActive(participant.id, false));
      actions.appendChild(deactivateBtn);
    } else {
      const activateBtn = document.createElement('button');
      activateBtn.className = 'btn btn-primary btn-sm';
      activateBtn.textContent = 'Reaktivieren';
      activateBtn.addEventListener('click', () => this.toggleActive(participant.id, true));
      actions.appendChild(activateBtn);
    }

    row.appendChild(nameSpan);
    row.appendChild(actions);
    return row;
  },

  async toggleActive(participantId, active) {
    await this.supabase
      .from('participants')
      .update({ active })
      .eq('id', participantId);
    await this.loadParticipants();
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
