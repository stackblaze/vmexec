<template>
  <div class="space-y-3">
    <!-- Red banner: only when something is wrong (paused has its own bar). -->
    <div
      v-for="p in errors"
      :key="p.kind + (p.vm_name || '')"
      role="alert"
      class="flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 rounded-lg border border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300"
    >
      <svg class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10" /><path stroke-linecap="round" d="M12 8v4m0 4h.01" /></svg>
      <span class="flex-1 min-w-[16rem] text-sm">{{ p.message }}</span>
      <button
        v-if="p.kind === 'backup'"
        type="button"
        class="text-sm font-semibold underline underline-offset-2 bg-transparent border-0 p-0 cursor-pointer text-inherit"
        @click="$emit('show-failed')"
      >Show failed</button>
      <RouterLink
        v-else-if="p.kind === 'storage' || p.kind === 'vcenter'"
        :to="p.kind === 'storage' ? '/settings/storage' : '/settings/vcenter'"
        class="text-sm font-semibold underline underline-offset-2 text-inherit"
      >Details</RouterLink>
    </div>

    <div
      aria-label="Backup status"
      class="flex flex-wrap items-center gap-y-2 px-4 py-2.5 rounded-lg border border-border bg-card text-sm"
    >
      <button
        type="button"
        class="pr-4 mr-4 border-0 border-r border-solid border-border bg-transparent p-0 text-left cursor-pointer text-main"
        :disabled="!status || !status.last24h.failed"
        @click="$emit('show-failed')"
      >
        Last 24 h:
        <strong class="font-semibold text-emerald-600 dark:text-emerald-400">{{ status?.last24h.succeeded ?? '–' }} succeeded</strong>,
        <strong class="font-semibold" :class="status?.last24h.failed ? 'text-red-600 dark:text-red-400' : 'text-muted'">{{ status?.last24h.failed ?? '–' }} failed</strong>
      </button>
      <span class="pr-4 mr-4 border-r border-border">Next run: {{ nextRunText }}</span>
      <RouterLink to="/settings/storage" class="inline-flex items-center gap-2 pr-4 mr-4 border-r border-border no-underline text-main">
        <span class="w-2 h-2 rounded-full" :class="storageDot" aria-hidden="true"></span>
        {{ storageText }}
      </RouterLink>
      <RouterLink to="/settings/storage" class="no-underline text-main">
        {{ status?.storage?.cache ? `Cache ${status.storage.cache.used_gb} of ${status.storage.cache.total_gb} GB` : 'Storage details' }}
      </RouterLink>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { statusApi } from '@/api/client'

defineEmits(['show-failed'])
const props = defineProps({ refreshKey: { type: Number, default: 0 } })

const status = ref(null)
let timer = null

const errors = computed(() => (status.value?.problems || []).filter((p) => p.severity === 'error'))

const nextRunText = computed(() => {
  const n = status.value?.next_run
  if (!n) return '…'
  return n.vm_count > 1 ? `${n.label} · ${n.vm_count} VMs` : n.label
})

const storageText = computed(() => {
  const s = status.value?.storage
  if (!s) return 'Storage…'
  if (s.healthy) return 'Storage healthy'
  return 'Storage unavailable'
})
const storageDot = computed(() => {
  const s = status.value?.storage
  if (!s) return 'bg-slate-400'
  return s.healthy ? 'bg-emerald-500' : 'bg-red-500'
})

async function load() {
  try {
    status.value = await statusApi.get()
  } catch {
    /* keep the last status */
  }
}

defineExpose({ load })

onMounted(() => {
  load()
  timer = setInterval(load, 30000)
})
onUnmounted(() => clearInterval(timer))
// a parent action (run, policy change) asks for a refresh by bumping refreshKey
watch(() => props.refreshKey, load)
</script>
