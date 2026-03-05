// ===========================================
// Auth - Einfache Namens-Auswahl (kein Passwort)
// ===========================================

const Auth = {
  storageKey: 'reko_user',

  // Aktuellen User aus localStorage lesen
  getUser() {
    const raw = localStorage.getItem(this.storageKey);
    if (!raw) return null;
    try { return JSON.parse(raw); } catch { return null; }
  },

  // User setzen (nach Namens-Auswahl)
  setUser(participant) {
    localStorage.setItem(this.storageKey, JSON.stringify({
      id: participant.id,
      name: participant.name,
      role: participant.role || 'member',
    }));
  },

  // Abmelden mit Redirect
  logout() {
    localStorage.removeItem(this.storageKey);
    window.location.href = 'index.html';
  },

  // Abmelden ohne Redirect (fuer Login-Seite)
  logout_silent() {
    localStorage.removeItem(this.storageKey);
  },

  // Pruefen ob eingeloggt, sonst redirect
  requireAuth() {
    const user = this.getUser();
    if (!user) {
      window.location.href = 'index.html';
      return null;
    }
    return user;
  },
};
