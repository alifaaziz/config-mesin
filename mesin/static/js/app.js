const state = {
  devices: [], activeId: null, users: [],
  currentPage: 1, itemsPerPage: 30, sortCol: 'id', sortDir: 'asc',
  selectedUsers: new Map(),

  logs: [], logCurrentPage: 1, logItemsPerPage: 30,

  machineTimeDate: null,
  machineTimeInterval: null
};

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let toastTimer;

// ==========================================
// INISIALISASI LUCIDE ICONS
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
  if (typeof lucide !== 'undefined') lucide.createIcons();
});
function refreshIcons() {
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

// ==========================================
// UTILITIES (TOAST, MODAL, API)
// ==========================================
function toast(message, error = false) {
  const el = $('#toast');
  if (!el) return;
  el.textContent = message;
  el.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.className = 'toast', 3200);
}

function modal(id, open = true) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.toggle('open', open);
    el.setAttribute('aria-hidden', String(!open));
  }
}

async function api(url, options = {}) {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
  let data = {};
  try { data = await response.json(); } catch { }
  if (!response.ok) {
    const error = new Error(data.error || 'Permintaan gagal.');
    error.users = data.users;
    throw error;
  }
  return data;
}

function activeDevice() {
  return state.devices.find(device => device.id === state.activeId);
}

// ==========================================
// LOGOUT & VIEW NAVIGATOR
// ==========================================
$('#btnLogout')?.addEventListener('click', async () => {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.reload();
  } catch (err) { toast('Gagal logout', true); }
});

const navs = ['navUser', 'navAdmins', 'navLogs'];
const cards = ['userViewCard', 'adminViewCard', 'logViewCard'];

function switchView(activeNav, activeCard) {
  navs.forEach(nav => {
    const el = document.getElementById(nav);
    if (el) el.classList.remove('active');
  });
  cards.forEach(card => {
    const el = document.getElementById(card);
    if (el) el.style.display = 'none';
  });

  const aNav = document.getElementById(activeNav);
  if (aNav) aNav.classList.add('active');

  const aCard = document.getElementById(activeCard);
  if (aCard) aCard.style.display = 'block';
}

$('#navUser')?.addEventListener('click', () => switchView('navUser', 'userViewCard'));

$('#navAdmins')?.addEventListener('click', () => {
  switchView('navAdmins', 'adminViewCard');
  loadAdmins();
});

$('#navLogs')?.addEventListener('click', () => {
  switchView('navLogs', 'logViewCard');
  loadLogs();
});

// ==========================================
// ADMIN MANAGEMENT (CRUD)
// ==========================================
// 1. Render Tabel Admin (Dengan Validasi Role / RBAC)
async function loadAdmins() {
  try {
    const res = await api('/api/admins');
    const tbody = $('#adminRows');
    if (tbody) {
      const admins = res.admins || [];
      tbody.innerHTML = admins.map(a => {
        // Cek Hak Akses
        const isSelf = a.id === window.CURRENT_USER_ID;
        const isTargetSuperadmin = a.is_superuser;
        const canEdit = window.IS_SUPERUSER || !isTargetSuperadmin;
        const canDelete = (window.IS_SUPERUSER || !isTargetSuperadmin) && !isSelf;

        // Render Tombol
        let actionHtml = '';
        if (canEdit) {
          actionHtml += `<button class="edit-button" onclick="openEditAdmin(${a.id}, '${escapeHtml(a.username)}', '${escapeHtml(a.first_name || '')}')" style="margin-right: 6px;">
            <i data-lucide="pencil" style="width:12px; height:12px; margin-right:4px;"></i> Edit
          </button>`;
        }
        if (canDelete) {
          actionHtml += `<button class="delete-button" onclick="deleteAdmin(${a.id}, '${escapeHtml(a.username)}')">
            <i data-lucide="trash-2" style="width:12px; height:12px; margin-right:4px;"></i> Hapus
          </button>`;
        }

        // Tampilkan teks gembok jika akses diblokir
        if (!canEdit && !canDelete) {
          actionHtml = `<span style="font-size: 12px; color: #a2aba7; font-weight: 500; display: inline-flex; align-items: center; justify-content: flex-end;"><i data-lucide="lock" style="width:12px; margin-right:4px;"></i> Terkunci</span>`;
        }

        return `
          <tr>
            <td><strong>${escapeHtml(a.username)}</strong> ${a.is_superuser ? '<span class="role-pill admin" style="margin-left:8px;">Superuser</span>' : ''}</td>
            <td>${escapeHtml(a.first_name || '—')}</td>
            <td>${escapeHtml(a.date_joined || '-')}</td>
            <td><span class="status-pill"><i></i>Aktif</span></td>
            <td style="text-align: right; white-space: nowrap;">
              ${actionHtml}
            </td>
          </tr>
        `;
      }).join('');
      refreshIcons();
    }
  } catch (err) {
    toast(err.message || 'Gagal memuat data admin', true);
  }
}

// 2. Fungsi Membuka Modal Edit Admin
window.openEditAdmin = function (id, username, firstName) {
  $('#editAdminId').value = id;
  $('#editAdminUser').value = username;
  $('#editAdminName').value = firstName;
  $('#editAdminPass').value = '';
  if ($('#editAdminError')) $('#editAdminError').textContent = '';
  modal('editAdminModal', true);
}

// 3. Submit Update Admin
$('#editAdminForm')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const id = $('#editAdminId').value;
  const btn = $('#updateAdminBtn');
  btn.disabled = true;
  btn.textContent = 'Menyimpan...';

  try {
    await api(`/api/admins/${id}`, {
      method: 'PUT',
      body: JSON.stringify({
        username: $('#editAdminUser').value,
        nama_lengkap: $('#editAdminName').value,
        password: $('#editAdminPass').value
      })
    });
    modal('editAdminModal', false);
    toast('Data admin berhasil diperbarui');
    loadAdmins();
  } catch (err) {
    if ($('#editAdminError')) $('#editAdminError').textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Simpan Perubahan';
  }
});

$('#btnNewAdmin')?.addEventListener('click', () => {
  const form = $('#addAdminForm');
  if (form) form.reset();
  if ($('#addAdminError')) $('#addAdminError').textContent = '';
  modal('addAdminModal', true);
});

$('#addAdminForm')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = $('#saveAdminBtn');
  btn.disabled = true;
  btn.textContent = 'Menyimpan...';
  try {
    await api('/api/admins', {
      method: 'POST',
      body: JSON.stringify({
        nama_lengkap: $('#newAdminName').value,
        username: $('#newAdminUser').value,
        password: $('#newAdminPass').value
      })
    });
    modal('addAdminModal', false);
    toast('Admin baru berhasil ditambahkan');
    loadAdmins();
  } catch (err) {
    if ($('#addAdminError')) $('#addAdminError').textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Simpan Admin';
  }
});

window.deleteAdmin = async function (id, username) {
  if (!confirm(`Hapus hak akses untuk admin ${username}?`)) return;
  try {
    await api(`/api/admins/${id}`, { method: 'DELETE' });
    toast('Admin berhasil dihapus');
    loadAdmins();
  } catch (err) { toast(err.message, true); }
}

// ==========================================
// LOGS MANAGEMENT (WITH PAGINATION)
// ==========================================
async function loadLogs() {
  const btn = $('#btnRefreshLogs');
  if (btn) btn.innerHTML = 'Memuat...';
  try {
    const res = await api('/api/logs');
    state.logs = res.logs || [];
    state.logCurrentPage = 1; // Reset ke halaman pertama saat refresh
    drawLogs();
  } catch (err) {
    toast(err.message, true);
  } finally {
    if (btn) btn.innerHTML = '<i data-lucide="refresh-ccw" style="width:14px; margin-right:4px;"></i> Muat Ulang';
    refreshIcons();
  }
}

function drawLogs() {
  const searchInput = $('#searchLogInput');
  const query = searchInput ? searchInput.value.trim().toLowerCase() : '';

  // 1. Filter Data
  let filtered = state.logs.filter(l => {
    return `${l.username} ${l.action}`.toLowerCase().includes(query);
  });

  // 2. Pagination Math
  const totalItems = filtered.length;
  const totalPages = Math.ceil(totalItems / state.logItemsPerPage) || 1;
  if (state.logCurrentPage > totalPages) state.logCurrentPage = totalPages;

  const startIdx = (state.logCurrentPage - 1) * state.logItemsPerPage;
  const endIdx = startIdx + state.logItemsPerPage;
  const paginated = filtered.slice(startIdx, endIdx);

  // 3. Update Text Info
  const startNum = totalItems === 0 ? 0 : startIdx + 1;
  const endNum = Math.min(endIdx, totalItems);
  if ($('#logTableFoot')) $('#logTableFoot').textContent = `Menampilkan ${startNum}-${endNum} dari ${totalItems} data log (Hal. ${state.logCurrentPage} dari ${totalPages})`;

  // 4. Render Rows
  const tbody = $('#logRows');
  if (tbody) {
    if (paginated.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4"><div class="empty-state"><div class="empty-icon"><i data-lucide="history"></i></div><strong>${query ? 'Log tidak ditemukan' : 'Belum ada log aktivitas'}</strong></div></td></tr>`;
    } else {
      tbody.innerHTML = paginated.map(l => `
        <tr>
          <td style="white-space:nowrap; color:#68a47b; font-weight:600;">${l.waktu}</td>
          <td><strong>${escapeHtml(l.username)}</strong></td>
          <td>${escapeHtml(l.ip)}</td>
          <td style="color:#516059;">${escapeHtml(l.action)}</td>
        </tr>
      `).join('');
    }
    refreshIcons();
  }

  // 5. Render Pagination Controls
  let pagesHtml = '';
  let startPage = Math.max(1, state.logCurrentPage - 2);
  let endPage = Math.min(totalPages, startPage + 4);
  if (endPage - startPage < 4) startPage = Math.max(1, endPage - 4);

  for (let i = startPage; i <= endPage; i++) {
    const activeClass = i === state.logCurrentPage ? 'active' : '';
    pagesHtml += `<div class="page-item ${activeClass}" onclick="changeLogPage(${i})">${i}</div>`;
  }

  const limitOptions = [10, 20, 30, 50, 100].map(val => `<option value="${val}" ${state.logItemsPerPage === val ? 'selected' : ''}>${val} / halaman</option>`).join('');

  if ($('#logPaginationControls')) {
    $('#logPaginationControls').innerHTML = `
      <div class="page-numbers">
        <div class="page-arrow ${state.logCurrentPage === 1 ? 'disabled' : ''}" onclick="if(${state.logCurrentPage} > 1) changeLogPage(${state.logCurrentPage - 1})">‹</div>
        ${pagesHtml}
        <div class="page-arrow ${state.logCurrentPage === totalPages || totalPages === 0 ? 'disabled' : ''}" onclick="if(${state.logCurrentPage} < ${totalPages}) changeLogPage(${state.logCurrentPage + 1})">›</div>
      </div>
      <select class="page-size-select" onchange="changeLogLimit(this.value)">${limitOptions}</select>
      <div class="page-jump">
        Ke <input type="number" class="page-jump-input" min="1" max="${totalPages}" onkeydown="if(event.key === 'Enter') jumpLogPage(this.value, ${totalPages})">
      </div>
    `;
  }
}

// Global functions untuk interaksi pagination log
window.changeLogPage = function (newPage) { state.logCurrentPage = newPage; drawLogs(); };
window.changeLogLimit = function (newLimit) { state.logItemsPerPage = Number(newLimit); state.logCurrentPage = 1; drawLogs(); };
window.jumpLogPage = function (val, maxPage) {
  let p = Number(val);
  if (p >= 1 && p <= maxPage) {
    state.logCurrentPage = p;
    drawLogs();
  }
};

// Listeners untuk fitur pencarian Log
$('#btnRefreshLogs')?.addEventListener('click', loadLogs);
$('#searchLogInput')?.addEventListener('input', () => { state.logCurrentPage = 1; drawLogs(); });

// ==========================================
// MACHINE MANAGEMENT
// ==========================================
function drawDevices() {
  if ($('#machineCount')) $('#machineCount').textContent = state.devices.length;
  const active = activeDevice();
  if ($('#activeName')) $('#activeName').textContent = active?.name || 'Belum ada mesin aktif';
  if ($('#activeAddress')) $('#activeAddress').textContent = active ? `${active.ip} · Port ${active.port}` : 'Tambahkan mesin untuk mulai mengelola data.';
  if ($('#statusText')) $('#statusText').textContent = active ? 'Terhubung' : 'Belum terhubung';
  if ($('#statusDot')) $('#statusDot').classList.toggle('connected', Boolean(active));
  if ($('#refreshUsers')) $('#refreshUsers').disabled = !active;

  const container = $('#deviceList');
  if (!container) return;

  if (!state.devices.length) {
    container.innerHTML = '<div class="empty-state" style="height:120px"><strong>Belum ada mesin tersimpan</strong><span>Tambahkan mesin untuk memulai.</span></div>';
    return;
  }

  let html = '';
  const connected = state.devices.filter(d => d.id === state.activeId);
  const disconnected = state.devices.filter(d => d.id !== state.activeId);

  const machineRow = (d, isActive) => `
    <div class="device-row">
      <button class="device-option${isActive ? ' active' : ''}" data-device="${d.id}">
        <span class="dev-icon"><i data-lucide="cpu" style="width: 20px;"></i></span>
        <span><strong>${escapeHtml(d.name)}</strong><small>${escapeHtml(d.ip)} · Port ${d.port}</small></span>
        ${isActive ? '<span class="chosen"><i data-lucide="check" style="width: 18px;"></i></span>' : ''}
      </button>
      <button class="edit-machine-btn" data-edit-machine="${d.id}" title="Edit konfigurasi mesin"><i data-lucide="pencil" style="width: 14px;"></i></button>
      <button class="delete-machine-btn" data-del-machine="${d.id}" title="Hapus Mesin"><i data-lucide="x" style="width: 18px;"></i></button>
    </div>
  `;

  if (connected.length > 0) {
    html += '<div class="device-section-label">TERHUBUNG</div>';
    html += connected.map(d => machineRow(d, true)).join('');
  }

  if (disconnected.length > 0) {
    html += '<div class="device-section-label">BELUM TERHUBUNG</div>';
    html += disconnected.map(d => machineRow(d, false)).join('');
  }

  container.innerHTML = html;
  refreshIcons();

  // Listener Connect
  document.querySelectorAll('[data-device]').forEach(button =>
    button.addEventListener('click', () => selectDevice(Number(button.dataset.device)))
  );

  // Listener Edit Mesin
  document.querySelectorAll('[data-edit-machine]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = Number(btn.dataset.editMachine);
      const device = state.devices.find(d => d.id === id);
      if (!device) return;
      openEditMachine(device);
    });
  });

  // Listener Hapus
  document.querySelectorAll('[data-del-machine]').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const id = Number(e.currentTarget.dataset.delMachine);
      if (confirm('Hapus mesin ini secara permanen?')) {
        try {
          await api(`/api/devices/${id}`, { method: 'DELETE' });
          if (state.activeId === id) {
            state.activeId = null;
            state.users = [];
          }
          await loadDevices();
          drawUsers();
          toast('Mesin berhasil dihapus.');
        } catch (err) { toast(err.message, true); }
      }
    });
  });
}

async function loadDevices(autoFetchUsers = false) {
  try {
    const data = await api('/api/devices');
    state.devices = data.devices;
    if (data.active_id !== null && data.active_id !== undefined) state.activeId = data.active_id;
    drawDevices();
    if (autoFetchUsers && state.activeId) await refreshUsers();
  } catch (error) { toast(error.message, true); }
}

async function selectDevice(id) {
  const button = document.querySelector(`[data-device="${id}"]`);
  if (button) {
    button.disabled = true;
    button.classList.add('connecting');
  }
  try {
    const data = await api(`/api/devices/${id}/connect`, { method: 'POST' });
    state.activeId = data.device.id;
    state.users = data.users;
    await loadDevices();
    drawUsers();
    fetchMachineTime();
    modal('devicePicker', false);
    toast(`${data.users.length} data karyawan berhasil dimuat.`);
  } catch (error) {
    drawDevices();
    toast(error.message, true);
  }
}

$('#switchMachine')?.addEventListener('click', () => { drawDevices(); modal('devicePicker'); });
$('#openMachines')?.addEventListener('click', () => { drawDevices(); modal('devicePicker'); });
$('#addMachineFromPicker')?.addEventListener('click', () => { modal('devicePicker', false); modal('machineModal'); });

// Modals Setup
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => modal(button.dataset.close, false)));
document.querySelectorAll('.modal-backdrop').forEach(backdrop => backdrop.addEventListener('click', event => { if (event.target === backdrop) modal(backdrop.id, false); }));
document.addEventListener('keydown', event => { if (event.key === 'Escape') document.querySelectorAll('.modal-backdrop.open').forEach(el => modal(el.id, false)); });

// Add Machine Form
$('#machineForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  const formElement = event.currentTarget;
  const button = $('#connectSubmit');
  button.disabled = true;
  button.textContent = 'Menghubungkan…';
  if ($('#machineError')) $('#machineError').textContent = '';

  const form = new FormData(formElement);
  const payload = Object.fromEntries(form.entries());
  payload.port = Number(payload.port);

  try {
    const data = await api('/api/devices', { method: 'POST', body: JSON.stringify(payload) });
    state.activeId = data.device.id;
    state.users = data.users;
    await loadDevices();
    drawUsers();
    fetchMachineTime();
    modal('machineModal', false);
    formElement?.reset();
    toast('Mesin terhubung dan konfigurasi tersimpan.');
  } catch (error) {
    if ($('#machineError')) $('#machineError').textContent = error.message;
  } finally {
    button.disabled = false;
    button.innerHTML = 'Hubungkan mesin <span>→</span>';
  }
});

// Edit Machine
function openEditMachine(device) {
  const form = document.getElementById('editMachineForm');
  if (!form) return;
  form.elements.machine_id.value = device.id;
  form.elements.name.value = device.name || '';
  form.elements.ip.value = device.ip || '';
  form.elements.port.value = device.port || 4370;
  form.elements.comm_key.value = '';
  if (document.getElementById('editMachineError')) document.getElementById('editMachineError').textContent = '';
  modal('devicePicker', false);
  modal('editMachineModal', true);
}

document.getElementById('editMachineSubmit')?.addEventListener('click', async () => {
  const form = document.getElementById('editMachineForm');
  const btn = document.getElementById('editMachineSubmit');
  const errEl = document.getElementById('editMachineError');
  if (errEl) errEl.textContent = '';

  const machineId = Number(form.elements.machine_id.value);
  const payload = {
    name: form.elements.name.value.trim(),
    ip: form.elements.ip.value.trim(),
    port: Number(form.elements.port.value),
    comm_key: form.elements.comm_key.value,
  };

  if (!payload.ip) { if (errEl) errEl.textContent = 'Alamat IP wajib diisi.'; return; }
  btn.disabled = true; btn.textContent = 'Menyimpan…';

  try {
    const data = await api(`/api/devices/${machineId}`, { method: 'PUT', body: JSON.stringify(payload) });
    const idx = state.devices.findIndex(d => d.id === machineId);
    if (idx !== -1) state.devices[idx] = data.device;
    modal('editMachineModal', false);
    drawDevices();
    toast(`Konfigurasi mesin berhasil disimpan.`);
  } catch (err) {
    if (errEl) errEl.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Simpan konfigurasi <span>→</span>';
  }
});
function closeEditMachine() { modal('editMachineModal', false); modal('devicePicker', true); drawDevices(); }
document.getElementById('editMachineCancel')?.addEventListener('click', closeEditMachine);
document.getElementById('editMachineClose')?.addEventListener('click', closeEditMachine);

// ==========================================
// USER MANAGEMENT
// ==========================================
function drawUsers() {
  const searchInput = $('#searchInput');
  if (!searchInput) return; // Guard clause

  const query = searchInput.value.trim().toLowerCase();

  // Filter
  let filtered = state.users.filter(user => {
    const id = user.user_id ?? user.id_mesin ?? '';
    return `${id} ${user.nama}`.toLowerCase().includes(query);
  });

  // Sort
  filtered.sort((a, b) => {
    let valA, valB;
    if (state.sortCol === 'id') {
      valA = Number(a.user_id ?? a.id_mesin ?? 0);
      valB = Number(b.user_id ?? b.id_mesin ?? 0);
    } else if (state.sortCol === 'nama') {
      valA = (a.nama || '').toLowerCase();
      valB = (b.nama || '').toLowerCase();
    } else if (state.sortCol === 'role') {
      valA = Number(b.kode_privilege ?? 0);
      valB = Number(a.kode_privilege ?? 0);
    } else if (state.sortCol === 'status') {
      valA = a.enabled ? 1 : 0;
      valB = b.enabled ? 1 : 0;
    }
    if (valA < valB) return state.sortDir === 'asc' ? -1 : 1;
    if (valA > valB) return state.sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  // Pagination
  const totalItems = filtered.length;
  const totalPages = Math.ceil(totalItems / state.itemsPerPage) || 1;
  if (state.currentPage > totalPages) state.currentPage = totalPages;

  const startIdx = (state.currentPage - 1) * state.itemsPerPage;
  const endIdx = startIdx + state.itemsPerPage;
  const paginated = filtered.slice(startIdx, endIdx);

  // Headers
  document.querySelectorAll('th.sortable').forEach(th => {
    th.classList.remove('asc', 'desc');
    const icon = th.querySelector('.sort-icon');
    if (icon) icon.textContent = '↕';
    if (th.dataset.sort === state.sortCol) {
      th.classList.add(state.sortDir);
      if (icon) icon.textContent = state.sortDir === 'asc' ? '↓' : '↑';
    }
  });

  const startNum = totalItems === 0 ? 0 : startIdx + 1;
  const endNum = Math.min(endIdx, totalItems);

  if ($('#tableFoot')) $('#tableFoot').textContent = `Menampilkan ${startNum}-${endNum} dari ${totalItems} data (Hal. ${state.currentPage} dari ${totalPages})`;
  if ($('#userCount')) $('#userCount').textContent = `${totalItems} karyawan`;

  // Render Rows
  const tbody = $('#userRows');
  if (tbody) {
    tbody.innerHTML = paginated.length ? paginated.map((user, index) => {
      const id = escapeHtml(user.user_id ?? user.id_mesin ?? '');
      const priv = Number(user.kode_privilege ?? 0);
      const roleName = escapeHtml(user.role || (priv === 3 ? 'Admin' : 'User'));
      const roleClass = priv > 0 ? 'admin' : '';
      const isChecked = state.selectedUsers.has(id) ? 'checked' : '';

      return `<tr>
        <td style="text-align: center;"><input type="checkbox" class="user-checkbox" data-pin="${id}" data-nama="${escapeHtml(user.nama || '—')}" ${isChecked}></td>
        <td>${id}</td>
        <td><strong>${escapeHtml(user.nama || '—')}</strong></td>
        <td><span class="role-pill ${roleClass}">${roleName}</span></td>
        <td><span class="status-pill ${user.enabled ? '' : 'off'}"><i></i>${user.enabled ? 'Aktif' : 'Nonaktif'}</span></td>
        <td>
          <div class="row-actions">
            <button class="edit-button" data-edit="${startIdx + index}"><i data-lucide="pencil" style="width:12px; margin-right:4px;"></i> Edit</button>
            <button class="delete-button" data-delete="${startIdx + index}">Hapus</button>
          </div>
        </td>
      </tr>`;
    }).join('') : `<tr><td colspan="6"><div class="empty-state"><div class="empty-icon"><i data-lucide="user-x"></i></div><strong>${query ? 'Data tidak ditemukan' : 'Belum ada data'}</strong></div></td></tr>`;

    refreshIcons();
  }

  // Render Controls
  let pagesHtml = '';
  let startPage = Math.max(1, state.currentPage - 2);
  let endPage = Math.min(totalPages, startPage + 4);
  if (endPage - startPage < 4) startPage = Math.max(1, endPage - 4);

  for (let i = startPage; i <= endPage; i++) {
    const activeClass = i === state.currentPage ? 'active' : '';
    pagesHtml += `<div class="page-item ${activeClass}" onclick="changePage(${i})">${i}</div>`;
  }
  const limitOptions = [10, 20, 50, 100, 200].map(val => `<option value="${val}" ${state.itemsPerPage === val ? 'selected' : ''}>${val} / halaman</option>`).join('');

  if ($('#paginationControls')) {
    $('#paginationControls').innerHTML = `
      <div class="page-numbers">
        <div class="page-arrow ${state.currentPage === 1 ? 'disabled' : ''}" onclick="if(${state.currentPage} > 1) changePage(${state.currentPage - 1})">‹</div>
        ${pagesHtml}
        <div class="page-arrow ${state.currentPage === totalPages || totalPages === 0 ? 'disabled' : ''}" onclick="if(${state.currentPage} < ${totalPages}) changePage(${state.currentPage + 1})">›</div>
      </div>
      <select class="page-size-select" onchange="changeLimit(this.value)">${limitOptions}</select>
      <div class="page-jump">
        Ke <input type="number" class="page-jump-input" min="1" max="${totalPages}" onkeydown="if(event.key === 'Enter') jumpPage(this.value, ${totalPages})">
      </div>
    `;
  }

  // Listeners
  document.querySelectorAll('[data-edit]').forEach(btn => btn.addEventListener('click', () => openEdit(filtered[Number(btn.dataset.edit)])));
  document.querySelectorAll('[data-delete]').forEach(btn => btn.addEventListener('click', () => deleteUser(filtered[Number(btn.dataset.delete)], btn)));
  document.querySelectorAll('.user-checkbox').forEach(cb => {
    cb.addEventListener('change', (e) => {
      if (e.target.checked) state.selectedUsers.set(e.target.dataset.pin, e.target.dataset.nama);
      else state.selectedUsers.delete(e.target.dataset.pin);
      updateBulkDeleteState();
    });
  });

  updateBulkDeleteState();
}

window.changePage = function (newPage) { state.currentPage = newPage; drawUsers(); };
window.changeLimit = function (newLimit) { state.itemsPerPage = Number(newLimit); state.currentPage = 1; drawUsers(); };
window.jumpPage = function (val, maxPage) {
  let p = Number(val);
  if (p >= 1 && p <= maxPage) { state.currentPage = p; drawUsers(); }
};

$('#searchInput')?.addEventListener('input', () => { state.currentPage = 1; drawUsers(); });
document.querySelectorAll('th.sortable').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.sort;
    if (state.sortCol === col) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    else { state.sortCol = col; state.sortDir = 'asc'; }
    state.currentPage = 1;
    drawUsers();
  });
});

async function refreshUsers() {
  if (!state.activeId) return;
  const btn = $('#refreshUsers');
  if (btn) btn.disabled = true;
  try {
    const data = await api(`/api/devices/${state.activeId}/users`);
    state.users = data.users;
    drawUsers();
    await fetchMachineTime();
    toast(`${data.users.length} karyawan dan waktu berhasil disinkronkan.`);
  }
  catch (error) { toast(error.message, true); }
  finally { if (btn) btn.disabled = !state.activeId; }
}
$('#refreshUsers')?.addEventListener('click', refreshUsers);

function openEdit(user) {
  const form = $('#editForm');
  if (!form) return;
  form.elements.pin.value = user.user_id ?? user.id_mesin ?? '';
  form.elements.nama.value = user.nama ?? '';
  form.elements.privilege.value = String(user.kode_privilege ?? 0);
  form.elements.enabled.checked = Boolean(user.enabled);
  if ($('#editError')) $('#editError').textContent = '';
  modal('editModal');
}

$('#editForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  if (!state.activeId) return toast('Pilih mesin aktif terlebih dahulu.', true);

  const form = event.currentTarget;
  const button = $('#updateSubmit');
  button.disabled = true; button.textContent = 'Menyimpan…';
  if ($('#editError')) $('#editError').textContent = '';

  const payload = {
    pin: form.elements.pin.value,
    nama: form.elements.nama.value,
    privilege: Number(form.elements.privilege.value),
    enabled: form.elements.enabled.checked
  };

  try {
    const data = await api(`/api/devices/${state.activeId}/users/${encodeURIComponent(payload.pin)}`, { method: 'PUT', body: JSON.stringify(payload) });
    state.users = data.users; drawUsers(); modal('editModal', false);
    toast(data.message || 'Data diperbarui.');
  } catch (error) {
    if ($('#editError')) $('#editError').textContent = error.message;
    if (error.users) { state.users = error.users; drawUsers(); }
  } finally {
    button.disabled = false; button.innerHTML = 'Simpan perubahan <span>→</span>';
  }
});

async function deleteUser(user, button) {
  const pin = String(user.user_id ?? user.id_mesin ?? '');
  if (!state.activeId || !window.confirm(`Hapus permanen "${user.nama || pin}" (ID ${pin}) dari mesin?`)) return;
  button.disabled = true;
  try {
    const data = await api(`/api/devices/${state.activeId}/users/${encodeURIComponent(pin)}`, { method: 'DELETE' });
    state.users = data.users; drawUsers(); toast(data.message || 'Berhasil dihapus.');
  } catch (error) {
    if (error.users) { state.users = error.users; drawUsers(); }
    toast(error.message, true);
  }
}

// ==========================================
// BULK DELETE
// ==========================================
$('#selectAll')?.addEventListener('change', (e) => {
  const isChecked = e.target.checked;
  document.querySelectorAll('.user-checkbox').forEach(cb => {
    cb.checked = isChecked;
    if (isChecked) state.selectedUsers.set(cb.dataset.pin, cb.dataset.nama);
    else state.selectedUsers.delete(cb.dataset.pin);
  });
  updateBulkDeleteState();
});

function updateBulkDeleteState() {
  const btnDel = $('#btnBulkDelete');
  const btnCancel = $('#btnDeselectAll');
  if (!btnDel) return;

  if (state.selectedUsers.size > 0) {
    btnDel.style.display = 'inline-flex';
    if (btnCancel) btnCancel.style.display = 'inline-flex';
    if ($('#selectedCount')) $('#selectedCount').textContent = state.selectedUsers.size;
  } else {
    btnDel.style.display = 'none';
    if (btnCancel) btnCancel.style.display = 'none';
  }

  const visibleCheckboxes = document.querySelectorAll('.user-checkbox');
  const allVisibleChecked = visibleCheckboxes.length > 0 && Array.from(visibleCheckboxes).every(cb => cb.checked);
  const selectAll = document.getElementById('selectAll');
  if (selectAll) selectAll.checked = allVisibleChecked;
}

$('#btnDeselectAll')?.addEventListener('click', () => {
  state.selectedUsers.clear();
  document.querySelectorAll('.user-checkbox').forEach(cb => cb.checked = false);
  const selectAll = document.getElementById('selectAll');
  if (selectAll) selectAll.checked = false;
  updateBulkDeleteState();
});

$('#btnBulkDelete')?.addEventListener('click', () => {
  const selectedForDelete = Array.from(state.selectedUsers.entries()).map(([pin, nama]) => ({ pin, nama }));
  if ($('#modalUserCount')) $('#modalUserCount').textContent = selectedForDelete.length;
  if ($('#deleteUserList')) $('#deleteUserList').innerHTML = selectedForDelete.map(u => `<li><strong>ID: ${u.pin}</strong> — ${u.nama}</li>`).join('');

  const confirmCheck = $('#confirmDeleteCheck');
  if (confirmCheck) confirmCheck.checked = false;

  const executeBtn = $('#executeBulkDelete');
  if (executeBtn) {
    executeBtn.disabled = true;
    executeBtn.style.opacity = '0.5';
    executeBtn.style.cursor = 'not-allowed';
  }
  if ($('#bulkDeleteError')) $('#bulkDeleteError').textContent = '';
  modal('bulkDeleteModal', true);
});

$('#confirmDeleteCheck')?.addEventListener('change', (e) => {
  const executeBtn = $('#executeBulkDelete');
  if (!executeBtn) return;
  if (e.target.checked) {
    executeBtn.disabled = false; executeBtn.style.opacity = '1'; executeBtn.style.cursor = 'pointer';
  } else {
    executeBtn.disabled = true; executeBtn.style.opacity = '0.5'; executeBtn.style.cursor = 'not-allowed';
  }
});

$('#executeBulkDelete')?.addEventListener('click', async () => {
  if (!state.activeId || state.selectedUsers.size === 0) return;
  const btn = $('#executeBulkDelete');
  btn.disabled = true; btn.textContent = 'Menghapus...';
  if ($('#bulkDeleteError')) $('#bulkDeleteError').textContent = '';

  try {
    const pins = Array.from(state.selectedUsers.keys());
    const data = await api(`/api/devices/${state.activeId}/users/batch-delete`, { method: 'POST', body: JSON.stringify({ pins: pins }) });
    state.users = data.users;
    state.selectedUsers.clear();
    drawUsers();
    modal('bulkDeleteModal', false);
    toast(data.message || `${pins.length} data berhasil dihapus.`);
  } catch (err) {
    if ($('#bulkDeleteError')) $('#bulkDeleteError').textContent = err.message;
    if (err.users) { state.users = err.users; drawUsers(); }
  } finally {
    btn.innerHTML = 'Hapus Sekarang <span>→</span>';
    btn.disabled = false;
  }
});

// ==========================================
// IMPORT EXCEL & NATIVE BROWSER DOWNLOAD
// ==========================================

// Helper murni browser tag (Tanpa fallback PyWebView)
async function downloadFile(url, defaultFilename) {
  toast('Menyiapkan file untuk diunduh...');
  const absoluteUrl = window.location.origin + url;

  const a = document.createElement('a');
  a.style.display = 'none';
  a.href = absoluteUrl;
  a.download = defaultFilename;

  document.body.appendChild(a);
  a.click();

  setTimeout(() => { a.remove(); }, 500);
}

// Sidebar Dropdown Toggle
const bulkEditToggle = document.getElementById('bulkEditToggle');
const bulkEditMenu = document.getElementById('bulkEditMenu');
const bulkEditArrow = document.getElementById('bulkEditArrow');

function closeBulkEditDropdown() {
  if (bulkEditMenu) { bulkEditMenu.classList.remove('open'); bulkEditMenu.setAttribute('aria-hidden', 'true'); }
  if (bulkEditToggle) bulkEditToggle.setAttribute('aria-expanded', 'false');
  if (bulkEditArrow) bulkEditArrow.classList.remove('open');
}

bulkEditToggle?.addEventListener('click', () => {
  if (bulkEditMenu.classList.contains('open')) closeBulkEditDropdown();
  else {
    bulkEditMenu.classList.add('open'); bulkEditMenu.setAttribute('aria-hidden', 'false');
    bulkEditToggle.setAttribute('aria-expanded', 'true'); bulkEditArrow.classList.add('open');
  }
});
document.addEventListener('click', (e) => {
  const dropdown = document.getElementById('bulkEditDropdown');
  if (dropdown && !dropdown.contains(e.target)) closeBulkEditDropdown();
});

// Unduh Excel (Users)
$('#exportExcelBtn')?.addEventListener('click', async () => {
  closeBulkEditDropdown();
  if (!state.activeId) return toast('Pilih mesin terlebih dahulu.', true);
  const device = activeDevice();
  const machineName = (device?.name || `Mesin_${state.activeId}`).trim().replace(/[\\/:*?"<>|]+/g, '_');
  await downloadFile(`/api/devices/${state.activeId}/export-excel`, `Data_Karyawan_${machineName}.xlsx`);
});

$('#downloadTemplateBtn')?.addEventListener('click', async () => {
  closeBulkEditDropdown();
  await downloadFile('/api/download-template', 'Template_Import_Karyawan.xlsx');
});

// Import Excel (Users)
let pendingImportUpdates = [];

$('#importExcelBtn')?.addEventListener('click', () => {
  closeBulkEditDropdown();
  if (!state.activeId) return toast('Pilih mesin terlebih dahulu.', true);
  $('#excelFileInput')?.click();
});

$('#excelFileInput')?.addEventListener('change', async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;

  toast('Membaca file Excel...');
  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`/api/devices/${state.activeId}/preview-excel`, { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Gagal membaca Excel.');

    const { summary, preview } = data;
    pendingImportUpdates = preview.filter(item => item.status === 'changed');

    const chipsEl = $('#importSummaryChips');
    if (chipsEl) {
      chipsEl.innerHTML = `
        <span class="summary-chip primary"><strong>${summary.total_rows}</strong> Baris Dibaca</span>
        <span class="summary-chip changed"><strong>${summary.changed_count}</strong> Diubah</span>
        <span class="summary-chip unchanged"><strong>${summary.unchanged_count}</strong> Sama</span>
        ${summary.not_found_count > 0 ? `<span class="summary-chip not-found"><strong>${summary.not_found_count}</strong> Tidak Ada</span>` : ''}
      `;
    }

    const tbody = $('#importPreviewRows');
    if (tbody) {
      if (!preview.length) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding: 24px;">Data kosong.</td></tr>';
      } else {
        tbody.innerHTML = preview.map(row => {
          let badge = '', cls = '';
          if (row.status === 'changed') { badge = '<span class="pill-badge changed">Diubah</span>'; cls = 'row-changed'; }
          else if (row.status === 'unchanged') { badge = '<span class="pill-badge unchanged">Sama</span>'; }
          else { badge = '<span class="pill-badge not-found">Tidak Ada</span>'; cls = 'row-not-found'; }

          return `<tr class="${cls}">
            <td><strong>${escapeHtml(row.pin)}</strong></td>
            <td>${escapeHtml(row.current_name)}</td>
            <td class="new-name-cell">${escapeHtml(row.new_name)}</td>
            <td style="text-align: right;">${badge}</td>
          </tr>`;
        }).join('');
      }
    }

    const confirmBtn = $('#confirmImportBtn');
    if (confirmBtn) {
      if (pendingImportUpdates.length === 0) {
        confirmBtn.disabled = true; confirmBtn.textContent = 'Tidak Ada Perubahan';
      } else {
        confirmBtn.disabled = false; confirmBtn.innerHTML = `Simpan (${pendingImportUpdates.length}) <span>→</span>`;
      }
    }
    modal('importModal', true);
  } catch (err) { toast(err.message, true); }
  event.target.value = '';
});

$('#confirmImportBtn')?.addEventListener('click', async () => {
  if (!state.activeId || !pendingImportUpdates.length) return;
  const btn = $('#confirmImportBtn');
  btn.disabled = true; btn.textContent = 'Menyimpan...';

  try {
    const payload = pendingImportUpdates.map(u => ({ pin: u.pin, nama: u.new_name, privilege: u.privilege, enabled: u.enabled }));
    const data = await api(`/api/devices/${state.activeId}/users/batch`, { method: 'POST', body: JSON.stringify({ updates: payload }) });
    state.users = data.users; drawUsers(); modal('importModal', false);
    toast(data.message || `Berhasil memperbarui.`);
  } catch (err) { toast(err.message, true); }
  finally { btn.disabled = false; btn.innerHTML = 'Simpan <span>→</span>'; }
});

// ==========================================
// TOGGLE PASSWORD (MANUAL PER INPUT)
// ==========================================
function setupPasswordToggle(btnSelector, inputSelector) {
  const btn = $(btnSelector);
  const input = $(inputSelector);
  if (!btn || !input) return;
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    const isPass = input.type === 'password';
    input.type = isPass ? 'text' : 'password';
    const eyeOpen = btn.querySelector('.eye-open');
    const eyeClosed = btn.querySelector('.eye-closed');
    if (eyeOpen) eyeOpen.style.display = isPass ? 'none' : 'inline';
    if (eyeClosed) eyeClosed.style.display = isPass ? 'inline' : 'none';
  });
}

// ==========================================
// PENGATURAN WAKTU MESIN (REAL-TIME & SYNC)
// ==========================================
function startMachineTimer(timeString) {
  if (state.machineTimeInterval) clearInterval(state.machineTimeInterval);

  // Parsing string "YYYY-MM-DD HH:MM:SS" (Abaikan timezone agar tidak bergeser)
  const [datePart, timePart] = timeString.split(' ');
  const [year, month, day] = datePart.split('-');
  const [hours, minutes, seconds] = timePart.split(':');

  state.machineTimeDate = new Date(year, month - 1, day, hours, minutes, seconds);

  const displayTime = $('#machineTimeDisplay');
  const displayDate = $('#machineDateDisplay');

  state.machineTimeInterval = setInterval(() => {
    state.machineTimeDate.setSeconds(state.machineTimeDate.getSeconds() + 1);

    if (displayTime && displayDate) {
      const h = String(state.machineTimeDate.getHours()).padStart(2, '0');
      const m = String(state.machineTimeDate.getMinutes()).padStart(2, '0');
      const s = String(state.machineTimeDate.getSeconds()).padStart(2, '0');
      const y = state.machineTimeDate.getFullYear();
      const mo = String(state.machineTimeDate.getMonth() + 1).padStart(2, '0');
      const d = String(state.machineTimeDate.getDate()).padStart(2, '0');

      displayTime.textContent = `${h}:${m}:${s}`;
      displayDate.textContent = `${y}/${mo}/${d}`;
    }
  }, 1000);
}

async function fetchMachineTime() {
  if (!state.activeId) return;
  try {
    const res = await api(`/api/devices/${state.activeId}/time`);
    if (res.time_str) {
      $('#timeWidget').style.display = 'block';
      startMachineTimer(res.time_str);
    }
  } catch (err) {
    console.error("Gagal mengambil waktu:", err.message);
    $('#timeWidget').style.display = 'none';
  }
}

// Buka Modal Waktu
$('#btnOpenTimeSync')?.addEventListener('click', () => {
  if (!state.machineTimeDate) return;
  // Set default form ke waktu mesin saat ini
  const y = state.machineTimeDate.getFullYear();
  const m = String(state.machineTimeDate.getMonth() + 1).padStart(2, '0');
  const d = String(state.machineTimeDate.getDate()).padStart(2, '0');
  const h = String(state.machineTimeDate.getHours()).padStart(2, '0');
  const min = String(state.machineTimeDate.getMinutes()).padStart(2, '0');
  const s = String(state.machineTimeDate.getSeconds()).padStart(2, '0');

  $('#manualDate').value = `${y}-${m}-${d}`;
  $('#manualTime').value = `${h}:${min}:${s}`;
  if ($('#timeSyncError')) $('#timeSyncError').textContent = '';
  modal('timeSyncModal', true);
});

// Sinkronisasi dengan Jam Komputer Admin (Browser)
$('#btnSyncComputer')?.addEventListener('click', async (e) => {
  if (!state.activeId) return;
  const btn = e.currentTarget;
  const originalText = btn.innerHTML;
  btn.disabled = true; btn.textContent = 'Menyinkronkan...';

  try {
    // Tarik waktu seketika dari browser komputer admin yang sedang buka web
    const now = new Date();
    const payload = {
      mode: 'client_computer',
      tahun: now.getFullYear(),
      bulan: now.getMonth() + 1,
      hari: now.getDate(),
      jam: now.getHours(),
      menit: now.getMinutes(),
      detik: now.getSeconds()
    };

    const res = await api(`/api/devices/${state.activeId}/time`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });

    modal('timeSyncModal', false);
    toast(res.message);
    if (res.new_time) startMachineTimer(res.new_time);
  } catch (err) {
    if ($('#timeSyncError')) $('#timeSyncError').textContent = err.message;
  } finally {
    btn.disabled = false; btn.innerHTML = originalText;
  }
});

// Sinkronisasi Manual
$('#manualTimeForm')?.addEventListener('submit', async (e) => {
  e.preventDefault(); // Mencegah reload halaman

  if (!state.activeId) return;
  const btn = $('#btnSyncManual');
  btn.disabled = true; btn.textContent = 'Menyimpan...';

  try {
    const dateVal = $('#manualDate').value;
    const timeVal = $('#manualTime').value;
    const [thn, bln, hr] = dateVal.split('-');
    const [jm, mnt, dtk] = (timeVal.length === 5 ? timeVal + ':00' : timeVal).split(':');

    const payload = {
      mode: 'manual',
      tahun: parseInt(thn), bulan: parseInt(bln), hari: parseInt(hr),
      jam: parseInt(jm), menit: parseInt(mnt), detik: parseInt(dtk)
    };

    const res = await api(`/api/devices/${state.activeId}/time`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });

    modal('timeSyncModal', false);
    toast(res.message);
    if (res.new_time) startMachineTimer(res.new_time);
  } catch (err) {
    if ($('#timeSyncError')) $('#timeSyncError').textContent = err.message;
  } finally {
    btn.disabled = false; btn.innerHTML = 'Simpan Waktu <span>→</span>';
  }
});

// Inisialisasi manual per input password
setupPasswordToggle('#toggleNewAdminPass', '#newAdminPass');
setupPasswordToggle('#toggleEditAdminPass', '#editAdminPass');
setupPasswordToggle('#toggleMachineCommKey', '#machineCommKey');
setupPasswordToggle('#toggleEditMachineCommKey', '#editMachineCommKey');

// Start the App
loadDevices(true);