<template>
  <div v-if="visible" class="fixed inset-0 z-[120] flex items-center justify-center p-3" role="dialog" aria-modal="true">
    <div class="absolute inset-0 bg-black/55 backdrop-blur-[2px]" @click="onClose(true)"></div>
    <div class="relative w-full max-w-6xl h-[min(44rem,calc(100vh-1.5rem))] flex flex-col overflow-hidden rounded-lg bg-card border border-border shadow-card">
      <div class="flex justify-between items-center gap-4 px-6 py-[1.125rem] border-b border-border bg-nav">
        <div>
          <h2 class="text-xl font-bold tracking-wide uppercase">Setup Wizard</h2>
          <p class="text-xs mt-0.5 text-muted">
            Step {{ step }} of 5 · {{ stepNames[step - 1] }}
          </p>
        </div>
        <button type="button" class="p-1.5 rounded-md text-muted transition-[color,background] duration-150 hover:text-main hover:bg-btn-sec" aria-label="Close" @click="onClose(true)">×</button>
      </div>

      <div v-if="error" class="shrink-0 px-6 py-3 text-sm font-medium leading-[1.45] border-b border-red-500/25 bg-red-500/12 text-red-400" role="alert">{{ error }}</div>

      <div class="flex flex-1 min-h-0 overflow-hidden">
        <nav class="w-52 shrink-0 border-r border-border bg-nav py-3.5 overflow-y-auto self-stretch max-sm:w-[3.25rem]" aria-label="Setup steps">
          <div
            v-for="n in 5"
            :key="n"
            class="flex items-center gap-3 px-[1.125rem] py-3 text-sm border-l-[3px] border-transparent transition-[color,border-color,background] duration-150 max-sm:justify-center max-sm:px-2 max-sm:py-2.5"
            :class="step === n ? 'text-main border-l-brand bg-brand/6' : 'text-muted'"
          >
            <span
              class="w-[1.375rem] h-[1.375rem] shrink-0 flex items-center justify-center rounded-full text-[0.6875rem] font-semibold border"
              :class="step === n ? 'border-brand bg-brand text-white' : step > n ? 'border-emerald-500/50 text-emerald-400 bg-emerald-500/8' : 'border-border text-muted bg-card'"
            >{{ n }}</span>
            <span class="font-medium leading-[1.2] max-sm:hidden">{{ stepNames[n - 1] }}</span>
          </div>
        </nav>

        <div class="flex-1 min-h-0 overflow-hidden relative">
          <!-- Step 1: Storage -->
          <div v-show="step === 1" class="absolute inset-0 overflow-y-auto px-8 py-6">
            <div class="flex flex-wrap justify-between items-center gap-3 mb-4 border-b border-border pb-3">
              <h3 class="font-semibold text-base">Backup storage</h3>
              <div class="flex gap-3">
                <label v-for="t in ['SMB','NFS','S3']" :key="t" class="flex items-center gap-1 text-xs font-medium cursor-pointer">
                  <input v-model="storageType" type="radio" :value="t" /> {{ t }}
                </label>
              </div>
            </div>
            <div v-if="storageType === 'SMB'" class="max-w-3xl space-y-3">
              <div><span class="block text-xs font-semibold uppercase text-muted mb-1">UNC Path</span><input v-model="storage.smb_unc_path" class="w-full py-2 px-3 font-mono text-sm mt-1" placeholder="\\server\share\backups" /></div>
              <div class="grid grid-cols-2 gap-4">
                <div><span class="block text-xs font-semibold uppercase text-muted mb-1">Username</span><input v-model="storage.smb_user" class="w-full py-2 px-3 text-sm mt-1" /></div>
                <div><span class="block text-xs font-semibold uppercase text-muted mb-1">Password</span><input v-model="storage.smb_password" type="password" class="w-full py-2 px-3 text-sm mt-1" /></div>
              </div>
            </div>
            <div v-else-if="storageType === 'NFS'" class="max-w-3xl">
              <span class="block text-xs font-semibold uppercase text-muted mb-1">NFS Export Path</span>
              <input v-model="storage.nfs_path" class="w-full py-2 px-3 font-mono text-sm mt-1" placeholder="/mnt/backups" />
            </div>
            <div v-else class="max-w-3xl grid grid-cols-2 gap-4">
              <div class="col-span-2"><span class="block text-xs font-semibold uppercase text-muted mb-1">S3 Endpoint</span><input v-model="storage.s3_endpoint" class="w-full py-2 px-3 text-sm mt-1" /></div>
              <div><span class="block text-xs font-semibold uppercase text-muted mb-1">Access Key</span><input v-model="storage.s3_access_key" class="w-full py-2 px-3 text-sm mt-1" /></div>
              <div><span class="block text-xs font-semibold uppercase text-muted mb-1">Secret Key</span><input v-model="storage.s3_secret_key" type="password" class="w-full py-2 px-3 text-sm mt-1" /></div>
              <div><span class="block text-xs font-semibold uppercase text-muted mb-1">Bucket</span><input v-model="storage.s3_bucket" class="w-full py-2 px-3 text-sm mt-1" /></div>
              <div><span class="block text-xs font-semibold uppercase text-muted mb-1">Region</span><input v-model="storage.s3_region" class="w-full py-2 px-3 text-sm mt-1" placeholder="us-east-1" /></div>
            </div>
            <div v-if="storageStatus" class="mt-4 px-4 py-3 rounded text-sm font-medium max-w-3xl" :style="storageStatusStyle">{{ storageStatus }}</div>
          </div>

          <!-- Step 2: Hosts -->
          <div v-show="step === 2" class="absolute inset-0 overflow-y-auto px-8 py-6">
            <div class="flex flex-col min-h-full">
              <h3 class="font-semibold text-base mb-1">ESXi / vCenter</h3>
              <p class="text-sm mb-4 text-muted">Register a standalone ESXi host or vCenter Server.</p>
              <div class="grid grid-cols-1 sm:grid-cols-12 gap-3 mb-4">
                <div class="sm:col-span-4">
                  <span class="block text-xs font-semibold uppercase text-muted mb-1">Alias</span>
                  <input v-model="newHost.name" placeholder="e.g. vcenter-prod" class="w-full py-2 px-3 text-sm mt-1" autocomplete="off" :disabled="hostAddBusy" />
                </div>
                <div class="sm:col-span-8">
                  <span class="block text-xs font-semibold uppercase text-muted mb-1">IP / FQDN</span>
                  <input v-model="newHost.host_ip" placeholder="10.0.0.50 or vcenter.example.com" class="w-full py-2 px-3 font-mono text-sm mt-1" autocomplete="off" spellcheck="false" :disabled="hostAddBusy" />
                </div>
                <div class="sm:col-span-5">
                  <span class="block text-xs font-semibold uppercase text-muted mb-1">User</span>
                  <input v-model="newHost.username" placeholder="administrator@vsphere.local" class="w-full py-2 px-3 text-sm mt-1" autocomplete="off" spellcheck="false" :disabled="hostAddBusy" />
                </div>
                <div class="sm:col-span-4">
                  <span class="block text-xs font-semibold uppercase text-muted mb-1">Password</span>
                  <input v-model="newHost.password" type="password" class="w-full py-2 px-3 text-sm mt-1" autocomplete="new-password" :disabled="hostAddBusy" />
                </div>
                <div class="sm:col-span-3">
                  <span class="block text-xs font-semibold uppercase text-muted mb-1">Connection</span>
                  <select v-model="newHost.connection_type" class="w-full py-2 px-3 text-sm mt-1" :disabled="hostAddBusy">
                    <option value="auto">Auto-detect</option>
                    <option value="standalone">Standalone ESXi</option>
                    <option value="vcenter">vCenter Server</option>
                  </select>
                </div>
                <div class="sm:col-span-12 flex justify-end">
                  <button type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-4 py-2 text-sm font-medium text-btn-sec-text hover:bg-btn-sec-hover transition-[background-color] duration-200 disabled:opacity-60 disabled:cursor-not-allowed" :disabled="hostAddBusy" @click="addHost">
                    <span v-if="hostAddBusy" class="inline-block h-3.5 w-3.5 rounded-full border-2 border-current border-r-transparent animate-spin" aria-hidden="true"></span>
                    {{ hostAddBusy ? 'Connecting…' : 'Add Host' }}
                  </button>
                </div>
              </div>
              <div class="rounded-lg border border-border bg-card shadow-card transition-all duration-300 overflow-hidden flex-1 min-h-0 overflow-y-auto">
                <div class="px-4 py-2.5 border-b border-border font-semibold text-sm bg-nav">Registered Hosts</div>
                <ul class="divide-y divide-border text-sm overflow-y-auto max-h-64">
                  <li v-if="!hosts.length" class="px-4 py-3 text-center text-muted">No hosts added yet.</li>
                  <li v-for="h in hosts" :key="h.id" class="px-4 py-3 flex justify-between items-center gap-3">
                    <div>
                      <span class="font-medium block">{{ h.name }}</span>
                      <span class="text-xs font-mono text-brand">{{ h.host_ip }}</span>
                    </div>
                    <button type="button" class="text-xs hover:text-red-400" @click="deleteHost(h)">Remove</button>
                  </li>
                </ul>
              </div>
            </div>
          </div>

          <!-- Step 3: VMs -->
          <div v-show="step === 3" class="absolute inset-0 overflow-y-auto px-8 py-6">
            <div class="flex flex-col min-h-full">
              <div class="flex flex-wrap justify-between items-start gap-3 mb-4">
                <div>
                  <h3 class="font-semibold text-base mb-1">Select VMs to protect</h3>
                  <p class="text-sm text-muted">Templates and vCLS agent VMs are excluded automatically; this backup server is deselected by default.</p>
                </div>
                <div class="flex gap-2">
                  <button type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-3 py-1.5 text-xs font-medium text-btn-sec-text hover:bg-btn-sec-hover transition-[background-color] duration-200" @click="selectAllVms(true)">All</button>
                  <button type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-3 py-1.5 text-xs font-medium text-btn-sec-text hover:bg-btn-sec-hover transition-[background-color] duration-200" @click="selectAllVms(false)">None</button>
                </div>
              </div>
              <div class="flex-1 min-h-0 overflow-y-auto rounded-lg border border-border bg-card shadow-card transition-all duration-300 overflow-hidden">
                <table class="w-full border-separate border-spacing-0 text-sm">
                  <thead><tr><th class="w-10 text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav"></th><th class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav">VM Name</th><th class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav">Host</th><th class="text-right text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav">Disk</th></tr></thead>
                  <tbody>
                    <tr v-if="!vms.length"><td colspan="4" class="p-4 text-center text-sm text-muted">No VMs found.</td></tr>
                    <tr v-for="v in vms" :key="v.id">
                      <td class="text-center px-4 py-3 border-b border-border align-middle"><input v-model="v._selected" type="checkbox" /></td>
                      <td class="font-mono text-xs px-4 py-3 border-b border-border align-middle">{{ v.vm_name }}</td>
                      <td class="text-xs text-muted px-4 py-3 border-b border-border align-middle">{{ hostLabel(v.esxi_host_id) }}</td>
                      <td class="text-right text-xs px-4 py-3 border-b border-border align-middle">{{ v.storage_gb ? v.storage_gb.toFixed(1) + ' GB' : '—' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- Step 4: Schedule -->
          <div v-show="step === 4" class="absolute inset-0 overflow-y-auto px-8 py-6">
            <h3 class="font-semibold text-base mb-1">Default schedule</h3>
            <p class="text-sm mb-4 text-muted">Applied to all selected VMs. Adjust per VM later on Backup.</p>
            <div class="max-w-md space-y-3">
              <div>
                <span class="block text-xs font-semibold uppercase text-muted mb-1">Frequency</span>
                <select v-model="schedule.frequency" class="w-full py-2 px-3 text-sm">
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
              </div>
              <div :style="{ opacity: schedule.frequency === 'daily' ? 0.35 : 1 }">
                <span class="block text-xs font-semibold uppercase text-muted mb-1">Days</span>
                <div class="grid grid-cols-7 gap-0.5 mt-1">
                  <label v-for="d in dayLabels" :key="d.num" class="text-center text-xs py-1 rounded border border-border cursor-pointer">
                    <input v-model="schedule.days" type="checkbox" :value="String(d.num)" class="sr-only" :disabled="schedule.frequency === 'daily'" /> {{ d.lbl }}
                  </label>
                </div>
              </div>
              <div class="grid grid-cols-4 gap-2">
                <div><span class="block text-xs font-semibold uppercase text-muted mb-1">Hour</span><input v-model.number="schedule.hour" type="number" min="0" max="23" class="w-full px-2 py-1 text-center font-mono text-sm" /></div>
                <div><span class="block text-xs font-semibold uppercase text-muted mb-1">Min</span><input v-model.number="schedule.minute" type="number" min="0" max="59" class="w-full px-2 py-1 text-center font-mono text-sm" /></div>
                <div><span class="block text-xs font-semibold uppercase text-muted mb-1">Keep</span><input v-model.number="schedule.retention" type="number" min="1" max="60" class="w-full px-2 py-1 text-center font-mono text-sm" /></div>
                <div class="flex flex-col items-center"><span class="block text-xs font-semibold uppercase text-muted mb-1">Active</span><input v-model="schedule.active" type="checkbox" class="mt-2" /></div>
              </div>
              <label class="flex items-center gap-2 text-sm cursor-pointer">
                <input v-model="schedule.stagger" type="checkbox" /> Stagger start times (spreads VMs across the day so they don't all fire at once)
              </label>
              <div v-if="schedule.stagger" class="mt-2 ml-6">
                <span class="block text-xs font-semibold uppercase text-muted mb-1">Gap between jobs (minutes)</span>
                <input v-model.number="schedule.staggerInterval" type="number" min="5" max="180" step="5" class="w-28 py-2 px-3 text-sm" />
              </div>
              <div v-if="storageType !== 'S3'" class="pt-2 border-t border-dashed border-border">
                <label class="flex items-center gap-2 text-sm"><input v-model="schedule.cbt" type="checkbox" /> Enable incremental (CBT)</label>
                <div v-if="schedule.cbt && needsVddk" class="mt-2 rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2.5 text-amber-400 text-xs leading-relaxed">
                  <p class="font-semibold mb-0.5">Incremental backups need the VMware VDDK, which is not installed yet</p>
                  <p class="opacity-90">
                    CBT streams changed blocks through VMware's VDDK. It is proprietary software,
                    not open source, and cannot be redistributed with VMExec — download it directly
                    from
                    <a href="https://developer.broadcom.com/sdks/vmware-virtual-disk-development-kit-vddk/latest"
                       target="_blank" rel="noopener noreferrer" class="underline hover:no-underline">Broadcom</a>
                    (free developer account), then place the <strong>Linux 64-bit</strong>
                    <code class="font-mono">VMware-vix-disklib-*.tar.gz</code> in
                    <code class="font-mono">vendor/vddk/</code> on the server — it installs automatically.
                    You can finish setup now; jobs will fail until it is in place.
                  </p>
                </div>
                <div class="mt-2"><span class="block text-xs font-semibold uppercase text-muted mb-1">Full every N runs</span><input v-model.number="schedule.cbtInterval" type="number" min="1" max="60" class="w-24 px-2 py-1 text-center text-sm ml-2" /></div>
              </div>
            </div>
          </div>

          <!-- Step 5: Complete -->
          <div v-show="step === 5" class="absolute inset-0 overflow-y-auto px-8 py-6">
            <h3 class="font-semibold text-base mb-1">Setup complete</h3>
            <p class="text-sm mb-4 text-muted">{{ summary }}</p>

            <div class="rounded-lg border border-border bg-card shadow-card max-w-2xl divide-y divide-border text-sm">
              <div class="px-4 py-3 flex justify-between gap-4">
                <span class="text-muted">Backup storage</span>
                <span class="font-mono text-right">{{ completeSummary.storage }}</span>
              </div>
              <div class="px-4 py-3 flex justify-between gap-4">
                <span class="text-muted">{{ hosts.length === 1 ? 'Host' : 'Hosts' }}</span>
                <span class="text-right">{{ completeSummary.hosts }}</span>
              </div>
              <div class="px-4 py-3 flex justify-between gap-4">
                <span class="text-muted">Protected VMs</span>
                <span class="text-right">{{ completeSummary.vms }}</span>
              </div>
              <div class="px-4 py-3 flex justify-between gap-4">
                <span class="text-muted">Schedule</span>
                <span class="text-right">{{ completeSummary.schedule }}</span>
              </div>
              <div v-if="completeSummary.window" class="px-4 py-3 flex justify-between gap-4">
                <span class="text-muted">Backup window</span>
                <span class="font-mono text-right">{{ completeSummary.window }}</span>
              </div>
              <div class="px-4 py-3 flex justify-between gap-4">
                <span class="text-muted">Incremental</span>
                <span class="text-right">{{ completeSummary.cbt }}</span>
              </div>
              <div class="px-4 py-3 flex justify-between gap-4">
                <span class="text-muted">Retention</span>
                <span class="text-right">keep {{ schedule.retention }} restore points per VM</span>
              </div>
            </div>

            <p class="text-sm mt-4 text-muted">Fine-tune any VM's schedule on the Backup tab.</p>
          </div>
        </div>
      </div>

      <div class="shrink-0 flex items-center gap-3 px-6 py-4 border-t border-border bg-nav">
        <button v-if="step > 1 && step < 5" type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-4 py-2 text-sm text-btn-sec-text hover:bg-btn-sec-hover transition-[background-color] duration-200" @click="step--">Back</button>
        <div class="flex-1"></div>
        <button type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover disabled:opacity-55 disabled:cursor-not-allowed transition-[background-color] duration-200" :disabled="busy" @click="next">
          {{ nextLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { configApi, hostsApi, jobsApi } from '@/api/client'
import { useSetupWizard } from '@/composables/useSetupWizard'
import { useModal } from '@/composables/useModal'
import { shouldProtectVm } from '@/composables/useInfra'

const { visible, close } = useSetupWizard()
const { confirm, alert } = useModal()
const router = useRouter()

const stepNames = ['Storage', 'ESXi Hosts', 'Select VMs', 'Schedule', 'Complete']
const step = ref(1)
const error = ref('')
const busy = ref(false)
const storageStatus = ref('')
const storageStatusOk = ref(true)
const summary = ref('')
const storageType = ref('NFS')
const storage = reactive({ smb_unc_path: '', smb_user: '', smb_password: '', nfs_path: '/mnt/backups', s3_endpoint: '', s3_access_key: '', s3_secret_key: '', s3_bucket: '', s3_region: '' })
const hosts = ref([])
const hostAddBusy = ref(false)
// The API reports VDDK state per host-add. Surface it rather than discarding it.
const needsVddk = computed(() => hosts.value.some((h) => h.vddk_installed === false))

const DAY_NAMES = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
const completeSummary = computed(() => {
  const pad = (n) => String(n).padStart(2, '0')
  const count = vms.value.filter((v) => v._selected).length
  const interval = schedule.stagger ? (schedule.staggerInterval || 30) : 0
  const start = schedule.hour * 60 + schedule.minute
  const end = start + Math.max(0, count - 1) * interval
  const fmt = (m) => `${pad(Math.floor(m / 60) % 24)}:${pad(m % 60)}`
  const freq = schedule.frequency === 'daily'
    ? 'Daily'
    : `Weekly (${schedule.days.map((d) => DAY_NAMES[+d]).join(', ')})`
  return {
    storage: storageType.value === 'S3'
      ? `S3 · ${storage.s3_bucket}`
      : `${storageType.value} · ${storageType.value === 'NFS' ? storage.nfs_path : storage.smb_unc_path}`,
    hosts: hosts.value.map((h) => `${h.name} (${h.host_ip})`).join(', ') || '—',
    vms: `${count} selected`,
    schedule: `${freq} from ${fmt(start)}`
      + (schedule.stagger && count > 1 ? `, one VM every ${interval} min` : '')
      + (schedule.active ? '' : ' (jobs created inactive)'),
    window: schedule.stagger && count > 1 ? `${fmt(start)} – ${fmt(end)}` : '',
    cbt: (storageType.value !== 'S3' && schedule.cbt)
      ? `CBT on, full backup every ${schedule.cbtInterval} runs`
      : 'off — every run is a full backup',
  }
})
const vms = ref([])
const newHost = reactive({ name: '', host_ip: '', username: 'root', password: '', connection_type: 'auto' })
const schedule = reactive({ frequency: 'daily', days: ['0','1','2','3','4'], hour: 2, minute: 0, retention: 7, active: true, stagger: true, staggerInterval: 30, cbt: true, cbtInterval: 7 })
const dayLabels = [{ num: 0, lbl: 'Mo' }, { num: 1, lbl: 'Tu' }, { num: 2, lbl: 'We' }, { num: 3, lbl: 'Th' }, { num: 4, lbl: 'Fr' }, { num: 5, lbl: 'Sa' }, { num: 6, lbl: 'Su' }]

const storageStatusStyle = computed(() => ({
  background: storageStatusOk.value ? 'rgba(34,197,94,0.12)' : 'rgba(59,130,246,0.08)',
  color: storageStatusOk.value ? '#4ade80' : 'var(--text-muted)',
}))

const nextLabel = computed(() => {
  if (busy.value) return 'Working…'
  if (step.value === 4) return 'Apply & Finish'
  if (step.value === 5) return 'Go to Backup'
  return 'Continue'
})

watch(visible, async (open) => {
  if (!open) return
  step.value = 1
  error.value = ''
  storageStatus.value = ''
  try {
    hosts.value = await hostsApi.list()
    const cfg = await configApi.get()
    storageType.value = cfg.storage_type || 'NFS'
    Object.assign(storage, cfg)
    schedule.cbt = cfg.cbt_enabled !== false
    schedule.cbtInterval = cfg.cbt_full_interval || 7
  } catch { /* ignore */ }
})

function hostLabel(id) {
  const h = hosts.value.find((x) => x.id === id)
  return h ? h.name : `Host #${id}`
}

function onClose(skip) {
  if (step.value >= 5 && !skip) localStorage.setItem('setup_wizard_done', '1')
  close()
  document.body.style.overflow = ''
}

watch(visible, (v) => { document.body.style.overflow = v ? 'hidden' : '' })

function storagePayload() {
  const body = { storage_type: storageType.value }
  if (storageType.value === 'SMB') {
    body.smb_unc_path = storage.smb_unc_path
    body.smb_user = storage.smb_user
    if (storage.smb_password) body.smb_password = storage.smb_password
  } else if (storageType.value === 'NFS') {
    body.nfs_path = storage.nfs_path || '/mnt/backups'
  } else {
    body.s3_endpoint = storage.s3_endpoint
    body.s3_access_key = storage.s3_access_key
    if (storage.s3_secret_key) body.s3_secret_key = storage.s3_secret_key
    body.s3_bucket = storage.s3_bucket
    body.s3_region = storage.s3_region
  }
  return body
}

async function addHost() {
  if (hostAddBusy.value) return
  error.value = ''
  if (!newHost.name || !newHost.host_ip || !newHost.username || !newHost.password) {
    error.value = 'Fill in alias, host, username, and password.'
    return
  }
  // Without this try/catch the rejection is unhandled: the request fails, the
  // reason only ever reaches the devtools console, and the wizard looks idle.
  hostAddBusy.value = true
  try {
    const host = await hostsApi.create({ ...newHost })
    if (!hosts.value.some((h) => h.id === host.id)) hosts.value.push(host)
    newHost.password = ''
  } catch (e) {
    error.value = e.message || 'Could not add host.'
  } finally {
    hostAddBusy.value = false
  }
}

async function deleteHost(h) {
  const ok = await confirm(`Remove ${h.name} from VMExec?`, { title: 'Remove host', confirmText: 'Remove', danger: true })
  if (!ok) return
  await hostsApi.remove(h.id)
  hosts.value = hosts.value.filter((x) => x.id !== h.id)
}

function selectAllVms(on) {
  vms.value.forEach((v) => { v._selected = on })
}

async function next() {
  error.value = ''
  try {
    if (step.value === 5) {
      localStorage.setItem('setup_wizard_done', '1')
      onClose(true)
      router.push('/backup')
      return
    }
    busy.value = true
    if (step.value === 1) {
      storageStatus.value = 'Testing storage connection…'
      storageStatusOk.value = false
      await configApi.updateStorage(storagePayload())
      const test = await configApi.testStorage()
      if (!test.ok) throw new Error(test.message || 'Storage test failed')
      storageStatus.value = '✓ ' + test.message
      storageStatusOk.value = true
      step.value = 2
    } else if (step.value === 2) {
      if (!hosts.value.length) throw new Error('Add at least one ESXi host.')
      const warnings = []
      for (const h of hosts.value) {
        try { await hostsApi.sync(h.id) } catch (e) { warnings.push(`${h.name}: ${e.message}`) }
      }
      if (warnings.length === hosts.value.length) throw new Error('Could not discover VMs from any host.')
      const list = await jobsApi.vms()
      // If a selection already exists on the server, SHOW IT. Re-deriving ticks
      // from a name heuristic every visit meant re-opening the wizard silently
      // proposed a different selection than the one actually running, and
      // finishing it overwrote a working schedule. The heuristic is only a
      // first-run default now.
      const hasExisting = list.some((v) => v.is_selected)
      vms.value = list.map((v) => ({
        ...v,
        _selected: hasExisting ? !!v.is_selected : shouldProtectVm(v.vm_name),
      }))
      step.value = 3
      if (warnings.length) error.value = 'Some hosts could not be synced: ' + warnings.join('; ')
    } else if (step.value === 3) {
      if (!vms.value.some((v) => v._selected)) throw new Error('Select at least one VM to protect.')
      step.value = 4
    } else if (step.value === 4) {
      await applySchedule()
      step.value = 5
    }
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    busy.value = false
  }
}

async function applySchedule() {
  const selected = vms.value.filter((v) => v._selected)
  const days = schedule.frequency === 'daily' ? '0,1,2,3,4,5,6' : (schedule.days.length ? schedule.days.join(',') : '0,1,2,3,4,5,6')
  if (schedule.frequency === 'weekly' && !schedule.days.length) throw new Error('Pick at least one day for a weekly schedule.')

  const cbtEnabled = storageType.value !== 'S3' && schedule.cbt
  await configApi.update({ cbt_enabled: cbtEnabled, cbt_full_interval: schedule.cbtInterval })

  // Write ONLY what changed. This loop used to PATCH every row it knew about,
  // so finishing the wizard from a page with nothing ticked (a stale tab, or a
  // click on "None") blanket-deselected every scheduled job in the database.
  // A deselect is now sent only for rows the SERVER currently has selected.
  let updated = 0
  let deselected = 0
  for (const v of vms.value) {
    if (v._selected) {
      await jobsApi.patch(v.id, {
        is_selected: true,
        is_job_active: schedule.active,
        schedule_hour: schedule.hour,
        schedule_minute: schedule.minute,
        retention_count: schedule.retention,
        schedule_frequency: schedule.frequency,
        schedule_days: days,
        power_off_for_backup: false,
        cbt_enabled: cbtEnabled,
      })
      updated++
    } else if (v.is_selected) {
      await jobsApi.patch(v.id, { is_selected: false, is_job_active: false })
      deselected++
    }
  }
  // The old per-host hour offset was a no-op in the common case of a single
  // registered vCenter: every VM shares one host, so nothing staggered and all
  // jobs fired at the same minute. Use the backend's per-VM stagger, which
  // spreads jobs at max_schedules_per_hour anchored at the chosen start time.
  if (schedule.stagger && updated > 0) {
    await jobsApi.inventoryApply({ updates: [], restagger: true, base_hour: schedule.hour, base_minute: schedule.minute, interval_minutes: schedule.staggerInterval || 30 })
  }
  summary.value = `Configured ${updated} VM(s) for scheduled backups`
    + (deselected ? `, removed ${deselected} from the schedule` : '')
    + (schedule.stagger && updated > 1 ? ', start times staggered' : '') + '.'

}
</script>
