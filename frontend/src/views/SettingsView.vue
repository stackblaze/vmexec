<template>
  <div>
    <h1 class="text-2xl font-bold mb-6">Settings</h1>
    <div class="flex gap-6 items-start max-md:flex-col">
      <aside class="w-[13.5rem] shrink-0 sticky top-4 max-md:w-full max-md:static">
        <div class="overflow-hidden flex flex-col max-h-[calc(100vh-7rem)] bg-card border border-border rounded-lg shadow-card transition-all duration-300">
          <div class="py-3.5 px-4 text-[0.6875rem] font-bold uppercase tracking-wider text-muted border-b border-border bg-nav">Settings</div>
          <nav class="flex flex-col p-1.5 gap-0.5 flex-1 min-h-0 overflow-y-auto max-md:flex-row max-md:flex-wrap">
            <button
              v-for="p in panels"
              :key="p.id"
              type="button"
              class="flex items-center gap-2.5 w-full px-3 py-2 text-[0.8125rem] font-medium text-left text-muted bg-transparent border-0 rounded-md cursor-pointer transition-colors duration-150 hover:text-main hover:bg-btn-sec-hover max-md:w-auto max-md:flex-1 max-md:min-w-[calc(50%-0.25rem)] max-md:justify-center"
              :class="{ 'text-brand bg-brand/10 font-semibold': panel === p.id }"
              @click="go(p.id)"
            >{{ p.label }}</button>
          </nav>
          <div v-if="auth.isAdmin" class="p-2.5 border-t border-border bg-nav shrink-0 max-md:hidden">
            <button
              type="button"
              class="w-full px-3 py-2 text-[0.8125rem] font-medium rounded-md border border-dashed border-border text-muted bg-transparent cursor-pointer transition-[color,border-color,background] duration-150 hover:text-brand hover:border-brand hover:bg-brand/6"
              @click="openWizard"
            >Setup wizard</button>
          </div>
        </div>
      </aside>

      <div class="flex-1 min-w-0">
        <div
          v-if="msg"
          class="mb-4 text-sm px-4 py-2.5 rounded border"
          :class="msgOk ? 'text-emerald-400 border-emerald-400/30' : 'text-red-400 border-red-400/30'"
        >{{ msg }}</div>

        <!-- Storage -->
        <div v-if="panel === 'storage'">
          <h2 class="text-[1.375rem] font-bold mb-1">Storage</h2>
          <p class="text-sm text-muted mb-4">Primary backup repository and optional secondary copy.</p>
          <div class="bg-card border border-border rounded-lg shadow-card transition-all duration-300 p-5 mb-4">
            <h3 class="text-sm font-semibold mb-3">Primary repository</h3>
            <div class="flex flex-wrap items-center gap-3 mb-4">
              <div class="flex flex-wrap items-center gap-3">
                <label v-for="t in ['SMB','NFS','S3']" :key="t" class="inline-flex items-center gap-1.5 text-xs font-medium cursor-pointer">
                  <input v-model="cfg.storage_type" type="radio" :value="t" /> {{ t }}
                </label>
              </div>
              <button
                type="button"
                class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-3 py-1.5 text-xs font-semibold text-btn-sec-text hover:bg-btn-sec-hover ml-auto"
                @click="testStorage"
              >Verify connection</button>
            </div>
            <div v-if="cfg.storage_type === 'SMB'" class="space-y-3">
              <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">UNC Path</span><input v-model="cfg.smb_unc_path" class="w-full py-2 px-3 font-mono text-sm mt-1" /></div>
              <div class="grid grid-cols-2 gap-4">
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Username</span><input v-model="cfg.smb_user" class="w-full py-2 px-3 text-sm mt-1" /></div>
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Password</span><input v-model="cfg.smb_password" type="password" placeholder="(Unchanged)" class="w-full py-2 px-3 text-sm mt-1" /></div>
              </div>
            </div>
            <div v-else-if="cfg.storage_type === 'NFS'">
              <span class="block mb-1 text-xs font-semibold uppercase text-muted">NFS Export Path</span><input v-model="cfg.nfs_path" class="w-full py-2 px-3 font-mono text-sm mt-1" />
            </div>
            <div v-else class="grid grid-cols-2 gap-4">
              <div class="col-span-2"><span class="block mb-1 text-xs font-semibold uppercase text-muted">S3 Endpoint</span><input v-model="cfg.s3_endpoint" class="w-full py-2 px-3 text-sm mt-1" /></div>
              <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Access Key</span><input v-model="cfg.s3_access_key" class="w-full py-2 px-3 text-sm mt-1" /></div>
              <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Secret Key</span><input v-model="cfg.s3_secret_key" type="password" placeholder="(Unchanged)" class="w-full py-2 px-3 text-sm mt-1" /></div>
              <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Bucket</span><input v-model="cfg.s3_bucket" class="w-full py-2 px-3 text-sm mt-1" /></div>
              <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Region</span><input v-model="cfg.s3_region" class="w-full py-2 px-3 text-sm mt-1" /></div>
            </div>
          </div>
          <div class="bg-card border border-border rounded-lg shadow-card transition-all duration-300 p-5">
            <h3 class="text-sm font-semibold mb-3">Secondary copy (3-2-1)</h3>
            <label class="flex items-center gap-2 text-sm mb-4 cursor-pointer">
              <input v-model="cfg.secondary_copy_enabled" type="checkbox" /> Enable secondary copy after backup
            </label>
            <div :class="{ 'opacity-50 pointer-events-none': !cfg.secondary_copy_enabled }">
              <div class="flex flex-wrap items-center gap-3 mb-4">
                <span class="block mb-0 text-xs font-semibold uppercase text-muted">Repository type</span>
                <div class="flex flex-wrap items-center gap-3">
                  <label v-for="t in ['SMB','NFS','S3']" :key="'s'+t" class="inline-flex items-center gap-1.5 text-xs font-medium cursor-pointer">
                    <input v-model="cfg.secondary_storage_type" type="radio" :value="t" /> {{ t }}
                  </label>
                </div>
              </div>
              <div v-if="cfg.secondary_storage_type === 'SMB'" class="space-y-3">
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">UNC Path</span><input v-model="cfg.secondary_smb_unc_path" class="w-full py-2 px-3 font-mono text-sm mt-1" /></div>
                <div class="grid grid-cols-2 gap-4">
                  <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Username</span><input v-model="cfg.secondary_smb_user" class="w-full py-2 px-3 text-sm mt-1" /></div>
                  <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Password</span><input v-model="cfg.secondary_smb_password" type="password" placeholder="(Unchanged)" class="w-full py-2 px-3 text-sm mt-1" /></div>
                </div>
              </div>
              <div v-else-if="cfg.secondary_storage_type === 'NFS' || !cfg.secondary_storage_type">
                <span class="block mb-1 text-xs font-semibold uppercase text-muted">NFS Export Path</span><input v-model="cfg.secondary_nfs_path" class="w-full py-2 px-3 font-mono text-sm mt-1" />
              </div>
              <div v-else class="grid grid-cols-2 gap-4">
                <div class="col-span-2"><span class="block mb-1 text-xs font-semibold uppercase text-muted">S3 Endpoint</span><input v-model="cfg.secondary_s3_endpoint" class="w-full py-2 px-3 text-sm mt-1" /></div>
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Access Key</span><input v-model="cfg.secondary_s3_access_key" class="w-full py-2 px-3 text-sm mt-1" /></div>
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Secret Key</span><input v-model="cfg.secondary_s3_secret_key" type="password" placeholder="(Unchanged)" class="w-full py-2 px-3 text-sm mt-1" /></div>
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Bucket</span><input v-model="cfg.secondary_s3_bucket" class="w-full py-2 px-3 text-sm mt-1" /></div>
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Region</span><input v-model="cfg.secondary_s3_region" class="w-full py-2 px-3 text-sm mt-1" /></div>
              </div>
            </div>
          </div>
          <div class="flex justify-end gap-2 mt-4">
            <button
              type="button"
              class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-6 py-2 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-55"
              @click="saveStorage"
            >Save storage</button>
          </div>
        </div>

        <!-- Engine -->
        <div v-else-if="panel === 'engine'">
          <h2 class="text-[1.375rem] font-bold mb-1">Engine</h2>
          <p class="text-sm text-muted mb-4">Worker, transport, and backup policy.</p>
          <div class="bg-card border border-border rounded-lg shadow-card transition-all duration-300 p-4">
            <section class="border-t border-border py-3 first:border-t-0 first:pt-0">
              <h3 class="text-[0.8125rem] font-semibold mb-2">Concurrency &amp; transport</h3>
              <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Max global</span><input v-model.number="cfg.max_global_backups" type="number" min="1" max="32" class="w-full py-1.5 px-3 text-center text-sm" /></div>
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Max per host</span><input v-model.number="cfg.max_backups_per_host" type="number" min="1" max="8" class="w-full py-1.5 px-3 text-center text-sm" /></div>
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Schedules / hour</span><input v-model.number="cfg.max_schedules_per_hour" type="number" min="1" max="12" class="w-full py-1.5 px-3 text-center text-sm" /></div>
                <div>
                  <span class="block mb-1 text-xs font-semibold uppercase text-muted">Transport</span>
                  <select v-model="cfg.backup_transport" class="w-full py-1.5 px-3 text-sm">
                    <option value="nbd">VDDK / NBD</option>
                    <option value="nfc">NFC only</option>
                    <option value="legacy">Legacy</option>
                  </select>
                </div>
                <div v-if="cfg.backup_transport === 'nbd' || !cfg.backup_transport" class="col-span-2">
                  <span class="block mb-1 text-xs font-semibold uppercase text-muted">VDDK library path</span><input v-model="cfg.vddk_libdir" class="w-full py-1.5 px-3 text-sm font-mono" />
                  <p class="mt-1.5 text-xs leading-relaxed text-muted">
                    The VDDK is proprietary and cannot be shipped with VMExec, so you supply it once.
                    Download the <strong>Linux 64-bit</strong> tarball
                    (<code class="font-mono">VMware-vix-disklib-*.tar.gz</code>, v8 or v9) from
                    <a href="https://developer.broadcom.com/sdks/vmware-virtual-disk-development-kit-vddk/latest"
                       target="_blank" rel="noopener noreferrer"
                       class="text-brand underline hover:no-underline">Broadcom</a>
                    (free account required), drop it in <code class="font-mono">vendor/vddk/</code> on the
                    server, and it installs automatically the next time a host is added.
                    Until then, backups using this transport will fail.
                  </p>
                </div>
                <div v-if="cfg.backup_transport === 'legacy'" class="col-span-2">
                  <span class="block mb-1 text-xs font-semibold uppercase text-muted">Disk estimate ×</span><input v-model.number="cfg.datastore_est_multiplier" type="number" min="1" max="3" step="0.1" class="w-full py-1.5 px-3 text-center text-sm" />
                </div>
              </div>
            </section>
            <section class="border-t border-border py-3 first:border-t-0 first:pt-0">
              <h3 class="text-[0.8125rem] font-semibold mb-2">Backups &amp; retention</h3>
              <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <div>
                  <span class="block mb-1 text-xs font-semibold uppercase text-muted">Incremental (CBT)</span>
                  <div class="flex items-center gap-2 min-h-8 mt-1">
                    <label class="relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center">
                      <input v-model="cfg.cbt_enabled" type="checkbox" class="peer sr-only" :disabled="cfg.storage_type === 'S3'" />
                      <span class="h-5 w-9 rounded-full bg-border peer-checked:bg-brand peer-disabled:opacity-45 transition-colors"></span>
                      <span class="absolute left-0.5 top-0.5 size-4 rounded-full bg-white shadow transition-transform peer-checked:translate-x-4"></span>
                    </label>
                    <span class="text-xs font-medium">{{ cfg.cbt_enabled ? 'On' : 'Off' }}</span>
                  </div>
                </div>
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Full every N runs</span><input v-model.number="cfg.cbt_full_interval" type="number" min="1" max="60" class="w-full py-1.5 px-3 text-center text-sm" /></div>
                <div>
                  <span class="block mb-1 text-xs font-semibold uppercase text-muted" title="Comma-separated path prefixes skipped during backup. Default fcd/ excludes vSphere CNS / Kubernetes CSI volumes, which attach and detach as pods move — protect those at the Kubernetes layer (e.g. Velero) instead.">Exclude disks</span>
                  <input v-model="cfg.exclude_disk_patterns" type="text" placeholder="fcd/" class="w-full py-1.5 px-3 text-sm font-mono" />
                </div>
                <div>
                  <span class="block mb-1 text-xs font-semibold uppercase text-muted">Retention</span>
                  <select v-model="cfg.retention_mode" class="w-full py-1.5 px-3 text-sm mt-1">
                    <option value="count">Count (per VM)</option>
                    <option value="gfs">GFS</option>
                  </select>
                </div>
                <template v-if="cfg.retention_mode === 'gfs'">
                  <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Daily</span><input v-model.number="cfg.gfs_daily_keep" type="number" min="1" max="90" class="w-full py-1.5 px-3 text-center text-sm mt-1" /></div>
                  <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Weekly</span><input v-model.number="cfg.gfs_weekly_keep" type="number" min="0" max="52" class="w-full py-1.5 px-3 text-center text-sm mt-1" /></div>
                  <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Monthly</span><input v-model.number="cfg.gfs_monthly_keep" type="number" min="0" max="120" class="w-full py-1.5 px-3 text-center text-sm mt-1" /></div>
                </template>
              </div>
              <p v-if="cfg.storage_type === 'S3'" class="mt-2 text-xs px-3 py-2 rounded bg-amber-500/12 text-amber-500">S3 selected — CBT disabled; full backups only.</p>
            </section>
            <section class="border-t border-border py-3 first:border-t-0 first:pt-0">
              <h3 class="text-[0.8125rem] font-semibold mb-2">Safety &amp; performance</h3>
              <div class="grid grid-cols-2 gap-3 items-end min-[641px]:grid-cols-4 min-[1101px]:grid-cols-7">
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Min DS free %</span><input v-model.number="cfg.datastore_min_free_pct" type="number" min="5" max="50" class="w-full py-1.5 px-3 text-center text-sm" /></div>
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">DS headroom GB</span><input v-model.number="cfg.datastore_headroom_gb" type="number" min="0" max="500" class="w-full py-1.5 px-3 text-center text-sm" /></div>
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Min repo GB</span><input v-model.number="cfg.repo_min_free_gb" type="number" min="1" max="10000" class="w-full py-1.5 px-3 text-center text-sm" /></div>
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Compression</span><input v-model.number="cfg.perf_compression_level" type="number" min="0" max="9" class="w-full py-1.5 px-3 text-center text-sm" /></div>
                <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">ESXi timeout</span><input v-model.number="cfg.backup_timeout_mins" type="number" min="5" max="1440" class="w-full py-1.5 px-3 text-center text-sm" /></div>
                <div>
                  <span class="block mb-1 text-xs font-semibold uppercase text-muted">Skip infra VMs</span>
                  <div class="flex items-center gap-2 min-h-8 mt-1">
                    <label class="relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center">
                      <input v-model="cfg.exclude_infra_vms" type="checkbox" class="peer sr-only" />
                      <span class="h-5 w-9 rounded-full bg-border peer-checked:bg-brand peer-disabled:opacity-45 transition-colors"></span>
                      <span class="absolute left-0.5 top-0.5 size-4 rounded-full bg-white shadow transition-transform peer-checked:translate-x-4"></span>
                    </label>
                    <span class="text-xs font-medium">{{ cfg.exclude_infra_vms ? 'On' : 'Off' }}</span>
                  </div>
                </div>
              </div>
            </section>
            <div class="flex justify-end gap-2 mt-3 pt-3 border-t border-border">
              <button
                type="button"
                class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-5 py-1.5 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-55"
                @click="saveStorage"
              >Save engine settings</button>
            </div>
          </div>
        </div>

        <!-- Hosts -->
        <div v-else-if="panel === 'hosts'">
          <h2 class="text-[1.375rem] font-bold mb-1">ESXi</h2>
          <p class="text-sm text-muted mb-4">Register standalone ESXi hypervisors or a vCenter Server.</p>
          <div class="bg-card border border-border rounded-lg shadow-card transition-all duration-300 overflow-hidden">
            <div class="flex items-center justify-between gap-3 py-3 px-5 border-b border-border bg-nav">
              <span class="font-semibold text-sm">Registered hosts</span>
              <button
                type="button"
                class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-hover disabled:opacity-55"
                @click="openAddHost"
              >Add host</button>
            </div>
            <div v-if="!hosts.length" class="p-8 text-center text-sm text-muted">No hosts configured.</div>
            <div v-for="h in hosts" :key="h.id" class="flex justify-between items-center px-5 py-3 border-b border-border">
              <div>
                <div class="font-medium">{{ h.name }}</div>
                <div class="text-xs font-mono text-brand">{{ h.host_ip }} · {{ h.connection_type || 'auto' }}</div>
              </div>
              <button
                type="button"
                class="inline-flex items-center justify-center p-1.5 rounded-md border border-border bg-transparent text-muted cursor-pointer transition-[color,background,border-color] duration-150 hover:text-red-400 hover:bg-red-500/8 hover:border-red-500/25"
                title="Remove host"
                @click="removeHost(h.id)"
              >
                <svg class="size-4 block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
              </button>
            </div>
          </div>
        </div>

        <!-- Kubernetes -->
        <div v-else-if="panel === 'kubernetes'">
          <h2 class="text-[1.375rem] font-bold mb-1">Kubernetes</h2>
          <p class="text-sm text-muted mb-4">Clusters registered for state-level backups (etcd / datastore snapshots, per-tenant exports).</p>
          <div class="bg-card border border-border rounded-lg shadow-card overflow-hidden">
            <div class="flex items-center justify-between gap-3 py-3 px-5 border-b border-border bg-nav">
              <span class="font-semibold text-sm">Registered clusters</span>
              <button type="button" class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-hover" @click="router.push('/kubernetes')">Manage in Kubernetes tab</button>
            </div>
            <div v-if="!clusters.length" class="p-8 text-center text-sm text-muted">No clusters registered. Add one from the Kubernetes tab.</div>
            <div v-for="c in clusters" :key="c.id" class="flex justify-between items-center px-5 py-3 border-b border-border">
              <div>
                <div class="font-medium">{{ c.name }}</div>
                <div class="text-xs font-mono text-brand">
                  {{ (c.targets || []).map((t) => t.name).join(', ') || 'no targets' }}
                  · {{ c.schedule_frequency === 'interval' ? `every ${c.interval_hours}h` : 'daily' }} · keep {{ c.retention_count }}
                </div>
              </div>
              <div class="text-xs" :class="c.last_status === 'Success' ? 'text-emerald-500' : (c.last_status === 'Failed' ? 'text-red-500' : 'text-muted')">{{ c.last_status }}</div>
            </div>
          </div>
        </div>

        <!-- Email -->
        <div v-else-if="panel === 'email'">
          <h2 class="text-[1.375rem] font-bold mb-1">Email (SMTP)</h2>
          <p class="text-sm text-muted mb-4">Outbound alerts and notifications.</p>
          <div class="bg-card border border-border rounded-lg shadow-card transition-all duration-300 p-5">
            <div class="flex flex-wrap items-center gap-3 mb-4">
              <span class="text-xs text-muted">Send a test message using the settings below.</span>
              <button
                type="button"
                class="inline-flex items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec px-3 py-1.5 text-xs font-semibold text-btn-sec-text hover:bg-btn-sec-hover ml-auto"
                @click="testEmail"
              >Send test email</button>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div class="col-span-2"><span class="block mb-1 text-xs font-semibold uppercase text-muted">SMTP server</span><input v-model="cfg.smtp_server" class="w-full py-2 px-3 font-mono text-sm mt-1" /></div>
              <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Port</span><input v-model.number="cfg.smtp_port" type="number" class="w-full py-2 px-3 text-center font-mono text-sm mt-1" /></div>
              <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Username</span><input v-model="cfg.smtp_user" class="w-full py-2 px-3 font-mono text-sm mt-1" /></div>
              <div><span class="block mb-1 text-xs font-semibold uppercase text-muted">Password</span><input v-model="cfg.smtp_password" type="password" placeholder="(Unchanged)" class="w-full py-2 px-3 font-mono text-sm mt-1" /></div>
              <div class="col-span-2"><span class="block mb-1 text-xs font-semibold uppercase text-muted">Default recipient</span><input v-model="cfg.smtp_to_email" type="email" class="w-full py-2 px-3 font-mono text-sm mt-1" /></div>
              <label class="flex items-center gap-2 cursor-pointer col-span-2"><input v-model="cfg.smtp_use_tls" type="checkbox" /><span class="text-sm">Use STARTTLS (port 587)</span></label>
              <label class="flex items-center gap-2 cursor-pointer col-span-2"><input v-model="cfg.smtp_use_ssl" type="checkbox" /><span class="text-sm">Use SSL/TLS (port 465)</span></label>
            </div>
            <div class="flex justify-end gap-2 mt-4">
              <button
                type="button"
                class="inline-flex items-center justify-center gap-1.5 rounded-md border-0 bg-brand px-6 py-2 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-55"
                @click="saveEmail"
              >Save email settings</button>
            </div>
          </div>
        </div>

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
        <div v-else-if="panel === 'syslogs'">
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
      </div>
    </div>

    <!-- Add host modal -->
    <FormModal
      :open="showAddHost"
      :title="hostAddResult ? (hostAddResult.vddk_installed ? 'Host added — VDDK ready' : 'Host added — VDDK setup') : 'Add ESXi / vCenter host'"
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
          >{{ hostAddBusy ? 'Adding…' : 'Add host' }}</button>
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
import { configApi, hostsApi, usersApi, logsApi, k8sApi } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useSetupWizard } from '@/composables/useSetupWizard'
import { useModal } from '@/composables/useModal'
import FormModal from '@/components/FormModal.vue'

const props = defineProps({ panel: { type: String, default: 'storage' } })
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { open: openWizard } = useSetupWizard()
const { confirm, alert } = useModal()

const panel = computed(() => props.panel || route.params.panel || 'storage')
const cfg = ref({ secondary_storage_type: 'NFS' })
const hosts = ref([])
const clusters = ref([])
const users = ref([])
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
    { id: 'hosts', label: 'ESXi' },
    { id: 'kubernetes', label: 'Kubernetes' },
    { id: 'engine', label: 'Engine' },
    { id: 'email', label: 'SMTP' },
    { id: 'users', label: 'Users' },
    { id: 'syslogs', label: 'System Logs' },
  ]
  if (!auth.isAdmin) return all.filter((p) => p.id === 'syslogs')
  return all
})

function go(id) { router.push(`/settings/${id}`) }

async function load() {
  if (auth.isAdmin) {
    cfg.value = await configApi.get()
    if (!cfg.value.secondary_storage_type) cfg.value.secondary_storage_type = 'NFS'
    hosts.value = await hostsApi.list()
    try { clusters.value = await k8sApi.list() } catch (e) { clusters.value = [] }
    if (panel.value === 'users') users.value = await usersApi.list()
  }
  if (panel.value === 'syslogs') {
    logs.value = await logsApi.system({ service_lines: 100, worker_lines: 100 })
  }
}

async function saveStorage() {
  await configApi.updateStorage(cfg.value)
  msg.value = 'Saved.'; msgOk.value = true
}

async function saveEmail() {
  await configApi.update(cfg.value)
  msg.value = 'Email settings saved.'; msgOk.value = true
}

async function testStorage() {
  const r = await configApi.testStorage()
  msg.value = r.message; msgOk.value = r.ok
}

async function testEmail() {
  const r = await configApi.testEmail()
  msg.value = r.message; msgOk.value = r.ok
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
    try { clusters.value = await k8sApi.list() } catch (e) { clusters.value = [] }
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
  if (!await confirm('Remove this host?', { title: 'Remove host', confirmText: 'Remove', danger: true })) return
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
