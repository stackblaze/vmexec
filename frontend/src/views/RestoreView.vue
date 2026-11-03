<template>
  <div class="space-y-5">
    <div>
      <h1 class="text-2xl font-bold">Restore</h1>
      <p class="text-sm text-muted mt-1">Pick a VM, then a restore point. It is restored as a new VM, powered off, next to the original.</p>
    </div>

    <div v-if="scanError" class="px-4 py-3 rounded-lg border border-red-500/40 bg-red-500/10 text-sm text-red-700 dark:text-red-300" role="alert">{{ scanError }}</div>

    <div class="flex flex-wrap gap-5 items-start">
      <!-- VMs with backups -->
      <section aria-label="VMs with backups" class="flex-[1_1_18rem] min-w-0 rounded-lg border border-border bg-card shadow-card">
        <div class="px-4 py-3 border-b border-border">
          <label>
            <span class="sr-only">Search VMs</span>
            <input v-model="searchQuery" type="search" :placeholder="`Search ${groupedBackups.length} VMs with backups…`" class="w-full px-3 py-2 text-sm" />
          </label>
        </div>
        <div class="max-h-[32rem] overflow-y-auto divide-y divide-border">
          <p v-if="scanLoading" class="px-4 py-6 text-sm text-muted m-0">Reading backups…</p>
          <button
            v-for="g in filteredGroups"
            :key="g.vm_name"
            type="button"
            class="w-full text-left flex items-center gap-3 px-4 py-3 border-0 cursor-pointer"
            :class="selectedGroup?.vm_name === g.vm_name ? 'bg-brand/10' : 'bg-transparent hover:bg-blue-500/[0.04]'"
            :aria-pressed="selectedGroup?.vm_name === g.vm_name"
            @click="selectVm(g)"
          >
            <span class="flex-1 min-w-0">
              <span class="block text-sm font-semibold truncate">{{ g.vm_name }}</span>
              <span class="block text-xs text-muted">{{ g.versions.length }} restore point{{ g.versions.length === 1 ? '' : 's' }} · latest {{ g.versions[0]?.date }}</span>
            </span>
            <svg class="w-4 h-4 text-muted shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" /></svg>
          </button>
          <p v-if="!scanLoading && !filteredGroups.length" class="px-4 py-6 text-sm text-muted m-0">
            {{ groupedBackups.length ? 'No VMs match.' : 'No backups yet.' }}
          </p>
        </div>
      </section>

      <!-- Points + restore form -->
      <section aria-label="Restore points" class="flex-[2_1_28rem] min-w-0 rounded-lg border border-border bg-card shadow-card">
        <div v-if="!selectedGroup" class="px-6 py-12 text-center text-sm text-muted">Pick a VM on the left.</div>
        <template v-else>
          <div class="px-5 py-4 border-b border-border">
            <h2 class="text-base font-semibold m-0">{{ selectedGroup.vm_name }}</h2>
            <p class="text-xs text-muted mt-0.5 mb-0">Newest first. Any point can be restored; incrementals are rebuilt from their full automatically.</p>
          </div>
          <fieldset class="border-0 m-0 p-0">
            <legend class="sr-only">Restore point</legend>
            <div class="max-h-[18rem] overflow-y-auto divide-y divide-border">
              <label
                v-for="(v, idx) in selectedGroup.versions"
                :key="v.path"
                class="flex items-center gap-3 px-5 py-3 cursor-pointer"
                :class="selectedVersion?.path === v.path ? 'bg-brand/10' : 'hover:bg-blue-500/[0.04]'"
              >
                <input type="radio" name="restore-point" class="accent-brand" :checked="selectedVersion?.path === v.path" @change="selectVersion(v, idx)" />
                <span class="flex-1 text-sm">{{ v.date }}<span v-if="idx === 0" class="ml-2 text-xs text-muted">latest</span></span>
                <span class="text-[0.6875rem] font-semibold px-2 py-0.5 rounded-full" :class="pointBadgeClass(v)">{{ pointTypeLabel(v) }}</span>
                <span class="w-28 text-right text-xs text-muted" title="Size of the virtual disk. S3 stores only the data in it, compressed; see Settings → Storage.">{{ v.size }} disk size</span>
              </label>
            </div>
          </fieldset>

          <form class="px-5 py-4 border-t border-border space-y-4" @submit.prevent="submitRestore">
            <h3 class="text-sm font-semibold m-0">Restore as a new VM</h3>
            <div class="grid gap-4 grid-cols-[repeat(auto-fit,minmax(14rem,1fr))] text-sm">
              <label class="block">
                New VM name
                <input v-model="form.target_name" required class="mt-1 w-full py-2 px-3 text-sm" autocomplete="off" />
              </label>
              <label class="block">
                Datastore
                <select v-model="form.datastore" required class="mt-1 w-full py-2 px-3 text-sm" :disabled="!datastores.length">
                  <option v-if="!datastores.length" value="" disabled>Loading datastores…</option>
                  <option v-for="ds in datastores" :key="dsName(ds)" :value="dsName(ds)">{{ dsLabel(ds) }}</option>
                </select>
              </label>
              <label v-if="hosts.length > 1" class="block">
                vCenter
                <select v-model="form.target_esxi_id" required class="mt-1 w-full py-2 px-3 text-sm" @change="loadDatastores">
                  <option v-for="h in hosts" :key="h.id" :value="h.id">{{ h.name }}</option>
                </select>
              </label>
            </div>
            <p class="text-xs text-amber-700 dark:text-amber-400 m-0">
              The new VM is registered powered off. If {{ selectedGroup.vm_name }} is still running, disconnect the copy's network adapter before powering it on: it has the same IP addresses.
            </p>
            <p v-if="error" class="text-sm text-red-600 dark:text-red-400 m-0" role="alert">{{ error }}</p>
            <button type="submit" :class="btnPrimary" class="px-4 py-2 text-sm font-semibold" :disabled="!canDeploy || busy">
              {{ busy ? 'Starting…' : 'Start restore' }}
            </button>
          </form>
        </template>
      </section>
    </div>

    <section aria-labelledby="recent-h" class="space-y-2">
      <h2 id="recent-h" class="text-base font-semibold m-0">Recent restores</h2>
    <div class="rounded-lg border border-border bg-card shadow-card overflow-x-auto">
      <table class="w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav">Target VM</th>
            <th class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav">Host</th>
            <th class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav">Progress</th>
            <th class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav">Started</th>
            <th class="text-right text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in restores" :key="r.id">
            <td class="px-4 py-3 border-b border-border align-middle font-semibold">{{ r.target_name }}</td>
            <td class="px-4 py-3 border-b border-border align-middle text-xs">{{ r.target_esxi_host }}</td>
            <td class="px-4 py-3 border-b border-border align-middle min-w-[140px]">
              <button
                v-if="r.status === 'In Progress' || r.status === 'Success' || r.status === 'Failed'"
                type="button"
                class="w-full text-left rounded-md cursor-pointer transition-shadow border-0 bg-transparent p-0"
                :class="r.status === 'Failed' ? 'hover:ring-2 hover:ring-red-500/25' : 'hover:ring-2 hover:ring-blue-500/25'"
                title="View restore details"
                @click="openRestoreDrawer(r)"
              >
                <div v-if="r.status === 'In Progress'">
                  <div class="flex justify-between text-xs mb-1">
                    <span class="truncate max-w-[120px] text-brand">{{ r.current_action || 'Restoring…' }}</span>
                    <span class="font-mono">{{ r.progress }}%</span>
                  </div>
                  <div class="block h-1 mt-1 bg-border rounded-sm overflow-hidden">
                    <div class="h-full bg-brand rounded-sm transition-[width] duration-500 ease-in-out" :style="{ width: r.progress + '%' }"></div>
                  </div>
                </div>
                <StatusBadge v-else v-bind="restoreProgress(r)" />
              </button>
              <span v-else class="text-xs text-muted">—</span>
            </td>
            <td class="px-4 py-3 border-b border-border align-middle text-xs font-mono text-muted">
              <span>{{ formatDate(r.start_time) }}</span>
              <span v-if="r.duration_seconds != null" class="block text-[0.7rem] opacity-70">took {{ formatDuration(r.duration_seconds) }}</span>
            </td>
            <td class="text-right px-4 py-3 border-b border-border align-middle">
              <div class="inline-flex gap-1 items-center justify-end">
                <button
                  v-if="r.status === 'In Progress'"
                  type="button"
                  :class="btnIconDanger"
                  title="Stop restore"
                  @click="stop(r.id)"
                >
                  <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6h12v12H6z"/></svg>
                </button>
                <button type="button" :class="btnIconSecondary" class="hover:text-red-500" title="Remove from list" @click="remove(r.id)">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="!restores.length">
            <td colspan="5" class="py-8 text-center text-muted">
              <div class="text-sm">No restores yet</div>

            </td>
          </tr>
        </tbody>
      </table>
    </div>

    </section>

    <div v-if="detailRestore" class="fixed inset-0 z-80">
      <div class="absolute inset-0 bg-black/45 backdrop-blur-[1px]" @click="closeRestoreDrawer"></div>
      <aside
        class="absolute top-0 right-0 bottom-0 w-full max-w-md flex flex-col bg-card border-l border-border shadow-[-4px_0_24px_rgba(0,0,0,0.18)]"
        role="dialog"
        aria-labelledby="restore-detail-title"
      >
        <div class="flex items-center justify-between gap-3 px-4 pt-4 pb-3 border-b border-border bg-nav shrink-0">
          <div class="min-w-0">
            <h3 id="restore-detail-title" class="text-base font-semibold leading-tight m-0 truncate">{{ restoreDrawerTitle }}</h3>
            <p class="text-sm font-mono text-brand mt-0.5 truncate">{{ detailRestore.target_name }}</p>
          </div>
          <button
            type="button"
            class="shrink-0 p-1.5 rounded-md text-muted border border-border bg-transparent cursor-pointer hover:text-main hover:bg-card"
            aria-label="Close"
            @click="closeRestoreDrawer"
          >
            <svg class="w-4 h-4 block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>

        <div class="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-4">
          <div class="grid grid-cols-2 gap-3 text-xs">
            <div>
              <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Host</span>
              <span class="font-mono text-brand">{{ detailRestore.target_esxi_host || '—' }}</span>
            </div>
            <div>
              <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Datastore</span>
              <span class="font-mono text-muted">{{ detailRestore.datastore || '—' }}</span>
            </div>
            <div>
              <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Started</span>
              <span class="font-mono text-muted">{{ formatDate(detailRestore.start_time) }}</span>
            </div>
            <div v-if="detailRestore.end_time">
              <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Finished</span>
              <span class="font-mono text-muted">{{ formatDate(detailRestore.end_time) }}</span>
            </div>
            <div v-if="detailRestore.duration_seconds != null">
              <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Duration</span>
              <span class="font-mono text-muted">{{ formatDuration(detailRestore.duration_seconds) }}</span>
            </div>
            <div class="col-span-2">
              <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Source backup</span>
              <span class="font-mono text-muted break-all">{{ detailRestore.source_path || '—' }}</span>
            </div>
          </div>

          <div v-if="detailRestore.status === 'In Progress'">
            <span class="block text-xs font-semibold uppercase tracking-wide text-muted mb-2">Progress</span>
            <div class="rounded-lg border border-blue-500/25 bg-blue-500/8 p-4">
              <div class="flex items-center justify-between gap-2 mb-2">
                <StatusBadge cls="status-running" label="Running" />
                <span class="text-lg font-bold font-mono text-brand tabular-nums">{{ detailRestore.progress }}%</span>
              </div>
              <div class="h-2 rounded-sm bg-border overflow-hidden mb-2">
                <div class="h-full bg-brand rounded-sm transition-[width] duration-500 ease-in-out" :style="{ width: detailRestore.progress + '%' }"></div>
              </div>
              <p class="text-sm text-main m-0">{{ detailRestore.current_action || 'Restoring…' }}</p>
            </div>
          </div>

          <div v-else-if="detailRestore.status === 'Failed'">
            <span class="block text-xs font-semibold uppercase tracking-wide text-muted mb-2">Error</span>
            <pre class="text-xs leading-relaxed whitespace-pre-wrap break-words font-mono p-3 rounded-lg border border-red-500/25 bg-red-500/8 text-red-400 m-0">{{ detailRestore.error_message || 'No error message recorded.' }}</pre>
          </div>
        </div>

        <div class="flex items-center justify-end gap-2 px-4 py-3.5 border-t border-border bg-nav shrink-0">
          <button type="button" :class="btnSecondary" class="px-3 py-1.5 text-xs font-medium" @click="closeRestoreDrawer">Close</button>
          <button
            v-if="detailRestore.status === 'In Progress'"
            type="button"
            :class="btnDanger"
            class="px-3 py-1.5 text-xs font-semibold"
            @click="stopFromDrawer"
          >Stop restore</button>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { restoreApi, hostsApi } from '@/api/client'
import { formatDate, formatDuration, statusBadge } from '@/composables/useJobProgress'
import { useModal } from '@/composables/useModal'
import StatusBadge from '@/components/StatusBadge.vue'

const btnPrimary =
  'inline-flex items-center justify-center rounded-md border-0 bg-brand text-white hover:bg-brand-hover transition-colors duration-200 disabled:opacity-55'
const btnSecondary =
  'inline-flex items-center justify-center rounded-md border border-btn-sec-border bg-btn-sec text-btn-sec-text hover:bg-btn-sec-hover transition-colors duration-200'
const btnDanger =
  'inline-flex items-center justify-center rounded-md border-0 bg-red-600 text-white hover:bg-red-700 transition-colors duration-200'
const btnIcon =
  'inline-flex items-center justify-center w-8 h-8 rounded-md transition-colors duration-200 disabled:opacity-55 disabled:cursor-not-allowed shrink-0'
const btnIconDanger = `${btnIcon} border-0 bg-red-600 text-white hover:bg-red-700`
const btnIconSecondary = `${btnIcon} border border-btn-sec-border bg-btn-sec text-btn-sec-text hover:bg-btn-sec-hover`

const pointBadgeStyles = {
  full: 'bg-blue-500/15 text-blue-700 dark:text-blue-300',
  incremental: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  'synthetic-full': 'bg-violet-500/15 text-violet-700 dark:text-violet-300',
  legacy: 'bg-gray-500/15 text-muted',
}

const { confirm } = useModal()

const restores = ref([])
const detailRestore = ref(null)
const hosts = ref([])
const groupedBackups = ref([])
const datastores = ref([])
const scanLoading = ref(false)
const scanError = ref('')
const searchQuery = ref('')
const selectedGroup = ref(null)
const selectedVersion = ref(null)
const error = ref('')
const busy = ref(false)
const form = ref({ source_ova: '', target_esxi_id: null, datastore: '', target_name: '' })
let timer = null

const filteredGroups = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return groupedBackups.value
  return groupedBackups.value.filter((g) => g.vm_name.toLowerCase().includes(q))
})

const restoreDrawerTitle = computed(() => {
  if (!detailRestore.value) return 'Restore details'
  if (detailRestore.value.status === 'In Progress') return 'Restore in progress'
  if (detailRestore.value.status === 'Failed') return 'Restore failed'
  if (detailRestore.value.status === 'Success') return 'Restore succeeded'
  return 'Restore details'
})

const canDeploy = computed(() =>
  Boolean(selectedVersion.value?.path && form.value.target_esxi_id && form.value.datastore && form.value.target_name.trim())
)

function restoreProgress(r) {
  const b = statusBadge(r.status, r.status === 'In Progress')
  return { cls: b.cls, label: b.label }
}

function openRestoreDrawer(r) { detailRestore.value = r }
function closeRestoreDrawer() { detailRestore.value = null }

async function stopFromDrawer() {
  if (!detailRestore.value) return
  await stop(detailRestore.value.id)
  closeRestoreDrawer()
}

function pointKey(version) {
  const pt = version.point_type || (version.backup_type === 'legacy' ? 'legacy' : 'full')
  return pt.replace('_', '-')
}

function pointTypeLabel(version) {
  return { full: 'Full', incremental: 'Incremental', 'synthetic-full': 'Full (merged)', legacy: 'Legacy full' }[pointKey(version)] || 'Full'
}

function pointBadgeClass(version) {
  return pointBadgeStyles[pointKey(version)] || pointBadgeStyles.full
}

function dsName(ds) {
  return typeof ds === 'string' ? ds : ds.name
}

function dsLabel(ds) {
  if (typeof ds === 'string') return ds
  return ds.free_gb != null ? `${ds.name} (${ds.free_gb} GB free)` : ds.name
}

function stamp() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`
}

async function scanRepository() {
  scanLoading.value = true
  scanError.value = ''
  try {
    // newest first: point folders are named by timestamp (YYYYMMDD-HHMMSS)
    groupedBackups.value = (await restoreApi.backups()).map((g) => ({
      ...g,
      versions: [...(g.versions || [])].sort((a, b) => b.path.localeCompare(a.path)),
    }))
  } catch (e) {
    groupedBackups.value = []
    scanError.value = e.message || 'Could not read the backups.'
  } finally {
    scanLoading.value = false
  }
}

function selectVm(group) {
  selectedGroup.value = group
  form.value.target_name = `${group.vm_name}-restored-${stamp()}`
  error.value = ''
  if (group.versions?.length) selectVersion(group.versions[0])
  else selectedVersion.value = null
}

function selectVersion(version) {
  selectedVersion.value = version
  form.value.source_ova = version.path
}

async function load() {
  const [r, h] = await Promise.all([restoreApi.list(), hostsApi.list()])
  restores.value = r
  if (detailRestore.value) {
    const updated = r.find((job) => job.id === detailRestore.value.id)
    detailRestore.value = updated || null
  }
  hosts.value = h
  if (h.length && !form.value.target_esxi_id) {
    form.value.target_esxi_id = h[0].id
    await loadDatastores()
  }
}

async function loadDatastores() {
  if (!form.value.target_esxi_id) return
  try {
    const ds = await hostsApi.datastores(form.value.target_esxi_id)
    datastores.value = Array.isArray(ds) ? ds : ds.datastores || []
    form.value.datastore = datastores.value.length ? dsName(datastores.value[0]) : ''
  } catch {
    datastores.value = []
    form.value.datastore = ''
  }
}

async function submitRestore() {
  if (!canDeploy.value) return
  const name = form.value.target_name.trim()
  const ok = await confirm(
    `Restore ${selectedGroup.value.vm_name} (${selectedVersion.value.date}) as a new VM named ${name} on ${form.value.datastore}? It is created powered off.`,
    { title: 'Start restore', confirmText: 'Start restore' },
  )
  if (!ok) return
  error.value = ''
  busy.value = true
  try {
    await restoreApi.create({
      target_esxi_id: form.value.target_esxi_id,
      source_ova: form.value.source_ova,
      target_name: name,
      datastore: form.value.datastore,
    })
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function stop(id) { await restoreApi.stop(id); await load() }
async function remove(id) { await restoreApi.remove(id); await load() }

onMounted(() => {
  load()
  scanRepository()
  timer = setInterval(load, 3000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>
