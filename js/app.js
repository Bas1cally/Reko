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
  protocols: {},  // KW -> protocol mapping
  monthWeeks: [], // alle KWs des Monats
  currentKw: null,
  currentYear: null,
  participants: [],
  saveTimers: {},
  currentUser: null,

  async init() {
    this.supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

    this.currentUser = Auth.requireAuth();
    if (!this.currentUser) return;

    this.isProtokolleur = this.currentUser.role === 'protokolleur';

    // Aktuellen User im Header anzeigen
    const userEl = document.getElementById('current-user');
    if (userEl) userEl.textContent = this.isProtokolleur ? 'Protokolleur' : this.currentUser.name;

    document.getElementById('loading').style.display = 'block';
    document.getElementById('app-content').style.display = 'none';

    try {
      this.calculateMonthWeeks();
      await this.loadParticipants();
      await this.loadAllMonthProtocols();
      this.renderKwTabs();
      await this.switchToKw(this.currentKw);
      // Lesebestaetigungen nur fuer Protokolleur relevant (Uebersicht)
      // Fuer normale User: automatisch als gelesen markieren
      if (!this.isProtokolleur) {
        await this.markAsRead();
      }
    } catch (err) {
      console.error('Init error:', err);
      document.getElementById('loading').innerHTML =
        '<p style="color:var(--mb-red)">Fehler beim Laden. Bitte Seite neu laden.</p>';
    }
  },

  // Alle KWs berechnen die im aktuellen Monat liegen
  calculateMonthWeeks() {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth(); // 0-based

    // Aktuelle KW ermitteln (ISO)
    this.currentYear = year;
    this.currentKw = this.getISOWeek(now);

    // Alle Montage im aktuellen Monat finden
    const weeks = [];
    const seen = new Set();

    // Vom 1. des Monats bis zum letzten Tag
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);

    for (let d = new Date(firstDay); d <= lastDay; d.setDate(d.getDate() + 1)) {
      const kw = this.getISOWeek(d);
      const kwYear = this.getISOYear(d);
      const key = `${kwYear}-${kw}`;
      if (!seen.has(key)) {
        seen.add(key);
        weeks.push({ kw, year: kwYear });
      }
    }

    this.monthWeeks = weeks;
  },

  getISOWeek(date) {
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  },

  getISOYear(date) {
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    return d.getUTCFullYear();
  },

  getMonthName() {
    const now = new Date();
    return now.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
  },

  renderKwTabs() {
    const container = document.getElementById('kw-tabs');
    container.innerHTML = '';

    // Monatsname als Label
    const monthLabel = document.createElement('span');
    monthLabel.className = 'kw-month-label';
    monthLabel.textContent = this.getMonthName();
    container.appendChild(monthLabel);

    for (const week of this.monthWeeks) {
      const tab = document.createElement('button');
      tab.className = 'kw-tab' + (week.kw === this.currentKw ? ' active' : '');
      tab.dataset.kw = week.kw;
      tab.dataset.year = week.year;

      const isCurrent = week.kw === this.getISOWeek(new Date());
      tab.innerHTML = `KW ${week.kw}${isCurrent ? ' <span class="kw-tab-current">aktuell</span>' : ''}<span class="kw-tab-dot"></span>`;

      tab.addEventListener('click', () => this.switchToKw(week.kw, week.year));
      container.appendChild(tab);
    }
  },

  updateKwTabStates() {
    const tabs = document.querySelectorAll('.kw-tab');
    tabs.forEach(tab => {
      const kw = parseInt(tab.dataset.kw);
      tab.classList.toggle('active', kw === this.currentKw);
      // Abgeschlossene KWs markieren
      const proto = this.protocols[kw];
      if (!proto) {
        tab.classList.add('kw-tab-closed');
      } else {
        tab.classList.remove('kw-tab-closed');
      }
    });
    // Inhalts-Indikatoren aktualisieren
    this.updateKwTabDots();
  },

  async updateKwTabDots() {
    const tabs = document.querySelectorAll('.kw-tab');
    for (const tab of tabs) {
      const kw = parseInt(tab.dataset.kw);
      const proto = this.protocols[kw];
      const dot = tab.querySelector('.kw-tab-dot');
      if (!dot || !proto) continue;

      const { data: entries } = await this.supabase
        .from('entries')
        .select('content')
        .eq('protocol_id', proto.id)
        .neq('content', '');

      const hasContent = entries && entries.some(e => e.content && e.content.trim());
      dot.classList.toggle('has-content', hasContent);
    }
  },

  async switchToKw(kw, year) {
    this.currentKw = kw;
    if (year) this.currentYear = year;

    document.getElementById('loading').style.display = 'block';
    document.getElementById('app-content').style.display = 'none';

    // Protokoll fuer diese KW laden/erstellen
    await this.loadOrCreateProtocolForKw(kw, this.currentYear);
    this.protocol = this.protocols[kw];

    this.updateKwTabStates();
    await this.render();

    // Normale User automatisch als "gelesen" markieren
    if (!this.isProtokolleur && this.currentUser.id) {
      await this.markAsRead();
    }

    document.getElementById('loading').style.display = 'none';
    document.getElementById('app-content').style.display = 'block';
  },

  async loadAllMonthProtocols() {
    for (const week of this.monthWeeks) {
      await this.loadOrCreateProtocolForKw(week.kw, week.year);
    }
  },

  async loadOrCreateProtocolForKw(kw, year) {
    // Erst schauen ob schon geladen
    if (this.protocols[kw]) return;

    const { data, error } = await this.supabase.rpc('create_protocol_for_week', {
      p_cw: kw,
      p_year: year,
    });
    if (error) throw error;

    const { data: proto } = await this.supabase
      .from('protocols')
      .select('*')
      .eq('id', data)
      .single();

    this.protocols[kw] = proto;
  },

  async loadParticipants() {
    const { data } = await this.supabase
      .from('participants')
      .select('*')
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

    // Alte Lesebestaetigungen-Section ausblenden (ersetzt durch automatisches Gelesen)
    const confSection = document.getElementById('confirmations-section');
    if (confSection) confSection.style.display = 'none';

    // Header
    document.getElementById('week-dates').textContent =
      `KW ${this.protocol.calendar_week}: ${this.formatDate(this.protocol.week_start)} - ${this.formatDate(this.protocol.week_end)}`;

    // Zukunfts-KW erkennen: KW liegt nach der aktuellen KW
    const realKw = this.getISOWeek(new Date());
    const realYear = this.getISOYear(new Date());
    const isFutureWeek = this.protocol.year > realYear ||
      (this.protocol.year === realYear && this.protocol.calendar_week > realKw);

    // "Woche abschliessen" nur fuer Protokolleur bei vergangenen/aktueller KW anzeigen
    const closeBtn = document.getElementById('btn-close-week');
    if (closeBtn) closeBtn.style.display = (isFutureWeek || !this.isProtokolleur) ? 'none' : '';

    // Anwesenheit bei zukuenftigen KWs ausblenden
    const attendanceSection = document.querySelector('.attendance-section');
    if (attendanceSection) attendanceSection.style.display = isFutureWeek ? 'none' : '';

    // Anwesenheit
    await this.renderAttendance(attendance);

    // Ablauf rendern
    const container = document.getElementById('entries-container');
    container.innerHTML = '';

    // 1. Bericht Betriebsrat
    const brEntry = entries.find(e => e.section === 'betriebsrat');
    if (brEntry) {
      container.appendChild(this.createSection('Bericht des Bereichsbetriebsrates', [brEntry]));
    }

    // 2. Blitzlicht - Berichte aller Anwesenden (eigener Bericht zuerst)
    const blitzEntries = entries.filter(e => e.section === 'blitzlicht');
    blitzEntries.sort((a, b) => {
      const aIsMine = a.author_name === this.currentUser.name ? 0 : 1;
      const bIsMine = b.author_name === this.currentUser.name ? 0 : 1;
      return aIsMine - bIsMine;
    });
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
  async renderAttendance(attendanceList) {
    const grid = document.getElementById('attendance-grid');
    grid.innerHTML = '';

    // Gelesen-Status laden (read_confirmations fuer diese KW)
    const { data: readConfs } = await this.supabase
      .from('read_confirmations')
      .select('participant_id, confirmed')
      .eq('calendar_week', this.protocol.calendar_week)
      .eq('year', this.protocol.year)
      .eq('confirmed', true);
    const readSet = new Set((readConfs || []).map(r => r.participant_id));

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
        const isPresent = att && att.present;
        const hasRead = readSet.has(p.id);
        const isMe = this.currentUser && this.currentUser.id === p.id;

        const item = document.createElement('div');
        item.className = 'attendance-item'
          + (isPresent ? ' present' : '')
          + (hasRead && !isPresent ? ' has-read' : '')
          + (isMe ? ' is-me' : '');

        if (isPresent) {
          item.innerHTML = `<span class="check">&#10003;</span><span>${p.name}</span>`;
        } else if (hasRead) {
          item.innerHTML = `<span class="read-icon">&#128065;</span><span>${p.name}</span><span class="gelesen-badge">Gelesen</span>`;
        } else {
          item.innerHTML = `<span class="check">&#10003;</span><span>${p.name}</span>`;
        }

        // Nur Protokolleur darf Anwesenheit togglen
        if (this.isProtokolleur) {
          item.style.cursor = 'pointer';
          item.addEventListener('click', () => this.toggleAttendance(p.id, item));
        } else {
          item.style.cursor = 'default';
        }
        items.appendChild(item);
      }

      group.appendChild(items);
      grid.appendChild(group);
    }
  },

  async toggleAttendance(participantId, element) {
    if (!this.isProtokolleur) return;
    const isPresent = element.classList.toggle('present');
    element.classList.remove('has-read');
    if (isPresent) {
      element.innerHTML = `<span class="check">&#10003;</span><span>${element.querySelector('span:nth-child(2)').textContent}</span>`;
    }
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
        this.autoResize(textarea);
        this.debounceSaveEntry(entry.id, textarea.value, card);
      });
      requestAnimationFrame(() => this.autoResize(textarea));

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

  // --- Akkordeon: eine Karte oeffnen, andere schliessen ---
  toggleAccordion(card) {
    const section = card.closest('.category-section');
    if (!section) { card.classList.toggle('open'); return; }
    const wasOpen = card.classList.contains('open');
    // Alle Karten in dieser Sektion schliessen
    section.querySelectorAll('.entry-card.open').forEach(c => c.classList.remove('open'));
    // Geklickte Karte oeffnen (wenn sie vorher zu war)
    if (!wasOpen) {
      card.classList.add('open');
      // Textarea resize nachdem Karte sichtbar ist
      const ta = card.querySelector('textarea');
      if (ta) requestAnimationFrame(() => this.autoResize(ta));
    }
  },

  // --- Entry Card ---
  async createEntryCard(entry) {
    const card = document.createElement('div');
    card.className = 'entry-card' + (entry.content ? ' has-content' : '');

    // Berechtigung: nur Autor oder Protokolleur darf bearbeiten/loeschen
    const isOwner = entry.author_name === this.currentUser.name;
    const canEdit = isOwner || this.isProtokolleur;

    const header = document.createElement('div');
    header.className = 'entry-card-header';
    header.innerHTML = `
      <span class="name">Bericht von ${entry.author_name || 'Unbekannt'}</span>
      <div class="entry-card-actions">
        <span class="status">${entry.content ? 'Eingetragen' : 'Offen'}</span>
        ${canEdit ? '<button class="btn-delete-entry" title="Bericht löschen">&times;</button>' : ''}
      </div>
    `;
    header.querySelector('.name').addEventListener('click', () => this.toggleAccordion(card));
    header.querySelector('.entry-card-actions .status').addEventListener('click', () => this.toggleAccordion(card));
    if (canEdit) {
      header.querySelector('.btn-delete-entry').addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!confirm(`Bericht von "${entry.author_name || 'Unbekannt'}" wirklich löschen?`)) return;
        // Anhaenge aus Storage loeschen (Hyperlinks ueberspringen)
        const { data: atts } = await this.supabase.from('attachments').select('storage_path').eq('entry_id', entry.id);
        if (atts && atts.length > 0) {
          const storagePaths = atts.filter(a => a.storage_path !== 'hyperlink').map(a => a.storage_path);
          if (storagePaths.length > 0) {
            await this.supabase.storage.from('attachments').remove(storagePaths);
          }
        }
        await this.supabase.from('entries').delete().eq('id', entry.id);
        card.remove();
        this.showSave('saved');
      });
    }

    const body = document.createElement('div');
    body.className = 'entry-card-body';

    const textarea = document.createElement('textarea');
    textarea.value = entry.content || '';
    textarea.placeholder = `Bericht von ${entry.author_name || ''} ...`;
    if (canEdit) {
      textarea.addEventListener('input', () => {
        this.autoResize(textarea);
        this.debounceSaveEntry(entry.id, textarea.value, card, header);
      });
    } else {
      textarea.readOnly = true;
      textarea.style.opacity = '0.8';
      textarea.style.cursor = 'default';
    }
    // Initial resize nach Render
    requestAnimationFrame(() => this.autoResize(textarea));

    body.appendChild(textarea);

    // Datei-Upload
    const uploadArea = document.createElement('div');
    uploadArea.className = 'file-upload-area';

    const fileList = document.createElement('div');
    fileList.className = 'file-list';

    if (canEdit) {
      const uploadBtns = document.createElement('div');
      uploadBtns.className = 'upload-buttons';

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

      // Hyperlink-Button
      const linkBtn = document.createElement('button');
      linkBtn.className = 'file-upload-btn link-upload-btn';
      linkBtn.type = 'button';
      linkBtn.innerHTML = '+ Link einfügen';
      linkBtn.addEventListener('click', () => this.showLinkDialog(entry.id, fileList, linkBtn));

      uploadBtns.appendChild(uploadBtn);
      uploadBtns.appendChild(linkBtn);
      uploadArea.appendChild(uploadBtns);
    }
    uploadArea.appendChild(fileList);
    body.appendChild(uploadArea);

    card.appendChild(header);
    card.appendChild(body);

    // Drag & Drop
    let dragCounter = 0;
    body.addEventListener('dragenter', (e) => { e.preventDefault(); dragCounter++; body.classList.add('drag-over'); });
    body.addEventListener('dragleave', () => { dragCounter--; if (dragCounter <= 0) { dragCounter = 0; body.classList.remove('drag-over'); } });
    body.addEventListener('dragover', (e) => e.preventDefault());
    body.addEventListener('drop', (e) => {
      e.preventDefault();
      dragCounter = 0;
      body.classList.remove('drag-over');
      if (e.dataTransfer.files.length > 0) {
        for (const file of e.dataTransfer.files) {
          this.uploadFile(entry.id, file, fileList);
        }
      }
    });

    // Vorhandene Anhaenge laden
    const attachments = await this.loadAttachments(entry.id);
    for (const att of attachments) {
      this.addFileItem(fileList, att);
    }

    return card;
  },

  // --- Textarea Auto-Resize ---
  autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
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
    // Hyperlinks separat behandeln
    if (attachment.storage_path === 'hyperlink') {
      this.addLinkItem(container, attachment);
      return;
    }

    const IMAGE_EXTS = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'];
    const ext = attachment.original_name.split('.').pop().toLowerCase();
    const isImage = IMAGE_EXTS.includes(ext);

    const item = document.createElement('div');
    item.className = 'file-item';

    let thumbHtml = '';
    if (isImage) {
      const { data: urlData } = this.supabase.storage.from('attachments').getPublicUrl(attachment.storage_path);
      if (urlData && urlData.publicUrl) {
        thumbHtml = `<img src="${urlData.publicUrl}" class="file-thumb" alt="">`;
      }
    }

    item.innerHTML = `
      <div class="file-item-content">
        ${thumbHtml}
        <a href="#" onclick="App.downloadFile('${attachment.storage_path}', '${attachment.original_name}'); return false;">
          ${attachment.original_name}
        </a>
      </div>
      <button class="remove-file" onclick="App.removeFile('${attachment.id}', '${attachment.storage_path}', this)">&times;</button>
    `;
    container.appendChild(item);
  },

  // --- Hyperlink einfuegen ---
  showLinkDialog(entryId, fileListEl, triggerBtn) {
    // Altes Dialog entfernen falls vorhanden
    const existing = triggerBtn.parentElement.querySelector('.link-dialog');
    if (existing) { existing.remove(); return; }

    const dialog = document.createElement('div');
    dialog.className = 'link-dialog';
    dialog.innerHTML = `
      <input type="url" class="link-input" placeholder="https://..." autofocus>
      <input type="text" class="link-input" placeholder="Anzeigename (optional)">
      <div class="link-dialog-actions">
        <button class="btn btn-primary btn-sm link-save-btn">Speichern</button>
        <button class="btn btn-secondary btn-sm link-cancel-btn">Abbrechen</button>
      </div>
    `;
    triggerBtn.parentElement.appendChild(dialog);

    const urlInput = dialog.querySelector('input[type="url"]');
    const nameInput = dialog.querySelector('input[type="text"]');
    urlInput.focus();

    dialog.querySelector('.link-save-btn').addEventListener('click', () => {
      const url = urlInput.value.trim();
      if (!url) { urlInput.focus(); return; }
      const displayName = nameInput.value.trim() || url;
      this.saveHyperlink(entryId, url, displayName, fileListEl);
      dialog.remove();
    });
    dialog.querySelector('.link-cancel-btn').addEventListener('click', () => dialog.remove());
    urlInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); nameInput.focus(); }
    });
    nameInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); dialog.querySelector('.link-save-btn').click(); }
    });
  },

  async saveHyperlink(entryId, url, displayName, fileListEl) {
    this.showSave('saving');
    const { data: att, error } = await this.supabase
      .from('attachments')
      .insert({
        entry_id: entryId,
        filename: url,
        original_name: displayName,
        storage_path: 'hyperlink',
      })
      .select()
      .single();

    if (!error && att) {
      this.addLinkItem(fileListEl, att);
      this.showSave('saved');
    }
  },

  addLinkItem(container, attachment) {
    const item = document.createElement('div');
    item.className = 'file-item file-item-link';
    item.innerHTML = `
      <div class="file-item-content">
        <span class="link-icon">&#128279;</span>
        <a href="${attachment.filename}" target="_blank" rel="noopener noreferrer">
          ${attachment.original_name}
        </a>
      </div>
      <button class="remove-file" onclick="App.removeLink('${attachment.id}', this)">&times;</button>
    `;
    container.appendChild(item);
  },

  async removeLink(attachmentId, btn) {
    await this.supabase.from('attachments').delete().eq('id', attachmentId);
    btn.parentElement.remove();
    this.showSave('saved');
  },

  // --- Automatisch als gelesen markieren (fuer normale User) ---
  async markAsRead() {
    if (!this.protocol || !this.currentUser.id) return;
    try {
      await this.supabase
        .from('read_confirmations')
        .upsert({
          calendar_week: this.protocol.calendar_week,
          year: this.protocol.year,
          participant_id: this.currentUser.id,
          confirmed: true,
          confirmed_at: new Date().toISOString(),
        }, { onConflict: 'calendar_week,year,participant_id' });
    } catch (e) {
      console.warn('Gelesen-Markierung fehlgeschlagen:', e);
    }
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

    // Anhaenge fuer alle Entries laden
    const allEntries = entData || [];
    const entryAttachments = {};
    for (const entry of allEntries) {
      const { data: atts } = await this.supabase
        .from('attachments')
        .select('*')
        .eq('entry_id', entry.id);
      if (atts && atts.length > 0) entryAttachments[entry.id] = atts;
    }

    // PDF generieren und herunterladen
    if (!window.jspdf) {
      throw new Error('PDF-Bibliothek (jsPDF) nicht geladen. Bitte Seite neu laden.');
    }
    await this.generatePDF(this.protocol, attData || [], allEntries, entryAttachments);

    // Lesebestaetigung nur fuer ABWESENDE Teilnehmer (Anwesende waren live dabei)
    try {
      const presentIds = new Set((attData || []).filter(a => a.present).map(a => a.participant_id));
      const absentParticipants = this.participants.filter(p => !presentIds.has(p.id));
      const confirmInserts = absentParticipants.map(p => ({
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

    // Protokoll aus Cache entfernen
    const closedKw = this.protocol.calendar_week;
    delete this.protocols[closedKw];

    // Kurz warten damit der PDF-Download starten kann
    await new Promise(r => setTimeout(r, 1500));

    // Tab als abgeschlossen markieren, zur aktuellen echten KW wechseln
    this.updateKwTabStates();
    const realKw = this.getISOWeek(new Date());
    const realYear = this.getISOYear(new Date());
    // Wenn die geschlossene KW die aktuelle war, zur naechsten offenen wechseln
    const nextKw = this.monthWeeks.find(w => this.protocols[w.kw] || w.kw !== closedKw);
    if (nextKw) {
      await this.switchToKw(realKw, realYear);
    } else {
      window.location.reload();
    }
  },

  // ===========================================
  // PDF Generierung
  // ===========================================
  async generatePDF(proto, attendance, entries, entryAttachments) {
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ unit: 'mm', format: 'a4' });
    const pageW = doc.internal.pageSize.getWidth();
    const pageH = doc.internal.pageSize.getHeight();
    const margin = 20;
    const maxW = pageW - 2 * margin;
    let y = margin;

    const IMAGE_EXTS = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'];

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

    const URL_REGEX = /https?:\/\/[^\s,)>\]]+/g;

    const writeWrapped = (text, size, style, color) => {
      addText(text, size, style, color);
      const lines = doc.splitTextToSize(text, maxW);
      const lineH = (size || 11) * 0.5;
      checkPage(lines.length * lineH);
      doc.text(lines, margin, y);
      y += lines.length * lineH + 2;

      // URLs als klickbare Links darunter auflisten
      const urls = text.match(URL_REGEX);
      if (urls && urls.length > 0) {
        const uniqueUrls = [...new Set(urls)];
        for (const url of uniqueUrls) {
          checkPage(6);
          doc.setFontSize(8);
          doc.setTextColor(0, 90, 180);
          doc.textWithLink(url, margin + 2, y, { url });
          y += 4;
        }
        doc.setTextColor(0, 0, 0);
      }
    };

    // Bild aus Supabase Storage laden und als Data-URL zurueckgeben
    const loadImageAsDataUrl = async (storagePath) => {
      try {
        const { data } = await this.supabase.storage.from('attachments').download(storagePath);
        if (!data) return null;
        return new Promise((resolve) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = () => resolve(null);
          reader.readAsDataURL(data);
        });
      } catch { return null; }
    };

    // Anhaenge fuer einen Entry in PDF einfuegen
    const addAttachments = async (entryId) => {
      const atts = entryAttachments[entryId];
      if (!atts || atts.length === 0) return;

      for (const att of atts) {
        const ext = att.original_name.split('.').pop().toLowerCase();
        if (IMAGE_EXTS.includes(ext)) {
          // Bild einbetten
          const dataUrl = await loadImageAsDataUrl(att.storage_path);
          if (dataUrl) {
            const imgProps = doc.getImageProperties(dataUrl);
            let imgW = maxW;
            let imgH = (imgProps.height / imgProps.width) * imgW;
            // Max 120mm hoch
            if (imgH > 120) { imgH = 120; imgW = (imgProps.width / imgProps.height) * imgH; }
            checkPage(imgH + 8);
            addText('', 8, 'italic', [120, 120, 120]);
            doc.text(att.original_name, margin, y);
            y += 4;
            doc.addImage(dataUrl, ext === 'png' ? 'PNG' : 'JPEG', margin, y, imgW, imgH);
            y += imgH + 4;
          }
        } else if (att.storage_path === 'hyperlink') {
          // Hyperlink: klickbar im PDF
          checkPage(6);
          doc.setFontSize(9);
          doc.setTextColor(0, 90, 180);
          doc.textWithLink(att.original_name, margin + 2, y, { url: att.filename });
          y += 5;
          doc.setTextColor(0, 0, 0);
        } else {
          // Nicht-Bild: als Texthinweis
          checkPage(8);
          addText('', 9, 'italic', [120, 120, 120]);
          doc.text(`[Anhang: ${att.original_name}]`, margin, y);
          y += 5;
        }
      }
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
      await addAttachments(brEntry.id);
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
        await addAttachments(entry.id);
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
      await addAttachments(sonstigesEntry.id);
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

  // Lesebestaetigungen werden jetzt automatisch beim Oeffnen des Protokolls gesetzt
  // Die alte manuelle Bestaetigungs-Section wird nicht mehr angezeigt

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
