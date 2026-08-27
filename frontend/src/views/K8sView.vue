<template>
  <div class="max-w-7xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h1 class="text-xl font-bold">Kubernetes</h1>
        <p class="text-xs text-muted mt-0.5">State-level backups: etcd / datastore snapshots per cluster. Node VMs stay unimaged — rebuild them from templates, restore state from here.</p>
      </div>
      <button type="button" :class="btnPrimary" class="px-3 py-1.5 text-sm" @click="showAdd = true">Register cluster</button>
    </div>

    <div class="rounded-lg border border-border bg-card shadow-card overflow-x-auto">
      <table class="w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th v-for="h in ['Cluster', 'Targets', 'Schedule', 'Last snapshot', 'Status', 'Actions']" :key="h"
                class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav whitespace-nowrap">{{ h }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!clusters.length">
            <td colspan="6" class="px-4 py-8 text-center text-muted text-xs">
              No clusters registered. Register one with its kubeconfig to start snapshotting etcd.
            </td>
          </tr>
          <tr v-for="c in clusters" :key="c.id" class="hover:bg-nav/50">
            <td class="px-4 py-3 border-b border-border font-medium">{{ c.name }}</td>
            <td class="px-4 py-3 border-b border-border text-xs">
              <span v-for="t in c.targets" :key="t.name" class="inline-block mr-1 mb-0.5 px-1.5 py-0.5 rounded border border-border font-mono text-[0.65rem]">{{ t.name }}</span>
            </td>
            <td class="px-4 py-3 border-b border-border text-xs whitespace-nowrap">
              {{ c.schedule_frequency === 'interval' ? `Every ${c.interval_hours}h` : 'Daily' }}
              {{ String(c.schedule_hour).padStart(2, '0') }}:{{ String(c.schedule_minute).padStart(2, '0') }}
              · keep {{ c.retention_count }}
            </td>
            <td class="px-4 py-3 border-b border-border text-xs font-mono whitespace-nowrap">{{ c.last_backup ? formatDate(c.last_backup) : '—' }}</td>
            <td class="px-4 py-3 border-b border-border text-xs">
              <span v-if="c.current_action" class="text-brand">{{ c.current_action }}</span>
              <span v-else :class="c.last_status === 'Success' ? 'text-emerald-500' : (c.last_status === 'Failed' ? 'text-red-500' : 'text-muted')">{{ c.last_status }}</span>
            </td>
            <td class="px-4 py-3 border-b border-border whitespace-nowrap">
              <button type="button" :class="btnIconSecondary" title="Snapshot now" @click="runNow(c)">▶</button>
              <button type="button" :class="btnIconSecondary" class="ml-1" title="Test connectivity" @click="testCluster(c)">✓</button>
              <button type="button" :class="btnIconSecondary" class="ml-1" title="Snapshots" @click="showBackups(c)">☰</button>
              <button type="button" :class="btnIconSecondary" class="ml-1" title="Management etcd (k3s) S3 offload" @click="openK3s(c)">S3</button>
              <button type="button" :class="btnIconSecondary" class="ml-1 hover:text-red-500" title="Remove" @click="removeCluster(c)">✕</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="detail" class="mt-4 rounded-lg border border-border bg-card shadow-card p-4">
      <div class="flex justify-between items-center mb-2">
        <h2 class="text-sm font-semibold">Snapshots — {{ detail.cluster }}</h2>
        <button type="button" class="text-xs opacity-60" @click="detail = null">Close</button>
      </div>
      <div v-for="t in detail.targets" :key="t.target" class="mb-3">
        <div class="text-xs font-semibold text-muted mb-1">{{ t.target }} · {{ t.points.length }} point(s)</div>
        <div class="text-xs font-mono space-y-0.5">
          <div v-for="p in [...t.points].reverse().slice(0, 12)" :key="p.id" class="flex gap-4">
            <span>{{ p.id }}</span>
            <span>{{ p.size_bytes ? (p.size_bytes / 1048576).toFixed(1) + ' MB' : '?' }}</span>
            <span v-if="p.etcd_status && p.etcd_status.revision" class="text-muted">rev {{ p.etcd_status.revision }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- k3s management-etcd S3 panel -->
    <div v-if="k3s" class="mt-4 rounded-lg border border-border bg-card shadow-card p-4">
      <div class="flex justify-between items-center mb-2">
        <h2 class="text-sm font-semibold">Management etcd (k3s) — {{ k3s.clusterName }}</h2>
        <button type="button" class="text-xs opacity-60" @click="k3s = null">Close</button>
      </div>
      <div v-if="!k3s.status" class="text-xs text-muted">Loading…</div>
      <template v-else>
        <div v-if="!k3s.status.nodes.length" class="text-xs text-muted">No k3s embedded-etcd nodes detected on this cluster.</div>
        <template v-else>
          <div class="text-xs mb-2">
            <div v-for="n in k3s.status.nodes" :key="n.name" class="font-mono">
              {{ n.name }} · last local snapshot: {{ n.last_local_snapshot || 'none' }}
            </div>
          </div>
          <div class="text-xs mb-3">
            S3 secret: <strong :class="k3s.status.secret_present ? 'text-emerald-500' : 'text-amber-500'">{{ k3s.status.secret_present ? 'configured' : 'not configured' }}</strong>
            <span v-if="k3s.status.bucket_error" class="text-red-500 ml-2">bucket check: {{ k3s.status.bucket_error }}</span>
          </div>
          <div v-if="k3s.status.bucket_objects && k3s.status.bucket_objects.length" class="text-xs font-mono mb-3">
            <div class="font-sans font-semibold text-muted mb-1">Latest uploads in bucket:</div>
            <div v-for="o in k3s.status.bucket_objects" :key="o.key">{{ o.modified.slice(0, 19) }} · {{ (o.size / 1048576).toFixed(1) }} MB · {{ o.key }}</div>
          </div>
          <div v-else-if="k3s.status.secret_present && !k3s.status.bucket_error" class="text-xs text-amber-500 mb-3">
            Secret configured but no snapshots in the bucket yet — the node config fragment below must be applied (one k3s restart per node).
          </div>
          <div class="grid grid-cols-3 gap-2 mb-2">
            <input v-model="k3sForm.endpoint" type="text" placeholder="s3 endpoint (e2)" class="py-1 px-2 text-xs font-mono" />
            <input v-model="k3sForm.access_key" type="text" placeholder="access key" class="py-1 px-2 text-xs font-mono" />
            <input v-model="k3sForm.secret_key" type="password" placeholder="secret key" class="py-1 px-2 text-xs font-mono" />
            <input v-model="k3sForm.bucket" type="text" placeholder="bucket" class="py-1 px-2 text-xs font-mono" />
            <input v-model="k3sForm.folder" type="text" placeholder="folder (etcd/kmj)" class="py-1 px-2 text-xs font-mono" />
            <input v-model="k3sForm.schedule_cron" type="text" placeholder="cron (0 */6 * * *)" class="py-1 px-2 text-xs font-mono" />
          </div>
          <button type="button" :class="btnPrimary" class="px-3 py-1.5 text-xs" :disabled="k3sApplying" @click="applyK3s">{{ k3sApplying ? 'Applying…' : 'Apply S3 secret to cluster' }}</button>
          <div v-if="k3s.fragment" class="mt-3">
            <div class="text-xs font-semibold text-muted mb-1">Secret {{ k3s.secretAction }}. Final step (host-level, cannot be done via the API): drop this on each etcd node as <code>/etc/rancher/k3s/config.yaml.d/etcd-s3.yaml</code>, then <code>systemctl restart k3s</code> one node at a time:</div>
            <pre class="text-[0.65rem] font-mono p-2 rounded border border-border bg-nav overflow-x-auto">{{ k3s.fragment }}</pre>
            <div class="text-xs text-amber-500 mt-1">Also save <code>/var/lib/rancher/k3s/server/token</code> off-cluster — restoring onto new nodes requires it.</div>
          </div>
        </template>
      </template>
    </div>

    <!-- Register modal -->
    <!-- No click-outside dismiss: the form holds a pasted kubeconfig -->
    <div v-if="showAdd" class="fixed inset-0 z-40 flex items-center justify-center bg-black/50">
      <div class="w-full max-w-2xl rounded-lg border border-border bg-card p-5 shadow-xl">
        <h2 class="text-base font-semibold mb-3">Register Kubernetes cluster</h2>
        <div class="grid grid-cols-2 gap-3 mb-3">
          <div>
            <span class="block text-xs font-semibold uppercase text-muted mb-1">Name</span>
            <input v-model="form.name" type="text" placeholder="kmj-management" class="w-full py-1.5 px-3 text-sm" />
          </div>
          <div>
            <span class="block text-xs font-semibold uppercase text-muted mb-1">Snapshot every</span>
            <select v-model.number="form.interval_hours" class="w-full py-1.5 px-3 text-sm">
              <option :value="1">1 hour</option>
              <option :value="2">2 hours</option>
              <option :value="6">6 hours</option>
              <option :value="12">12 hours</option>
            </select>
          </div>
        </div>
        <div class="mb-3">
          <span class="block text-xs font-semibold uppercase text-muted mb-1">Kubeconfig (stored encrypted)</span>
          <textarea v-model="form.kubeconfig" rows="6" class="w-full py-1.5 px-3 text-xs font-mono" placeholder="apiVersion: v1&#10;kind: Config&#10;..."></textarea>
        </div>
        <div class="mb-3">
          <span class="block text-xs font-semibold uppercase text-muted mb-1">Snapshot targets</span>
          <div v-for="(t, i) in form.targets" :key="i" class="flex gap-2 mb-1.5 items-center">
            <input v-model="t.name" type="text" placeholder="name" class="w-40 py-1 px-2 text-xs font-mono" />
            <select v-model="t.profile" class="py-1 px-2 text-xs">
              <option value="kamaji">kamaji-etcd</option>
              <option value="k3s">k3s etcd (host)</option>
              <option value="tenants">tenants (per-tenant export)</option>
              <option value="kubeadm">kubeadm etcd</option>
              <option value="custom">custom</option>
            </select>
            <input v-model="t.namespace" type="text" :placeholder="t.profile === 'kubeadm' ? 'kube-system (default)' : 'namespace'" class="w-44 py-1 px-2 text-xs font-mono" />
            <input v-model="t.selector" type="text" placeholder="label selector (profile default)" class="flex-1 py-1 px-2 text-xs font-mono" />
            <button type="button" class="text-xs opacity-60 hover:text-red-500" @click="form.targets.splice(i, 1)">✕</button>
          </div>
          <button type="button" class="text-xs text-brand" @click="form.targets.push({ name: '', profile: 'kamaji', namespace: '', selector: '' })">+ add target</button>
        </div>
        <div class="flex justify-end gap-2">
          <button type="button" :class="btnSecondary" class="px-3 py-1.5 text-sm" @click="showAdd = false">Cancel</button>
          <button type="button" :class="btnPrimary" class="px-3 py-1.5 text-sm" :disabled="saving" @click="createCluster">{{ saving ? 'Saving…' : 'Register' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { k8sApi } from '@/api/client'
import { useModal } from '@/composables/useModal'

const btnPrimary =
  'inline-flex items-center justify-center rounded-md border-0 bg-brand text-white hover:bg-brand-hover transition-colors duration-200 disabled:opacity-55'
const btnSecondary =
  'inline-flex items-center justify-center rounded-md border border-btn-sec-border bg-btn-sec text-btn-sec-text hover:bg-btn-sec-hover transition-colors duration-200'
const btnIconSecondary =
  'inline-flex items-center justify-center w-8 h-8 rounded-md transition-colors duration-200 disabled:opacity-55 shrink-0 border border-btn-sec-border bg-btn-sec text-btn-sec-text hover:bg-btn-sec-hover'

const { confirm, alert } = useModal()
const clusters = ref([])
const showAdd = ref(false)
const saving = ref(false)
const detail = ref(null)
let timer = null

const form = reactive({
  name: '',
  kubeconfig: '',
  interval_hours: 1,
  targets: [{ name: 'tenant-datastore', profile: 'kamaji', namespace: '', selector: '' }],
})

async function load() {
  clusters.value = await k8sApi.list()
}

async function createCluster() {
  const named = form.targets.filter((t) => t.name)
  if (!named.length) {
    await alert('Add at least one snapshot target (a name is required).', { title: 'Missing targets' })
    return
  }
  if (!form.kubeconfig.includes('apiVersion')) {
    await alert('Paste the full kubeconfig YAML (it should contain "apiVersion: v1").', { title: 'Invalid kubeconfig' })
    return
  }
  saving.value = true
  try {
    const targets = named.map((t) => {
      const out = { name: t.name, profile: t.profile }
      if (t.namespace) out.namespace = t.namespace
      if (t.selector) out.selector = t.selector
      return out
    })
    const c = await k8sApi.create({ name: form.name, kubeconfig: form.kubeconfig, targets })
    await k8sApi.patch(c.id, { schedule_frequency: 'interval', interval_hours: form.interval_hours })
    showAdd.value = false
    form.name = ''; form.kubeconfig = ''
    await load()
  } catch (e) {
    await alert(String(e.message || e), { title: 'Register failed' })
  } finally {
    saving.value = false
  }
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
})
onUnmounted(() => clearInterval(timer))
</script>
