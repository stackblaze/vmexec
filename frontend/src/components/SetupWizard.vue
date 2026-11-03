<template>
  <div v-if="visible" class="fixed inset-0 z-[120] flex items-center justify-center p-3" role="dialog" aria-modal="true" aria-labelledby="wizard-title">
    <div class="absolute inset-0 bg-black/55 backdrop-blur-[2px]" @click="onClose"></div>
    <div class="relative w-full max-w-5xl max-h-[calc(100vh-1.5rem)] flex flex-col overflow-hidden rounded-lg bg-card border border-border shadow-card">
      <div class="flex flex-wrap justify-between items-center gap-4 px-6 py-4 border-b border-border">
        <div>
          <h2 id="wizard-title" class="text-xl font-bold m-0">Set up backups</h2>
          <p class="text-xs text-muted mt-0.5 mb-0">Two steps. Storage and vCenter were set up by install.sh.</p>
        </div>
        <ol aria-label="Steps" class="list-none m-0 p-0 flex gap-2 text-xs">
          <li
            v-for="(name, i) in ['Choose VMs', 'Choose policy']"
            :key="name"
            :aria-current="step === i + 1 ? 'step' : undefined"
            class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full"
            :class="step === i + 1 ? 'bg-brand/10 font-semibold text-main' : 'text-muted'"
          >
            <span
              class="w-5 h-5 rounded-full inline-flex items-center justify-center text-[0.6875rem]"
              :class="step === i + 1 ? 'bg-brand text-white' : step > i + 1 ? 'bg-emerald-500 text-white' : 'border border-border'"
            >{{ step > i + 1 ? '✓' : i + 1 }}</span>{{ name }}
          </li>
        </ol>
      </div>

      <div aria-label="Checks" class="flex flex-wrap gap-x-7 gap-y-1.5 px-6 py-3 bg-nav border-b border-border text-xs">
        <span v-for="c in checks" :key="c.label" class="inline-flex items-center gap-2">
          <span class="w-2 h-2 rounded-full" :class="c.ok === null ? 'bg-slate-400' : c.ok ? 'bg-emerald-500' : 'bg-red-500'" aria-hidden="true"></span>
          {{ c.label }}
        </span>
      </div>

      <div v-if="error" class="px-6 py-3 text-sm border-b border-red-500/25 bg-red-500/10 text-red-700 dark:text-red-400" role="alert">{{ error }}</div>

      <!-- Step 1: VMs -->
      <div v-if="step === 1" class="flex-1 min-h-0 overflow-y-auto px-6 py-5 space-y-3">
        <div v-if="!hosts.length" class="text-sm">
          No vCenter is connected yet.
          <RouterLink to="/settings/vcenter" class="text-brand" @click="onClose">Connect it in Settings → vCenter</RouterLink>,
          then come back.
        </div>
        <template v-else>
          <div class="flex flex-wrap items-center gap-3">
            <label class="flex-1 min-w-[14rem]">
              <span class="sr-only">Search VMs</span>
              <input v-model="search" type="search" :placeholder="`Search ${vms.length} VMs…`" class="w-full py-2 px-3 text-sm" />
            </label>
            <span class="text-xs text-muted">{{ picked.size }} selected</span>
            <button type="button" class="text-xs text-brand bg-transparent border-0 cursor-pointer" :disabled="refreshing" @click="refreshVms">
              {{ refreshing ? 'Refreshing…' : 'Refresh VM list' }}
            </button>
          </div>
          <div class="rounded-md border border-border divide-y divide-border">
            <label
              v-for="vm in shown"
              :key="vm.id"
              class="flex items-center gap-3 min-h-12 px-3.5 text-sm cursor-pointer hover:bg-blue-500/[0.04]"
            >
              <input type="checkbox" class="w-4 h-4 accent-brand" :checked="picked.has(vm.id)" @change="toggle(vm.id, $event.target.checked)" />
              <span class="flex-1 min-w-0 truncate">{{ vm.vm_name }}</span>
              <span class="text-xs text-muted whitespace-nowrap">
                {{ vm.storage_gb ? `${vm.storage_gb} GB` : '' }}{{ vm.storage_gb && neverOff.has(vm.vm_name) ? ' · ' : '' }}{{ neverOff.has(vm.vm_name) ? 'never powered off' : '' }}{{ vm.policy_name ? ` · now ${vm.policy_name}` : '' }}
              </span>
            </label>
            <p v-if="!shown.length" class="px-3.5 py-6 text-sm text-muted text-center m-0">
              {{ vms.length ? 'No VMs match.' : 'No VMs found yet. Refresh the VM list.' }}
            </p>
          </div>
        </template>
      </div>

      <!-- Step 2: policy -->
      <div v-else class="flex-1 min-h-0 overflow-y-auto px-6 py-5 space-y-3">
        <p v-if="added.length" class="text-sm m-0">Protect <strong>{{ added.length }} new VM{{ added.length === 1 ? '' : 's' }}</strong> with:</p>
        <p v-else class="text-sm m-0">No new VMs picked. VMs that are already protected keep their policy.</p>
        <p v-if="removed.length" class="text-sm m-0 text-amber-700 dark:text-amber-400">
          Stop protecting {{ removed.length }} VM{{ removed.length === 1 ? '' : 's' }}: {{ removed.map((v) => v.vm_name).join(', ') }}. Their restore points are kept.
        </p>
        <div v-if="added.length" class="grid gap-3 grid-cols-[repeat(auto-fit,minmax(15rem,1fr))]" role="radiogroup" aria-label="Policy">
          <label
            v-for="p in policies"
            :key="p.id"
            class="block rounded-lg border-2 px-4 py-3 cursor-pointer bg-card"
            :class="policyId === p.id ? 'border-brand' : 'border-border hover:border-brand/50'"
          >
            <input v-model="policyId" type="radio" name="policy" :value="p.id" class="sr-only" />
            <span class="block text-sm font-semibold">{{ p.name }}</span>
            <span class="block text-xs text-muted mt-0.5">{{ p.summary }}</span>
          </label>
        </div>
        <p class="text-xs text-muted m-0">Always incremental. Start times are spread out for you. Policies are edited in Settings → Policies.</p>
      </div>

      <div class="flex flex-wrap justify-end gap-3 px-6 py-4 border-t border-border">
        <button v-if="step === 2" type="button" :class="btnSecondary" @click="step = 1">Back</button>
        <div class="flex-1"></div>
        <button type="button" :class="btnSecondary" @click="onClose">{{ step === 1 ? 'Skip for now' : 'Cancel' }}</button>
        <button
          v-if="step === 1"
          type="button"
          :class="btnPrimary"
          :disabled="!added.length && !removed.length"
          @click="step = 2"
        >Next: choose policy</button>
        <button v-else type="button" :class="btnPrimary" :disabled="busy || (added.length && !policyId)" @click="finish">
          {{ busy ? 'Saving…' : finishLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { hostsApi, jobsApi, policiesApi, statusApi } from '@/api/client'
import { useSetupWizard } from '@/composables/useSetupWizard'

const btnPrimary =
  'inline-flex items-center justify-center rounded-md border-0 bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-55 disabled:cursor-not-allowed'
const btnSecondary =
  'inline-flex items-center justify-center rounded-md border border-btn-sec-border bg-btn-sec px-4 py-2 text-sm text-btn-sec-text hover:bg-btn-sec-hover'

const { visible, close } = useSetupWizard()

const step = ref(1)
const hosts = ref([])
const vms = ref([])
const policies = ref([])
const status = ref(null)
const picked = ref(new Set())
const policyId = ref(null)
const search = ref('')
const busy = ref(false)
const refreshing = ref(false)
const error = ref('')

const neverOff = computed(() => new Set(status.value?.never_powered_off || []))

const checks = computed(() => {
  const s = status.value
  const vc = s?.vcenters || []
  return [
    { label: s ? (s.storage.healthy ? 'Storage: ZeroFS on S3, healthy' : 'Storage not available') : 'Storage…', ok: s ? s.storage.healthy : null },
    { label: vc.length ? (vc.every((v) => v.reachable) ? 'vCenter connected' : 'vCenter not reachable') : 'No vCenter', ok: s ? vc.length > 0 && vc.every((v) => v.reachable) : null },
    { label: s && s.problems.some((p) => p.kind === 'vddk') ? 'VDDK not installed' : 'VDDK installed', ok: s ? !s.problems.some((p) => p.kind === 'vddk') : null },
    { label: s?.storage?.encrypted ? 'Backups encrypted' : 'Encryption unknown', ok: s ? !!s.storage.encrypted : null },
  ]
})

const added = computed(() => vms.value.filter((v) => picked.value.has(v.id) && !v.policy_id))
const removed = computed(() => vms.value.filter((v) => !picked.value.has(v.id) && v.policy_id))
const finishLabel = computed(() => {
  if (added.value.length) return `Protect ${added.value.length} VM${added.value.length === 1 ? '' : 's'}`
  return `Stop protecting ${removed.value.length}`
})

const shown = computed(() => {
  const q = search.value.toLowerCase()
  return vms.value.filter((v) => !q || v.vm_name.toLowerCase().includes(q))
})

function toggle(id, on) {
  const s = new Set(picked.value)
  if (on) s.add(id); else s.delete(id)
  picked.value = s
}

async function load() {
  error.value = ''
  try {
    const [h, v, p, s] = await Promise.all([hostsApi.list(), jobsApi.vms(), policiesApi.list(), statusApi.get()])
    hosts.value = h
    vms.value = v
    policies.value = p
    status.value = s
    picked.value = new Set(v.filter((x) => x.policy_id).map((x) => x.id))
    if (!policyId.value && p.length) policyId.value = p[0].id
  } catch (e) {
    error.value = e.message || 'Could not load.'
  }
}

async function refreshVms() {
  refreshing.value = true
  try {
    for (const h of hosts.value) await hostsApi.sync(h.id)
    vms.value = await jobsApi.vms()
  } catch (e) {
    error.value = e.message || 'Could not refresh the VM list.'
  } finally {
    refreshing.value = false
  }
}

async function finish() {
  busy.value = true
  error.value = ''
  try {
    if (added.value.length) await policiesApi.assign(added.value.map((v) => v.id), policyId.value)
    if (removed.value.length) await policiesApi.assign(removed.value.map((v) => v.id), null)
    localStorage.setItem('setup_wizard_done', '1')
    onClose()
  } catch (e) {
    error.value = e.message || 'Could not save.'
  } finally {
    busy.value = false
  }
}

function onClose() {
  close()
  document.body.style.overflow = ''
}

watch(visible, (open) => {
  document.body.style.overflow = open ? 'hidden' : ''
  if (open) {
    step.value = 1
    search.value = ''
    load()
  }
})
</script>
