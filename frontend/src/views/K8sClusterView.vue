<template>
  <div class="max-w-7xl mx-auto px-4 py-6">
    <!-- header -->
    <div class="flex items-center justify-between mb-4">
      <div class="min-w-0">
        <button type="button" class="text-xs text-muted hover:text-brand mb-1" @click="$router.push('/kubernetes')">← Clusters</button>
        <h1 class="text-xl font-bold truncate">{{ cluster ? cluster.name : 'Cluster' }}</h1>
        <p v-if="cluster" class="text-xs text-muted mt-0.5">
          {{ (cluster.targets || []).length }} snapshot job(s) ·
          last run {{ cluster.last_backup ? formatDate(cluster.last_backup) : '—' }} ·
          <span :class="cluster.last_status === 'Success' ? 'text-emerald-500' : (cluster.last_status === 'Failed' ? 'text-red-500' : 'text-muted')">{{ cluster.last_status }}</span>
        </p>
      </div>
      <div v-if="cluster" class="flex items-center gap-2 shrink-0">
        <button type="button" :class="btnPrimary" class="px-3 py-1.5 text-sm" @click="openJobModal">Add job</button>
      </div>
    </div>

    <div v-if="!cluster" class="text-sm text-muted py-12 text-center">Loading…</div>

    <!-- jobs table -->
    <div v-else class="rounded-lg border border-border bg-card shadow-card overflow-x-auto">
      <table class="w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th v-for="h in ['Job', 'Type', 'Schedule', 'Status', 'Actions']" :key="h"
                class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav whitespace-nowrap">{{ h }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!(cluster.targets || []).length">
            <td colspan="5" class="px-4 py-8 text-center text-muted text-xs">No jobs yet. Add one with “Add job”.</td>
          </tr>
          <tr v-for="t in cluster.targets" :key="t.name" class="hover:bg-nav/50">
            <td class="px-4 py-3 border-b border-border font-mono text-xs align-middle">
              <button type="button" class="text-brand hover:underline" @click="showBackups(t)">{{ t.name }}</button>
            </td>
            <td class="px-4 py-3 border-b border-border text-xs text-muted align-middle">{{ t.profile || 'custom' }}<span v-if="t.tenant" class="text-brand"> · {{ t.tenant }}</span></td>
            <td class="px-4 py-3 border-b border-border text-xs whitespace-nowrap align-middle">
              <span v-if="t.is_job_active === false" class="text-amber-500">paused</span>
              <span v-else>{{ targetSchedLabel(t) }}</span>
            </td>
            <td class="px-4 py-3 border-b border-border text-xs align-middle">
              <span :class="cluster.last_status === 'Success' ? 'text-emerald-500' : (cluster.last_status === 'Failed' ? 'text-red-500' : 'text-muted')">{{ cluster.last_status }}</span>
            </td>
            <td class="px-4 py-3 border-b border-border whitespace-nowrap align-middle">
              <div class="flex items-center justify-end" data-job-menu>
                <button type="button" :class="btnIconSecondary" title="Job menu" @click="toggleJobMenu(t, $event)">⋯</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Job menu (teleported to escape table overflow clipping) -->
    <Teleport to="body">
      <div v-if="jobMenu" data-job-menu class="fixed z-[90] w-48 rounded-md border border-border bg-card shadow-lg py-1"
           :style="{ top: jobMenu.y + 'px', left: jobMenu.x + 'px' }">
        <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-xs text-left hover:bg-nav" @click="jobAction(showBackups, jobMenu.t)"><span class="w-4 text-center">☰</span> Snapshots</button>
        <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-xs text-left hover:bg-nav" @click="jobAction(runTarget, jobMenu.t)"><span class="w-4 text-center">▶</span> Snapshot now</button>
        <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-xs text-left hover:bg-nav" @click="jobAction(startRenameJob, jobMenu.t)"><span class="w-4 text-center">✎</span> Rename job</button>
        <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-xs text-left hover:bg-nav" @click="jobAction(openSchedule, jobMenu.t)"><span class="w-4 text-center">🕑</span> Schedule &amp; retention</button>
        <div class="my-1 border-t border-border"></div>
        <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-xs text-left text-red-500 hover:bg-red-500/8" @click="jobAction(removeTarget, jobMenu.t)"><span class="w-4 text-center">✕</span> Remove job</button>
      </div>
    </Teleport>

    <!-- Schedule drawer -->
    <div v-if="sched" class="fixed inset-0 z-80">
      <div class="absolute inset-0 bg-black/45 backdrop-blur-[1px]" @click="sched = null"></div>
      <aside class="absolute top-0 right-0 bottom-0 w-full max-w-md flex flex-col bg-card border-l border-border shadow-[-4px_0_24px_rgba(0,0,0,0.18)]">
        <div class="flex items-center justify-between gap-3 px-4 pt-4 pb-3 border-b border-border bg-nav shrink-0">
          <div class="min-w-0">
            <h3 class="text-base font-semibold leading-tight m-0 truncate">Schedule &amp; retention</h3>
            <p class="text-sm font-mono text-brand mt-0.5 truncate">{{ sched.target }}</p>
          </div>
          <button type="button" class="shrink-0 p-1.5 rounded-md text-muted border border-border bg-transparent hover:text-main hover:bg-card" @click="sched = null">✕</button>
        </div>
        <div class="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-4 text-xs">
          <div>
            <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Frequency</span>
            <select v-model="sched.schedule_frequency" class="w-full py-1.5 px-2">
              <option value="interval">Every N hours</option>
              <option value="daily">Daily</option>
            </select>
          </div>
          <div v-if="sched.schedule_frequency === 'interval'">
            <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Every</span>
            <select v-model.number="sched.interval_hours" class="w-full py-1.5 px-2">
              <option :value="1">1 hour</option><option :value="2">2 hours</option><option :value="3">3 hours</option><option :value="6">6 hours</option><option :value="12">12 hours</option>
            </select>
          </div>
          <div class="grid grid-cols-3 gap-2">
            <div><span class="block font-semibold uppercase tracking-wide text-muted mb-1">Anchor</span><input v-model.number="sched.schedule_hour" type="number" min="0" max="23" class="w-full py-1.5 px-2 text-center font-mono" /></div>
            <div><span class="block font-semibold uppercase tracking-wide text-muted mb-1">Minute</span><input v-model.number="sched.schedule_minute" type="number" min="0" max="59" class="w-full py-1.5 px-2 text-center font-mono" /></div>
            <div><span class="block font-semibold uppercase tracking-wide text-muted mb-1">Keep</span><input v-model.number="sched.retention_count" type="number" min="1" max="336" class="w-full py-1.5 px-2 text-center font-mono" /></div>
          </div>
          <label class="flex items-center gap-2 cursor-pointer">
            <input v-model="sched.is_job_active" type="checkbox" />
            <span :class="sched.is_job_active ? 'text-emerald-600' : 'text-muted'">{{ sched.is_job_active ? 'Active — runs on schedule' : 'Paused' }}</span>
          </label>
          <button type="button" :class="btnPrimary" class="w-full px-3 py-2 font-semibold" :disabled="savingSched" @click="saveSchedule">{{ savingSched ? 'Saving…' : 'Save schedule' }}</button>
        </div>
      </aside>
    </div>

    <!-- Snapshots drawer -->
    <div v-if="detail" class="fixed inset-0 z-80">
      <div class="absolute inset-0 bg-black/45 backdrop-blur-[1px]" @click="detail = null"></div>
      <aside class="absolute top-0 right-0 bottom-0 w-full max-w-md flex flex-col bg-card border-l border-border shadow-[-4px_0_24px_rgba(0,0,0,0.18)]">
        <div class="flex items-center justify-between gap-3 px-4 pt-4 pb-3 border-b border-border bg-nav shrink-0">
          <div class="min-w-0">
            <h3 class="text-base font-semibold leading-tight m-0 truncate">Snapshots</h3>
            <p class="text-sm font-mono text-brand mt-0.5 truncate">{{ detail.cluster }} / {{ detail.jobName }}</p>
          </div>
          <button type="button" class="shrink-0 p-1.5 rounded-md text-muted border border-border bg-transparent hover:text-main hover:bg-card" @click="detail = null">✕</button>
        </div>
        <div class="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-4">
          <div v-for="tg in detail.targets" :key="tg.target">
            <span class="block text-xs font-semibold uppercase tracking-wide text-muted mb-2">{{ tg.target }} · {{ tg.points.length }} point(s)</span>
            <div class="rounded-lg border border-border overflow-hidden">
              <div v-for="p in [...tg.points].reverse().slice(0, 12)" :key="p.id" class="flex items-center gap-3 px-3 py-1.5 text-xs font-mono border-b border-border last:border-b-0">
                <span class="text-muted">{{ p.id }}</span>
                <span class="ml-auto tabular-nums">{{ p.size_bytes ? (p.size_bytes / 1048576).toFixed(1) + ' MB' : '?' }}</span>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>

    <!-- Rename job modal -->
    <div v-if="renamingJob" class="fixed inset-0 z-40 flex items-center justify-center bg-black/50">
      <div class="w-full max-w-sm rounded-lg border border-border bg-card p-5 shadow-xl">
        <h2 class="text-base font-semibold mb-3">Rename job</h2>
        <input v-model="renameJobValue" type="text" class="w-full py-2 px-3 text-sm font-mono mb-4" @keyup.enter="saveRenameJob" />
        <div class="flex justify-end gap-2">
          <button type="button" :class="btnSecondary" class="px-3 py-1.5 text-sm" @click="renamingJob = null">Cancel</button>
          <button type="button" :class="btnPrimary" class="px-3 py-1.5 text-sm" :disabled="savingRenameJob" @click="saveRenameJob">{{ savingRenameJob ? 'Saving…' : 'Rename' }}</button>
        </div>
      </div>
    </div>

    <!-- Rename modal -->
    <div v-if="renaming" class="fixed inset-0 z-40 flex items-center justify-center bg-black/50">
      <div class="w-full max-w-sm rounded-lg border border-border bg-card p-5 shadow-xl">
        <h2 class="text-base font-semibold mb-3">Rename cluster</h2>
        <input v-model="renameValue" type="text" class="w-full py-2 px-3 text-sm mb-4" @keyup.enter="saveRename" />
        <div class="flex justify-end gap-2">
          <button type="button" :class="btnSecondary" class="px-3 py-1.5 text-sm" @click="renaming = false">Cancel</button>
          <button type="button" :class="btnPrimary" class="px-3 py-1.5 text-sm" :disabled="savingRename" @click="saveRename">{{ savingRename ? 'Saving…' : 'Rename' }}</button>
        </div>
      </div>
    </div>

    <!-- Create job modal -->
    <div v-if="jobModal" class="fixed inset-0 z-40 flex items-center justify-center bg-black/50">
      <div class="w-full max-w-2xl rounded-lg border border-border bg-card p-6 shadow-xl">
        <h2 class="text-base font-semibold mb-1">Create snapshot job</h2>
        <p class="text-xs text-muted mb-4">On cluster <span class="font-mono text-brand">{{ cluster.name }}</span></p>
        <div class="grid grid-cols-2 gap-3 mb-3">
          <div><span class="block text-xs font-semibold uppercase text-muted mb-1">Job name</span><input v-model="jobForm.name" type="text" placeholder="tenant-datastore" class="w-full py-1.5 px-3 text-sm font-mono" /></div>
          <div>
            <span class="block text-xs font-semibold uppercase text-muted mb-1">Type</span>
            <select v-model="jobForm.profile" class="w-full py-1.5 px-3 text-sm" @change="onProfileChange">
              <option value="kamaji">kamaji-etcd (datastore snapshot)</option>
              <option value="k3s">k3s etcd (host snapshot)</option>
              <option value="tenant">tenant (single tenant export)</option>
              <option value="tenants">tenants (all, one chain each)</option>
              <option value="kubeadm">kubeadm etcd</option>
              <option value="custom">custom</option>
            </select>
          </div>
        </div>
        <div v-if="jobForm.profile === 'tenant'" class="mb-3">
          <span class="block text-xs font-semibold uppercase text-muted mb-1">Tenant</span>
          <select v-model="jobForm.tenant" class="w-full py-1.5 px-3 text-sm">
            <option value="" disabled>{{ tenantList === null ? 'Loading…' : (tenantList.length ? 'Select a tenant' : 'No tenants discovered') }}</option>
            <option v-for="tn in tenantList || []" :key="tn" :value="tn">{{ tn }}</option>
          </select>
          <p class="text-[0.7rem] text-muted mt-1">One job per tenant — its own chain, schedule and retention.</p>
        </div>
        <div v-if="!['tenants','tenant','k3s'].includes(jobForm.profile)" class="grid grid-cols-2 gap-3 mb-3">
          <div><span class="block text-xs font-semibold uppercase text-muted mb-1">Namespace <span class="normal-case text-muted/70">(optional)</span></span><input v-model="jobForm.namespace" type="text" placeholder="profile default" class="w-full py-1.5 px-3 text-sm font-mono" /></div>
          <div><span class="block text-xs font-semibold uppercase text-muted mb-1">Label selector <span class="normal-case text-muted/70">(optional)</span></span><input v-model="jobForm.selector" type="text" placeholder="profile default" class="w-full py-1.5 px-3 text-sm font-mono" /></div>
        </div>
        <div class="grid grid-cols-4 gap-3 mb-4">
          <div>
            <span class="block text-xs font-semibold uppercase text-muted mb-1">Frequency</span>
            <select v-model="jobForm.schedule_frequency" class="w-full py-1.5 px-2 text-sm"><option value="interval">Every N h</option><option value="daily">Daily</option></select>
          </div>
          <div v-if="jobForm.schedule_frequency === 'interval'">
            <span class="block text-xs font-semibold uppercase text-muted mb-1">Every</span>
            <select v-model.number="jobForm.interval_hours" class="w-full py-1.5 px-2 text-sm"><option :value="1">1 h</option><option :value="2">2 h</option><option :value="3">3 h</option><option :value="6">6 h</option><option :value="12">12 h</option></select>
          </div>
          <div><span class="block text-xs font-semibold uppercase text-muted mb-1">Anchor</span><input v-model.number="jobForm.schedule_hour" type="number" min="0" max="23" class="w-full py-1.5 px-2 text-center text-sm font-mono" /></div>
          <div><span class="block text-xs font-semibold uppercase text-muted mb-1">Keep</span><input v-model.number="jobForm.retention_count" type="number" min="1" max="336" class="w-full py-1.5 px-2 text-center text-sm font-mono" /></div>
        </div>
        <div class="flex justify-end gap-2">
          <button type="button" :class="btnSecondary" class="px-3 py-1.5 text-sm" @click="jobModal = false">Cancel</button>
          <button type="button" :class="btnPrimary" class="px-3 py-1.5 text-sm" :disabled="savingJob" @click="createJob">{{ savingJob ? 'Saving…' : 'Create job' }}</button>
        </div>
      </div>
    </div>

    <!-- k3s drawer (compact) -->
    <div v-if="openK3s" class="fixed inset-0 z-80">
      <div class="absolute inset-0 bg-black/45 backdrop-blur-[1px]" @click="openK3s = false"></div>
      <aside class="absolute top-0 right-0 bottom-0 w-full max-w-md flex flex-col bg-card border-l border-border shadow-[-4px_0_24px_rgba(0,0,0,0.18)]">
        <div class="flex items-center justify-between gap-3 px-4 pt-4 pb-3 border-b border-border bg-nav shrink-0">
          <h3 class="text-base font-semibold">Management etcd (k3s) S3</h3>
          <button type="button" class="shrink-0 p-1.5 rounded-md text-muted border border-border bg-transparent hover:text-main hover:bg-card" @click="openK3s = false">✕</button>
        </div>
        <div class="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-3 text-xs">
          <div v-if="!k3sStatus" class="text-muted">Loading…</div>
          <template v-else>
            <div v-if="!k3sStatus.nodes.length" class="text-muted">No k3s embedded-etcd nodes detected.</div>
            <template v-else>
              <div class="rounded-lg border border-emerald-500/25 bg-emerald-500/8 p-3">The management etcd is already backed up by its snapshot job. This enables k3s's own S3 upload as belt-and-braces.</div>
              <div v-for="n in k3sStatus.nodes" :key="n.name" class="font-mono">{{ n.name }} · {{ n.last_local_snapshot || 'none' }}</div>
              <div>S3 secret: <strong :class="k3sStatus.secret_present ? 'text-emerald-500' : 'text-amber-500'">{{ k3sStatus.secret_present ? 'configured' : 'not configured' }}</strong></div>
              <button type="button" :class="btnPrimary" class="w-full px-3 py-2 font-semibold" :disabled="k3sApplying" @click="applyK3sFromSecondary">{{ k3sApplying ? 'Applying…' : 'Configure from secondary-copy credentials' }}</button>
              <div v-if="k3sFragment">
                <p class="text-muted mb-1">Secret {{ k3sSecretAction }}. Apply on each etcd node as <code>/etc/rancher/k3s/config.yaml.d/etcd-s3.yaml</code>, then restart k3s one node at a time:</p>
                <pre class="text-[0.65rem] font-mono p-2 rounded border border-border bg-nav overflow-x-auto">{{ k3sFragment }}</pre>
              </div>
            </template>
          </template>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { k8sApi } from '@/api/client'
import { useModal } from '@/composables/useModal'

const props = defineProps({ id: { type: String, required: true } })
const { confirm, alert } = useModal()
import { useRouter } from 'vue-router'
const router = useRouter()
const menuOpen = ref(false)
const jobMenu = ref(null)  // { t, x, y }
function toggleJobMenu(t, ev) {
  if (jobMenu.value && jobMenu.value.t.name === t.name) { jobMenu.value = null; return }
  const rect = ev.currentTarget.getBoundingClientRect()
  const width = 192
  const x = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))
  jobMenu.value = { t, x, y: rect.bottom + 4 }
}
function jobAction(fn, t) { jobMenu.value = null; fn(t) }
function onDocClick(e) {
  if (!e.target.closest('[data-cluster-menu]')) menuOpen.value = false
  if (!e.target.closest('[data-job-menu]')) jobMenu.value = null
}

async function removeCluster() {
  const ok = await confirm(`Remove cluster ${cluster.value.name}? Stored snapshots stay on disk.`, { title: 'Remove cluster', confirmText: 'Remove' })
  if (!ok) return
  await k8sApi.remove(cid)
  router.push('/kubernetes')
}

const renaming = ref(false)
const renameValue = ref('')
const savingRename = ref(false)
function startRename() {
  renameValue.value = cluster.value.name
  renaming.value = true
}
async function saveRename() {
  const name = renameValue.value.trim()
  if (!name || name === cluster.value.name) { renaming.value = false; return }
  savingRename.value = true
  try {
    await k8sApi.patch(cid, { name })
    renaming.value = false
    await load()
  } catch (e) {
    await alert(String(e.message || e), { title: 'Rename failed' })
  } finally {
    savingRename.value = false
  }
}

const btnPrimary = 'inline-flex items-center justify-center rounded-md border-0 bg-brand text-white hover:bg-brand-hover transition-colors duration-200 disabled:opacity-55'
const btnSecondary = 'inline-flex items-center justify-center rounded-md border border-btn-sec-border bg-btn-sec text-btn-sec-text hover:bg-btn-sec-hover transition-colors duration-200'
const btnIconSecondary = 'inline-flex items-center justify-center w-8 h-8 rounded-md transition-colors duration-200 disabled:opacity-55 shrink-0 border border-btn-sec-border bg-btn-sec text-btn-sec-text hover:bg-btn-sec-hover'

const cid = Number(props.id)
const cluster = ref(null)
let timer = null

async function load() {
  const all = await k8sApi.list()
  cluster.value = all.find((c) => c.id === cid) || null
}

function formatDate(iso) { return iso ? iso.replace('T', ' ').slice(0, 19) : '—' }

function targetSchedLabel(t) {
  const c = cluster.value
  const freq = t.schedule_frequency || c.schedule_frequency || 'interval'
  const h = t.schedule_hour ?? c.schedule_hour
  const m = t.schedule_minute ?? c.schedule_minute
  const keep = t.retention_count || c.retention_count
  const iv = t.interval_hours || c.interval_hours || 1
  return `${freq === 'interval' ? `every ${iv}h` : 'daily'} ${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')} · keep ${keep}`
}

async function runTarget(t) { await k8sApi.runTarget(cid, t.name); await load() }

const renamingJob = ref(null)
const renameJobValue = ref('')
const savingRenameJob = ref(false)
function startRenameJob(t) { renamingJob.value = t; renameJobValue.value = t.name }
async function saveRenameJob() {
  const name = renameJobValue.value.trim()
  if (!name || name === renamingJob.value.name) { renamingJob.value = null; return }
  savingRenameJob.value = true
  try {
    await k8sApi.patchTarget(cid, renamingJob.value.name, { name })
    renamingJob.value = null
    await load()
  } catch (e) {
    await alert(String(e.message || e), { title: 'Rename failed' })
  } finally {
    savingRenameJob.value = false
  }
}

async function removeTarget(t) {
  const ok = await confirm(`Remove job "${t.name}"? Stored snapshots stay on disk.`, { title: 'Remove job', confirmText: 'Remove' })
  if (!ok) return
  const targets = (cluster.value.targets || []).filter((x) => x.name !== t.name)
  await k8sApi.patch(cid, { targets }); await load()
}

async function testCluster() {
  try {
    const r = await k8sApi.test(cid)
    const lines = r.results.map((x) => x.ok ? `✓ ${x.target}: ${x.pod}` : `✗ ${x.target}: ${x.error}`)
    await alert(lines.join('\n') || 'No jobs configured.', { title: 'Connectivity' })
  } catch (e) { await alert(String(e.message || e), { title: 'Connectivity' }) }
}

// schedule drawer
const sched = ref(null)
const savingSched = ref(false)
function openSchedule(t) {
  const c = cluster.value
  sched.value = {
    target: t.name,
    schedule_frequency: t.schedule_frequency || c.schedule_frequency || 'interval',
    interval_hours: t.interval_hours || c.interval_hours || 1,
    schedule_hour: t.schedule_hour ?? c.schedule_hour,
    schedule_minute: t.schedule_minute ?? c.schedule_minute,
    retention_count: t.retention_count || c.retention_count,
    is_job_active: t.is_job_active !== false,
  }
}
async function saveSchedule() {
  savingSched.value = true
  try {
    await k8sApi.patchTarget(cid, sched.value.target, {
      schedule_frequency: sched.value.schedule_frequency, interval_hours: sched.value.interval_hours,
      schedule_hour: sched.value.schedule_hour, schedule_minute: sched.value.schedule_minute,
      retention_count: sched.value.retention_count, is_job_active: sched.value.is_job_active,
    })
    sched.value = null; await load()
  } catch (e) { await alert(String(e.message || e), { title: 'Save failed' }) } finally { savingSched.value = false }
}

// snapshots drawer — scoped to the clicked job
const detail = ref(null)
async function showBackups(t) {
  const all = await k8sApi.backups(cid)
  // backups() returns per-target rows; the tenants profile yields one
  // "tenant: X" row per tenant, so match those by prefix.
  const isTenants = t.profile === 'tenants'
  const match = all.targets.filter((x) => isTenants ? x.target.startsWith('tenant:') : x.target === t.name)
  detail.value = { cluster: all.cluster, jobName: t.name, targets: match }
}

// create job
const jobModal = ref(false)
const savingJob = ref(false)
const jobForm = reactive({ name: '', profile: 'kamaji', tenant: '', namespace: '', selector: '', schedule_frequency: 'interval', interval_hours: 1, schedule_hour: 0, retention_count: 48 })
const tenantList = ref(null)
function openJobModal() {
  jobModal.value = true
  tenantList.value = null
  Object.assign(jobForm, { name: '', profile: 'kamaji', tenant: '', namespace: '', selector: '', schedule_frequency: 'interval', interval_hours: 1, schedule_hour: 0, retention_count: 48 })
}
async function onProfileChange() {
  if ((jobForm.profile === 'tenant' || jobForm.profile === 'tenants') && tenantList.value === null) {
    try { tenantList.value = (await k8sApi.tenants(cid)).tenants } catch { tenantList.value = [] }
  }
}
// auto-name a single-tenant job after the tenant unless the user typed one
watch(() => jobForm.tenant, (tn) => {
  if (jobForm.profile === 'tenant' && tn && (!jobForm.name || jobForm.name.startsWith('tenant-'))) {
    jobForm.name = `tenant-${tn}`
  }
})
async function createJob() {
  if (jobForm.profile === 'tenant' && !jobForm.tenant) { await alert('Select a tenant.', { title: 'Missing tenant' }); return }
  if (!jobForm.name.trim()) { await alert('A job name is required.', { title: 'Missing name' }); return }
  if ((cluster.value.targets || []).some((t) => t.name === jobForm.name.trim())) { await alert('A job with that name already exists.', { title: 'Duplicate' }); return }
  savingJob.value = true
  try {
    const target = { name: jobForm.name.trim(), profile: jobForm.profile, schedule_frequency: jobForm.schedule_frequency, interval_hours: jobForm.interval_hours, schedule_hour: jobForm.schedule_hour, schedule_minute: 0, retention_count: jobForm.retention_count, is_job_active: true }
    if (jobForm.profile === 'tenant') target.tenant = jobForm.tenant
    if (jobForm.namespace) target.namespace = jobForm.namespace
    if (jobForm.selector) target.selector = jobForm.selector
    await k8sApi.patch(cid, { targets: [...(cluster.value.targets || []), target] })
    jobModal.value = false; await load()
  } catch (e) { await alert(String(e.message || e), { title: 'Create job failed' }) } finally { savingJob.value = false }
}

// k3s
const openK3s = ref(false)
const k3sStatus = ref(null)
const k3sApplying = ref(false)
const k3sFragment = ref(null)
const k3sSecretAction = ref('')
watch(openK3s, async (v) => {
  if (v) { k3sStatus.value = null; k3sFragment.value = null; try { k3sStatus.value = await k8sApi.k3sStatus(cid) } catch (e) { await alert(String(e.message || e), { title: 'k3s status' }); openK3s.value = false } }
})
async function applyK3sFromSecondary() {
  k3sApplying.value = true
  try {
    const r = await k8sApi.k3sApplyS3FromSecondary(cid)
    k3sFragment.value = r.config_fragment; k3sSecretAction.value = r.secret
    k3sStatus.value = await k8sApi.k3sStatus(cid)
  } catch (e) { await alert(String(e.message || e), { title: 'Apply failed' }) } finally { k3sApplying.value = false }
}

import { useRoute } from 'vue-router'
const route = useRoute()
onMounted(() => {
  load(); timer = setInterval(load, 10000); document.addEventListener('click', onDocClick)
  if (route.query.k3s) openK3s.value = true
})
onUnmounted(() => { clearInterval(timer); document.removeEventListener('click', onDocClick) })
</script>
