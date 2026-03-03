// ===========================================
// Auth - Shared Login via Supabase Email Auth
// ===========================================
// In Supabase einen User anlegen:
//   Email: reko@team.local
//   Password: (euer Gruppenpasswort)

const AUTH_EMAIL = 'reko@team.local';

const Auth = {
  supabase: null,

  init(supabaseClient) {
    this.supabase = supabaseClient;
  },

  async login(password) {
    const { data, error } = await this.supabase.auth.signInWithPassword({
      email: AUTH_EMAIL,
      password: password,
    });
    if (error) throw error;
    return data;
  },

  async logout() {
    await this.supabase.auth.signOut();
    window.location.href = 'index.html';
  },

  async getSession() {
    const { data: { session } } = await this.supabase.auth.getSession();
    return session;
  },

  async requireAuth() {
    const session = await this.getSession();
    if (!session) {
      window.location.href = 'index.html';
      return null;
    }
    return session;
  }
};
