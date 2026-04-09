const API = window.location.origin + '/api';
let token = localStorage.getItem('notifli_token');
let currentBiz = null;
let clientsCache = [];

// ── Init ──────────────────────────────────────────────────────────────
window.onload = () => {
  if (token) { initApp(); } else { showScreen('auth'); }
};

async function initApp() {
  try {
    const me = await apiFetch('/auth/me');
    currentBiz = me;
    document.getElementById('sidebar-biz-name').textContent = me.name;
    showTrialBanner(me);
    showScreen('app');
    showPage('dashboard');
    loadDashboard();
  } catch {
    logout();
  }
}

function showScreen(name) {
  document.getElementById('auth-screen').classList.toggle('hidden', name !== 'auth');
  document.getElementById('app-screen').classList.toggle('hidden', name !== 'app');
}

function showTab(tab) {
  document.getElementById('login-form').classList.toggle('hidden', tab !== 'login');
  document.getElementById('register-form').classList.toggle('hidden', tab !== 'register');
  document.querySelectorAll('.tab').forEach((t, i) => {
    t.classList.toggle('active', (i === 0 && tab === 'login') || (i === 1 && tab === 'register'));
  });
}

function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  document.getElementById(`page-${name}`).classList.remove('hidden');
  document.querySelectorAll('.nav-link').forEach(l => {
    if (l.getAttribute('onclick')?.includes(name)) l.classList.add('active');
  });
  if (name === 'dashboard') loadDashboard();
  if (name === 'appointments') loadAppointments();
  if (name === 'clients') loadClients();
  if (name === 'sms-logs') loadSMSLogs();
  if (name === 'settings') loadSettings();
}

function showTrialBanner(biz) {
  const banner = document.getElementById('trial-banner');
  if (biz.subscription_status === 'trial' && biz.trial_ends_at) {
    const days = Math.ceil((new Date(biz.trial_ends_at) - new Date()) / 86400000);
    banner.textContent = days > 0 ? `⏳ ${days} days left in trial` : '⚠️ Trial expired';
    banner.classList.remove('hidden');
  } else if (biz.subscription_status === 'active') {
    banner.textContent = '✅ Pro Plan Active';
  } else {
    banner.textContent = '⚠️ Subscription inactive';
  }
}

// ── Auth ──────────────────────────────────────────────────────────────
async function doLogin(e) {
  e.preventDefault();
  const email = document.getElementById('login-email').value;
  const password = document.getElementById('login-password').value;
  try {
    const res = await apiFetch('/auth/login', 'POST', { email, password });
    token = res.access_token;
    localStorage.setItem('notifli_token', token);
    await initApp();
  } catch (err) {
    document.getElementById('login-error').textContent = err.message || 'Login failed';
  }
}

async function doRegister(e) {
  e.preventDefault();
  const data = {
    name: document.getElementById('reg-name').value,
    email: document.getElementById('reg-email').value,
    password: document.getElementById('reg-password').value,
    business_type: document.getElementById('reg-type').value,
    timezone: document.getElementById('reg-tz').value
  };
  try {
    const res = await apiFetch('/auth/register', 'POST', data);
    token = res.access_token;
    localStorage.setItem('notifli_token', token);
    await initApp();
  } catch (err) {
    document.getElementById('reg-error').textContent = err.message || 'Registration failed';
  }
}

function logout() {
  token = null;
  localStorage.removeItem('notifli_token');
  showScreen('auth');
}

// ── Dashboard ─────────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const stats = await apiFetch('/dashboard/stats');
    document.getElementById('stat-clients').textContent = stats.total_clients;
    document.getElementById('stat-upcoming').textContent = stats.upcoming_appointments;
    document.getElementById('stat-noshows').textContent = stats.no_shows_this_month;
    document.getElementById('stat-reminders').textContent = stats.total_reminders_sent;
  } catch {}
}

// ── Appointments ──────────────────────────────────────────────────────
async function loadAppointments() {
  const filter = document.getElementById('appt-filter')?.value || 'upcoming';
  const container = document.getElementById('appointments-list');
  container.innerHTML = '<div class="empty-state">Loading...</div>';
  try {
    let appts = await apiFetch('/appointments');
    const now = new Date();
    if (filter === 'upcoming') appts = appts.filter(a => new Date(a.scheduled_at) >= now && ['scheduled','confirmed'].includes(a.status));
    else if (filter !== 'all') appts = appts.filter(a => a.status === filter);
    appts.sort((a,b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));

    if (!appts.length) { container.innerHTML = '<div class="empty-state">No appointments found</div>'; return; }

    container.innerHTML = appts.map(a => {
      const dt = new Date(a.scheduled_at).toLocaleString('en-US', {weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
      const r24 = a.reminder_24h_sent ? '✅' : '⏳';
      const r2  = a.reminder_2h_sent  ? '✅' : '⏳';
      return `<div class="list-item">
        <div class="list-item-info">
          <div class="list-item-name">${a.client_name} ${statusBadge(a.status)}</div>
          <div class="list-item-sub">${a.service || 'Appointment'} · ${dt}</div>
          <div class="list-item-sub">24h reminder ${r24} · 2h reminder ${r2} · 📞 ${a.client_phone}</div>
        </div>
        <div class="list-item-actions">
          <button class="btn-sm btn-send" onclick="sendReminder(${a.id})">Send Reminder</button>
          <button class="btn-sm btn-cancel-appt" onclick="cancelAppt(${a.id})">Cancel</button>
        </div>
      </div>`;
    }).join('');
  } catch(e) {
    container.innerHTML = `<div class="empty-state">Error: ${e.message}</div>`;
  }
}

async function addAppointment(e) {
  e.preventDefault();
  const data = {
    client_id: parseInt(document.getElementById('appt-client').value),
    service: document.getElementById('appt-service').value,
    scheduled_at: document.getElementById('appt-datetime').value,
    duration_minutes: parseInt(document.getElementById('appt-duration').value) || 60,
    notes: document.getElementById('appt-notes').value
  };
  try {
    await apiFetch('/appointments', 'POST', data);
    hideModal('add-appt-modal');
    loadAppointments();
    toast('Appointment scheduled!', 'success');
  } catch(e) { toast(e.message, 'error'); }
}

async function sendReminder(id) {
  try {
    const r = await apiFetch(`/appointments/${id}/send-reminder`, 'POST');
    const mode = r.demo ? ' (Demo mode - Twilio not configured)' : '';
    toast(`Reminder sent${mode}: "${r.message.substring(0,60)}..."`, 'success');
  } catch(e) { toast(e.message, 'error'); }
}

async function cancelAppt(id) {
  if (!confirm('Cancel this appointment?')) return;
  try {
    await apiFetch(`/appointments/${id}`, 'PATCH', { status: 'cancelled' });
    loadAppointments();
    toast('Appointment cancelled', 'success');
  } catch(e) { toast(e.message, 'error'); }
}

// ── Clients ───────────────────────────────────────────────────────────
async function loadClients() {
  const container = document.getElementById('clients-list');
  container.innerHTML = '<div class="empty-state">Loading...</div>';
  try {
    clientsCache = await apiFetch('/clients');
    if (!clientsCache.length) { container.innerHTML = '<div class="empty-state">No clients yet. Add your first client!</div>'; return; }
    container.innerHTML = clientsCache.map(c => `
      <div class="list-item">
        <div class="list-item-info">
          <div class="list-item-name">${c.name} ${c.opt_out ? '<span class="status-badge status-cancelled">Opted Out</span>' : ''}</div>
          <div class="list-item-sub">📞 ${c.phone}${c.email ? ` · ✉️ ${c.email}` : ''}${c.notes ? ` · ${c.notes}` : ''}</div>
        </div>
        <div class="list-item-actions">
          <button class="btn-sm btn-cancel-appt" onclick="deleteClient(${c.id})">Delete</button>
        </div>
      </div>`).join('');
  } catch(e) {
    container.innerHTML = `<div class="empty-state">Error loading clients</div>`;
  }
}

async function addClient(e) {
  e.preventDefault();
  const data = {
    name: document.getElementById('client-name').value,
    phone: document.getElementById('client-phone').value,
    email: document.getElementById('client-email').value || null,
    notes: document.getElementById('client-notes').value || null
  };
  try {
    await apiFetch('/clients', 'POST', data);
    hideModal('add-client-modal');
    e.target.reset();
    loadClients();
    toast('Client added!', 'success');
  } catch(e) { toast(e.message, 'error'); }
}

async function deleteClient(id) {
  if (!confirm('Delete this client?')) return;
  try {
    await apiFetch(`/clients/${id}`, 'DELETE');
    loadClients();
    toast('Client deleted', 'success');
  } catch(e) { toast(e.message, 'error'); }
}

// ── SMS Logs ──────────────────────────────────────────────────────────
async function loadSMSLogs() {
  const container = document.getElementById('sms-logs-list');
  container.innerHTML = '<div class="empty-state">Loading...</div>';
  try {
    const logs = await apiFetch('/sms-logs');
    if (!logs.length) { container.innerHTML = '<div class="empty-state">No SMS logs yet</div>'; return; }
    container.innerHTML = logs.map(l => {
      const dt = new Date(l.sent_at).toLocaleString();
      const badge = l.direction === 'outbound' ? `<span class="status-badge sms-out">Sent</span>` : `<span class="status-badge sms-in">Received</span>`;
      return `<div class="list-item">
        <div class="list-item-info">
          <div class="list-item-name">${l.client_phone} ${badge}</div>
          <div class="list-item-sub">${l.message}</div>
          <div class="list-item-sub">${dt} · ${l.status}</div>
        </div>
      </div>`;
    }).join('');
  } catch { container.innerHTML = '<div class="empty-state">Error loading logs</div>'; }
}

// ── Settings ──────────────────────────────────────────────────────────
async function loadSettings() {
  try {
    const s = await apiFetch('/settings/reminders');
    document.getElementById('set-24h').checked = s.send_24h;
    document.getElementById('set-2h').checked = s.send_2h;
    document.getElementById('set-ai').checked = s.ai_personalize;
    document.getElementById('set-custom').value = s.custom_message || '';

    // Billing
    const biz = currentBiz;
    const billingEl = document.getElementById('billing-status');
    const upgradeBtn = document.getElementById('upgrade-btn');
    if (biz.subscription_status === 'active') {
      billingEl.textContent = '✅ Pro Plan — Active';
      upgradeBtn.textContent = 'Manage Subscription';
    } else if (biz.subscription_status === 'trial') {
      const days = Math.ceil((new Date(biz.trial_ends_at) - new Date()) / 86400000);
      billingEl.textContent = `Free Trial — ${days} days remaining`;
    } else {
      billingEl.textContent = '⚠️ No active subscription';
    }
  } catch {}
}

async function saveSettings() {
  const data = {
    send_24h: document.getElementById('set-24h').checked,
    send_2h: document.getElementById('set-2h').checked,
    ai_personalize: document.getElementById('set-ai').checked,
    custom_message: document.getElementById('set-custom').value || null
  };
  try {
    await apiFetch('/settings/reminders', 'PATCH', data);
    document.getElementById('settings-msg').textContent = 'Settings saved!';
    setTimeout(() => document.getElementById('settings-msg').textContent = '', 3000);
  } catch(e) { toast(e.message, 'error'); }
}

async function startCheckout() {
  try {
    const r = await apiFetch('/billing/checkout', 'POST');
    if (r.checkout_url) window.location.href = r.checkout_url;
  } catch(e) { toast(e.message, 'error'); }
}

// ── Modals ────────────────────────────────────────────────────────────
function showModal(id) {
  document.getElementById(id).classList.remove('hidden');
  // Populate client dropdown for appointments modal
  if (id === 'add-appt-modal') {
    const sel = document.getElementById('appt-client');
    sel.innerHTML = '<option value="">Select Client...</option>' +
      clientsCache.map(c => `<option value="${c.id}">${c.name} — ${c.phone}</option>`).join('');
    // If clients not loaded yet, load them
    if (!clientsCache.length) apiFetch('/clients').then(c => {
      clientsCache = c;
      sel.innerHTML = '<option value="">Select Client...</option>' +
        c.map(cl => `<option value="${cl.id}">${cl.name} — ${cl.phone}</option>`).join('');
    });
  }
}
function hideModal(id) { document.getElementById(id).classList.add('hidden'); }
window.onclick = e => { if (e.target.classList.contains('modal')) e.target.classList.add('hidden'); };

// ── Toast ─────────────────────────────────────────────────────────────
function toast(msg, type='') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast ${type}`;
  setTimeout(() => t.classList.add('hidden'), 4000);
}

// ── Helpers ───────────────────────────────────────────────────────────
function statusBadge(status) {
  return `<span class="status-badge status-${status}">${status}</span>`;
}

async function apiFetch(path, method='GET', body=null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${API}${path}`, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || 'Request failed');
  return data;
}
