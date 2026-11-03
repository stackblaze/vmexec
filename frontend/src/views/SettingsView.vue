<template>
  <div>
    <h1 class="text-2xl font-bold mb-1">Settings</h1>
    <p class="text-sm text-muted mb-5">Storage, vCenter and VDDK are set up by install.sh. Policies and alerts are edited here.</p>

    <div role="tablist" aria-label="Settings" class="flex flex-wrap gap-1 border-b border-border mb-5">
      <button
        v-for="p in panels"
        :key="p.id"
        type="button"
        role="tab"
        :aria-selected="panel === p.id"
        class="min-h-11 px-4 -mb-px text-sm bg-transparent border-0 border-b-2 border-solid cursor-pointer"
        :class="panel === p.id ? 'border-brand text-main font-semibold' : 'border-transparent text-muted font-medium hover:text-main'"
        @click="go(p.id)"
      >{{ p.label }}</button>
    </div>

    <div
      v-if="msg"
      class="mb-4 text-sm px-4 py-2.5 rounded border"
      :class="msgOk ? 'text-emerald-600 dark:text-emerald-400 border-emerald-400/30' : 'text-red-600 dark:text-red-400 border-red-400/30'"
    >{{ msg }}</div>

    <!-- Storage (read-only: set by install.sh) -->
    <section v-if="panel === 'storage'" role="tabpanel" aria-label="Storage" class="bg-card border border-border rounded-lg shadow-card p-6 space-y-5">
      <div class="flex flex-wrap justify-between items-center gap-3">
        <h2 class="text-lg font-semibold m-0">Backup storage</h2>
        <span
          class="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full"
          :class="status?.storage?.healthy ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400' : 'bg-red-500/15 text-red-700 dark:text-red-400'"
        ><span class="w-2 h-2 rounded-full" :class="status?.storage?.healthy ? 'bg-emerald-500' : 'bg-red-500'" aria-hidden="true"></span>{{ status ? (status.storage.healthy ? 'ZeroFS healthy' : 'Not available') : 'Checking…' }}</span>
      </div>
      <p v-if="status?.storage?.error" class="text-sm text-red-600 dark:text-red-400 m-0">{{ status.storage.error }}</p>
      <dl class="grid gap-x-6 gap-y-4 grid-cols-[repeat(auto-fit,minmax(13rem,1fr))] mt-0 text-sm">
        <div><dt class="text-xs text-muted mb-1">S3 location</dt><dd class="m-0 font-mono text-xs">{{ status?.storage?.location || 'Not set by install.sh' }}</dd></div>
        <div><dt class="text-xs text-muted mb-1">Stored in S3</dt><dd class="m-0">{{ s3Used }}</dd></div>
        <div><dt class="text-xs text-muted mb-1">Encryption</dt><dd class="m-0">{{ status?.storage?.encrypted ? 'On · password in the region vault' : 'Unknown' }}</dd></div>
        <div><dt class="text-xs text-muted mb-1">Write check</dt><dd class="m-0">{{ status?.storage?.probe_ms != null ? `${status.storage.probe_ms} ms, synced to S3` : '—' }}</dd></div>
        <div><dt class="text-xs text-muted mb-1">Mount</dt><dd class="m-0 font-mono text-xs">{{ cfg.nfs_path || '/mnt/backups' }}{{ status?.storage?.fstype ? ` (${status.storage.fstype})` : '' }}</dd></div>
      </dl>
      <div v-if="status?.storage?.cache">
        <div class="flex justify-between text-sm mb-1.5"><span>Local cache</span><span class="text-muted">{{ status.storage.cache.used_gb }} GB of {{ status.storage.cache.total_gb }} GB</span></div>
        <div role="progressbar" aria-label="Local cache used" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round(status.storage.cache.used_pct)" class="h-2 rounded bg-border overflow-hidden">
          <div class="h-full bg-brand" :style="{ width: status.storage.cache.used_pct + '%' }"></div>
        </div>
        <p class="text-xs text-muted mt-2 mb-0">The cache only speeds things up. Backups live in S3, so there is no disk to fill.</p>
      </div>
    </section>

    <!-- Policies -->
    <section v-else-if="panel === 'policies'" role="tabpanel" aria-label="Policies" class="bg-card border border-border rounded-lg shadow-card p-6 space-y-4">
      <div class="flex flex-wrap justify-between items-center gap-3">
        <h2 class="text-lg font-semibold m-0">Backup policies</h2>
        <button v-if="auth.isOperator && !editing" type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-3 py-2 text-sm font-medium text-btn-sec-text hover:bg-btn-sec-hover disabled:opacity-55 !text-brand !border-brand" @click="startEdit(null)">New policy</button>
      </div>
      <div class="rounded-md border border-border divide-y divide-border">
        <div v-for="p in policies" :key="p.id" class="px-4 py-3.5">
          <div v-if="editing?.id !== p.id" class="flex flex-wrap items-center gap-3">
            <div class="flex-1 min-w-[16rem]">
              <div class="text-sm font-semibold">{{ p.name }} <span class="font-normal text-muted">· {{ p.vm_count }} VM{{ p.vm_count === 1 ? '' : 's' }}</span></div>
              <div class="text-xs text-muted mt-0.5">{{ p.summary }}</div>
            </div>
            <template v-if="auth.isOperator && !editing">
              <button type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-3 py-2 text-sm font-medium text-btn-sec-text hover:bg-btn-sec-hover disabled:opacity-55 !py-1.5 !text-xs" @click="startEdit(p)">Edit</button>
              <button v-if="!p.vm_count" type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-3 py-2 text-sm font-medium text-btn-sec-text hover:bg-btn-sec-hover disabled:opacity-55 !py-1.5 !text-xs hover:!text-red-600" @click="deletePolicy(p)">Delete</button>
            </template>
          </div>
          <form v-else class="space-y-3" @submit.prevent="savePolicy"><PolicyFields v-model="editing" /><div class="flex gap-2"><button type="submit" class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-3 py-2 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-55">Save</button><button type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-3 py-2 text-sm font-medium text-btn-sec-text hover:bg-btn-sec-hover disabled:opacity-55" @click="editing = null">Cancel</button></div></form>
        </div>
        <form v-if="editing && !editing.id" class="px-4 py-3.5 space-y-3" @submit.prevent="savePolicy">
          <PolicyFields v-model="editing" />
          <div class="flex gap-2"><button type="submit" class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-3 py-2 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-55">Create policy</button><button type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-3 py-2 text-sm font-medium text-btn-sec-text hover:bg-btn-sec-hover disabled:opacity-55" @click="editing = null">Cancel</button></div>
        </form>
      </div>
      <p class="text-xs text-muted m-0">Backups are always incremental, with a full every {{ cfg.cbt_full_interval || 7 }}th run. VMs in a policy start {{ 5 }} minutes apart.</p>
      <label class="flex flex-wrap items-center gap-3 pt-4 border-t border-border text-sm">
        <span class="flex-1 min-w-[16rem]">Parallel backups<span class="block text-xs text-muted">How many VMs back up at the same time</span></span>
        <input v-model.number="cfg.max_global_backups" type="number" min="1" max="32" class="w-20 py-2 px-2 text-sm text-center" :disabled="!auth.isAdmin" @change="saveParallel" />
      </label>
    </section>

    <!-- vCenter -->
    <section v-else-if="panel === 'vcenter'" role="tabpanel" aria-label="vCenter" class="space-y-4">
      <div class="bg-card border border-border rounded-lg shadow-card p-6 space-y-5">
        <div class="flex flex-wrap justify-between items-center gap-3">
          <h2 class="text-lg font-semibold m-0">vCenter</h2>
          <button v-if="auth.isAdmin && !hosts.length" type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-3 py-2 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-55" @click="openAddHost">Connect vCenter</button>
        </div>
        <p v-if="!hosts.length" class="text-sm text-muted m-0">No vCenter connected. install.sh registers it; on a manual install, connect it here.</p>
        <div v-for="h in hosts" :key="h.id" class="flex flex-wrap items-start gap-x-6 gap-y-3 text-sm">
          <dl class="flex-1 grid gap-x-6 gap-y-4 grid-cols-[repeat(auto-fit,minmax(13rem,1fr))] m-0">
            <div><dt class="text-xs text-muted mb-1">Address</dt><dd class="m-0 font-mono text-xs">{{ h.host_ip }}</dd></div>
            <div><dt class="text-xs text-muted mb-1">Account</dt><dd class="m-0 font-mono text-xs">{{ h.username }}</dd></div>
            <div><dt class="text-xs text-muted mb-1">Connection</dt><dd class="m-0">{{ reachable(h) }}</dd></div>
            <div><dt class="text-xs text-muted mb-1">VDDK</dt><dd class="m-0">{{ vddkText }}</dd></div>
          </dl>
          <button v-if="auth.isAdmin" type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-3 py-2 text-sm font-medium text-btn-sec-text hover:bg-btn-sec-hover disabled:opacity-55 !py-1.5 !text-xs hover:!text-red-600" @click="removeHost(h.id)">Disconnect</button>
        </div>
      </div>
    </section>

    <!-- Alerts -->
    <section v-else-if="panel === 'alerts'" role="tabpanel" aria-label="Alerts" class="bg-card border border-border rounded-lg shadow-card p-6 space-y-4">
      <h2 class="text-lg font-semibold m-0">Alerts</h2>
      <form class="space-y-4" @submit.prevent="saveAlerts">
        <label class="block text-sm">
          Webhook URL
          <span class="block text-xs text-muted mb-1.5">Discord, Slack or any HTTPS endpoint that accepts JSON.{{ cfg.alert_webhook_set ? ` Saved: ${cfg.alert_webhook_hint} (leave empty to keep it).` : '' }}</span>
          <input v-model="webhook" type="url" inputmode="url" autocomplete="off" :placeholder="cfg.alert_webhook_set ? 'Saved — paste a new URL to replace it' : 'https://discord.com/api/webhooks/…'" class="w-full py-2 px-3 text-sm" :disabled="!auth.isAdmin" />
        </label>
        <fieldset class="border-0 m-0 p-0 flex flex-wrap gap-x-6 gap-y-1">
          <legend class="text-sm mb-2">Send an alert when</legend>
          <label class="inline-flex items-center gap-2 min-h-9 text-sm"><input v-model="cfg.alert_on_failure" type="checkbox" class="w-4 h-4 accent-brand" :disabled="!auth.isAdmin" /> A backup fails</label>
          <label class="inline-flex items-center gap-2 min-h-9 text-sm"><input v-model="cfg.alert_on_missed" type="checkbox" class="w-4 h-4 accent-brand" :disabled="!auth.isAdmin" /> A scheduled backup is missed</label>
          <label class="inline-flex items-center gap-2 min-h-9 text-sm"><input v-model="cfg.alert_on_storage" type="checkbox" class="w-4 h-4 accent-brand" :disabled="!auth.isAdmin" /> Backup storage is unhealthy</label>
        </fieldset>
        <div v-if="auth.isAdmin" class="flex flex-wrap gap-2">
          <button type="submit" class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-3 py-2 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-55">Save</button>
          <button type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-3 py-2 text-sm font-medium text-btn-sec-text hover:bg-btn-sec-hover disabled:opacity-55" @click="testWebhook">Send test</button>
          <button v-if="cfg.alert_webhook_set" type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-3 py-2 text-sm font-medium text-btn-sec-text hover:bg-btn-sec-hover disabled:opacity-55 hover:!text-red-600" @click="clearWebhook">Remove webhook</button>
        </div>
      </form>
    </section>

        <!-- Users -->
        <div v-else-if="panel === 'users' && auth.isAdmin">
          <div class="flex items-center justify-between gap-3 mb-4">
            <h2 class="text-[1.375rem] font-bold m-0">User Management</h2>
            <button
              type="button"
              class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-hover disabled:opacity-55"
              @click="openAddUser"
            >Add user</button>
          </div>
          <div class="bg-card border border-border rounded-lg shadow-card transition-all duration-300 overflow-hidden">
              <table class="w-full text-sm">
                <thead>
                  <tr class="text-xs uppercase text-muted border-b border-border">
                    <th class="px-5 py-3 text-left">Username</th>
                    <th class="px-5 py-3 text-left">Role</th>
                    <th class="px-5 py-3 text-left">MFA</th>
                    <th class="px-5 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="u in users" :key="u.id" class="border-b border-border">
                    <td class="px-5 py-3 font-medium">{{ u.username }} <span v-if="u.username === auth.user?.username" class="text-[10px] opacity-50">(you)</span></td>
                    <td class="px-5 py-3">
                      <select
                        :value="u.role"
                        class="text-xs py-1 px-2 rounded border border-border"
                        :disabled="u.username === auth.user?.username"
                        @change="updateRole(u.id, $event.target.value)"
                      >
                        <option value="admin">Admin</option>
                        <option value="operator">Operator</option>
                        <option value="viewer">Viewer</option>
                      </select>
                    </td>
                    <td class="px-5 py-3">
                      <span
                        class="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                        :class="u.is_mfa_enabled ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'"
                      >{{ u.is_mfa_enabled ? 'Enabled' : 'Pending' }}</span>
                    </td>
                    <td class="px-5 py-3">
                      <div class="flex flex-wrap gap-1.5 justify-end">
                        <button type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-2 py-1 text-xs font-medium text-btn-sec-text hover:bg-btn-sec-hover" @click="resetPw(u.id)">Reset PW</button>
                        <button type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-2 py-1 text-xs font-medium text-btn-sec-text hover:bg-btn-sec-hover" @click="resetMfa(u.id)">Reset MFA</button>
                        <button
                          v-if="u.username !== auth.user?.username"
                          type="button"
                          class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-red-600 px-2 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-55"
                          @click="removeUser(u.id)"
                        >Delete</button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
          </div>
        </div>

        <!-- Syslogs -->
        <div v-else-if="panel === 'logs'">
          <div class="flex items-center justify-between gap-3 mb-4">
            <h2 class="text-[1.375rem] font-bold m-0">System Logs</h2>
            <button
              type="button"
              class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-3 py-1.5 text-xs font-semibold text-btn-sec-text hover:bg-btn-sec-hover"
              @click="load"
            >Refresh logs</button>
          </div>
          <div class="flex flex-col gap-4">
            <div class="bg-card border border-border rounded-lg shadow-card overflow-hidden">
              <div class="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted border-b border-border bg-nav">Service</div>
              <pre class="text-xs p-4 m-0 overflow-auto max-h-80 font-mono leading-relaxed whitespace-pre-wrap break-words bg-[#0a0a0a] text-lime-400">{{ logs.service_log }}</pre>
            </div>
            <div class="bg-card border border-border rounded-lg shadow-card overflow-hidden">
              <div class="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted border-b border-border bg-nav">Worker</div>
              <pre class="text-xs p-4 m-0 overflow-auto max-h-80 font-mono leading-relaxed whitespace-pre-wrap break-words bg-[#0a0a0a] text-lime-400">{{ logs.worker_log }}</pre>
            </div>
          </div>
        </div>

    <!-- Add host modal -->
    <FormModal
      :open="showAddHost"
      :title="hostAddResult ? (hostAddResult.vddk_installed ? 'vCenter connected — VDDK ready' : 'vCenter connected — VDDK setup') : 'Connect vCenter'"
      :subtitle="hostAddResult ? '' : 'VMExec verifies the connection and detects standalone ESXi vs vCenter.'"
      :busy="hostAddBusy"
      @close="closeAddHost"
    >
      <div v-if="hostAddResult" class="space-y-3">
        <p class="text-sm">Registered <strong>{{ hostAddResult.name }}</strong>.</p>
        <div
          class="text-sm px-3 py-2.5 rounded border"
          :class="hostAddResult.vddk_installed ? 'bg-emerald-500/10 border-emerald-400/30 text-emerald-400' : 'bg-amber-500/10 border-amber-400/30 text-amber-400'"
        >
          <p class="font-semibold mb-1">{{ hostAddResult.vddk_installed ? 'VDDK addon installed' : 'VDDK addon not installed' }}</p>
          <p class="text-xs leading-relaxed opacity-90">{{ hostAddResult.vddk_message || (hostAddResult.vddk_installed ? 'Live backup transport is set to VDDK / NBD.' : 'Place a VMware-vix-disklib tarball in vendor/vddk/ on the server, or install VDDK manually.') }}</p>
          <p v-if="!hostAddResult.vddk_installed" class="mt-2 text-xs leading-relaxed opacity-90">
            The VDDK is proprietary and cannot be shipped with VMExec. Download the
            <strong>Linux 64-bit</strong> tarball (<code class="font-mono">VMware-vix-disklib-*.tar.gz</code>,
            v8 or v9) from
            <a href="https://developer.broadcom.com/sdks/vmware-virtual-disk-development-kit-vddk/latest"
               target="_blank" rel="noopener noreferrer"
               class="underline hover:no-underline">Broadcom</a>
            (free account required) and place it in <code class="font-mono">vendor/vddk/</code> on the server.
          </p>
        </div>
      </div>
      <form v-else class="space-y-3" @submit.prevent="submitAddHost">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div class="sm:col-span-2">
            <span class="block mb-1 text-xs font-semibold uppercase text-muted">Alias</span>
            <input v-model="newHost.name" placeholder="e.g. esxi-01 or vcenter-prod" class="w-full py-2 px-3 text-sm" required autocomplete="off" :disabled="hostAddBusy" />
          </div>
          <div class="sm:col-span-2">
            <span class="block mb-1 text-xs font-semibold uppercase text-muted">IP or FQDN</span>
            <input v-model="newHost.host_ip" placeholder="10.0.0.50 or vcenter.local" class="w-full py-2 px-3 text-sm font-mono" required autocomplete="off" :disabled="hostAddBusy" />
          </div>
          <div>
            <span class="block mb-1 text-xs font-semibold uppercase text-muted">Username</span>
            <input v-model="newHost.username" placeholder="administrator@vsphere.local" class="w-full py-2 px-3 text-sm" required autocomplete="off" spellcheck="false" :disabled="hostAddBusy" />
          </div>
          <div>
            <span class="block mb-1 text-xs font-semibold uppercase text-muted">Password</span>
            <input v-model="newHost.password" type="password" class="w-full py-2 px-3 text-sm" required autocomplete="new-password" :disabled="hostAddBusy" />
          </div>
          <div class="sm:col-span-2">
            <span class="block mb-1 text-xs font-semibold uppercase text-muted">Connection type</span>
            <select v-model="newHost.connection_type" class="w-full py-2 px-3 text-sm" :disabled="hostAddBusy">
              <option value="auto">Auto-detect (recommended)</option>
              <option value="standalone">Standalone ESXi</option>
              <option value="vcenter">vCenter Server</option>
            </select>
          </div>
        </div>
        <div v-if="hostAddBusy" class="pt-1 space-y-2">
          <div class="flex justify-between text-xs">
            <span class="text-muted">{{ hostAddPhase }}</span>
            <span class="font-mono text-brand">{{ hostAddProgress }}%</span>
          </div>
          <div class="h-1.5 rounded-sm bg-border overflow-hidden">
            <div class="h-full bg-brand rounded-sm transition-[width] duration-300 ease-out" :style="{ width: hostAddProgress + '%' }"></div>
          </div>
        </div>
        <p v-if="hostAddError" class="text-xs px-3 py-2 rounded bg-red-500/12 text-red-400">{{ hostAddError }}</p>
      </form>
      <template #footer>
        <button
          v-if="hostAddResult"
          type="button"
          class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-hover"
          @click="closeAddHost"
        >Done</button>
        <template v-else>
          <button
            type="button"
            class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-4 py-2 text-sm font-medium text-btn-sec-text hover:bg-btn-sec-hover disabled:opacity-55"
            :disabled="hostAddBusy"
            @click="closeAddHost"
          >Cancel</button>
          <button
            type="button"
            class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-55"
            :disabled="hostAddBusy"
            @click="submitAddHost"
          >{{ hostAddBusy ? 'Connecting…' : 'Connect' }}</button>
        </template>
      </template>
    </FormModal>

    <!-- Add user modal -->
    <FormModal
      :open="showAddUser"
      :title="userAddResult ? 'User created' : 'Add new user'"
      :subtitle="userAddResult ? '' : 'A temporary password will be generated for the new account.'"
      :busy="userAddBusy"
      @close="closeAddUser"
    >
      <div v-if="userAddResult" class="space-y-3">
        <p class="text-sm"><strong>{{ userAddResult.username }}</strong> was created with role <strong>{{ userAddResult.role }}</strong>.</p>
        <div class="text-sm px-3 py-2.5 rounded bg-emerald-500/10 border border-emerald-400/30 text-emerald-400">
          <span class="block text-xs font-semibold uppercase mb-1">Temporary password</span>
          <code class="font-mono text-sm select-all">{{ userAddResult.temporary_password }}</code>
        </div>
        <p class="text-xs text-muted">Share this password securely. The user will be prompted to set up MFA on first login.</p>
      </div>
      <form v-else class="space-y-3" @submit.prevent="submitAddUser">
        <div>
          <span class="block mb-1 text-xs font-semibold uppercase text-muted">Username</span>
          <input v-model="newUser.name" class="w-full py-2 px-3 text-sm" required autocomplete="off" :disabled="userAddBusy" />
        </div>
        <div>
          <span class="block mb-1 text-xs font-semibold uppercase text-muted">Role</span>
          <select v-model="newUser.role" class="w-full py-2 px-3 text-sm" :disabled="userAddBusy">
            <option value="operator">Operator</option>
            <option value="viewer">Viewer</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <p v-if="userAddError" class="text-xs px-3 py-2 rounded bg-red-500/12 text-red-400">{{ userAddError }}</p>
      </form>
      <template #footer>
        <button
          v-if="userAddResult"
          type="button"
          class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-hover"
          @click="closeAddUser"
        >Done</button>
        <template v-else>
          <button
            type="button"
            class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-4 py-2 text-sm font-medium text-btn-sec-text hover:bg-btn-sec-hover disabled:opacity-55"
            :disabled="userAddBusy"
            @click="closeAddUser"
          >Cancel</button>
          <button
            type="button"
            class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-55"
            :disabled="userAddBusy"
            @click="submitAddUser"
          >{{ userAddBusy ? 'Creating…' : 'Create user' }}</button>
        </template>
      </template>
    </FormModal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { configApi, hostsApi, usersApi, logsApi, statusApi, policiesApi, alertsApi } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useModal } from '@/composables/useModal'
import FormModal from '@/components/FormModal.vue'
import PolicyFields from '@/components/PolicyFields.vue'

const props = defineProps({ panel: { type: String, default: 'storage' } })
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { confirm, alert } = useModal()

const ALIASES = { hosts: 'vcenter', syslogs: 'logs', engine: 'policies', email: 'alerts' }
const panel = computed(() => {
  const p = props.panel || route.params.panel || 'storage'
  return ALIASES[p] || p
})
const cfg = ref({})
const hosts = ref([])
const users = ref([])
const policies = ref([])
const status = ref(null)
const editing = ref(null)
const webhook = ref('')
const logs = ref({ service_log: '', worker_log: '' })
const msg = ref('')
const msgOk = ref(true)
const showAddHost = ref(false)
const hostAddBusy = ref(false)
const hostAddProgress = ref(0)
const hostAddPhase = ref('')
const hostAddError = ref('')
const hostAddResult = ref(null)
const newHost = ref({ name: '', host_ip: '', username: '', password: '', connection_type: 'auto' })
const showAddUser = ref(false)
const userAddBusy = ref(false)
const userAddError = ref('')
const userAddResult = ref(null)
const newUser = ref({ name: '', role: 'operator' })

const HOST_ADD_PHASES = [
  { at: 10, label: 'Connecting to host…' },
  { at: 30, label: 'Verifying credentials…' },
  { at: 50, label: 'Registering host…' },
  { at: 70, label: 'Installing VDDK addon…' },
]

let hostProgressTimer = null

const panels = computed(() => {
  const all = [
    { id: 'storage', label: 'Storage' },
    { id: 'policies', label: 'Policies' },
    { id: 'vcenter', label: 'vCenter' },
    { id: 'alerts', label: 'Alerts' },
    { id: 'users', label: 'Users' },
    { id: 'logs', label: 'Logs' },
  ]
  if (!auth.isAdmin) return all.filter((p) => !['users', 'alerts'].includes(p.id))
  return all
})

function go(id) {
  msg.value = ''
  editing.value = null
  router.push(`/settings/${id}`)
}

// What the bucket holds: what you pay for (VM disk sizes are mostly empty space).
const s3Used = computed(() => {
  const u = status.value?.storage?.s3_usage
  if (!u) return 'Not measured yet'
  const gb = u.bytes / 1024 ** 3
  const size = gb >= 1024 ? `${(gb / 1024).toFixed(2)} TB` : gb >= 1 ? `${gb.toFixed(1)} GB` : `${(u.bytes / 1024 ** 2).toFixed(0)} MB`
  const at = u.at ? new Date(u.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }) : ''
  return at ? `${size} · checked ${at}` : size
})

const vddkText = computed(() => {
  const vddk = (status.value?.problems || []).find((p) => p.kind === 'vddk')
  return vddk ? 'Not installed' : 'Installed'
})

function reachable(h) {
  const vc = (status.value?.vcenters || []).find((v) => v.address === h.host_ip)
  if (!vc) return 'Checking…'
  return vc.reachable ? 'Connected' : 'Not reachable'
}

async function load() {
  const jobs = [statusApi.get().then((s) => { status.value = s }).catch(() => {})]
  if (auth.isAdmin) {
    jobs.push(configApi.get().then((c) => { cfg.value = c }))
    jobs.push(hostsApi.list().then((h) => { hosts.value = h }))
    if (panel.value === 'users') jobs.push(usersApi.list().then((u) => { users.value = u }))
  }
  if (panel.value === 'policies') jobs.push(policiesApi.list().then((p) => { policies.value = p }))
  if (panel.value === 'logs') jobs.push(logsApi.system({ service_lines: 100, worker_lines: 100 }).then((l) => { logs.value = l }))
  await Promise.all(jobs)
}

function startEdit(p) {
  msg.value = ''
  editing.value = p
    ? { id: p.id, name: p.name, frequency: p.frequency, days: p.days, hour: p.hour, minute: p.minute, keep_daily: p.keep_daily, keep_weekly: p.keep_weekly, keep_monthly: p.keep_monthly }
    : { id: null, name: '', frequency: 'daily', days: '0,1,2,3,4,5,6', hour: 2, minute: 0, keep_daily: 7, keep_weekly: 4, keep_monthly: 6 }
}

async function savePolicy() {
  const { id, ...body } = editing.value
  try {
    if (id) await policiesApi.update(id, body)
    else await policiesApi.create(body)
    editing.value = null
    policies.value = await policiesApi.list()
    msg.value = id ? 'Policy saved. Its VMs were rescheduled.' : 'Policy created.'
    msgOk.value = true
  } catch (e) {
    msg.value = e.message; msgOk.value = false
  }
}

async function deletePolicy(p) {
  if (!await confirm(`Delete the ${p.name} policy?`, { title: 'Delete policy', confirmText: 'Delete', danger: true })) return
  try {
    await policiesApi.remove(p.id)
    policies.value = await policiesApi.list()
  } catch (e) {
    msg.value = e.message; msgOk.value = false
  }
}

async function saveParallel() {
  const n = Math.max(1, Math.min(32, Number(cfg.value.max_global_backups) || 1))
  cfg.value = await configApi.update({ max_global_backups: n })
  msg.value = `Up to ${n} backups run at the same time.`; msgOk.value = true
}

async function saveAlerts() {
  const body = {
    alert_on_failure: !!cfg.value.alert_on_failure,
    alert_on_missed: !!cfg.value.alert_on_missed,
    alert_on_storage: !!cfg.value.alert_on_storage,
  }
  if (webhook.value.trim()) body.alert_webhook_url = webhook.value.trim()
  try {
    cfg.value = await configApi.update(body)
    webhook.value = ''
    msg.value = 'Alerts saved.'; msgOk.value = true
  } catch (e) {
    msg.value = e.message; msgOk.value = false
  }
}

async function testWebhook() {
  const r = await alertsApi.test(webhook.value.trim() || null)
  msg.value = r.message; msgOk.value = r.ok
}

async function clearWebhook() {
  if (!await confirm('Remove the webhook? No alerts will be sent.', { title: 'Remove webhook', confirmText: 'Remove', danger: true })) return
  cfg.value = await configApi.update({ alert_webhook_url: '' })
  msg.value = 'Webhook removed.'; msgOk.value = true
}

function startHostProgress() {
  hostAddProgress.value = 0
  hostAddPhase.value = HOST_ADD_PHASES[0].label
  let phaseIdx = 0
  hostProgressTimer = setInterval(() => {
    if (hostAddProgress.value < 90) {
      hostAddProgress.value = Math.min(90, hostAddProgress.value + 2)
      while (phaseIdx + 1 < HOST_ADD_PHASES.length && hostAddProgress.value >= HOST_ADD_PHASES[phaseIdx + 1].at) {
        phaseIdx += 1
        hostAddPhase.value = HOST_ADD_PHASES[phaseIdx].label
      }
    }
  }, 250)
}

function stopHostProgress(final = 100) {
  if (hostProgressTimer) {
    clearInterval(hostProgressTimer)
    hostProgressTimer = null
  }
  hostAddProgress.value = final
  if (final >= 100) hostAddPhase.value = 'Complete'
}

function openAddHost() {
  hostAddError.value = ''
  hostAddResult.value = null
  hostAddProgress.value = 0
  hostAddPhase.value = ''
  showAddHost.value = true
}

function closeAddHost() {
  if (hostAddBusy.value) return
  showAddHost.value = false
  hostAddError.value = ''
  hostAddResult.value = null
  hostAddProgress.value = 0
  hostAddPhase.value = ''
  newHost.value = { name: '', host_ip: '', username: '', password: '', connection_type: 'auto' }
}

async function submitAddHost() {
  if (hostAddBusy.value) return
  hostAddError.value = ''
  hostAddResult.value = null
  hostAddBusy.value = true
  startHostProgress()
  try {
    const host = await hostsApi.create(newHost.value)
    stopHostProgress(100)
    hostAddResult.value = host
    hosts.value = await hostsApi.list()
    msg.value = `Registered ${host.name}.`
    msgOk.value = true
  } catch (e) {
    stopHostProgress(0)
    hostAddPhase.value = ''
    hostAddError.value = e.message || 'Could not add host.'
  } finally {
    hostAddBusy.value = false
  }
}

function openAddUser() {
  userAddError.value = ''
  userAddResult.value = null
  showAddUser.value = true
}

function closeAddUser() {
  if (userAddBusy.value) return
  showAddUser.value = false
  userAddError.value = ''
  userAddResult.value = null
  newUser.value = { name: '', role: 'operator' }
}

async function submitAddUser() {
  if (userAddBusy.value) return
  userAddError.value = ''
  userAddResult.value = null
  userAddBusy.value = true
  try {
    const r = await usersApi.create({ username: newUser.value.name, role: newUser.value.role })
    userAddResult.value = { username: newUser.value.name, role: newUser.value.role, temporary_password: r.temporary_password }
    users.value = await usersApi.list()
    msg.value = `User ${newUser.value.name} created.`
    msgOk.value = true
  } catch (e) {
    userAddError.value = e.message || 'Could not create user.'
  } finally {
    userAddBusy.value = false
  }
}

async function removeHost(id) {
  if (!await confirm('Disconnect this vCenter? Backups of its VMs stop until it is connected again.', { title: 'Disconnect vCenter', confirmText: 'Disconnect', danger: true })) return
  await hostsApi.remove(id)
  hosts.value = await hostsApi.list()
}

async function updateRole(id, role) {
  await usersApi.role(id, { role })
  users.value = await usersApi.list()
}

async function resetPw(id) {
  const r = await usersApi.resetPassword(id)
  await alert(`Temporary password: ${r.temporary_password}`, { title: 'Password reset' })
}

async function resetMfa(id) {
  if (!await confirm('Reset MFA? User will set it up again on next login.', { title: 'Reset MFA', confirmText: 'Reset' })) return
  await usersApi.resetMfa(id)
  users.value = await usersApi.list()
}

async function removeUser(id) {
  if (!await confirm('Delete user? This cannot be undone.', { title: 'Delete user', confirmText: 'Delete', danger: true })) return
  await usersApi.remove(id)
  users.value = await usersApi.list()
}

watch(panel, load)
onMounted(load)
onUnmounted(() => {
  if (hostProgressTimer) clearInterval(hostProgressTimer)
})
</script>
