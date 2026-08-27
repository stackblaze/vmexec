<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-4 mb-6">
      <h1 class="text-2xl font-bold">Backup</h1>
      <button type="button" :class="btnSecondary" class="px-3 py-1.5 text-sm" @click="showInventory = true">Inventory</button>
    </div>

    <div
      v-if="paused"
      class="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 mb-3 border border-amber-500/35 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400"
    >
      <span class="text-sm">All backups are paused</span>
      <button type="button" :class="btnSecondary" class="px-3 py-1 text-xs" @click="togglePause(false)">Resume all</button>
    </div>

    <div class="flex flex-wrap gap-3 mb-4">
      <input v-model="search" type="text" placeholder="Search VMs…" class="flex-1 min-w-[200px] px-3 py-2 text-sm" />
      <select v-model="stateFilter" class="py-2 px-3 text-sm">
        <option value="all">All States</option>
        <option value="active">Currently Running</option>
        <option value="scheduled">Scheduled</option>
        <option value="error">Failed</option>
        <option value="success">Successful</option>
      </select>
    </div>

    <div
      v-if="selectedIds.size"
      class="flex flex-wrap items-center gap-3 px-4 py-2.5 mb-3 border border-border rounded-md bg-nav"
    >
      <span class="text-sm font-medium">{{ selectedIds.size }} selected</span>
      <button type="button" :class="btnPrimary" class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium" @click="runSelected">
        <svg class="w-3.5 h-3.5 shrink-0" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>
        Run selected
      </button>
      <button type="button" :class="btnDanger" class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium" @click="abortSelected">
        <svg class="w-3.5 h-3.5 shrink-0" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6h12v12H6z"/></svg>
        Abort selected
      </button>
      <button type="button" :class="btnSecondary" class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium" @click="allSelectedPaused ? resumeSelected() : pauseSelected()">
        <svg v-if="allSelectedPaused" class="w-3.5 h-3.5 shrink-0" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h3v14H5V5zm5 7l9-7v14l-9-7z"/></svg>
        <svg v-else class="w-3.5 h-3.5 shrink-0" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h4v14H6V5zm8 0h4v14h-4V5z"/></svg>
        {{ allSelectedPaused ? 'Resume selected' : 'Pause selected' }}
      </button>
      <button type="button" :class="btnSecondary" class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium hover:text-red-500" @click="removeSelected">
        <svg class="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
        Remove selected
      </button>
      <button type="button" class="text-xs font-medium opacity-60" @click="clearSelection">Clear</button>
    </div>

    <div class="rounded-lg border border-border bg-card shadow-card overflow-x-auto">
      <table class="w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th class="w-10 text-center text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav">
              <input ref="selectAllRef" type="checkbox" class="w-4 h-4 cursor-pointer accent-brand" :checked="allVisibleSelected" @change="toggleSelectAll" />
            </th>
            <th
              class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav cursor-pointer select-none whitespace-nowrap hover:text-main"
              :class="{ 'text-brand': sortKey === 'name' }"
              @click="setSort('name')"
            >
              Virtual Machine<span class="inline-block w-3 ml-0.5 opacity-85">{{ sortInd('name') }}</span>
            </th>
            <th
              class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav cursor-pointer select-none whitespace-nowrap hover:text-main"
              :class="{ 'text-brand': sortKey === 'host' }"
              @click="setSort('host')"
            >
              Host<span class="inline-block w-3 ml-0.5 opacity-85">{{ sortInd('host') }}</span>
            </th>
            <th
              class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav cursor-pointer select-none whitespace-nowrap hover:text-main"
              :class="{ 'text-brand': sortKey === 'status' }"
              @click="setSort('status')"
            >
              Status<span class="inline-block w-3 ml-0.5 opacity-85">{{ sortInd('status') }}</span>
            </th>
            <th class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav">Progress</th>
            <th
              class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav cursor-pointer select-none whitespace-nowrap hover:text-main"
              :class="{ 'text-brand': sortKey === 'lastbackup' }"
              @click="setSort('lastbackup')"
            >
              Last Backup<span class="inline-block w-3 ml-0.5 opacity-85">{{ sortInd('lastbackup') }}</span>
            </th>
            <th
              class="text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav cursor-pointer select-none whitespace-nowrap hover:text-main"
              :class="{ 'text-brand': sortKey === 'schedule' }"
              @click="setSort('schedule')"
            >
              Schedule<span class="inline-block w-3 ml-0.5 opacity-85">{{ sortInd('schedule') }}</span>
            </th>
            <th class="text-right text-[0.7rem] font-semibold uppercase tracking-wide text-muted px-4 py-3 border-b border-border bg-nav">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="vm in sorted" :key="vm.id" class="hover:bg-blue-500/[0.04]">
            <td class="text-center px-4 py-3 border-b border-border align-middle">
              <input type="checkbox" class="w-4 h-4 cursor-pointer accent-brand" :checked="selectedIds.has(vm.id)" @change="toggleSelect(vm.id, $event.target.checked)" />
            </td>
            <td class="px-4 py-3 border-b border-border align-middle">
              <div class="font-semibold">{{ vm.vm_name }}</div>
              <div class="text-xs text-muted">{{ vm.cpu_count }} vCPU · {{ Math.round((vm.memory_mb || 0) / 1024) }}GB · {{ vm.storage_gb }}GB</div>
            </td>
            <td class="px-4 py-3 border-b border-border align-middle text-xs font-mono text-brand">{{ vm.host_name || '—' }}</td>
            <td class="px-4 py-3 border-b border-border align-middle">
              <StatusBadge v-bind="scheduleState(vm)" />
            </td>
            <td class="px-4 py-3 border-b border-border align-middle min-w-[140px]">
              <button
                v-if="isActive(vm) || hasRun(vm)"
                type="button"
                class="w-full text-left rounded-md cursor-pointer transition-shadow border-0 bg-transparent p-0"
                :class="isActive(vm) || !isFailed(vm) ? 'hover:ring-2 hover:ring-blue-500/25' : 'hover:ring-2 hover:ring-red-500/25'"
                title="View backup details"
                @click="openJobDrawer(vm)"
              >
                <div v-if="isActive(vm)">
                  <div class="flex justify-between text-xs mb-1">
                    <span class="truncate max-w-[120px] text-brand">{{ progressText(vm) }}</span>
                    <span v-if="!startingUp(vm)" class="font-mono">{{ liveProgress(vm).progress }}%</span>
                  </div>
                  <div class="block h-1 mt-1 bg-border rounded-sm overflow-hidden">
                    <div v-if="startingUp(vm)" class="h-full w-2/5 bg-brand rounded-sm animate-pulse"></div>
                    <div v-else class="h-full bg-brand rounded-sm transition-[width] duration-500 ease-in-out" :style="{ width: liveProgress(vm).progress + '%' }"></div>
                  </div>
                </div>
                <StatusBadge v-else v-bind="rowStatus(vm)" />
              </button>
              <span v-else class="text-xs text-muted italic">Not backed up</span>
            </td>
            <td class="px-4 py-3 border-b border-border align-middle text-xs font-mono whitespace-nowrap text-muted">
              <span>{{ formatDate(liveProgress(vm).last_backup_ts ? liveProgress(vm).last_backup_ts : vm.last_backup) }}</span>
              <span v-if="!isActive(vm) && vm.last_backup && vm.last_backup_duration > 0" class="block text-[0.7rem] opacity-70">took {{ formatDuration(vm.last_backup_duration) }}</span>
            </td>
            <td class="px-4 py-3 border-b border-border align-middle text-xs whitespace-nowrap">{{ scheduleLabel(vm) }}</td>
            <td class="text-right px-4 py-3 border-b border-border align-middle whitespace-nowrap overflow-visible relative">
              <div class="inline-flex gap-1 items-center justify-end">
                <button
                  v-if="isActive(vm)"
                  type="button"
                  :class="btnIconDanger"
                  title="Stop backup"
                  :disabled="!auth.isOperator"
                  @click="stopJob(vm.id)"
                >
                  <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6h12v12H6z"/></svg>
                </button>
                <button
                  v-else
                  type="button"
                  :class="btnIconPrimary"
                  title="Run backup"
                  :disabled="!auth.isOperator"
                  @click="runJob(vm.id)"
                >
                  <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>
                </button>
                <div class="inline-block" data-schedule-menu>
                  <button type="button" :class="btnIconSecondary" title="Schedule settings" @click="toggleScheduleMenu(vm.id, $event)">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  </button>
                </div>
                <button type="button" :class="btnIconSecondary" class="hover:text-red-500" title="Remove from tasks" @click="removeVm(vm)">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="!sorted.length">
            <td colspan="8" class="py-12 text-center text-muted">
              <div v-if="!jobs.length" class="text-sm font-medium mb-1">No backup tasks configured</div>
              <div v-if="!jobs.length" class="text-xs opacity-70 mb-3">Select VMs in Inventory, then apply selection.</div>
              <button v-if="!jobs.length" type="button" :class="btnSecondary" class="px-3 py-1.5 text-xs font-semibold" @click="showInventory = true">Open Inventory</button>
              <span v-else>No VMs match your filters</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Inventory drawer -->
    <div v-if="showInventory" class="fixed inset-0 z-80">
      <div class="absolute inset-0 bg-black/45 backdrop-blur-[1px]" @click="showInventory = false"></div>
      <aside
        class="absolute top-0 right-0 bottom-0 w-full max-w-lg flex flex-col bg-card border-l border-border shadow-[-4px_0_24px_rgba(0,0,0,0.18)]"
        role="dialog"
        aria-labelledby="inventory-drawer-title"
      >
        <div class="flex items-center justify-between gap-3 px-4 pt-4 pb-3 border-b border-border bg-nav shrink-0">
          <div>
            <h3 id="inventory-drawer-title" class="text-base font-semibold leading-tight m-0">Backup inventory</h3>
            <p class="text-[0.625rem] mt-0.5 text-muted opacity-75">{{ allVms.length }} VM(s) · scan and enable backup</p>
          </div>
          <button
            type="button"
            class="p-1.5 rounded-md text-muted border border-border bg-transparent cursor-pointer hover:text-main hover:bg-card"
            aria-label="Close inventory"
            @click="showInventory = false"
          >
            <svg class="w-4 h-4 block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="flex-1 min-h-0 overflow-hidden flex flex-col">
          <div id="backup-inventory-panel" class="flex flex-col h-full min-h-0">
            <div class="flex flex-col gap-2 px-4 py-3 border-b border-border bg-nav shrink-0">
              <select v-model="scanHostId" class="w-full px-3 py-2 text-xs rounded-md">
                <option v-for="h in hosts" :key="h.id" :value="h.id">{{ h.name }} ({{ h.host_ip }})</option>
              </select>
              <button type="button" :class="btnPrimary" class="w-full px-3 py-2 text-xs font-semibold" @click="syncHost">Scan datacenter</button>
            </div>
            <div class="flex-1 min-h-0 overflow-auto">
              <table class="w-full border-collapse text-xs text-left">
                <thead>
                  <tr>
                    <th class="sticky top-0 z-[1] w-11 text-center text-[0.6875rem] font-semibold uppercase tracking-wide text-muted px-3 py-2 bg-nav border-b border-border">
                      <input type="checkbox" class="w-3.5 h-3.5 cursor-pointer accent-brand" :checked="inventoryAllSelected" @change="toggleInventoryAll" aria-label="Select all for backup" />
                    </th>
                    <th class="sticky top-0 z-[1] w-[4.5rem] text-center text-[0.6875rem] font-semibold uppercase tracking-wide text-muted px-3 py-2 bg-nav border-b border-border">Power</th>
                    <th class="sticky top-0 z-[1] text-left text-[0.6875rem] font-semibold uppercase tracking-wide text-muted px-3 py-2 bg-nav border-b border-border">Virtual Machine</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="vm in allVms" :key="vm.id" class="hover:bg-blue-500/[0.04]">
                    <td class="w-11 text-center px-3 py-2 border-b border-border align-middle">
                      <input type="checkbox" class="w-3.5 h-3.5 cursor-pointer accent-brand" :checked="vm.is_selected" @change="toggleInventoryVm(vm, $event.target.checked)" />
                    </td>
                    <td class="w-[4.5rem] text-center px-3 py-2 border-b border-border align-middle">
                      <StatusBadge :cls="powerCls(vm.power_state)" :label="powerLabel(vm.power_state)" class="text-[0.625rem] px-[0.45rem] py-0.5" />
                    </td>
                    <td class="px-3 py-2 border-b border-border align-middle">
                      <div class="font-medium overflow-hidden text-ellipsis whitespace-nowrap max-w-64" :title="vm.vm_name">{{ vm.vm_name }}</div>
                      <div class="text-[0.625rem] font-mono opacity-60 mt-0.5 overflow-hidden text-ellipsis whitespace-nowrap">{{ vm.host_name }}</div>
                    </td>
                  </tr>
                  <tr v-if="!allVms.length">
                    <td colspan="3" class="px-3 py-8 text-center text-xs font-medium text-muted">No inventory. Run a scan.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <div class="flex items-center justify-between gap-3 px-4 py-3.5 border-t border-border bg-nav shrink-0 max-[480px]:flex-col max-[480px]:items-stretch max-[480px]:gap-2.5">
          <span class="text-xs text-muted shrink-0">{{ inventorySelectionLabel }}</span>
          <div class="flex gap-2 flex-wrap justify-end max-[480px]:justify-stretch">
            <button type="button" :class="btnSecondary" class="px-3 py-1.5 text-xs font-medium max-[480px]:flex-1" @click="showInventory = false">Cancel</button>
            <button type="button" :class="btnPrimary" class="px-3 py-1.5 text-xs font-semibold max-[480px]:flex-1" :disabled="!inventoryPendingCount" @click="applyInventory">Apply selection ({{ inventoryPendingCount }})</button>
          </div>
        </div>
      </aside>
    </div>

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
              <span class="block font-semibold uppercase tracking-wide text-muted mb-1">Schedule</span>
              <span>{{ scheduleLabel(detailVm) }}</span>
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

    <!-- Schedule popover (teleported to escape table overflow clipping) -->
    <Teleport to="body">
      <div
        v-if="schedMenu"
        data-schedule-menu
        class="fixed z-[90] w-[16rem] p-3 rounded-lg border border-border bg-card shadow-[0_10px_28px_rgba(0,0,0,0.16)] text-left"
        :style="{ top: schedMenu.y + 'px', left: schedMenu.x + 'px' }"
      >
        <div class="text-[0.6875rem] font-bold uppercase tracking-wider text-muted mb-2 pb-1.5 border-b border-border">Schedule</div>
        <JobSchedulePopover :vm="schedMenu.vm" @updated="onVmUpdated" />
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { jobsApi, hostsApi, logsApi } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useJobProgress, isJobActive, statusBadge, formatDate, formatDuration, formatRelativeTime } from '@/composables/useJobProgress'
import { useModal } from '@/composables/useModal'
import StatusBadge from '@/components/StatusBadge.vue'
import JobSchedulePopover from '@/components/JobSchedulePopover.vue'

const btnPrimary =
  'inline-flex items-center justify-center rounded-md border-0 bg-brand text-white hover:bg-brand-hover transition-colors duration-200 disabled:opacity-55'
const btnSecondary =
  'inline-flex items-center justify-center rounded-md border border-btn-sec-border bg-btn-sec text-btn-sec-text hover:bg-btn-sec-hover transition-colors duration-200'
const btnDanger =
  'inline-flex items-center justify-center rounded-md border-0 bg-red-600 text-white hover:bg-red-700 transition-colors duration-200'
const btnIcon =
  'inline-flex items-center justify-center w-8 h-8 rounded-md transition-colors duration-200 disabled:opacity-55 disabled:cursor-not-allowed shrink-0'
const btnIconPrimary = `${btnIcon} border-0 bg-brand text-white hover:bg-brand-hover`
const btnIconDanger = `${btnIcon} border-0 bg-red-600 text-white hover:bg-red-700`
const btnIconSecondary = `${btnIcon} border border-btn-sec-border bg-btn-sec text-btn-sec-text hover:bg-btn-sec-hover`

const auth = useAuthStore()
const { confirm, alert } = useModal()
const allVms = ref([])
const hosts = ref([])
const progressMap = ref({})
const paused = ref(false)
const search = ref('')
const stateFilter = ref('all')
const showInventory = ref(false)
const scanHostId = ref(null)
const pendingSelection = ref({})
const selectedIds = ref(new Set())
const sortKey = ref('schedule')
const sortDir = ref('asc')
const openScheduleId = ref(null)
const schedMenu = ref(null)  // { vm, x, y } — teleported popover position
const selectAllRef = ref(null)
const detailVm = ref(null)
const detailLogs = ref([])
const detailLogsLoading = ref(false)

useJobProgress((data) => { progressMap.value = data })

const jobs = computed(() => allVms.value.filter((v) => v.is_selected))

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

function scheduleLabel(vm) {
  const h = String(vm.schedule_hour).padStart(2, '0')
  const m = String(vm.schedule_minute).padStart(2, '0')
  const cbt = vm.cbt_enabled !== false ? 'CBT' : 'full'
  let freq = (vm.schedule_frequency || 'daily').replace(/^./, (c) => c.toUpperCase())
  if (vm.schedule_frequency === 'interval') freq = `Every ${vm.interval_hours || 6}h`
  return `${freq} ${h}:${m} · keep ${vm.retention_count} · ${cbt}`
}

function statusSort(vm) {
  return vm.is_job_active ? '0-scheduled' : '1-paused'
}

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  return jobs.value.filter((vm) => {
    if (!vm.vm_name.toLowerCase().includes(q)) return false
    const p = liveProgress(vm)
    const active = isActive(vm)
    const status = p.last_status || vm.last_status
    if (stateFilter.value === 'active' && !active) return false
    if (stateFilter.value === 'scheduled' && !vm.is_job_active) return false
    if (stateFilter.value === 'error' && status !== 'Failed') return false
    if (stateFilter.value === 'success' && status !== 'Success') return false
    return true
  })
})

const sorted = computed(() => {
  const list = [...filtered.value]
  const dir = sortDir.value === 'asc' ? 1 : -1
  list.sort((a, b) => {
    let av; let bv
    if (sortKey.value === 'name') {
      av = a.vm_name.toLowerCase(); bv = b.vm_name.toLowerCase()
    } else if (sortKey.value === 'host') {
      av = (a.host_name || '').toLowerCase(); bv = (b.host_name || '').toLowerCase()
    } else if (sortKey.value === 'lastbackup') {
      av = a.last_backup ? new Date(a.last_backup).getTime() : 0
      bv = b.last_backup ? new Date(b.last_backup).getTime() : 0
    } else if (sortKey.value === 'status') {
      av = statusSort(a); bv = statusSort(b)
    } else if (sortKey.value === 'schedule') {
      av = (a.schedule_hour || 0) * 60 + (a.schedule_minute || 0)
      bv = (b.schedule_hour || 0) * 60 + (b.schedule_minute || 0)
    } else return 0
    if (av < bv) return -1 * dir
    if (av > bv) return 1 * dir
    return 0
  })
  return list
})

const allVisibleSelected = computed(() => sorted.value.length > 0 && sorted.value.every((v) => selectedIds.value.has(v.id)))

// One pause/resume toggle: Resume only when every selected VM is paused,
// otherwise Pause (a mixed selection pauses everything, then offers Resume).
const allSelectedPaused = computed(() => {
  const sel = allVms.value.filter((v) => selectedIds.value.has(v.id))
  return sel.length > 0 && sel.every((v) => v.is_job_active === false)
})
const inventoryAllSelected = computed(() => allVms.value.length > 0 && allVms.value.every((v) => v.is_selected))
const inventoryPendingCount = computed(() => Object.keys(pendingSelection.value).length)
const inventorySelectionLabel = computed(() => {
  const n = inventoryPendingCount.value
  return n ? `${n} change${n === 1 ? '' : 's'} pending` : 'No changes'
})

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

function toggleScheduleMenu(id, ev) {
  openScheduleId.value = openScheduleId.value === id ? null : id
  if (openScheduleId.value === null) { schedMenu.value = null; return }
  const vm = allVms.value.find((v) => v.id === id)
  const rect = ev.currentTarget.getBoundingClientRect()
  const width = 256
  const x = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))
  schedMenu.value = { vm, x, y: rect.bottom + 6 }
}

function onVmUpdated(updated) {
  const idx = allVms.value.findIndex((v) => v.id === updated.id)
  if (idx >= 0) allVms.value[idx] = { ...allVms.value[idx], ...updated }
}

function powerCls(s) {
  if (s === 'poweredOn') return 'status-success'
  return 'status-neutral'
}

function powerLabel(s) {
  if (s === 'poweredOn') return 'ON'
  if (s === 'poweredOff') return 'OFF'
  return s || '?'
}

async function load() {
  const [vms, h, sched] = await Promise.all([jobsApi.vms(), hostsApi.list(), jobsApi.scheduler()])
  allVms.value = vms
  hosts.value = h
  paused.value = sched.paused
  if (h.length && !scanHostId.value) scanHostId.value = h[0].id
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

async function removeVm(vm) {
  const running = isActive(vm)
  const msg = running
    ? `${vm.vm_name} has a backup running. Remove from tasks anyway?`
    : `Remove ${vm.vm_name} from backup tasks? You can re-enable it from Inventory.`
  const ok = await confirm(msg, { title: 'Remove from tasks', confirmText: 'Remove', danger: true })
  if (!ok) return
  await jobsApi.patch(vm.id, { is_selected: false, is_job_active: false })
  selectedIds.value.delete(vm.id)
  await load()
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

async function resumeSelected() {
  const ids = [...selectedIds.value]
  if (!ids.length) return
  const ok = await confirm(`Resume scheduled backups for ${ids.length} VM(s)?`, { title: 'Resume selected', confirmText: 'Resume' })
  if (!ok) return
  let n = 0
  for (const id of ids) {
    try {
      await jobsApi.patch(id, { is_job_active: true })
      n++
    } catch { /* continue */ }
  }
  await alert(`Resumed schedules for ${n} VM(s).`, { title: 'Resume selected' })
  clearSelection()
  await load()
}

async function removeSelected() {
  const ids = [...selectedIds.value]
  if (!ids.length) return
  const ok = await confirm(`Remove ${ids.length} VM(s) from backup tasks?`, { title: 'Remove selected', confirmText: 'Remove', danger: true })
  if (!ok) return
  for (const id of ids) {
    await jobsApi.patch(id, { is_selected: false, is_job_active: false })
  }
  clearSelection()
  await load()
}

function toggleInventoryVm(vm, checked) {
  pendingSelection.value[vm.id] = checked
  vm.is_selected = checked
}

function toggleInventoryAll(e) {
  allVms.value.forEach((vm) => toggleInventoryVm(vm, e.target.checked))
}

async function syncHost() {
  if (!scanHostId.value) return
  await hostsApi.sync(scanHostId.value)
  await load()
}

async function applyInventory() {
  const updates = Object.entries(pendingSelection.value).map(([id, sel]) => ({
    vm_id: Number(id),
    is_selected: sel,
  }))
  if (updates.length) {
    // Capacity check first: warn when the proposed jobs project past the
    // repository's capacity threshold, but let the user proceed.
    try {
      const res = await jobsApi.inventoryApply({ updates, restagger: true, dry_run: true })
      const p = res?.projection
      if (p?.warn) {
        const ok = await confirm(
          `This selection projects to ~${p.projected_gb >= 1000 ? (p.projected_gb / 1000).toFixed(2) + ' TB' : p.projected_gb.toFixed(0) + ' GB'} at steady state`
          + (p.capacity_gb ? ` on ${p.capacity_gb.toFixed(0)} GB of storage (${p.projected_pct.toFixed(0)}%)` : '')
          + '. Backups may fill the repository. Continue?',
          { title: 'Storage capacity', confirmText: 'Apply anyway' },
        )
        if (!ok) return
      }
    } catch { /* projection is advisory — never block apply on its failure */ }
    await jobsApi.inventoryApply({ updates, restagger: true })
  }
  pendingSelection.value = {}
  showInventory.value = false
  await load()
}

function onDocClick(e) {
  if (!e.target.closest('[data-schedule-menu]')) {
    openScheduleId.value = null
    schedMenu.value = null
  }
}

onMounted(() => {
  load()
  document.addEventListener('click', onDocClick)
})
onUnmounted(() => document.removeEventListener('click', onDocClick))
</script>
