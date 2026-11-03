<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold">Backup</h1>
        <p class="text-sm text-muted mt-1">{{ protectedCount }} of {{ allVms.length }} VMs protected</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button type="button" :class="btnSecondary" class="px-3 py-2 text-sm" :disabled="refreshing || !auth.isOperator" @click="refreshVms">
          {{ refreshing ? 'Refreshing…' : 'Refresh VM list' }}
        </button>
        <button v-if="auth.isOperator" type="button" :class="btnPrimary" class="px-4 py-2 text-sm font-semibold" @click="openWizard">Protect VMs</button>
      </div>
    </div>

    <div
      v-if="paused"
      class="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 border border-amber-500/35 rounded-lg bg-amber-500/10 text-amber-700 dark:text-amber-400"
    >
      <span class="text-sm">All scheduled backups are paused</span>
      <button type="button" :class="btnSecondary" class="px-3 py-1 text-xs" @click="togglePause(false)">Resume all</button>
    </div>

    <BackupStatus :refresh-key="statusKey" @show-failed="filter = 'failed'" />

    <section aria-label="Backup policies" class="grid gap-4 grid-cols-[repeat(auto-fit,minmax(15rem,1fr))]">
      <button
        v-for="p in policies"
        :key="p.id"
        type="button"
        class="text-left rounded-lg border bg-card px-5 py-4 cursor-pointer transition-colors"
        :class="filter === 'policy:' + p.id ? 'border-brand ring-2 ring-brand/20' : 'border-border hover:border-brand/50'"
        :aria-pressed="filter === 'policy:' + p.id"
        @click="filter = filter === 'policy:' + p.id ? 'all' : 'policy:' + p.id"
      >
        <span class="flex justify-between items-baseline gap-2">
          <span class="text-[0.9375rem] font-semibold">{{ p.name }}</span>
          <span class="text-xs text-muted">{{ p.vm_count }} VM{{ p.vm_count === 1 ? '' : 's' }}</span>
        </span>
        <span class="block text-xs text-muted mt-1">{{ p.summary }}</span>
      </button>
      <RouterLink
        to="/settings/policies"
        class="flex items-center justify-center min-h-[4.5rem] rounded-lg border border-dashed border-border text-sm font-medium text-brand no-underline hover:border-brand/50"
      >+ New policy</RouterLink>
    </section>

    <section aria-label="Virtual machines" class="rounded-lg border border-border bg-card shadow-card">
      <div class="flex flex-wrap items-center gap-3 px-4 py-3 border-b border-border">
        <label class="flex-1 min-w-[14rem]">
          <span class="sr-only">Search VMs</span>
          <input v-model="search" type="search" placeholder="Search VMs…" class="w-full px-3 py-2 text-sm" />
        </label>
        <div role="group" aria-label="Filter" class="inline-flex rounded-md border border-border overflow-hidden text-xs">
          <button
            v-for="f in filters"
            :key="f.id"
            type="button"
            class="px-3 py-2 border-0 border-l first:border-l-0 border-solid border-border cursor-pointer"
            :class="filter === f.id ? 'bg-brand/10 text-main font-semibold' : 'bg-card text-muted hover:text-main'"
            :aria-pressed="filter === f.id"
            @click="filter = f.id"
          >{{ f.label }} {{ f.count }}</button>
        </div>
      </div>

      <div
        v-if="selectedIds.size"
        class="flex flex-wrap items-center gap-3 px-4 py-2.5 border-b border-border bg-nav"
      >
        <span class="text-sm font-medium">{{ selectedIds.size }} selected</span>
        <button type="button" :class="btnPrimary" class="px-3 py-1.5 text-xs font-medium" @click="runSelected">Run now</button>
        <button type="button" :class="btnDanger" class="px-3 py-1.5 text-xs font-medium" @click="abortSelected">Stop</button>
        <button type="button" :class="btnSecondary" class="px-3 py-1.5 text-xs font-medium" @click="pauseSelected">Pause</button>
        <label class="inline-flex items-center gap-2 text-xs">
          <span>Policy</span>
          <select class="py-1.5 px-2 text-xs" :value="''" @change="assignSelected($event.target.value); $event.target.value = ''">
            <option value="" disabled>Move to…</option>
            <option v-for="p in policies" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
            <option value="none">Not protected</option>
          </select>
        </label>
        <button type="button" class="text-xs font-medium opacity-60 bg-transparent border-0 cursor-pointer" @click="clearSelection">Clear</button>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full min-w-[52rem] border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th class="w-10 text-center px-4 py-3 border-b border-border bg-nav">
                <input ref="selectAllRef" type="checkbox" class="w-4 h-4 cursor-pointer accent-brand" :checked="allVisibleSelected" aria-label="Select all shown" @change="toggleSelectAll" />
              </th>
              <th class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav cursor-pointer select-none whitespace-nowrap hover:text-main" :class="{ 'text-brand': sortKey === 'name' }" @click="setSort('name')">Virtual machine<span class="inline-block w-3 ml-0.5">{{ sortInd('name') }}</span></th>
              <th class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav cursor-pointer select-none whitespace-nowrap hover:text-main" :class="{ 'text-brand': sortKey === 'policy' }" @click="setSort('policy')">Policy<span class="inline-block w-3 ml-0.5">{{ sortInd('policy') }}</span></th>
              <th class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav cursor-pointer select-none whitespace-nowrap hover:text-main" :class="{ 'text-brand': sortKey === 'lastbackup' }" @click="setSort('lastbackup')">Last backup<span class="inline-block w-3 ml-0.5">{{ sortInd('lastbackup') }}</span></th>
              <th class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav">Restore points</th>
              <th class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav">Status</th>
              <th class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav !text-right"><span class="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="vm in sorted" :key="vm.id" class="hover:bg-blue-500/[0.04]">
              <td class="text-center px-4 py-3 border-b border-border">
                <input type="checkbox" class="w-4 h-4 cursor-pointer accent-brand" :checked="selectedIds.has(vm.id)" :aria-label="`Select ${vm.vm_name}`" @change="toggleSelect(vm.id, $event.target.checked)" />
              </td>
              <td class="px-4 py-3 border-b border-border">
                <div class="font-semibold">{{ vm.vm_name }}</div>
                <div class="text-xs text-muted">{{ specs(vm) }}</div>
              </td>
              <td class="px-4 py-3 border-b border-border">
                <label class="sr-only" :for="`policy-${vm.id}`">Policy for {{ vm.vm_name }}</label>
                <select
                  :id="`policy-${vm.id}`"
                  class="py-1 px-2 text-xs"
                  :class="vm.policy_id ? '' : 'text-muted'"
                  :value="vm.policy_id ? String(vm.policy_id) : 'none'"
                  :disabled="!auth.isOperator"
                  @change="changePolicy(vm, $event)"
                >
                  <option v-for="p in policies" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
                  <option value="none">Not protected</option>
                </select>
              </td>
              <td class="px-4 py-3 border-b border-border text-xs whitespace-nowrap">
                <template v-if="vm.last_backup">
                  <div>{{ formatDate(liveProgress(vm).last_backup_ts ? liveProgress(vm).last_backup_ts : vm.last_backup) }}</div>
                  <div v-if="vm.last_backup_duration > 0" class="text-muted">took {{ formatDuration(vm.last_backup_duration) }}</div>
                </template>
                <span v-else class="text-muted">{{ vm.policy_id ? 'Never' : '—' }}</span>
              </td>
              <td class="px-4 py-3 border-b border-border text-xs" :class="vm.restore_points ? '' : 'text-muted'">
                {{ vm.policy_id || vm.restore_points ? (vm.restore_points ?? '–') : '—' }}
              </td>
              <td class="px-4 py-3 border-b border-border min-w-[11rem]">
                <button
                  v-if="isActive(vm) || hasRun(vm)"
                  type="button"
                  class="w-full text-left rounded-md cursor-pointer border-0 bg-transparent p-0"
                  title="View backup details"
                  @click="openJobDrawer(vm)"
                >
                  <div v-if="isActive(vm)">
                    <div class="flex justify-between text-xs mb-1">
                      <span class="truncate max-w-[9rem] text-brand font-semibold">{{ progressText(vm) }}</span>
                      <span v-if="!startingUp(vm)" class="font-mono">{{ liveProgress(vm).progress }}%</span>
                    </div>
                    <div class="block h-1 bg-border rounded-sm overflow-hidden">
                      <div v-if="startingUp(vm)" class="h-full w-2/5 bg-brand rounded-sm animate-pulse"></div>
                      <div v-else class="h-full bg-brand rounded-sm transition-[width] duration-500" :style="{ width: liveProgress(vm).progress + '%' }"></div>
                    </div>
                  </div>
                  <StatusBadge v-else v-bind="rowStatus(vm)" />
                </button>
                <span v-else-if="vm.policy_id && !vm.is_job_active" class="text-xs text-amber-600 dark:text-amber-400">Paused</span>
                <span v-else-if="vm.policy_id" class="text-xs text-muted">Next {{ nextLabel(vm) }}</span>
              </td>
              <td class="text-right px-4 py-3 border-b border-border whitespace-nowrap">
                <template v-if="vm.policy_id">
                  <button v-if="isActive(vm)" type="button" :class="btnSecondary" class="px-3 py-1.5 text-xs" :disabled="!auth.isOperator" @click="stopJob(vm.id)">Stop</button>
                  <button v-else type="button" :class="btnSecondary" class="px-3 py-1.5 text-xs" :disabled="!auth.isOperator" @click="runJob(vm.id)">Run now</button>
                </template>
                <button
                  v-else-if="auth.isOperator && defaultPolicy"
                  type="button"
                  class="px-3 py-1.5 text-xs font-semibold rounded-md border border-brand text-brand bg-transparent cursor-pointer hover:bg-brand/10"
                  @click="protect(vm)"
                >Protect</button>
              </td>
            </tr>
            <tr v-if="!sorted.length">
              <td colspan="7" class="py-12 text-center text-muted text-sm">
                <template v-if="!allVms.length">No VMs yet. <button type="button" class="text-brand bg-transparent border-0 cursor-pointer p-0" @click="refreshVms">Refresh the VM list</button> from vCenter.</template>
                <template v-else>No VMs match.</template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Job details drawer (running or failed) -->
    <div v-if="detailVm" class="fixed inset-0 z-80">
      <div class="absolute inset-0 bg-black/45 backdrop-blur-[1px]" @click="closeJobDrawer"></div>
      <aside
        class="absolute top-0 right-0 bottom-0 w-full max-w-md flex flex-col bg-card border-l border-border shadow-[-4px_0_24px_rgba(0,0,0,0.18)]"
        role="dialog"
        aria-labelledby="job-drawer-title"
      >
        <div class="flex items-center justify-between gap-3 px-4 pt-4 pb-3 border-b border-border bg-nav shrink-0">
          <div class="min-w-0">
            <h3 id="job-drawer-title" class="text-base font-semibold leading-tight m-0 truncate">{{ drawerTitle }}</h3>
            <p class="text-sm font-mono text-brand mt-0.5 truncate">{{ detailVm.vm_name }}</p>
          </div>
          <button
            type="button"
            class="shrink-0 p-1.5 rounded-md text-muted border border-border bg-transparent cursor-pointer hover:text-main hover:bg-card"
            aria-label="Close"
            @click="closeJobDrawer"
          >
            <svg class="w-4 h-4 block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>

        <div class="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-4">
          <div class="grid grid-cols-2 gap-3 text-xs">
            <div>
              <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Host</span>
              <span class="font-mono text-brand">{{ detailVm.host_name || '—' }}</span>
            </div>
            <div>
              <span class="block font-semibold uppercase tracking-wide text-muted mb-1">{{ drawerIsRunning ? 'Started' : 'Last attempt' }}</span>
              <span class="font-mono text-muted">{{ formatDate(detailVm.last_backup) }}</span>
            </div>
            <div v-if="!drawerIsRunning && detailVm.last_backup_duration > 0">
              <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Duration</span>
              <span class="font-mono text-muted">{{ formatDuration(detailVm.last_backup_duration) }}</span>
            </div>
            <div class="col-span-2">
              <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Policy</span>
              <span>{{ detailVm.policy_name ? `${detailVm.policy_name} · next ${nextLabel(detailVm)}` : 'Not protected' }}</span>
            </div>
          </div>

          <div v-if="drawerIsRunning">
            <span class="block text-xs font-semibold uppercase tracking-wide text-muted mb-2">Progress</span>
            <div class="rounded-lg border border-blue-500/25 bg-blue-500/8 p-4">
              <div class="flex items-center justify-between gap-2 mb-2">
                <StatusBadge cls="status-running" label="Running" />
                <span v-if="!startingUp(detailVm)" class="text-lg font-bold font-mono text-brand tabular-nums">{{ drawerProgress.progress }}%</span>
              </div>
              <div class="h-2 rounded-sm bg-border overflow-hidden mb-2">
                <div v-if="startingUp(detailVm)" class="h-full w-2/5 bg-brand rounded-sm animate-pulse"></div>
                <div v-else class="h-full bg-brand rounded-sm transition-[width] duration-500 ease-in-out" :style="{ width: drawerProgress.progress + '%' }"></div>
              </div>
              <p class="text-sm text-main m-0">{{ progressText(detailVm) }}</p>
            </div>
          </div>

          <div v-else-if="isFailed(detailVm)">
            <span class="block text-xs font-semibold uppercase tracking-wide text-muted mb-2">Error</span>
            <pre class="text-xs leading-relaxed whitespace-pre-wrap break-words font-mono p-3 rounded-lg border border-red-500/25 bg-red-500/8 text-red-400 m-0">{{ failureMessage(detailVm) || 'No error message recorded.' }}</pre>
          </div>

          <div>
            <span class="block text-xs font-semibold uppercase tracking-wide text-muted mb-2">Recent log entries</span>
            <div v-if="detailLogsLoading" class="text-xs text-muted py-4 text-center">Loading…</div>
            <div v-else-if="!detailLogs.length" class="text-xs text-muted py-4 text-center italic">No log entries found.</div>
            <div v-else class="rounded-lg border border-border overflow-hidden">
              <div
                v-for="log in detailLogs"
                :key="log.id"
                class="px-3 py-2.5 border-b border-border last:border-b-0 text-xs"
              >
                <div class="flex items-center justify-between gap-2 mb-1">
                  <StatusBadge :cls="logClass(log.status)" :label="log.status" class="text-[0.625rem] px-2 py-0.5" />
                  <span class="font-mono text-muted shrink-0" :title="formatDate(log.timestamp)">{{ formatLogTime(log.timestamp) }}</span>
                </div>
                <p v-if="log.message" class="text-muted leading-snug m-0">{{ log.message }}</p>
              </div>
            </div>
          </div>
        </div>

        <div class="flex items-center justify-between gap-3 px-4 py-3.5 border-t border-border bg-nav shrink-0">
          <span class="text-xs text-muted">Check Settings → System Logs for full worker output.</span>
          <div class="flex gap-2 shrink-0">
            <button type="button" :class="btnSecondary" class="px-3 py-1.5 text-xs font-medium" @click="closeJobDrawer">Close</button>
            <button
              v-if="drawerIsRunning"
              type="button"
              :class="btnDanger"
              class="px-3 py-1.5 text-xs font-semibold"
              :disabled="!auth.isOperator"
              @click="stopFromDrawer"
            >Stop backup</button>
            <button
              v-else-if="isFailed(detailVm)"
              type="button"
              :class="btnPrimary"
              class="px-3 py-1.5 text-xs font-semibold"
              :disabled="!auth.isOperator"
              @click="retryFromDrawer"
            >Run again</button>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { jobsApi, hostsApi, logsApi, policiesApi } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useJobProgress, isJobActive, statusBadge, formatDate, formatDuration, formatRelativeTime } from '@/composables/useJobProgress'
import { useModal } from '@/composables/useModal'
import { useSetupWizard } from '@/composables/useSetupWizard'
import StatusBadge from '@/components/StatusBadge.vue'
import BackupStatus from '@/components/BackupStatus.vue'

const btnPrimary =
  'inline-flex items-center justify-center rounded-md border-0 bg-brand text-white hover:bg-brand-hover transition-colors duration-200 disabled:opacity-55'
const btnSecondary =
  'inline-flex items-center justify-center rounded-md border border-btn-sec-border bg-btn-sec text-btn-sec-text hover:bg-btn-sec-hover transition-colors duration-200 disabled:opacity-55'
const btnDanger =
  'inline-flex items-center justify-center rounded-md border-0 bg-red-600 text-white hover:bg-red-700 transition-colors duration-200'

const auth = useAuthStore()
const { confirm, alert } = useModal()
const { open: openWizard, visible: wizardVisible } = useSetupWizard()

const allVms = ref([])
const hosts = ref([])
const policies = ref([])
const progressMap = ref({})
const paused = ref(false)
const search = ref('')
const filter = ref('all')
const selectedIds = ref(new Set())
const sortKey = ref('policy')
const sortDir = ref('asc')
const selectAllRef = ref(null)
const detailVm = ref(null)
const detailLogs = ref([])
const detailLogsLoading = ref(false)
const refreshing = ref(false)
const statusKey = ref(0)

useJobProgress((data) => { progressMap.value = data })

const protectedCount = computed(() => allVms.value.filter((v) => v.policy_id).length)
const defaultPolicy = computed(() => policies.value[0] || null)

const filters = computed(() => {
  const failed = allVms.value.filter((v) => v.policy_id && (liveProgress(v).last_status || v.last_status) === 'Failed').length
  const list = [
    { id: 'all', label: 'All', count: allVms.value.length },
    { id: 'protected', label: 'Protected', count: protectedCount.value },
    { id: 'unprotected', label: 'Not protected', count: allVms.value.length - protectedCount.value },
  ]
  if (failed || filter.value === 'failed') list.push({ id: 'failed', label: 'Failed', count: failed })
  return list
})

function specs(vm) {
  const parts = []
  if (vm.cpu_count) parts.push(`${vm.cpu_count} vCPU`)
  if (vm.memory_mb) parts.push(`${Math.round(vm.memory_mb / 1024)} GB`)
  if (vm.storage_gb) parts.push(`${vm.storage_gb} GB disk`)
  return parts.join(' · ')
}

// Schedule times are the appliance's time zone (policy summaries carry it).
const serverTz = computed(() => (policies.value[0]?.summary.match(/\d\d:\d\d ([A-Za-z+\-0-9]+) ·/) || [])[1] || '')

function nextLabel(vm) {
  const hm = `${String(vm.schedule_hour).padStart(2, '0')}:${String(vm.schedule_minute).padStart(2, '0')}`
  return serverTz.value ? `${hm} ${serverTz.value}` : hm
}

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  return allVms.value.filter((vm) => {
    if (q && !vm.vm_name.toLowerCase().includes(q)) return false
    const f = filter.value
    if (f === 'protected' && !vm.policy_id) return false
    if (f === 'unprotected' && vm.policy_id) return false
    if (f === 'failed' && !(vm.policy_id && (liveProgress(vm).last_status || vm.last_status) === 'Failed')) return false
    if (f.startsWith('policy:') && String(vm.policy_id) !== f.slice(7)) return false
    return true
  })
})

const sorted = computed(() => {
  const list = [...filtered.value]
  const dir = sortDir.value === 'asc' ? 1 : -1
  list.sort((a, b) => {
    let av; let bv
    if (sortKey.value === 'policy') {
      // protected first, then by policy name
      av = a.policy_name ? `0${a.policy_name}` : '1'; bv = b.policy_name ? `0${b.policy_name}` : '1'
    } else if (sortKey.value === 'lastbackup') {
      av = a.last_backup ? new Date(a.last_backup).getTime() : 0
      bv = b.last_backup ? new Date(b.last_backup).getTime() : 0
    } else {
      av = a.vm_name.toLowerCase(); bv = b.vm_name.toLowerCase()
    }
    if (av < bv) return -1 * dir
    if (av > bv) return 1 * dir
    return a.vm_name.localeCompare(b.vm_name)
  })
  return list
})

const allVisibleSelected = computed(() => sorted.value.length > 0 && sorted.value.every((v) => selectedIds.value.has(v.id)))
watch(allVisibleSelected, (all) => {
  if (selectAllRef.value) selectAllRef.value.indeterminate = selectedIds.value.size > 0 && !all
})

function setSort(key) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else { sortKey.value = key; sortDir.value = 'asc' }
}

function sortInd(key) {
  return sortKey.value === key ? (sortDir.value === 'asc' ? '↑' : '↓') : ''
}

async function load() {
  const [vms, h, sched, pol] = await Promise.all([jobsApi.vms(), hostsApi.list(), jobsApi.scheduler(), policiesApi.list()])
  allVms.value = vms
  hosts.value = h
  paused.value = sched.paused
  policies.value = pol
  statusKey.value++
}

async function refreshVms() {
  refreshing.value = true
  try {
    for (const h of hosts.value) await hostsApi.sync(h.id)
    await load()
  } finally {
    refreshing.value = false
  }
}

async function assign(ids, policyId) {
  await policiesApi.assign(ids, policyId)
  await load()
}

async function protect(vm) {
  await assign([vm.id], defaultPolicy.value.id)
}

async function changePolicy(vm, e) {
  const value = e.target.value
  if (value === 'none') {
    const ok = await confirm(
      `Stop protecting ${vm.vm_name}? Scheduled backups stop. Its existing restore points are kept.`,
      { title: 'Stop protecting', confirmText: 'Stop protecting', danger: true },
    )
    if (!ok) {
      e.target.value = vm.policy_id ? String(vm.policy_id) : 'none'
      return
    }
    await assign([vm.id], null)
  } else {
    await assign([vm.id], Number(value))
  }
}

async function assignSelected(value) {
  const ids = [...selectedIds.value]
  if (!ids.length || !value) return
  if (value === 'none') {
    const ok = await confirm(`Stop protecting ${ids.length} VM(s)? Their existing restore points are kept.`,
      { title: 'Stop protecting', confirmText: 'Stop protecting', danger: true })
    if (!ok) return
    await assign(ids, null)
  } else {
    await assign(ids, Number(value))
  }
  clearSelection()
}

// The wizard changes protection: reload when it closes.
watch(wizardVisible, (open) => { if (!open) load() })

function liveProgress(vm) {
  return progressMap.value[vm.id] || {
    progress: vm.progress,
    current_action: vm.current_action,
    speed_mbps: 0,
    last_status: vm.last_status,
    last_backup_ts: vm.last_backup ? new Date(vm.last_backup).getTime() / 1000 : 0,
    secondary_copy_status: vm.last_secondary_copy_status,
    is_running: false,
    last_backup_message: vm.last_backup_message,
  }
}

function isActive(vm) {
  return isJobActive(liveProgress(vm))
}

// Active but no measurable progress yet (queued / preflight / snapshot / connecting).
// Show an indeterminate "working" bar instead of a dead 0% bar so the row never
// looks idle while a job is genuinely running.
function startingUp(vm) {
  if (!vm) return false
  const p = liveProgress(vm)
  return isActive(vm) && !((p.progress || 0) > 0)
}

const drawerIsRunning = computed(() => detailVm.value && isActive(detailVm.value))
const drawerProgress = computed(() => (detailVm.value ? liveProgress(detailVm.value) : { progress: 0, speed_mbps: 0 }))
const drawerStatus = computed(() => {
  if (!detailVm.value) return 'None'
  return liveProgress(detailVm.value).last_status || detailVm.value.last_status || 'None'
})
const drawerTitle = computed(() => {
  if (drawerIsRunning.value) return 'Backup in progress'
  const s = drawerStatus.value
  if (s === 'Failed') return 'Backup failed'
  if (s === 'Cancelled') return 'Backup cancelled'
  if (s === 'Success') return 'Last backup succeeded'
  return 'Backup details'
})

function rowStatus(vm) {
  const p = liveProgress(vm)
  const b = statusBadge(p.last_status || vm.last_status, isActive(vm))
  return { cls: b.cls, label: b.label }
}

function scheduleState(vm) {
  if (vm.is_job_active) return { cls: 'status-running', label: 'Scheduled' }
  return { cls: 'status-cancelled', label: 'Paused' }
}

function hasRun(vm) {
  const s = liveProgress(vm).last_status || vm.last_status
  return !!s && s !== 'Never' && s !== 'None'
}

function isFailed(vm) {
  const p = liveProgress(vm)
  return (p.last_status || vm.last_status) === 'Failed'
}

function failureMessage(vm) {
  const p = liveProgress(vm)
  return p.last_backup_message || vm.last_backup_message || ''
}

async function openJobDrawer(vm) {
  detailVm.value = vm
  detailLogsLoading.value = true
  detailLogs.value = []
  try {
    const logs = await logsApi.backup(50)
    detailLogs.value = logs.filter((l) => l.vm_name === vm.vm_name)
  } catch {
    detailLogs.value = []
  } finally {
    detailLogsLoading.value = false
  }
}

function closeJobDrawer() {
  detailVm.value = null
  detailLogs.value = []
}

async function retryFromDrawer() {
  if (!detailVm.value) return
  await runJob(detailVm.value.id)
  closeJobDrawer()
}

async function stopFromDrawer() {
  if (!detailVm.value) return
  await stopJob(detailVm.value.id)
}

function logClass(status) {
  const s = (status || '').toLowerCase()
  if (s === 'success') return 'status-success'
  if (s === 'failed') return 'status-error'
  if (s === 'cancelled') return 'status-cancelled'
  if (s === 'warning') return 'status-cancelled'
  return 'status-neutral'
}

function formatLogTime(ts) {
  return formatRelativeTime(ts)
}

function progressText(vm) {
  const p = liveProgress(vm)
  const action = p.current_action || 'Processing…'
  if (action.startsWith('PENDING_STOP')) return 'Stopping…'
  if (action.startsWith('PENDING_RUN')) return 'Starting…'
  if (action.startsWith('Queued')) return 'Queued…'
  if (action.startsWith('Backing up...') && (p.speed_mbps || 0) <= 0) {
    return 'Streaming disk via NBD…'
  }
  const speed = p.speed_mbps > 0 ? ` · ${p.speed_mbps} MB/s` : ''
  return action + speed
}

function toggleSelect(id, checked) {
  const s = new Set(selectedIds.value)
  if (checked) s.add(id); else s.delete(id)
  selectedIds.value = s
}

function toggleSelectAll(e) {
  const s = new Set(selectedIds.value)
  sorted.value.forEach((v) => { if (e.target.checked) s.add(v.id); else s.delete(v.id) })
  selectedIds.value = s
}

function clearSelection() {
  selectedIds.value = new Set()
}

async function runJob(id) {
  await jobsApi.run(id)
  await load()
}

async function stopJob(id) {
  await jobsApi.stop(id)
}

async function togglePause(p) {
  if (p) await jobsApi.pauseAll()
  else await jobsApi.resumeAll()
  paused.value = p
}

async function runSelected() {
  const ids = [...selectedIds.value]
  const idle = ids.filter((id) => {
    const vm = allVms.value.find((v) => v.id === id)
    return vm && !isActive(vm)
  })
  if (!idle.length) {
    await alert('All selected VMs are already running a backup.', { title: 'Run selected' })
    return
  }
  const ok = await confirm(`Start backup for ${idle.length} VM(s)?`, { title: 'Run selected', confirmText: 'Run' })
  if (!ok) return
  let started = 0
  for (const id of idle) {
    try { await jobsApi.run(id); started++ } catch { /* continue */ }
  }
  await alert(`Backup queued for ${started} VM(s).`, { title: 'Backups started' })
  clearSelection()
  await load()
}

async function abortSelected() {
  const running = [...selectedIds.value].filter((id) => {
    const vm = allVms.value.find((v) => v.id === id)
    return vm && isActive(vm)
  })
  if (!running.length) {
    await alert('No running backups among the selected VMs.', { title: 'Abort selected' })
    return
  }
  const ok = await confirm(`Abort ${running.length} running backup(s)?`, { title: 'Abort selected', confirmText: 'Abort', danger: true })
  if (!ok) return
  let stopped = 0
  for (const id of running) {
    try { await jobsApi.stop(id); stopped++ } catch { /* continue */ }
  }
  await alert(`Stop requested for ${stopped} backup(s).`, { title: 'Backups stopping' })
  clearSelection()
}

async function pauseSelected() {
  const ids = [...selectedIds.value]
  if (!ids.length) return
  const ok = await confirm(`Pause scheduled backups for ${ids.length} VM(s)?`, { title: 'Pause selected', confirmText: 'Pause' })
  if (!ok) return
  let n = 0
  for (const id of ids) {
    try {
      await jobsApi.patch(id, { is_job_active: false })
      n++
    } catch { /* continue */ }
  }
  await alert(`Paused schedules for ${n} VM(s).`, { title: 'Pause selected' })
  clearSelection()
  await load()
}


onMounted(load)
</script>
