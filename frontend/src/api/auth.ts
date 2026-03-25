export async function getAuthStatus() {
  const res = await fetch('/api/auth/status', { credentials: 'same-origin' });
  return res.json();
}

export async function login(username: string, password: string) {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const data = await res.json();
    throw new Error(data.detail || 'Erreur de connexion');
  }
  return res.json();
}

export async function setupAdmin(username: string, password: string) {
  const res = await fetch('/api/auth/setup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const data = await res.json();
    throw new Error(data.detail || 'Erreur');
  }
  return res.json();
}

export async function logout() {
  await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
}

export async function getUsers() {
  const res = await fetch('/api/admin/users', { credentials: 'same-origin' });
  return res.json();
}

export async function createUser(username: string, password: string, role: string) {
  const res = await fetch('/api/admin/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ username, password, role }),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

export async function deleteUser(id: string) {
  const res = await fetch(`/api/admin/users/${id}`, { method: 'DELETE', credentials: 'same-origin' });
  if (!res.ok && res.status !== 204) throw new Error((await res.json()).detail);
}

export async function resetPassword(id: string, password: string) {
  const res = await fetch(`/api/admin/users/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ password }),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
}
