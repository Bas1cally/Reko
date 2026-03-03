// ===== Entry toggle =====
function toggleEntry(header) {
    const block = header.closest('.entry-block');
    const body = block.querySelector('.entry-body');
    const isOpen = block.classList.contains('open');

    if (isOpen) {
        body.style.display = 'none';
        block.classList.remove('open');
    } else {
        body.style.display = 'block';
        block.classList.add('open');
    }
}

// ===== Attendance checkboxes =====
document.querySelectorAll('.attendance-checkbox').forEach(cb => {
    cb.addEventListener('change', async function () {
        const protocolId = this.dataset.protocolId;
        const participantId = this.dataset.participantId;
        const present = this.checked;
        const item = this.closest('.attendance-item');
        const timeSpan = item.querySelector('.attendance-time');

        try {
            const res = await fetch('/api/attendance', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    protocol_id: parseInt(protocolId),
                    participant_id: parseInt(participantId),
                    present: present,
                }),
            });
            const data = await res.json();

            if (data.ok) {
                item.classList.toggle('checked', present);
                timeSpan.textContent = data.checked_at || '';
            }
        } catch (e) {
            console.error('Attendance error:', e);
        }
    });
});

// ===== Save entry buttons =====
document.querySelectorAll('.save-entry-btn').forEach(btn => {
    btn.addEventListener('click', async function () {
        const protocolId = this.dataset.protocolId;
        const participantId = this.dataset.participantId;
        const block = this.closest('.entry-block');
        const textarea = block.querySelector('.entry-textarea');
        const statusSpan = this.closest('.entry-actions').querySelector('.save-status');
        const indicator = block.querySelector('.entry-indicator');

        try {
            this.disabled = true;
            this.textContent = 'Speichert...';

            const res = await fetch('/api/entry', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    protocol_id: parseInt(protocolId),
                    participant_id: parseInt(participantId),
                    content: textarea.value,
                }),
            });
            const data = await res.json();

            if (data.ok) {
                statusSpan.textContent = 'Gespeichert ' + data.updated_at;
                if (textarea.value.trim()) {
                    indicator.textContent = 'Eintrag vorhanden';
                    indicator.classList.add('has-content');
                } else {
                    indicator.textContent = 'Kein Eintrag';
                    indicator.classList.remove('has-content');
                }
                setTimeout(() => { statusSpan.textContent = ''; }, 3000);
            }
        } catch (e) {
            statusSpan.textContent = 'Fehler beim Speichern';
            console.error('Save error:', e);
        } finally {
            this.disabled = false;
            this.textContent = 'Speichern';
        }
    });
});

// ===== File upload =====
document.querySelectorAll('.file-input').forEach(input => {
    input.addEventListener('change', async function () {
        if (!this.files.length) return;

        const protocolId = this.dataset.protocolId;
        const participantId = this.dataset.participantId;
        const block = this.closest('.entry-block');
        const attachmentsList = block.querySelector('.attachments-list');

        const formData = new FormData();
        formData.append('file', this.files[0]);
        formData.append('protocol_id', protocolId);
        formData.append('participant_id', participantId);

        try {
            const res = await fetch('/api/upload', {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();

            if (data.ok) {
                const item = document.createElement('div');
                item.className = 'attachment-item';
                item.dataset.id = data.id;
                item.innerHTML = `
                    <a href="${data.url}" target="_blank">${data.name}</a>
                    <button class="btn-icon delete-attachment" data-id="${data.id}" title="Löschen">&times;</button>
                `;
                attachmentsList.appendChild(item);
                bindDeleteButtons(item);
            } else {
                alert(data.error || 'Upload fehlgeschlagen.');
            }
        } catch (e) {
            console.error('Upload error:', e);
            alert('Upload fehlgeschlagen.');
        }

        this.value = '';
    });
});

// ===== Delete attachment =====
function bindDeleteButtons(scope) {
    const root = scope || document;
    root.querySelectorAll('.delete-attachment').forEach(btn => {
        btn.addEventListener('click', async function (e) {
            e.stopPropagation();
            if (!confirm('Anhang löschen?')) return;

            const id = this.dataset.id;
            try {
                const res = await fetch(`/api/attachment/${id}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.ok) {
                    this.closest('.attachment-item').remove();
                }
            } catch (e) {
                console.error('Delete error:', e);
            }
        });
    });
}

// Bind existing delete buttons
bindDeleteButtons();
