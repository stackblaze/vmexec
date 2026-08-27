<template>
  <div class="min-h-screen flex flex-col">
    <header class="sticky top-0 z-50 bg-nav border-b border-border">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="grid grid-cols-[1fr_auto_1fr] items-center h-16 gap-3">
          <div class="flex items-center gap-2 justify-self-start min-w-0">
            <RouterLink
              to="/overview"
              class="inline-flex items-center rounded-md no-underline text-inherit transition-opacity duration-150 hover:opacity-85"
              aria-label="VMExec home — Overview"
            >
              <span class="text-[1.35rem] font-extrabold tracking-[-0.03em] leading-none pointer-events-none">
                <span class="text-orange-500">VM</span><span class="text-main font-bold">Exec</span>
              </span>
            </RouterLink>
          </div>

          <nav class="hidden md:flex items-center justify-center gap-[0.15rem] h-full justify-self-center" aria-label="Main">
            <RouterLink
              v-for="t in tabs"
              :key="t.to"
              :to="t.to"
              class="inline-flex items-center h-16 px-[0.65rem] border-b-2 border-transparent text-sm font-medium bg-transparent cursor-pointer whitespace-nowrap no-underline text-muted transition-[color,border-color,background] duration-150 hover:!text-main"
              :class="{ '!text-brand !border-b-brand': isActive(t.to) }"
            >{{ t.label }}</RouterLink>
          </nav>

          <div class="flex items-center gap-3 justify-self-end shrink-0">
            <div class="relative" data-theme-picker>
              <button
                type="button"
                class="inline-flex items-center justify-center p-2 rounded-md text-muted bg-transparent border-none cursor-pointer transition-[color,background] duration-150 hover:text-main hover:bg-btn-sec-hover"
                title="Change theme"
                aria-label="Change theme"
                @click="themeOpen = !themeOpen"
              >
                <svg v-if="theme === 'light'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
                <svg v-else-if="theme === 'dark'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>
                <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
              </button>
              <div
                class="absolute right-0 top-[calc(100%+0.35rem)] z-50 min-w-[9.5rem] p-[0.35rem] rounded-lg border border-border bg-card shadow-[0_10px_28px_rgba(0,0,0,0.16)]"
                :class="{ hidden: !themeOpen }"
              >
                <button
                  v-for="opt in themeOptions"
                  :key="opt.id"
                  type="button"
                  class="flex items-center gap-2 w-full px-2.5 py-2 text-[0.8125rem] text-left bg-transparent border-none cursor-pointer text-btn-sec-text rounded-md transition-[background,color] duration-150 hover:bg-btn-sec-hover hover:text-main"
                  :class="{ 'text-brand font-semibold bg-[rgba(59,130,246,0.1)]': theme === opt.id }"
                  @click="setTheme(opt.id)"
                >
                  <svg
                    class="w-3.5 shrink-0 text-brand"
                    :class="theme === opt.id ? 'opacity-100' : 'opacity-0'"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  ><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                  {{ opt.label }}
                </button>
              </div>
            </div>

            <div class="relative hidden md:block" data-user-menu>
              <button
                type="button"
                class="inline-flex items-center gap-2 py-[0.35rem] pr-[0.55rem] pl-[0.35rem] rounded-lg border border-border bg-card text-main text-[0.8125rem] font-semibold cursor-pointer transition-[background,border-color] duration-150 hover:bg-btn-sec-hover"
                :class="{ 'border-brand text-brand': menuOpen }"
                @click="menuOpen = !menuOpen"
              >
                <span class="w-7 h-7 rounded-full inline-flex items-center justify-center text-xs font-bold uppercase bg-[rgba(59,130,246,0.15)] text-brand shrink-0">{{ initials }}</span>
                <span class="hidden sm:inline max-w-32 overflow-hidden text-ellipsis whitespace-nowrap">{{ auth.user?.username }}</span>
                <svg class="w-3.5 h-3.5 opacity-60 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
              </button>
              <div
                class="absolute right-0 top-[calc(100%+0.35rem)] z-[55] min-w-44 p-[0.35rem] rounded-lg border border-border bg-card shadow-[0_10px_28px_rgba(0,0,0,0.16)]"
                :class="{ hidden: !menuOpen }"
              >
                <div class="px-2.5 pt-[0.45rem] pb-[0.35rem] text-[0.6875rem] font-bold uppercase tracking-wide text-muted">{{ auth.user?.username || 'Account' }}</div>
                <RouterLink
                  to="/account/profile"
                  class="flex items-center w-full px-2.5 py-2 text-[0.8125rem] text-left bg-transparent border-none cursor-pointer text-btn-sec-text rounded-md no-underline transition-[background,color] duration-150 hover:bg-btn-sec-hover hover:text-main"
                  @click="menuOpen = false"
                >Profile</RouterLink>
                <RouterLink
                  v-if="auth.isAdmin"
                  to="/account/api"
                  class="flex items-center w-full px-2.5 py-2 text-[0.8125rem] text-left bg-transparent border-none cursor-pointer text-btn-sec-text rounded-md no-underline transition-[background,color] duration-150 hover:bg-btn-sec-hover hover:text-main"
                  @click="menuOpen = false"
                >API Keys</RouterLink>
                <div class="h-px my-[0.35rem] mx-1 bg-border"></div>
                <button
                  type="button"
                  class="block w-full px-2.5 py-2 text-[0.8125rem] font-semibold text-left text-red-500 rounded-md border-none bg-transparent cursor-pointer font-sans transition-colors duration-150 hover:bg-[rgba(239,68,68,0.08)]"
                  @click="signOut"
                >Sign out</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </header>

    <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <RouterView />
    </main>

    <footer class="mt-auto border-t border-border bg-gradient-to-b from-nav to-app py-5 pb-4">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col gap-3">
        <div class="flex flex-wrap items-center justify-between gap-x-6 gap-y-4">
          <div class="flex items-center gap-3 min-w-0">
            <div class="flex flex-col gap-0.5 min-w-0">
              <span class="text-base font-extrabold tracking-[-0.02em] leading-tight">
                <span class="text-orange-500">VM</span><span class="text-main font-bold">Exec</span>
              </span>
              <span class="text-xs text-muted leading-[1.35]">Open-source backup &amp; disaster recovery for VMware ESXi</span>
            </div>
          </div>
          <nav class="flex flex-wrap items-center gap-x-4 gap-y-[0.35rem] text-xs" aria-label="Footer">
            <a href="https://github.com/stackblaze-adam/vmexec" target="_blank" rel="noopener noreferrer" class="text-muted no-underline font-medium transition-colors duration-150 hover:text-orange-500">GitHub</a>
            <a href="https://stackblaze.com" target="_blank" rel="noopener noreferrer" class="text-orange-500 font-semibold no-underline transition-colors duration-150 hover:text-orange-500">Stackblaze.com</a>
            <a href="https://opensource.org/license/mit" target="_blank" rel="noopener noreferrer" class="text-muted no-underline font-medium transition-colors duration-150 hover:text-orange-500">MIT License</a>
          </nav>
        </div>
        <div class="flex flex-wrap items-center gap-x-[0.65rem] gap-y-[0.35rem] pt-3 border-t border-border text-[0.6875rem] text-muted leading-[1.4]">
          <span>&copy; {{ year }} VMExec</span>
          <span class="opacity-45 select-none" aria-hidden="true">·</span>
          <span>Sponsored by Stackblaze</span>
          <span class="opacity-45 select-none" aria-hidden="true">·</span>
          <span>Not affiliated with VMware, Broadcom, Veritas, or Veeam</span>
        </div>
      </div>
    </footer>

    <ConfirmModal />
    <SetupWizard v-if="auth.isAdmin" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSetupWizard } from '@/composables/useSetupWizard'
import ConfirmModal from '@/components/ConfirmModal.vue'
import SetupWizard from '@/components/SetupWizard.vue'

const auth = useAuthStore()
const { open: openSetupWizard } = useSetupWizard()
const route = useRoute()
const router = useRouter()
const menuOpen = ref(false)
const themeOpen = ref(false)
const theme = ref(localStorage.getItem('userTheme') || 'light')
const year = new Date().getFullYear()

const themeOptions = [
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
  { id: 'cyberpunk', label: 'Cyberpunk' },
]

const tabs = [
  { to: '/overview', label: 'Overview' },
  { to: '/backup', label: 'Backup' },
  { to: '/restore', label: 'Restore' },
  { to: '/kubernetes', label: 'Kubernetes' },
  { to: '/settings/storage', label: 'Settings' },
]

const initials = computed(() => (auth.user?.username || '?').slice(0, 2).toUpperCase())

function isActive(path) {
  if (path.startsWith('/settings')) return route.path.startsWith('/settings')
  return route.path === path || route.path.startsWith(path + '/')
}

function setTheme(id) {
  theme.value = id
  themeOpen.value = false
  applyTheme()
}

function applyTheme() {
  localStorage.setItem('userTheme', theme.value)
  document.documentElement.setAttribute('data-theme', theme.value)
}

async function signOut() {
  menuOpen.value = false
  await auth.logout()
  router.push('/login')
}

function onDocClick(e) {
  if (!e.target.closest('[data-user-menu]')) menuOpen.value = false
  if (!e.target.closest('[data-theme-picker]')) themeOpen.value = false
}

onMounted(async () => {
  if (!auth.user) await auth.bootstrap()
  applyTheme()
  document.addEventListener('click', onDocClick)
  if (auth.isAdmin && auth.setupSuggested && !localStorage.getItem('setup_wizard_done')) {
    setTimeout(() => openSetupWizard(), 300)
  }
})
onUnmounted(() => document.removeEventListener('click', onDocClick))
</script>
