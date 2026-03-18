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
      this.loadArchiveMonths();
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

  // ===========================================
  // Monatsarchiv PDF
  // ===========================================

  MONTH_NAMES: ['Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'],

  ARCHIVE_SECTION_LABELS: {
    doctors: 'Aerzte',
    socialCounseling: 'Sozialberatung',
    healthPromotion: 'Betriebliche Gesundheitsfoerderung',
    wdOrganization: 'WD-Organisation',
    emergency: 'Notfall-/Rettungssanitaeter',
    worksCouncil: 'Betriebsratsmitglied',
  },

  async loadArchiveMonths() {
    const loadingEl = document.getElementById('archive-loading');
    const gridEl = document.getElementById('archive-months');
    const emptyEl = document.getElementById('archive-empty');

    loadingEl.style.display = 'block';
    gridEl.innerHTML = '';

    try {
      const resp = await fetch('archive_data.json?v=' + Date.now());
      if (!resp.ok) throw new Error('Archivdaten nicht gefunden');
      const archiveData = await resp.json();
      const entries = archiveData.archive || [];

      if (entries.length === 0) {
        emptyEl.style.display = 'block';
        loadingEl.style.display = 'none';
        return;
      }

      // Parse dates and group by month
      const months = {};
      for (const entry of entries) {
        const parts = entry.date.split('.');
        const day = parseInt(parts[0], 10);
        const month = parseInt(parts[1], 10);
        const year = parseInt(parts[2], 10);
        const key = `${year}-${String(month).padStart(2, '0')}`;
        if (!months[key]) months[key] = { year, month, entries: [] };
        months[key].entries.push({ ...entry, _day: day, _month: month, _year: year });
      }

      // Sort months descending
      const sortedKeys = Object.keys(months).sort().reverse();

      for (const key of sortedKeys) {
        const m = months[key];
        m.entries.sort((a, b) => a._day - b._day);

        const card = document.createElement('div');
        card.className = 'archive-month-card';
        card.innerHTML = `
          <span class="month-name">${this.MONTH_NAMES[m.month - 1]} ${m.year}</span>
          <span class="month-meta">${m.entries.length} Protokoll${m.entries.length !== 1 ? 'e' : ''}</span>
        `;
        card.addEventListener('click', () => this.generateMonthlyPDF(m, card));
        gridEl.appendChild(card);
      }

      loadingEl.style.display = 'none';
    } catch (err) {
      console.error('Archiv laden fehlgeschlagen:', err);
      loadingEl.style.display = 'none';
      emptyEl.style.display = 'block';
    }
  },

  async generateMonthlyPDF(monthData, cardEl) {
    if (!window.jspdf) {
      alert('PDF-Bibliothek nicht geladen. Bitte Seite neu laden.');
      return;
    }

    cardEl.classList.add('generating');
    const metaEl = cardEl.querySelector('.month-meta');
    const origMeta = metaEl.textContent;
    metaEl.textContent = 'PDF wird erstellt...';

    try {
      const { jsPDF } = window.jspdf;
      const doc = new jsPDF({ unit: 'mm', format: 'a4' });
      const pageW = doc.internal.pageSize.getWidth();
      const pageH = doc.internal.pageSize.getHeight();
      const margin = 20;
      const maxW = pageW - 2 * margin;
      let y = margin;

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
        doc.text('VERTRAULICH', pageW / 2, pageH / 2, { align: 'center', angle: 45 });
        doc.restoreGraphicsState();
      };

      const addText = (size, style, color) => {
        doc.setFontSize(size || 11);
        doc.setFont('helvetica', style || 'normal');
        doc.setTextColor(...(color || [0, 0, 0]));
      };

      const writeWrapped = (text, size, style, color) => {
        addText(size, style, color);
        const lines = doc.splitTextToSize(text, maxW);
        const lineH = (size || 11) * 0.5;
        checkPage(lines.length * lineH);
        doc.text(lines, margin, y);
        y += lines.length * lineH + 2;
      };

      // --- Deckblatt ---
      addWatermark();
      y = 60;
      addText(28, 'bold');
      doc.text('ReKo Monatsarchiv', pageW / 2, y, { align: 'center' });
      y += 14;

      addText(20, 'normal', [100, 100, 100]);
      doc.text(`${this.MONTH_NAMES[monthData.month - 1]} ${monthData.year}`, pageW / 2, y, { align: 'center' });
      y += 12;

      addText(12, 'normal', [150, 150, 150]);
      doc.text(`${monthData.entries.length} Protokoll${monthData.entries.length !== 1 ? 'e' : ''}`, pageW / 2, y, { align: 'center' });
      y += 20;

      // Inhaltsverzeichnis
      doc.setDrawColor(200, 200, 200);
      doc.line(margin + 20, y, pageW - margin - 20, y);
      y += 10;

      addText(14, 'bold');
      doc.text('Inhalt', pageW / 2, y, { align: 'center' });
      y += 10;

      for (let i = 0; i < monthData.entries.length; i++) {
        const entry = monthData.entries[i];
        const kw = this.getISOWeekFromDate(entry._day, entry._month, entry._year);
        addText(12, 'normal');
        doc.text(`KW ${kw}  -  ${entry.date}`, pageW / 2, y, { align: 'center' });
        y += 7;
      }

      // --- Pro Woche eine Sektion ---
      for (let i = 0; i < monthData.entries.length; i++) {
        const entry = monthData.entries[i];
        const kw = this.getISOWeekFromDate(entry._day, entry._month, entry._year);

        // Neue Seite fuer jede Woche
        doc.addPage();
        y = margin;
        addWatermark();

        // Wochen-Header
        addText(18, 'bold');
        doc.text(`ReKo Protokoll - KW ${kw} / ${entry._year}`, margin, y);
        y += 8;

        addText(10, 'normal', [100, 100, 100]);
        doc.text(`Datum: ${entry.date}`, margin, y);
        y += 8;

        // Trennlinie
        doc.setDrawColor(200, 200, 200);
        doc.line(margin, y, pageW - margin, y);
        y += 6;

        // Anwesenheit aus allen Kategorien
        const allPeople = [];
        for (const [section, people] of Object.entries(entry.data || {})) {
          for (const p of people) {
            allPeople.push({ ...p, section });
          }
        }

        const present = allPeople.filter(p => p.attended).map(p => p.name);
        const absent = allPeople.filter(p => !p.attended).map(p => p.name);

        writeWrapped('Anwesend: ' + (present.join(', ') || 'Niemand'), 10, 'normal');
        writeWrapped('Abwesend: ' + (absent.join(', ') || '-'), 10, 'normal', [120, 120, 120]);
        y += 4;

        // Berichte
        const reports = entry.reports || [];
        if (reports.length > 0) {
          checkPage(12);
          writeWrapped('BERICHTE / BLITZLICHT', 11, 'bold', [100, 100, 100]);

          for (const report of reports) {
            checkPage(12);
            writeWrapped(report.name || 'Unbekannt', 10, 'bold');
            if (report.content) {
              writeWrapped(report.content, 10, 'normal');
            }
            y += 2;
          }
          y += 2;
        }

        // Agenda
        const agenda = entry.agenda || [];
        if (agenda.length > 0) {
          checkPage(12);
          writeWrapped('TAGESORDNUNG', 11, 'bold', [100, 100, 100]);
          for (const item of agenda) {
            checkPage(6);
            writeWrapped('- ' + item, 10, 'normal');
          }
          y += 2;
        }
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

      const monthStr = String(monthData.month).padStart(2, '0');
      doc.save(`ReKo_Monatsarchiv_${monthData.year}-${monthStr}.pdf`);

      metaEl.textContent = origMeta;
      cardEl.classList.remove('generating');
    } catch (err) {
      console.error('PDF Fehler:', err);
      alert('Fehler beim Erstellen des PDFs: ' + err.message);
      metaEl.textContent = origMeta;
      cardEl.classList.remove('generating');
    }
  },

  getISOWeekFromDate(day, month, year) {
    const d = new Date(Date.UTC(year, month - 1, day));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  },
};
