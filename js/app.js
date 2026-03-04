// ===========================================
// ReKo Protokoll - Hauptanwendung
// ===========================================

const CATEGORY_LABELS = {
  aerzte: 'Ärzte',
  sozialberatung: 'Sozialberatung',
  bgf: 'Betriebliche Gesundheitsförderung',
  wd_orga: 'WD-Organisation',
  sanitaeter: 'Notfall-/Rettungssanitäter',
  betriebsrat: 'Betriebsratsmitglied',
};

const App = {
  supabase: null,
  protocol: null,
  participants: [],
  saveTimers: {},
  currentUser: null,

  async init() {
    this.supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

    this.currentUser = Auth.requireAuth();
    if (!this.currentUser) return;

    // Aktuellen User im Header anzeigen
    const userEl = document.getElementById('current-user');
    if (userEl) userEl.textContent = this.currentUser.name;

    document.getElementById('loading').style.display = 'block';
    document.getElementById('app-content').style.display = 'none';

    try {
      await this.loadOrCreateProtocol();
      await this.loadParticipants();
      await this.render();
      await this.renderConfirmations();
    } catch (err) {
      console.error('Init error:', err);
      document.getElementById('loading').innerHTML =
        '<p style="color:var(--mb-red)">Fehler beim Laden. Bitte Seite neu laden.</p>';
    }
  },

  async loadOrCreateProtocol() {
    const { data, error } = await this.supabase.rpc('create_weekly_protocol');
    if (error) throw error;

    const { data: proto } = await this.supabase
      .from('protocols')
      .select('*')
      .eq('id', data)
      .single();

    this.protocol = proto;
  },

  async loadParticipants() {
    const { data } = await this.supabase
      .from('participants')
      .select('*')
      .eq('active', true)
      .order('sort_order');
    this.participants = data || [];
  },

  async loadAttendance() {
    const { data } = await this.supabase
      .from('attendance')
      .select('*')
      .eq('protocol_id', this.protocol.id);
    return data || [];
  },

  async loadEntries() {
    const { data } = await this.supabase
      .from('entries')
      .select('*')
      .eq('protocol_id', this.protocol.id)
      .order('sort_order');
    return data || [];
  },

  async loadAttachments(entryId) {
    const { data } = await this.supabase
      .from('attachments')
      .select('*')
      .eq('entry_id', entryId);
    return data || [];
  },

  // --- Fehlende Sektionen anlegen falls noetig ---
  async ensureSections(entries) {
    let brEntry = entries.find(e => e.section === 'betriebsrat');
    let sonstigesEntry = entries.find(e => e.section === 'sonstiges');

    if (!brEntry) {
      const { data } = await this.supabase
        .from('entries')
        .insert({ protocol_id: this.protocol.id, section: 'betriebsrat', content: '', sort_order: 1 })
        .select().single();
      if (data) entries.push(data);
    }
    if (!sonstigesEntry) {
      const { data } = await this.supabase
        .from('entries')
        .insert({ protocol_id: this.protocol.id, section: 'sonstiges', content: '', sort_order: 99 })
        .select().single();
      if (data) entries.push(data);
    }
    return entries;
  },

  // --- Hauptrendering ---
  async render() {
    const attendance = await this.loadAttendance();
    let entries = await this.loadEntries();
    entries = await this.ensureSections(entries);

    // Header
    document.getElementById('kw-badge').textContent = `KW ${this.protocol.calendar_week}`;
    document.getElementById('week-dates').textContent =
      `${this.formatDate(this.protocol.week_start)} - ${this.formatDate(this.protocol.week_end)}`;

    // Anwesenheit
    this.renderAttendance(attendance);

    // Ablauf rendern
    const container = document.getElementById('entries-container');
    container.innerHTML = '';

    // 1. Bericht Betriebsrat
    const brEntry = entries.find(e => e.section === 'betriebsrat');
    if (brEntry) {
      container.appendChild(this.createSection('Bericht des Bereichsbetriebsrates', [brEntry]));
    }

    // 2. Blitzlicht - Berichte aller Anwesenden
    const blitzEntries = entries.filter(e => e.section === 'blitzlicht');
    container.appendChild(await this.createBlitzlichtSection(blitzEntries));

    // 3. Sonstiges
    const sonstigesEntry = entries.find(e => e.section === 'sonstiges');
    if (sonstigesEntry) {
      container.appendChild(this.createSection('Sonstiges', [sonstigesEntry]));
    }

    document.getElementById('loading').style.display = 'none';
    document.getElementById('app-content').style.display = 'block';
  },

  // --- Anwesenheit ---
  renderAttendance(attendanceList) {
    const grid = document.getElementById('attendance-grid');
    grid.innerHTML = '';

    // Nach Kategorie gruppieren
    const categories = [...new Set(this.participants.map(p => p.category))];

    for (const cat of categories) {
      const catParticipants = this.participants.filter(p => p.category === cat);
      const label = CATEGORY_LABELS[cat] || cat;

      const group = document.createElement('div');
      group.className = 'attendance-group';
      group.innerHTML = `<div class="attendance-group-label">${label}</div>`;

      const items = document.createElement('div');
      items.className = 'attendance-items';

      for (const p of catParticipants) {
        const att = attendanceList.find(a => a.participant_id === p.id);
        const item = document.createElement('div');
        item.className = 'attendance-item' + (att && att.present ? ' present' : '');
        item.innerHTML = `<span class="check">&#10003;</span><span>${p.name}</span>`;
        item.addEventListener('click', () => this.toggleAttendance(p.id, item));
        items.appendChild(item);
      }

      group.appendChild(items);
      grid.appendChild(group);
    }
  },

  async toggleAttendance(participantId, element) {
    const isPresent = element.classList.toggle('present');
    await this.supabase
      .from('attendance')
      .update({ present: isPresent })
      .eq('protocol_id', this.protocol.id)
      .eq('participant_id', participantId);
    this.showSave('saved');
  },

  // --- Sektionen (Betriebsrat, Sonstiges) ---
  createSection(title, entries) {
    const section = document.createElement('div');
    section.className = 'category-section';
    section.innerHTML = `<div class="category-header">${title}</div>`;

    for (const entry of entries) {
      const card = document.createElement('div');
      card.className = 'entry-card' + (entry.content ? ' has-content open' : ' open');

      const body = document.createElement('div');
      body.className = 'entry-card-body';
      body.style.display = 'block';

      const textarea = document.createElement('textarea');
      textarea.value = entry.content || '';
      textarea.placeholder = `${title} ...`;
      textarea.addEventListener('input', () => {
        this.debounceSaveEntry(entry.id, textarea.value, card);
      });

      body.appendChild(textarea);
      card.appendChild(body);
      section.appendChild(card);
    }

    return section;
  },

  // --- Blitzlicht (Berichte aller) ---
  async createBlitzlichtSection(existingEntries) {
    const section = document.createElement('div');
    section.className = 'category-section';
    section.innerHTML = `<div class="category-header">Berichte / Blitzlicht</div>`;

    // Bestehende Berichte anzeigen
    for (const entry of existingEntries) {
      section.appendChild(await this.createEntryCard(entry));
    }

    // Button: Neuen Bericht hinzufuegen
    const addBtn = document.createElement('button');
    addBtn.className = 'btn btn-primary';
    addBtn.style.marginTop = '12px';
    addBtn.textContent = '+ Eigenen Bericht hinzufügen';
    addBtn.addEventListener('click', async () => {
      const { data: newEntry, error } = await this.supabase
        .from('entries')
        .insert({
          protocol_id: this.protocol.id,
          author_name: this.currentUser.name,
          section: 'blitzlicht',
          content: '',
          sort_order: 10 + existingEntries.length,
        })
        .select()
        .single();

      if (!error && newEntry) {
        const card = await this.createEntryCard(newEntry);
        card.classList.add('open');
        section.insertBefore(card, addBtn);
        card.querySelector('textarea').focus();
      }
    });
    section.appendChild(addBtn);

    return section;
  },

  // --- Entry Card ---
  async createEntryCard(entry) {
    const card = document.createElement('div');
    card.className = 'entry-card' + (entry.content ? ' has-content' : '');

    const header = document.createElement('div');
    header.className = 'entry-card-header';
    header.innerHTML = `
      <span class="name">Bericht von ${entry.author_name || 'Unbekannt'}</span>
      <span class="status">${entry.content ? 'Eingetragen' : 'Offen'}</span>
    `;
    header.addEventListener('click', () => card.classList.toggle('open'));

    const body = document.createElement('div');
    body.className = 'entry-card-body';

    const textarea = document.createElement('textarea');
    textarea.value = entry.content || '';
    textarea.placeholder = `Bericht von ${entry.author_name || ''} ...`;
    textarea.addEventListener('input', () => {
      this.debounceSaveEntry(entry.id, textarea.value, card, header);
    });

    body.appendChild(textarea);

    // Datei-Upload
    const uploadArea = document.createElement('div');
    uploadArea.className = 'file-upload-area';

    const fileList = document.createElement('div');
    fileList.className = 'file-list';

    const uploadBtn = document.createElement('label');
    uploadBtn.className = 'file-upload-btn';
    uploadBtn.innerHTML = '+ Datei anhängen';
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.style.display = 'none';
    fileInput.addEventListener('change', (e) => {
      if (e.target.files[0]) {
        this.uploadFile(entry.id, e.target.files[0], fileList);
      }
    });
    uploadBtn.appendChild(fileInput);

    uploadArea.appendChild(uploadBtn);
    uploadArea.appendChild(fileList);
    body.appendChild(uploadArea);

    card.appendChild(header);
    card.appendChild(body);

    // Vorhandene Anhaenge laden
    const attachments = await this.loadAttachments(entry.id);
    for (const att of attachments) {
      this.addFileItem(fileList, att);
    }

    return card;
  },

  // --- Debounced Save ---
  debounceSaveEntry(entryId, content, card, header) {
    clearTimeout(this.saveTimers[entryId]);
    this.saveTimers[entryId] = setTimeout(async () => {
      this.showSave('saving');
      const { error } = await this.supabase
        .from('entries')
        .update({ content: content, updated_at: new Date().toISOString() })
        .eq('id', entryId);

      if (!error) {
        this.showSave('saved');
        card.classList.toggle('has-content', content.trim().length > 0);
        if (header) {
          header.querySelector('.status').textContent = content.trim() ? 'Eingetragen' : 'Offen';
        }
      }
    }, 600);
  },

  // --- Datei hochladen ---
  async uploadFile(entryId, file, fileListEl) {
    const filename = `${Date.now()}_${file.name}`;
    const storagePath = `${this.protocol.id}/${filename}`;

    this.showSave('saving');

    const { error: uploadErr } = await this.supabase.storage
      .from('attachments')
      .upload(storagePath, file);

    if (uploadErr) {
      console.error('Upload error:', uploadErr);
      this.showSave();
      return;
    }

    const { data: att, error: dbErr } = await this.supabase
      .from('attachments')
      .insert({
        entry_id: entryId,
        filename: filename,
        original_name: file.name,
        storage_path: storagePath,
      })
      .select()
      .single();

    if (!dbErr) {
      this.addFileItem(fileListEl, att);
      this.showSave('saved');
    }
  },

  addFileItem(container, attachment) {
    const item = document.createElement('div');
    item.className = 'file-item';
    item.innerHTML = `
      <a href="#" onclick="App.downloadFile('${attachment.storage_path}', '${attachment.original_name}'); return false;">
        ${attachment.original_name}
      </a>
      <button class="remove-file" onclick="App.removeFile('${attachment.id}', '${attachment.storage_path}', this)">&times;</button>
    `;
    container.appendChild(item);
  },

  async downloadFile(storagePath, originalName) {
    const { data } = await this.supabase.storage
      .from('attachments')
      .download(storagePath);
    if (data) {
      const url = URL.createObjectURL(data);
      const a = document.createElement('a');
      a.href = url;
      a.download = originalName;
      a.click();
      URL.revokeObjectURL(url);
    }
  },

  async removeFile(attachmentId, storagePath, btn) {
    await this.supabase.storage.from('attachments').remove([storagePath]);
    await this.supabase.from('attachments').delete().eq('id', attachmentId);
    btn.parentElement.remove();
    this.showSave('saved');
  },

  // ===========================================
  // Woche abschliessen: PDF generieren + Daten loeschen
  // ===========================================
  async closeWeek() {
    // Daten fuer PDF sammeln
    const { data: attData, error: attErr } = await this.supabase
      .from('attendance')
      .select('*, participants(name, category)')
      .eq('protocol_id', this.protocol.id);

    if (attErr) throw new Error('Anwesenheit konnte nicht geladen werden: ' + attErr.message);

    const { data: entData, error: entErr } = await this.supabase
      .from('entries')
      .select('*')
      .eq('protocol_id', this.protocol.id)
      .order('sort_order');

    if (entErr) throw new Error('Eintraege konnten nicht geladen werden: ' + entErr.message);

    // PDF generieren und herunterladen
    if (!window.jspdf) {
      throw new Error('PDF-Bibliothek (jsPDF) nicht geladen. Bitte Seite neu laden.');
    }
    this.generatePDF(this.protocol, attData || [], entData || []);

    // Lesebestaetigung fuer alle aktiven Teilnehmer anlegen (optional, Tabelle muss existieren)
    try {
      const confirmInserts = this.participants.map(p => ({
        calendar_week: this.protocol.calendar_week,
        year: this.protocol.year,
        participant_id: p.id,
        confirmed: false,
      }));
      if (confirmInserts.length > 0) {
        await this.supabase.from('read_confirmations').insert(confirmInserts);
      }
    } catch (e) {
      console.warn('Lesebestaetigungen konnten nicht angelegt werden:', e);
    }

    // Protokoll-Daten komplett loeschen (CASCADE loescht entries, attendance, attachments)
    const { error: delErr } = await this.supabase
      .from('protocols')
      .delete()
      .eq('id', this.protocol.id);

    if (delErr) {
      console.warn('Protokoll konnte nicht geloescht werden:', delErr.message);
      // Alternativ: als archived markieren
      await this.supabase
        .from('protocols')
        .update({ status: 'archived' })
        .eq('id', this.protocol.id);
    }

    // Seite neu laden -> neues leeres Protokoll wird erstellt
    window.location.reload();
  },

  // ===========================================
  // PDF Generierung
  // ===========================================
  generatePDF(proto, attendance, entries) {
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
    const brEntry = entries.find(e => e.section === 'betriebsrat' && e.content && e.content.trim());
    if (brEntry) {
      checkPage(12);
      writeWrapped('BERICHT BETRIEBSRAT', 11, 'bold', [100, 100, 100]);
      writeWrapped(brEntry.content, 10, 'normal');
      y += 4;
    }

    // Blitzlicht
    const blitzEntries = entries.filter(e => e.section === 'blitzlicht' && e.content && e.content.trim());
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
    const sonstigesEntry = entries.find(e => e.section === 'sonstiges' && e.content && e.content.trim());
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

  // ===========================================
  // Lesebestaetigung
  // ===========================================
  async renderConfirmations() {
    const container = document.getElementById('confirmations-section');
    if (!container) return;

    // Offene Bestaetigungen fuer aktuellen User laden
    const { data: pending } = await this.supabase
      .from('read_confirmations')
      .select('*')
      .eq('participant_id', this.currentUser.id)
      .eq('confirmed', false)
      .order('year', { ascending: false })
      .order('calendar_week', { ascending: false });

    if (!pending || pending.length === 0) {
      container.style.display = 'none';
      return;
    }

    container.style.display = 'block';
    const list = document.getElementById('confirmations-list');
    list.innerHTML = '';

    for (const item of pending) {
      const row = document.createElement('div');
      row.className = 'confirmation-row';
      row.innerHTML = `
        <span>Protokoll KW ${item.calendar_week} / ${item.year} gelesen?</span>
        <button class="btn btn-primary btn-sm" onclick="App.confirmRead('${item.id}', this)">Gelesen</button>
      `;
      list.appendChild(row);
    }
  },

  async confirmRead(confirmationId, btn) {
    await this.supabase
      .from('read_confirmations')
      .update({ confirmed: true, confirmed_at: new Date().toISOString() })
      .eq('id', confirmationId);

    btn.parentElement.remove();

    // Wenn keine mehr offen, Section ausblenden
    const list = document.getElementById('confirmations-list');
    if (list && list.children.length === 0) {
      document.getElementById('confirmations-section').style.display = 'none';
    }

    this.showSave('saved');
  },

  showSave(state) {
    const el = document.getElementById('save-indicator');
    el.className = 'save-indicator';
    if (state === 'saving') {
      el.textContent = 'Speichert...';
      el.classList.add('saving');
    } else if (state === 'saved') {
      el.textContent = 'Gespeichert';
      el.classList.add('saved');
      setTimeout(() => { el.className = 'save-indicator'; }, 2000);
    }
  },

  formatDate(dateStr) {
    const d = new Date(dateStr);
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  },
};
