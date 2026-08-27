const API = '/api/v1'

export async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })
  let data = null
  const text = await res.text()
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!res.ok) {
    const detail = data?.detail
    const msg = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map((d) => d.msg || d).join(', ')
        : res.statusText
    const err = new Error(msg || 'Request failed')
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

export const authApi = {
  login: (body) => api('/auth/session/login', { method: 'POST', body: JSON.stringify(body) }),
  mfa: (body) => api('/auth/session/mfa', { method: 'POST', body: JSON.stringify(body) }),
  mfaSetupStart: () => api('/auth/session/mfa-setup'),
  mfaSetupComplete: (body) => api('/auth/session/mfa-setup', { method: 'POST', body: JSON.stringify(body) }),
  logout: () => api('/auth/session/logout', { method: 'POST' }),
  me: () => api('/auth/me'),
  bootstrap: () => api('/bootstrap'),
}

export const jobsApi = {
  vms: () => api('/vms'),
  progress: () => api('/jobs/progress'),
  run: (id) => api(`/vms/${id}/run`, { method: 'POST' }),
  stop: (id) => api(`/vms/${id}/stop`, { method: 'POST' }),
  patch: (id, body) => api(`/vms/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  pauseAll: () => api('/jobs/pause', { method: 'POST' }),
  resumeAll: () => api('/jobs/resume', { method: 'POST' }),
  scheduler: () => api('/jobs/scheduler'),
  inventoryApply: (body) => api('/inventory/apply', { method: 'POST', body: JSON.stringify(body) }),
}

export const hostsApi = {
  list: () => api('/hosts'),
  create: (body) => api('/hosts', { method: 'POST', body: JSON.stringify(body) }),
  remove: (id) => api(`/hosts/${id}`, { method: 'DELETE' }),
  sync: (id) => api(`/hosts/${id}/sync-vms`, { method: 'POST' }),
  datastores: (id) => api(`/hosts/${id}/datastores`),
}

export const configApi = {
  get: () => api('/config'),
  update: (body) => api('/config', { method: 'PUT', body: JSON.stringify(body) }),
  updateStorage: (body) => api('/config/storage', { method: 'PUT', body: JSON.stringify(body) }),
  testStorage: () => api('/config/storage/test', { method: 'POST' }),
  testEmail: () => api('/config/email/test', { method: 'POST' }),
}

export const restoreApi = {
  list: () => api('/restores'),
  create: (body) => api('/restores', { method: 'POST', body: JSON.stringify(body) }),
  stop: (id) => api(`/restores/${id}/stop`, { method: 'POST' }),
  remove: (id) => api(`/restores/${id}`, { method: 'DELETE' }),
  backups: () => api('/backups'),
  chain: (name) => api(`/backups/chain/${encodeURIComponent(name)}`),
}

export const k8sApi = {
  list: () => api('/k8s/clusters'),
  create: (body) => api('/k8s/clusters', { method: 'POST', body: JSON.stringify(body) }),
  patch: (id, body) => api(`/k8s/clusters/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  remove: (id) => api(`/k8s/clusters/${id}`, { method: 'DELETE' }),
  run: (id) => api(`/k8s/clusters/${id}/run`, { method: 'POST' }),
  runTarget: (id, name) => api(`/k8s/clusters/${id}/run?target=${encodeURIComponent(name)}`, { method: 'POST' }),
  patchTarget: (id, name, body) => api(`/k8s/clusters/${id}/targets/${encodeURIComponent(name)}`, { method: 'PATCH', body: JSON.stringify(body) }),
  test: (id) => api(`/k8s/clusters/${id}/test`, { method: 'POST' }),
  backups: (id) => api(`/k8s/clusters/${id}/backups`),
  tenants: (id) => api(`/k8s/clusters/${id}/tenants`),
  k3sStatus: (id) => api(`/k8s/clusters/${id}/k3s-status`),
  k3sApplyS3: (id, body) => api(`/k8s/clusters/${id}/k3s-s3`, { method: 'POST', body: JSON.stringify(body) }),
  k3sApplyS3FromSecondary: (id) => api(`/k8s/clusters/${id}/k3s-s3/from-secondary`, { method: 'POST' }),
}

export const overviewApi = {
  get: () => api('/overview'),
}

export const usersApi = {
  list: () => api('/users'),
  create: (body) => api('/users', { method: 'POST', body: JSON.stringify(body) }),
  remove: (id) => api(`/users/${id}`, { method: 'DELETE' }),
  role: (id, body) => api(`/users/${id}/role`, { method: 'PATCH', body: JSON.stringify(body) }),
  resetPassword: (id) => api(`/users/${id}/reset-password`, { method: 'POST' }),
  resetMfa: (id) => api(`/users/${id}/reset-mfa`, { method: 'POST' }),
}

export const profileApi = {
  update: (body) => api('/profile', { method: 'PATCH', body: JSON.stringify(body) }),
}

export const keysApi = {
  list: () => api('/auth/api-keys'),
  create: (body) => api('/auth/api-keys', { method: 'POST', body: JSON.stringify(body) }),
  revoke: (id) => api(`/auth/api-keys/${id}`, { method: 'DELETE' }),
}

export const logsApi = {
  system: (params) => {
    const q = new URLSearchParams(params).toString()
    return api(`/logs/system?${q}`)
  },
  backup: (limit = 50) => api(`/logs/backup?limit=${limit}`),
}
