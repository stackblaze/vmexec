<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3 mb-6">
      <div>
        <h1 class="text-2xl font-bold">Overview</h1>
        <p class="text-sm mt-1 text-muted">Backup health, storage, and activity at a glance</p>
      </div>
      <div class="flex items-center gap-2 text-xs text-muted">
        <span>{{ updatedLabel }}</span>
        <button type="button" class="rounded bg-btn-sec border border-btn-sec-border text-btn-sec-text px-2 py-1 text-xs font-medium transition-colors duration-200 hover:bg-btn-sec-hover" @click="refresh(true)">Refresh</button>
      </div>
    </div>

    <div v-if="data?.setup_incomplete" class="mb-5 px-4 py-3 rounded-lg border border-yellow-500/35 bg-yellow-500/8 text-sm flex flex-wrap items-center justify-between gap-3">
      <span>Setup incomplete — configure storage, hosts, and select VMs to protect.</span>
      <button type="button" class="rounded bg-brand text-white px-3 py-1.5 text-xs font-semibold transition-colors duration-200 hover:bg-brand-hover" @click="openWizard">Open setup wizard</button>
    </div>

    <div v-if="data?.vddk_installed === false && data?.host_count > 0" class="mb-5 px-4 py-3 rounded-lg border border-yellow-500/35 bg-yellow-500/8 text-sm flex items-center justify-between gap-3">
      <span class="flex-1 min-w-0">
        <span class="block font-semibold mb-1">VDDK not installed — backups will fail</span>
        <span class="block leading-relaxed">
          VMExec streams virtual disks through VMware's Virtual Disk Development Kit (VDDK).
          It is <strong>proprietary software, not open source</strong>, and its licence forbids
          redistribution — so it cannot be bundled with VMExec and must be downloaded
          <strong>directly from Broadcom</strong> using a free developer account, where you accept
          their licence yourself.
          Choose the <strong>Linux 64-bit</strong> package
          (<code class="font-mono">VMware-vix-disklib-*.tar.gz</code>, v8 or v9 — match it to your
          vSphere version), then place the tarball in <code class="font-mono">vendor/vddk/</code>
          on the server. VMExec detects and installs it automatically; no restart needed, and this
          message clears once it is in place.
        </span>
      </span>
      <a href="https://developer.broadcom.com/sdks/vmware-virtual-disk-development-kit-vddk/latest" target="_blank" rel="noopener noreferrer" class="shrink-0 rounded bg-brand text-white px-3 py-1.5 text-xs font-semibold transition-colors duration-200 hover:bg-brand-hover">Download VDDK</a>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
      <div class="p-4 px-[1.1rem] rounded-lg border border-border bg-card">
        <div class="text-[0.6875rem] font-bold uppercase tracking-wider text-muted mb-1.5">Protected</div>
        <div class="text-[1.75rem] font-bold leading-tight tabular-nums">{{ data?.protected_count ?? '—' }}</div>
        <div class="text-[0.6875rem] mt-1 text-muted">{{ data?.scheduled_count ?? 0 }} scheduled</div>
      </div>
      <div class="p-4 px-[1.1rem] rounded-lg border border-border bg-card">
        <div class="text-[0.6875rem] font-bold uppercase tracking-wider text-muted mb-1.5">Running</div>
        <div class="text-[1.75rem] font-bold leading-tight tabular-nums text-blue-400">{{ data?.running_count ?? '—' }}</div>
        <div class="text-[0.6875rem] mt-1 text-muted">active backups</div>
      </div>
      <div class="p-4 px-[1.1rem] rounded-lg border border-border bg-card">
        <div class="text-[0.6875rem] font-bold uppercase tracking-wider text-muted mb-1.5">Success</div>
        <div class="text-[1.75rem] font-bold leading-tight tabular-nums text-emerald-500">{{ data?.status_counts?.Success ?? '—' }}</div>
        <div class="text-[0.6875rem] mt-1 text-muted">last run OK</div>
      </div>
      <div class="p-4 px-[1.1rem] rounded-lg border border-border bg-card">
        <div class="text-[0.6875rem] font-bold uppercase tracking-wider text-muted mb-1.5">Failed</div>
        <div class="text-[1.75rem] font-bold leading-tight tabular-nums text-red-400">{{ data?.status_counts?.Failed ?? '—' }}</div>
        <div class="text-[0.6875rem] mt-1 text-muted">need attention</div>
      </div>
      <div class="p-4 px-[1.1rem] rounded-lg border border-border bg-card">
        <div class="text-[0.6875rem] font-bold uppercase tracking-wider text-muted mb-1.5">7d success</div>
        <div class="text-[1.75rem] font-bold leading-tight tabular-nums">{{ data?.success_rate_7d != null ? data.success_rate_7d + '%' : '—' }}</div>
        <div class="text-[0.6875rem] mt-1 text-muted">{{ logTotal7d }} events</div>
      </div>
      <div class="p-4 px-[1.1rem] rounded-lg border border-border bg-card">
        <div class="text-[0.6875rem] font-bold uppercase tracking-wider text-muted mb-1.5">Engine</div>
        <div class="text-[1.75rem] font-bold leading-tight tabular-nums" :class="data?.worker_online ? 'text-emerald-500' : 'text-red-400'">{{ data?.worker_online ? 'Online' : 'Offline' }}</div>
        <div class="text-[0.6875rem] mt-1 text-muted">{{ workerSub }}</div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-5">
      <div class="bg-card border border-border rounded-lg shadow-card overflow-hidden transition-all duration-300">
        <div class="flex items-center justify-between gap-2 py-3 px-4 text-[0.8125rem] font-bold border-b border-border bg-nav">
          <span>Storage</span>
          <span class="text-[0.625rem] font-bold uppercase tracking-wide px-[0.45rem] py-[0.15rem] rounded-full bg-brand/12 text-brand">{{ data?.storage?.type ?? '—' }}</span>
        </div>
        <div class="p-4">
          <div class="flex items-baseline gap-1.5 min-w-0 mb-1 text-xs">
            <span class="text-muted">Backup path</span>
            <span class="text-muted">·</span>
            <span class="font-mono truncate text-brand">{{ data?.storage?.path ?? '—' }}</span>
          </div>
          <div v-if="data?.storage?.disk_total_gb" class="pt-3 mt-3 border-t border-border">
            <div class="flex justify-center my-6">
              <div class="relative mx-auto w-[7.5rem] h-[7.5rem]">
                <svg viewBox="0 0 36 36" class="w-full h-full -rotate-90">
                  <circle class="fill-none stroke-border stroke-[3.2]" cx="18" cy="18" r="15.9155" />
                  <circle class="fill-none stroke-[3.2] stroke-emerald-500 transition-[stroke-dasharray,stroke-dashoffset] duration-[450ms]" cx="18" cy="18" r="15.9155" pathLength="100" :style="donutSeg(freePct, 0)" />
                  <circle class="fill-none stroke-[3.2] stroke-slate-500 transition-[stroke-dasharray,stroke-dashoffset] duration-[450ms]" cx="18" cy="18" r="15.9155" pathLength="100" :style="donutSeg(usedPct, freePct)" />
                  <circle class="fill-none stroke-[3.2] stroke-brand transition-[stroke-dasharray,stroke-dashoffset] duration-[450ms]" cx="18" cy="18" r="15.9155" pathLength="100" :style="donutSeg(backupPct, freePct + usedPct)" />
                </svg>
                <div class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none text-center">
                  <div class="text-sm font-bold leading-tight tabular-nums">{{ data.storage.disk_free_gb?.toFixed(0) }} GB</div>
                  <div class="text-[0.625rem] font-semibold mt-0.5 text-muted">{{ data.storage.disk_free_pct?.toFixed(0) }}% free</div>
                </div>
              </div>
            </div>
            <p class="flex flex-wrap items-center justify-center gap-2 mt-1 text-[0.625rem] text-muted">
              <span class="inline-flex items-center gap-1"><span class="w-[0.45rem] h-[0.45rem] rounded-full shrink-0 bg-emerald-500"></span>Free <strong>{{ data.storage.disk_free_gb?.toFixed(1) }} GB</strong></span>
              <span>·</span>
              <span class="inline-flex items-center gap-1"><span class="w-[0.45rem] h-[0.45rem] rounded-full shrink-0 bg-slate-500"></span>Used <strong>{{ data.storage.disk_used_gb?.toFixed(1) }} GB</strong></span>
              <span>·</span>
              <span class="inline-flex items-center gap-1"><span class="w-[0.45rem] h-[0.45rem] rounded-full shrink-0 bg-brand"></span>Backups <strong>{{ data.storage.total_human }}</strong></span>
            </p>
            <p
              v-if="data?.storage?.projected_gb != null"
              class="mt-2 text-center text-[0.7rem] font-medium"
              :class="data.storage.projection_warn ? 'text-red-500' : (data.storage.projected_pct > 60 ? 'text-amber-500' : 'text-muted')"
              title="Estimated steady-state size of all scheduled jobs: 2 fulls plus retained daily deltas per VM, from vCenter committed sizes and measured incrementals"
            >
              Projected at steady state: <strong>{{ data.storage.projected_gb >= 1000 ? (data.storage.projected_gb / 1000).toFixed(2) + ' TB' : data.storage.projected_gb.toFixed(0) + ' GB' }}</strong>
              <template v-if="data.storage.projected_pct != null"> of {{ data.storage.disk_total_gb?.toFixed(0) }} GB ({{ data.storage.projected_pct.toFixed(0) }}%)</template>
              <template v-if="data.storage.projection_warn"> — over capacity</template>
            </p>
          </div>
          <div v-if="data?.storage?.scan_error" class="mt-3 text-xs text-red-400">{{ data.storage.scan_error }}</div>
        </div>
      </div>

      <div class="bg-card border border-border rounded-lg shadow-card overflow-hidden transition-all duration-300">
        <div class="flex items-center justify-between gap-2 py-3 px-4 text-[0.8125rem] font-bold border-b border-border bg-nav"><span>Backup status</span><span class="text-[10px] font-normal opacity-60">protected VMs · last run</span></div>
        <div class="p-4">
          <div v-for="row in statusRows" :key="row.key" class="flex items-center gap-2 mb-2">
            <span class="w-[4.5rem] text-[0.6875rem] font-semibold text-muted shrink-0">{{ row.key }}</span>
            <div class="flex-1 h-1.5 rounded-sm bg-border overflow-hidden"><div class="h-full rounded-sm transition-[width] duration-[350ms]" :style="{ width: row.pct + '%', background: row.color }"></div></div>
            <span class="w-6 text-right text-xs font-bold tabular-nums">{{ row.count }}</span>
          </div>
          <div class="mt-4 pt-3 border-t border-border grid grid-cols-2 gap-2 text-center">
            <div><div class="text-lg font-bold">{{ data?.host_count ?? '—' }}</div><div class="text-[10px] uppercase text-muted">{{ data?.host_label ?? 'Hosts' }}</div></div>
            <div><div class="text-lg font-bold">{{ data?.inventory_count ?? '—' }}</div><div class="text-[10px] uppercase text-muted">Inventory VMs</div></div>
          </div>
        </div>
      </div>

      <div class="bg-card border border-border rounded-lg shadow-card overflow-hidden transition-all duration-300">
        <div class="flex items-center justify-between gap-2 py-3 px-4 text-[0.8125rem] font-bold border-b border-border bg-nav"><span>Last 7 days</span><span class="text-[10px] font-normal opacity-60">backup events</span></div>
        <div class="p-4">
          <div v-for="row in logRows" :key="row.key" class="flex items-center gap-2 mb-2">
            <span class="w-[4.5rem] text-[0.6875rem] font-semibold text-muted shrink-0">{{ row.key }}</span>
            <div class="flex-1 h-1.5 rounded-sm bg-border overflow-hidden"><div class="h-full rounded-sm transition-[width] duration-[350ms]" :style="{ width: row.pct + '%', background: row.color }"></div></div>
            <span class="w-6 text-right text-xs font-bold tabular-nums">{{ row.count }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5">
      <div class="bg-card border border-border rounded-lg shadow-card overflow-hidden transition-all duration-300">
        <div class="flex items-center justify-between gap-2 py-3 px-4 text-[0.8125rem] font-bold border-b border-border bg-nav">
          <span>Live backups</span>
          <RouterLink to="/backup" class="text-xs font-medium text-brand hover:opacity-85 no-underline inline-flex items-center">View backups →</RouterLink>
        </div>
        <div class="p-4 min-h-20">
          <div v-if="!data?.live_jobs?.length" class="text-sm py-7 px-4 text-center text-muted italic opacity-75">No backups running</div>
          <div v-for="j in data?.live_jobs || []" :key="j.vm_id" class="py-2.5 border-b border-border last:border-b-0">
            <div class="flex justify-between text-sm"><span class="font-semibold">{{ j.vm_name }}</span><span class="font-mono text-blue-400">{{ j.progress }}%</span></div>
            <div class="text-xs truncate text-muted">{{ j.current_action }}</div>
            <div class="h-1 rounded-sm bg-border overflow-hidden mt-1.5"><div class="h-full bg-brand transition-[width] duration-500 rounded-sm" :style="{ width: j.progress + '%' }"></div></div>
          </div>
        </div>
      </div>
      <div class="bg-card border border-border rounded-lg shadow-card overflow-hidden transition-all duration-300">
        <div class="flex items-center justify-between gap-2 py-3 px-4 text-[0.8125rem] font-bold border-b border-border bg-nav">
          <span>Active restores</span>
          <RouterLink to="/restore" class="text-xs font-medium text-brand hover:opacity-85 no-underline inline-flex items-center">Restore →</RouterLink>
        </div>
        <div class="p-4 min-h-20">
          <div v-if="!data?.active_restores?.length" class="text-sm py-7 px-4 text-center text-muted italic opacity-75">No active restores</div>
          <div v-for="r in data?.active_restores || []" :key="r.id" class="py-2.5 border-b border-border last:border-b-0">
            <div class="flex justify-between text-sm"><span class="font-semibold">{{ r.vm_name }}</span><StatusBadge cls="status-running" label="In Progress" /></div>
            <div class="text-xs text-muted">{{ r.current_action || r.status }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <div class="bg-card border border-border rounded-lg shadow-card overflow-hidden transition-all duration-300">
        <div class="flex items-center justify-between gap-2 py-3 px-4 text-[0.8125rem] font-bold border-b border-border bg-nav"><span>Recent activity</span></div>
        <div class="p-4 min-h-20 max-h-80 overflow-y-auto">
          <div v-for="l in data?.recent_activity || []" :key="l.id" class="py-2.5 border-b border-border last:border-b-0 text-sm">
            <div class="flex justify-between gap-2">
              <span class="truncate font-medium">{{ l.vm_name }}</span>
              <StatusBadge :cls="logClass(l.status)" :label="l.status" />
            </div>
            <p v-if="l.message" class="text-[11px] leading-snug text-muted mt-1 truncate" :title="l.message">{{ l.message }}</p>
          </div>
          <div v-if="!data?.recent_activity?.length" class="text-sm py-7 px-4 text-center text-muted italic opacity-75">No recent activity</div>
        </div>
      </div>
      <div class="bg-card border border-border rounded-lg shadow-card overflow-hidden transition-all duration-300">
        <div class="flex items-center justify-between gap-2 py-3 px-4 text-[0.8125rem] font-bold border-b border-border bg-nav">
          <span>Needs attention</span>
          <span v-if="data?.attention?.length" class="text-[0.625rem] font-bold uppercase tracking-wide px-[0.45rem] py-[0.15rem] rounded-full bg-red-500/12 text-red-400">{{ data.attention.length }}</span>
        </div>
        <div class="p-4 min-h-20 max-h-80 overflow-y-auto">
          <div v-for="a in data?.attention || []" :key="a.vm_id + a.reason" class="py-2.5 border-b border-border last:border-b-0 text-sm">
            <span class="font-medium">{{ a.vm_name }}</span> — {{ a.reason }}
            <div class="text-xs mt-0.5 text-muted">{{ a.host_name }}</div>
            <p v-if="a.message" class="text-[11px] leading-snug text-red-400 mt-1 truncate" :title="a.message">{{ a.message }}</p>
          </div>
          <div v-if="!data?.attention?.length" class="text-sm py-7 px-4 text-center text-muted italic opacity-75">All clear</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { overviewApi } from '@/api/client'
import { useSetupWizard } from '@/composables/useSetupWizard'
import StatusBadge from '@/components/StatusBadge.vue'

const { open: openWizard } = useSetupWizard()
const data = ref(null)
const updatedAt = ref(null)
let timer = null

const updatedLabel = computed(() => updatedAt.value ? `Updated ${updatedAt.value.toLocaleTimeString()}` : 'Loading…')
const logTotal7d = computed(() => Object.values(data.value?.log_stats_7d || {}).reduce((a, b) => a + b, 0))
const workerSub = computed(() => {
  const age = data.value?.worker_last_seen_seconds
  if (age == null) return 'worker status'
  return age < 60 ? 'seen just now' : `seen ${Math.round(age / 60)}m ago`
})

const statusColors = { Success: '#10b981', Failed: '#ef4444', Cancelled: '#6b7280', Skipped: '#9ca3af', Never: '#64748b', Other: '#6b7280' }
const logColors = { Success: '#10b981', Failed: '#ef4444', Cancelled: '#6b7280', Skipped: '#9ca3af', Warning: '#f59e0b', Other: '#6b7280' }

const statusRows = computed(() => barRows(data.value?.status_counts, statusColors))
const logRows = computed(() => barRows(data.value?.log_stats_7d, logColors))

const freePct = computed(() => pct(data.value?.storage?.disk_free_gb, data.value?.storage?.disk_total_gb))
const usedPct = computed(() => {
  const total = data.value?.storage?.disk_total_gb || 0
  const used = (data.value?.storage?.disk_used_gb || 0) - (data.value?.storage?.disk_total_gb ? 0 : 0)
  return total ? Math.max(0, ((data.value?.storage?.disk_used_gb || 0) / total) * 100) : 0
})
const backupPct = computed(() => {
  const total = data.value?.storage?.disk_total_gb || 0
  if (!total) return 0
  const backupGb = (data.value?.storage?.disk_used_gb || 0) * 0.3
  return Math.min(20, (backupGb / total) * 100)
})

function pct(part, whole) {
  if (!whole) return 0
  return Math.min(100, Math.max(0, ((part || 0) / whole) * 100))
}

function barRows(counts, colors) {
  if (!counts) return []
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1
  return Object.entries(counts).filter(([k, n]) => n > 0 || k !== 'Other').map(([key, count]) => ({
    key, count,
    pct: Math.max(count ? (count / total) * 100 : 0, count ? 4 : 0),
    color: colors[key] || '#6b7280',
  }))
}

function donutSeg(pctVal, offset) {
  const p = Math.min(100, Math.max(0, pctVal))
  return { strokeDasharray: `${p} ${100 - p}`, strokeDashoffset: String(-offset) }
}

function logClass(s) {
  if (s === 'Success') return 'status-success'
  if (s === 'Failed') return 'status-error'
  return 'status-neutral'
}

async function refresh() {
  data.value = await overviewApi.get()
  updatedAt.value = new Date()
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 15000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>
