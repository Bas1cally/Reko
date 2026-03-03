// ===========================================
// ReKo Protokoll - Hauptanwendung
// ===========================================

const App = {
  supabase: null,
  protocol: null,
  participants: [],
  entries: {},
  saveTimers: {},

  async init() {
    this.supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
    Auth.init(this.supabase);

    const session = await Auth.requireAuth();
    if (!session) return;

    document.getElementById('loading').style.display = 'block';
    document.getElementById('app-content').style.display = 'none';

    try {
      await this.loadOrCreateProtocol();
      await this.loadParticipants();
      await this.render();
    } catch (err) {
      console.error('Init error:', err);
      document.getElementById('loading').innerHTML =
        '<p style="color:var(--mb-red)">Fehler beim Laden. Bitte Seite neu laden.</p>';
    }
  },

  // --- Protokoll laden oder erstellen ---
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

  // --- Teilnehmer laden ---
  async loadParticipants() {
    const { data } = await this.supabase
      .from('participants')
      .select('*')
      .eq('active', true)
      .order('sort_order');
    this.participants = data || [];
  },

  // --- Anwesenheit laden ---
  async loadAttendance() {
    const { data } = await this.supabase
      .from('attendance')
      .select('*')
      .eq('protocol_id', this.protocol.id);
    return data || [];
  },

  // --- Eintraege laden ---
  async loadEntries() {
    const { data } = await this.supabase
      .from('entries')
      .select('*')
      .eq('protocol_id', this.protocol.id);
    const map = {};
    (data || []).forEach(e => { map[e.participant_id] = e; });
    return map;
  },

  // --- Anhaenge laden ---
  async loadAttachments(entryId) {
    const { data } = await this.supabase
      .from('attachments')
      .select('*')
      .eq('entry_id', entryId);
    return data || [];
  },

  // --- Hauptrendering ---
  async render() {
    const attendance = await this.loadAttendance();
    this.entries = await this.loadEntries();

    // Header
    document.getElementById('kw-badge').textContent = `KW ${this.protocol.calendar_week}`;
    document.getElementById('week-dates').textContent =
      `${this.formatDate(this.protocol.week_start)} - ${this.formatDate(this.protocol.week_end)}`;

    // Anwesenheit
    this.renderAttendance(attendance);

    // Eintraege nach Kategorie
    const categories = [
      { key: 'meister', label: 'Meister' },
      { key: 'pitstop', label: 'Pitstop / Instandhaltung' },
      { key: 'logistik', label: 'Logistik' },
    ];

    const entriesContainer = document.getElementById('entries-container');
    entriesContainer.innerHTML = '';

    for (const cat of categories) {
      const catParticipants = this.participants.filter(p => p.category === cat.key);
      if (catParticipants.length === 0) continue;

      const section = document.createElement('div');
      section.className = 'category-section';
      section.innerHTML = `<div class="category-header">${cat.label}</div>`;

      for (const p of catParticipants) {
        const entry = this.entries[p.id] || { id: null, content: '' };
        section.appendChild(await this.createEntryCard(p, entry));
      }
      entriesContainer.appendChild(section);
    }

    document.getElementById('loading').style.display = 'none';
    document.getElementById('app-content').style.display = 'block';
  },

  // --- Anwesenheit rendern ---
  renderAttendance(attendanceList) {
    const grid = document.getElementById('attendance-grid');
    grid.innerHTML = '';

    for (const p of this.participants) {
      const att = attendanceList.find(a => a.participant_id === p.id);
      const item = document.createElement('div');
      item.className = 'attendance-item' + (att && att.present ? ' present' : '');
      item.innerHTML = `<span class="check">&#10003;</span><span>${p.name}</span>`;
      item.addEventListener('click', () => this.toggleAttendance(p.id, item, att));
      grid.appendChild(item);
    }
  },

  // --- Anwesenheit toggle ---
  async toggleAttendance(participantId, element, att) {
    const isPresent = element.classList.toggle('present');
    await this.supabase
      .from('attendance')
      .update({ present: isPresent })
      .eq('protocol_id', this.protocol.id)
      .eq('participant_id', participantId);
    this.showSave();
  },

  // --- Entry Card erstellen ---
  async createEntryCard(participant, entry) {
    const card = document.createElement('div');
    card.className = 'entry-card' + (entry.content ? ' has-content' : '');

    const header = document.createElement('div');
    header.className = 'entry-card-header';
    header.innerHTML = `
      <span class="name">${participant.name}</span>
      <span class="status">${entry.content ? 'Eingetragen' : 'Offen'}</span>
    `;
    header.addEventListener('click', () => card.classList.toggle('open'));

    const body = document.createElement('div');
    body.className = 'entry-card-body';

    const textarea = document.createElement('textarea');
    textarea.value = entry.content || '';
    textarea.placeholder = `Themen fuer ${participant.name} ...`;
    textarea.addEventListener('input', () => {
      this.debounceSave(participant.id, entry.id, textarea.value, card, header);
    });

    body.appendChild(textarea);

    // Datei-Upload
    const uploadArea = document.createElement('div');
    uploadArea.className = 'file-upload-area';

    const fileList = document.createElement('div');
    fileList.className = 'file-list';
    fileList.id = `files-${participant.id}`;

    const uploadBtn = document.createElement('label');
    uploadBtn.className = 'file-upload-btn';
    uploadBtn.innerHTML = '+ Datei anhaengen';
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.style.display = 'none';
    fileInput.addEventListener('change', (e) => {
      if (e.target.files[0] && entry.id) {
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
    if (entry.id) {
      const attachments = await this.loadAttachments(entry.id);
      for (const att of attachments) {
        this.addFileItem(fileList, att);
      }
    }

    return card;
  },

  // --- Debounced Save ---
  debounceSave(participantId, entryId, content, card, header) {
    clearTimeout(this.saveTimers[participantId]);
    this.saveTimers[participantId] = setTimeout(async () => {
      this.showSave('saving');
      const { error } = await this.supabase
        .from('entries')
        .update({ content: content, updated_at: new Date().toISOString() })
        .eq('id', entryId);

      if (!error) {
        this.showSave('saved');
        card.classList.toggle('has-content', content.trim().length > 0);
        header.querySelector('.status').textContent = content.trim() ? 'Eingetragen' : 'Offen';
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

  // --- Datei-Item anzeigen ---
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

  // --- Datei herunterladen ---
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

  // --- Datei entfernen ---
  async removeFile(attachmentId, storagePath, btn) {
    await this.supabase.storage.from('attachments').remove([storagePath]);
    await this.supabase.from('attachments').delete().eq('id', attachmentId);
    btn.parentElement.remove();
    this.showSave('saved');
  },

  // --- Protokoll archivieren ---
  async archiveProtocol() {
    await this.supabase.rpc('archive_protocol', { p_protocol_id: this.protocol.id });
    window.location.reload();
  },

  // --- Speicher-Indikator ---
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

  // --- Datum formatieren ---
  formatDate(dateStr) {
    const d = new Date(dateStr);
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  },
};
