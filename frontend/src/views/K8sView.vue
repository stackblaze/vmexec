<template>
  <div class="max-w-7xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h1 class="text-xl font-bold">Kubernetes</h1>
        <p class="text-xs text-muted mt-0.5">State-level backups: etcd / datastore snapshots per cluster. Node VMs stay unimaged — rebuild them from templates, restore state from here.</p>
      </div>
      <button type="button" :class="btnPrimary" class="px-3 py-1.5 text-sm" @click="showAdd = true">Register cluster</button>
    </div>

    <!-- Clusters — click a name to open its jobs -->
    <div class="rounded-lg border border-border bg-card shadow-card overflow-x-auto">
      <table class="w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th v-for="h in ['Cluster', 'Jobs', 'Last run', 'Status', 'Actions']" :key="h"
                class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav whitespace-nowrap">{{ h }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!clusters.length">
            <td colspan="5" class="px-4 py-8 text-center text-muted text-xs">
              No clusters registered. Register one with its kubeconfig to start snapshotting etcd.
            </td>
          </tr>
          <tr v-for="c in clusters" :key="c.id" class="hover:bg-nav/50">
            <td class="px-4 py-3 border-b border-border font-medium align-middle">
              <button type="button" class="text-brand hover:underline" @click="openCluster(c)">{{ c.name }}</button>
            </td>
            <td class="px-4 py-3 border-b border-border text-xs text-muted align-middle">{{ (c.targets || []).length }} job(s)</td>
            <td class="px-4 py-3 border-b border-border text-xs font-mono text-muted whitespace-nowrap align-middle">{{ c.last_backup ? formatDate(c.last_backup) : '—' }}</td>
            <td class="px-4 py-3 border-b border-border text-xs align-middle">
              <span v-if="c.current_action" class="text-brand">{{ c.current_action }}</span>
              <span v-else :class="c.last_status === 'Success' ? 'text-emerald-500' : (c.last_status === 'Failed' ? 'text-red-500' : 'text-muted')">{{ c.last_status }}</span>
            </td>
            <td class="px-4 py-3 border-b border-border whitespace-nowrap align-middle">
              <div class="flex items-center justify-end gap-1">
                <button type="button" :class="btnIconSecondary" title="Cluster menu" @click="toggleMenu(c.id, $event)">⋯</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Schedule drawer -->
    <div v-if="sched" class="fixed inset-0 z-80">
      <div class="absolute inset-0 bg-black/45 backdrop-blur-[1px]" @click="sched = null"></div>
      <aside class="absolute top-0 right-0 bottom-0 w-full max-w-md flex flex-col bg-card border-l border-border shadow-[-4px_0_24px_rgba(0,0,0,0.18)]" role="dialog">
        <div class="flex items-center justify-between gap-3 px-4 pt-4 pb-3 border-b border-border bg-nav shrink-0">
          <div class="min-w-0">
            <h3 class="text-base font-semibold leading-tight m-0 truncate">Schedule &amp; retention</h3>
            <p class="text-sm font-mono text-brand mt-0.5 truncate">{{ sched.name }} / {{ sched.target }}</p>
          </div>
          <button type="button" class="shrink-0 p-1.5 rounded-md text-muted border border-border bg-transparent cursor-pointer hover:text-main hover:bg-card" aria-label="Close" @click="sched = null">
            <svg class="w-4 h-4 block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
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
              <option :value="1">1 hour</option>
              <option :value="2">2 hours</option>
              <option :value="3">3 hours</option>
              <option :value="6">6 hours</option>
              <option :value="12">12 hours</option>
            </select>
          </div>
          <div class="grid grid-cols-3 gap-2">
            <div>
              <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Anchor hour</span>
              <input v-model.number="sched.schedule_hour" type="number" min="0" max="23" class="w-full py-1.5 px-2 text-center font-mono" />
            </div>
            <div>
              <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Minute</span>
              <input v-model.number="sched.schedule_minute" type="number" min="0" max="59" class="w-full py-1.5 px-2 text-center font-mono" />
            </div>
            <div>
              <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Keep</span>
              <input v-model.number="sched.retention_count" type="number" min="1" max="336" class="w-full py-1.5 px-2 text-center font-mono" />
            </div>
          </div>
          <label class="flex items-center gap-2 cursor-pointer">
            <input v-model="sched.is_job_active" type="checkbox" />
            <span :class="sched.is_job_active ? 'text-emerald-600' : 'text-muted'">{{ sched.is_job_active ? 'Active — snapshots run on schedule' : 'Paused — no scheduled snapshots' }}</span>
          </label>
          <div class="rounded-lg border border-border bg-nav p-2 font-mono text-[0.7rem] text-muted">
            {{ sched.schedule_frequency === 'interval' ? `Every ${sched.interval_hours}h` : 'Daily' }}
            at {{ String(sched.schedule_hour).padStart(2,'0') }}:{{ String(sched.schedule_minute).padStart(2,'0') }} ·
            keep {{ sched.retention_count }}
            <template v-if="sched.schedule_frequency === 'interval'"> ({{ (sched.retention_count * sched.interval_hours / 24).toFixed(1) }} days of history)</template>
          </div>
          <button type="button" :class="btnPrimary" class="w-full px-3 py-2 font-semibold" :disabled="savingSched" @click="saveSchedule">{{ savingSched ? 'Saving…' : 'Save schedule' }}</button>
        </div>
      </aside>
    </div>

    <!-- Snapshots drawer -->
    <div v-if="detail" class="fixed inset-0 z-80">
      <div class="absolute inset-0 bg-black/45 backdrop-blur-[1px]" @click="detail = null"></div>
      <aside class="absolute top-0 right-0 bottom-0 w-full max-w-md flex flex-col bg-card border-l border-border shadow-[-4px_0_24px_rgba(0,0,0,0.18)]" role="dialog">
        <div class="flex items-center justify-between gap-3 px-4 pt-4 pb-3 border-b border-border bg-nav shrink-0">
          <div class="min-w-0">
            <h3 class="text-base font-semibold leading-tight m-0 truncate">Snapshots</h3>
            <p class="text-sm font-mono text-brand mt-0.5 truncate">{{ detail.cluster }}</p>
          </div>
          <button type="button" class="shrink-0 p-1.5 rounded-md text-muted border border-border bg-transparent cursor-pointer hover:text-main hover:bg-card" aria-label="Close" @click="detail = null">
            <svg class="w-4 h-4 block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-4">
          <div v-for="t in detail.targets" :key="t.target">
            <span class="block text-xs font-semibold uppercase tracking-wide text-muted mb-2">{{ t.target }} · {{ t.points.length }} point(s)</span>
            <div class="rounded-lg border border-border overflow-hidden">
              <div v-for="p in [...t.points].reverse().slice(0, 12)" :key="p.id" class="flex items-center gap-3 px-3 py-1.5 text-xs font-mono border-b border-border last:border-b-0">
                <span class="text-muted">{{ p.id }}</span>
                <span class="ml-auto tabular-nums">{{ p.size_bytes ? (p.size_bytes / 1048576).toFixed(1) + ' MB' : '?' }}</span>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>

    <!-- k3s management-etcd S3 drawer -->
    <div v-if="k3s" class="fixed inset-0 z-80">
      <div class="absolute inset-0 bg-black/45 backdrop-blur-[1px]" @click="k3s = null"></div>
      <aside class="absolute top-0 right-0 bottom-0 w-full max-w-md flex flex-col bg-card border-l border-border shadow-[-4px_0_24px_rgba(0,0,0,0.18)]" role="dialog">
        <div class="flex items-center justify-between gap-3 px-4 pt-4 pb-3 border-b border-border bg-nav shrink-0">
          <div class="min-w-0">
            <h3 class="text-base font-semibold leading-tight m-0 truncate">Management etcd (k3s)</h3>
            <p class="text-sm font-mono text-brand mt-0.5 truncate">{{ k3s.clusterName }}</p>
          </div>
          <button type="button" class="shrink-0 p-1.5 rounded-md text-muted border border-border bg-transparent cursor-pointer hover:text-main hover:bg-card" aria-label="Close" @click="k3s = null">
            <svg class="w-4 h-4 block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-4 text-xs">
          <div v-if="!k3s.status" class="text-muted">Loading…</div>
          <template v-else>
            <div v-if="!k3s.status.nodes.length" class="text-muted">No k3s embedded-etcd nodes detected on this cluster.</div>
            <template v-else>
              <div class="rounded-lg border border-emerald-500/25 bg-emerald-500/8 p-3">
                This etcd is already backed up hourly by the <strong>management-etcd</strong> target above. This panel additionally enables k3s's own snapshot upload to S3 — first-party belt-and-braces.
              </div>
              <div>
                <span class="block font-semibold uppercase tracking-wide text-muted mb-2">Nodes · local snapshots</span>
                <div class="rounded-lg border border-border overflow-hidden">
                  <div v-for="n in k3s.status.nodes" :key="n.name" class="flex items-center gap-3 px-3 py-1.5 font-mono border-b border-border last:border-b-0">
                    <span>{{ n.name }}</span>
                    <span class="ml-auto text-muted">{{ n.last_local_snapshot || 'none' }}</span>
                  </div>
                </div>
              </div>
              <div>
                <span class="block font-semibold uppercase tracking-wide text-muted mb-1">S3 upload secret</span>
                <span :class="k3s.status.secret_present ? 'text-emerald-500' : 'text-amber-500'" class="font-semibold">{{ k3s.status.secret_present ? 'configured' : 'not configured' }}</span>
                <span v-if="k3s.status.bucket_error" class="text-red-500 ml-2">{{ k3s.status.bucket_error }}</span>
              </div>
              <div v-if="k3s.status.bucket_objects && k3s.status.bucket_objects.length">
                <span class="block font-semibold uppercase tracking-wide text-muted mb-2">Latest uploads</span>
                <div class="rounded-lg border border-border overflow-hidden font-mono">
                  <div v-for="o in k3s.status.bucket_objects" :key="o.key" class="px-3 py-1.5 border-b border-border last:border-b-0">{{ o.modified.slice(0, 16) }} · {{ (o.size / 1048576).toFixed(1) }} MB</div>
                </div>
              </div>
              <div v-else-if="k3s.status.secret_present && !k3s.status.bucket_error" class="rounded-lg border border-amber-500/25 bg-amber-500/8 p-3 text-amber-600">
                Secret configured, but no uploads yet — the node config fragment below must still be applied (one k3s restart per node).
              </div>
              <button type="button" :class="btnPrimary" class="w-full px-3 py-2 font-semibold" :disabled="k3sApplying" @click="applyK3sFromSecondary">
                {{ k3sApplying ? 'Applying…' : 'Configure from secondary-copy credentials' }}
              </button>
              <details>
                <summary class="cursor-pointer text-muted">Enter credentials manually</summary>
                <div class="grid grid-cols-1 gap-2 mt-2">
                  <input v-model="k3sForm.endpoint" type="text" placeholder="s3 endpoint (e2)" class="py-1.5 px-2 font-mono" />
                  <input v-model="k3sForm.access_key" type="text" placeholder="access key" class="py-1.5 px-2 font-mono" />
                  <input v-model="k3sForm.secret_key" type="password" placeholder="secret key" class="py-1.5 px-2 font-mono" />
                  <input v-model="k3sForm.bucket" type="text" placeholder="bucket" class="py-1.5 px-2 font-mono" />
                  <input v-model="k3sForm.folder" type="text" placeholder="folder" class="py-1.5 px-2 font-mono" />
                  <input v-model="k3sForm.schedule_cron" type="text" placeholder="cron (0 */6 * * *)" class="py-1.5 px-2 font-mono" />
                  <button type="button" :class="btnSecondary" class="px-3 py-1.5" :disabled="k3sApplying" @click="applyK3s">Apply S3 secret to cluster</button>
                </div>
              </details>
              <div v-if="k3s.fragment">
                <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Final host-level step</span>
                <p class="text-muted mb-2">Secret {{ k3s.secretAction }}. Drop this on each etcd node as <code>/etc/rancher/k3s/config.yaml.d/etcd-s3.yaml</code>, then <code>systemctl restart k3s</code> one node at a time:</p>
                <pre class="text-[0.65rem] font-mono p-2 rounded border border-border bg-nav overflow-x-auto">{{ k3s.fragment }}</pre>
                <p class="text-amber-500 mt-1">Also save <code>/var/lib/rancher/k3s/server/token</code> off-cluster — restores onto new nodes require it.</p>
              </div>
            </template>
          </template>
        </div>
      </aside>
    </div>

    <!-- Cluster menu (teleported to escape table overflow clipping) -->
    <Teleport to="body">
      <div v-if="menu" data-cluster-menu class="fixed z-[90] w-52 rounded-md border border-border bg-card shadow-lg py-1"
           :style="{ top: menu.y + 'px', left: menu.x + 'px' }">
        <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-xs text-left hover:bg-nav" @click="menuAction(openCluster, menu.c)"><span class="w-4 text-center">☰</span> Open jobs</button>
        <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-xs text-left hover:bg-nav" @click="menuAction(startRename, menu.c)"><span class="w-4 text-center">✎</span> Rename cluster</button>
        <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-xs text-left hover:bg-nav" @click="menuAction(testCluster, menu.c)"><span class="w-4 text-center">✓</span> Test connectivity</button>
        <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-xs text-left hover:bg-nav" @click="menuAction(openManagementK3s, menu.c)"><span class="w-4 text-center">S3</span> Management etcd (k3s)</button>
        <div class="my-1 border-t border-border"></div>
        <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-xs text-left text-red-500 hover:bg-red-500/8" @click="menuAction(removeCluster, menu.c)"><span class="w-4 text-center">✕</span> Remove cluster</button>
      </div>
    </Teleport>

    <!-- Rename modal -->
    <div v-if="renaming" class="fixed inset-0 z-40 flex items-center justify-center bg-black/50">
      <div class="w-full max-w-sm rounded-lg border border-border bg-card p-5 shadow-xl">
        <h2 class="text-base font-semibold mb-3">Rename cluster</h2>
        <input v-model="renameValue" type="text" class="w-full py-2 px-3 text-sm mb-4" @keyup.enter="saveRename" />
        <div class="flex justify-end gap-2">
          <button type="button" :class="btnSecondary" class="px-3 py-1.5 text-sm" @click="renaming = null">Cancel</button>
          <button type="button" :class="btnPrimary" class="px-3 py-1.5 text-sm" :disabled="savingRename" @click="saveRename">{{ savingRename ? 'Saving…' : 'Rename' }}</button>
        </div>
      </div>
    </div>

    <!-- Register cluster modal — identity only -->
    <!-- No click-outside dismiss: the form holds a pasted kubeconfig -->
    <div v-if="showAdd" class="fixed inset-0 z-40 flex items-center justify-center bg-black/50">
      <div class="w-full max-w-3xl rounded-lg border border-border bg-card p-6 shadow-xl">
        <h2 class="text-base font-semibold mb-1">Register Kubernetes cluster</h2>
        <p class="text-xs text-muted mb-4">Register the cluster by kubeconfig, then add snapshot jobs to it.</p>
        <div class="mb-3">
          <span class="block text-xs font-semibold uppercase text-muted mb-1">Name</span>
          <input v-model="form.name" type="text" placeholder="kmj-management" class="w-full py-1.5 px-3 text-sm" />
        </div>
        <div class="mb-4">
          <span class="block text-xs font-semibold uppercase text-muted mb-1">Kubeconfig (stored encrypted)</span>
          <textarea v-model="form.kubeconfig" rows="14" class="w-full py-1.5 px-3 text-xs font-mono" placeholder="apiVersion: v1&#10;kind: Config&#10;..."></textarea>
        </div>
        <div class="flex justify-end gap-2">
          <button type="button" :class="btnSecondary" class="px-3 py-1.5 text-sm" @click="showAdd = false">Cancel</button>
          <button type="button" :class="btnPrimary" class="px-3 py-1.5 text-sm" :disabled="saving" @click="createCluster">{{ saving ? 'Saving…' : 'Register' }}</button>
        </div>
      </div>
    </div>

    <!-- Create job (snapshot target) modal -->
    <div v-if="jobModal" class="fixed inset-0 z-40 flex items-center justify-center bg-black/50">
      <div class="w-full max-w-2xl rounded-lg border border-border bg-card p-6 shadow-xl">
        <h2 class="text-base font-semibold mb-1">Create snapshot job</h2>
        <p class="text-xs text-muted mb-4">On cluster <span class="font-mono text-brand">{{ jobModal.clusterName }}</span></p>
        <div class="grid grid-cols-2 gap-3 mb-3">
          <div>
            <span class="block text-xs font-semibold uppercase text-muted mb-1">Job name</span>
            <input v-model="jobForm.name" type="text" placeholder="tenant-datastore" class="w-full py-1.5 px-3 text-sm font-mono" />
          </div>
          <div>
            <span class="block text-xs font-semibold uppercase text-muted mb-1">Type</span>
            <select v-model="jobForm.profile" class="w-full py-1.5 px-3 text-sm">
              <option value="kamaji">kamaji-etcd (datastore snapshot)</option>
              <option value="k3s">k3s etcd (host snapshot)</option>
              <option value="tenants">tenants (per-tenant export)</option>
              <option value="kubeadm">kubeadm etcd</option>
              <option value="custom">custom</option>
            </select>
          </div>
        </div>
        <div v-if="!['tenants','k3s'].includes(jobForm.profile)" class="grid grid-cols-2 gap-3 mb-3">
          <div>
            <span class="block text-xs font-semibold uppercase text-muted mb-1">Namespace <span class="normal-case text-muted/70">(optional)</span></span>
            <input v-model="jobForm.namespace" type="text" placeholder="profile default" class="w-full py-1.5 px-3 text-sm font-mono" />
          </div>
          <div>
            <span class="block text-xs font-semibold uppercase text-muted mb-1">Label selector <span class="normal-case text-muted/70">(optional)</span></span>
            <input v-model="jobForm.selector" type="text" placeholder="profile default" class="w-full py-1.5 px-3 text-sm font-mono" />
          </div>
        </div>
        <div class="grid grid-cols-4 gap-3 mb-4">
          <div>
            <span class="block text-xs font-semibold uppercase text-muted mb-1">Frequency</span>
            <select v-model="jobForm.schedule_frequency" class="w-full py-1.5 px-2 text-sm">
              <option value="interval">Every N h</option>
              <option value="daily">Daily</option>
            </select>
          </div>
          <div v-if="jobForm.schedule_frequency === 'interval'">
            <span class="block text-xs font-semibold uppercase text-muted mb-1">Every</span>
            <select v-model.number="jobForm.interval_hours" class="w-full py-1.5 px-2 text-sm">
              <option :value="1">1 h</option><option :value="2">2 h</option><option :value="3">3 h</option><option :value="6">6 h</option><option :value="12">12 h</option>
            </select>
          </div>
          <div>
            <span class="block text-xs font-semibold uppercase text-muted mb-1">Anchor</span>
            <input v-model.number="jobForm.schedule_hour" type="number" min="0" max="23" class="w-full py-1.5 px-2 text-center text-sm font-mono" />
          </div>
          <div>
            <span class="block text-xs font-semibold uppercase text-muted mb-1">Keep</span>
            <input v-model.number="jobForm.retention_count" type="number" min="1" max="336" class="w-full py-1.5 px-2 text-center text-sm font-mono" />
          </div>
        </div>
        <div class="flex justify-end gap-2">
          <button type="button" :class="btnSecondary" class="px-3 py-1.5 text-sm" @click="jobModal = null">Cancel</button>
          <button type="button" :class="btnPrimary" class="px-3 py-1.5 text-sm" :disabled="savingJob" @click="createJob">{{ savingJob ? 'Saving…' : 'Create job' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { k8sApi } from '@/api/client'
import { useModal } from '@/composables/useModal'

const btnPrimary =
  'inline-flex items-center justify-center rounded-md border-0 bg-brand text-white hover:bg-brand-hover transition-colors duration-200 disabled:opacity-55'
const btnSecondary =
  'inline-flex items-center justify-center rounded-md border border-btn-sec-border bg-btn-sec text-btn-sec-text hover:bg-btn-sec-hover transition-colors duration-200'
const btnIconSecondary =
  'inline-flex items-center justify-center w-8 h-8 rounded-md transition-colors duration-200 disabled:opacity-55 shrink-0 border border-btn-sec-border bg-btn-sec text-btn-sec-text hover:bg-btn-sec-hover'

const { confirm, alert } = useModal()
const router = useRouter()

function openCluster(c) {
  router.push(`/kubernetes/${c.id}`)
}
function openManagementK3s(c) {
  router.push(`/kubernetes/${c.id}?k3s=1`)
}

const renaming = ref(null)
const renameValue = ref('')
const savingRename = ref(false)
function startRename(c) {
  renaming.value = c
  renameValue.value = c.name
}
async function saveRename() {
  const name = renameValue.value.trim()
  if (!name || name === renaming.value.name) { renaming.value = null; return }
  savingRename.value = true
  try {
    await k8sApi.patch(renaming.value.id, { name })
    renaming.value = null
    await load()
  } catch (e) {
    await alert(String(e.message || e), { title: 'Rename failed' })
  } finally {
    savingRename.value = false
  }
}

const clusters = ref([])
const menu = ref(null)  // { c, x, y }
const expanded = ref(null)
const showAdd = ref(false)

function toggleExpand(id) {
  expanded.value = expanded.value === id ? null : id
}

function toggleMenu(id, ev) {
  if (menu.value && menu.value.c.id === id) { menu.value = null; return }
  const c = clusters.value.find((x) => x.id === id)
  const rect = ev.currentTarget.getBoundingClientRect()
  // right-align a 208px (w-52) menu under the button, kept on-screen
  const width = 208
  const x = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))
  menu.value = { c, x, y: rect.bottom + 4 }
}
function menuAction(fn, c) {
  menu.value = null
  fn(c)
}
function onDocClick(e) {
  if (!e.target.closest('[data-cluster-menu]') && !e.target.closest('button[title="Cluster menu"]')) {
    menu.value = null
  }
}
const saving = ref(false)
const detail = ref(null)
const sched = ref(null)
const savingSched = ref(false)
let timer = null

const rows = computed(() => {
  const out = []
  for (const c of clusters.value) {
    const targets = c.targets && c.targets.length ? c.targets : [{ name: '(no targets)' }]
    targets.forEach((t, idx) => {
      out.push({ key: `${c.id}:${t.name}`, c, t, first: idx === 0, idx: out.length })
    })
  }
  return out
})

function targetSchedLabel(t, c) {
  const freq = t.schedule_frequency || c.schedule_frequency || 'interval'
  const h = (t.schedule_hour ?? c.schedule_hour)
  const m = (t.schedule_minute ?? c.schedule_minute)
  const keep = t.retention_count || c.retention_count
  const iv = t.interval_hours || c.interval_hours || 1
  const base = freq === 'interval' ? `every ${iv}h` : 'daily'
  return `${base} ${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')} · keep ${keep}`
}

function openSchedule(c, t) {
  sched.value = {
    id: c.id, name: c.name, target: t.name,
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
    await k8sApi.patchTarget(sched.value.id, sched.value.target, {
      schedule_frequency: sched.value.schedule_frequency,
      interval_hours: sched.value.interval_hours,
      schedule_hour: sched.value.schedule_hour,
      schedule_minute: sched.value.schedule_minute,
      retention_count: sched.value.retention_count,
      is_job_active: sched.value.is_job_active,
    })
    sched.value = null
    await load()
  } catch (e) {
    await alert(String(e.message || e), { title: 'Save failed' })
  } finally {
    savingSched.value = false
  }
}

async function runTarget(c, t) {
  await k8sApi.runTarget(c.id, t.name)
  await load()
}

const form = reactive({ name: '', kubeconfig: '' })

async function load() {
  clusters.value = await k8sApi.list()
}

async function createCluster() {
  if (!form.name.trim()) {
    await alert('A cluster name is required.', { title: 'Missing name' })
    return
  }
  if (!form.kubeconfig.includes('apiVersion')) {
    await alert('Paste the full kubeconfig YAML (it should contain "apiVersion: v1").', { title: 'Invalid kubeconfig' })
    return
  }
  saving.value = true
  try {
    await k8sApi.create({ name: form.name, kubeconfig: form.kubeconfig, targets: [] })
    showAdd.value = false
    form.name = ''; form.kubeconfig = ''
    await load()
  } catch (e) {
    await alert(String(e.message || e), { title: 'Register failed' })
  } finally {
    saving.value = false
  }
}

// --- Create snapshot job (add a target to a cluster) ---
const jobModal = ref(null)
const savingJob = ref(false)
const jobForm = reactive({
  name: '', profile: 'kamaji', namespace: '', selector: '',
  schedule_frequency: 'interval', interval_hours: 1, schedule_hour: 0, retention_count: 48,
})

function openJobModal(c) {
  jobModal.value = { id: c.id, clusterName: c.name, existing: (c.targets || []).map((t) => t.name) }
  Object.assign(jobForm, {
    name: '', profile: 'kamaji', namespace: '', selector: '',
    schedule_frequency: 'interval', interval_hours: 1, schedule_hour: 0, retention_count: 48,
  })
}

async function createJob() {
  if (!jobForm.name.trim()) {
    await alert('A job name is required.', { title: 'Missing name' })
    return
  }
  if (jobModal.value.existing.includes(jobForm.name.trim())) {
    await alert('A job with that name already exists on this cluster.', { title: 'Duplicate name' })
    return
  }
  savingJob.value = true
  try {
    const target = {
      name: jobForm.name.trim(), profile: jobForm.profile,
      schedule_frequency: jobForm.schedule_frequency,
      interval_hours: jobForm.interval_hours,
      schedule_hour: jobForm.schedule_hour, schedule_minute: 0,
      retention_count: jobForm.retention_count, is_job_active: true,
    }
    if (jobForm.namespace) target.namespace = jobForm.namespace
    if (jobForm.selector) target.selector = jobForm.selector
    const cluster = clusters.value.find((x) => x.id === jobModal.value.id)
    const targets = [...(cluster.targets || []), target]
    const cid = jobModal.value.id
    await k8sApi.patch(cid, { targets })
    jobModal.value = null
    expanded.value = cid
    await load()
  } catch (e) {
    await alert(String(e.message || e), { title: 'Create job failed' })
  } finally {
    savingJob.value = false
  }
}

async function removeTarget(c, t) {
  const ok = await confirm(`Remove job "${t.name}" from ${c.name}? Stored snapshots stay on disk.`, { title: 'Remove job', confirmText: 'Remove' })
  if (!ok) return
  const targets = (c.targets || []).filter((x) => x.name !== t.name)
  await k8sApi.patch(c.id, { targets })
  await load()
}

async function runNow(c) {
  await k8sApi.run(c.id)
  await load()
}

async function testCluster(c) {
  try {
    const r = await k8sApi.test(c.id)
    const lines = r.results.map((x) => x.ok ? `✓ ${x.target}: ${x.pod}` : `✗ ${x.target}: ${x.error}`)
    await alert(lines.length ? lines.join('\n') : 'No snapshot targets configured on this cluster.', { title: `Connectivity — ${c.name}` })
  } catch (e) {
    await alert(String(e.message || e), { title: `Connectivity — ${c.name}` })
  }
}

async function showBackups(c) {
  detail.value = await k8sApi.backups(c.id)
}

const k3s = ref(null)
const k3sApplying = ref(false)
const k3sForm = reactive({ endpoint: '', access_key: '', secret_key: '', bucket: '', folder: 'etcd/kmj-management', schedule_cron: '0 */6 * * *' })

async function openK3s(c) {
  k3s.value = { clusterId: c.id, clusterName: c.name, status: null, fragment: null }
  try {
    k3s.value.status = await k8sApi.k3sStatus(c.id)
  } catch (e) {
    await alert(String(e.message || e), { title: 'k3s status' })
    k3s.value = null
  }
}

async function applyK3sFromSecondary() {
  k3sApplying.value = true
  try {
    const r = await k8sApi.k3sApplyS3FromSecondary(k3s.value.clusterId)
    k3s.value.fragment = r.config_fragment
    k3s.value.secretAction = r.secret
    k3s.value.status = await k8sApi.k3sStatus(k3s.value.clusterId)
  } catch (e) {
    await alert(String(e.message || e), { title: 'Apply failed' })
  } finally {
    k3sApplying.value = false
  }
}

async function applyK3s() {
  if (!k3sForm.endpoint || !k3sForm.access_key || !k3sForm.secret_key || !k3sForm.bucket) {
    await alert('Endpoint, keys and bucket are required.', { title: 'Missing fields' })
    return
  }
  k3sApplying.value = true
  try {
    const r = await k8sApi.k3sApplyS3(k3s.value.clusterId, { ...k3sForm })
    k3s.value.fragment = r.config_fragment
    k3s.value.secretAction = r.secret
    k3s.value.status = await k8sApi.k3sStatus(k3s.value.clusterId)
  } catch (e) {
    await alert(String(e.message || e), { title: 'Apply failed' })
  } finally {
    k3sApplying.value = false
  }
}

async function removeCluster(c) {
  const ok = await confirm(`Remove cluster ${c.name}? Stored snapshots stay on disk.`, { title: 'Remove cluster', confirmText: 'Remove' })
  if (!ok) return
  await k8sApi.remove(c.id)
  await load()
}

function formatDate(iso) {
  return iso.replace('T', ' ').slice(0, 19)
}

onMounted(() => {
  load()
  timer = setInterval(load, 10000)
  document.addEventListener('click', onDocClick)
})
onUnmounted(() => {
  clearInterval(timer)
  document.removeEventListener('click', onDocClick)
})
</script>
