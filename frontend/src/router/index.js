import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
  { path: '/mfa-setup', name: 'mfa-setup', component: () => import('@/views/MfaSetupView.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/components/AppShell.vue'),
    children: [
      { path: '', redirect: '/backup' },
      // Overview was folded into Backup (status strip + banner); old links land there.
      { path: 'overview', redirect: '/backup' },
      { path: 'backup', name: 'backup', component: () => import('@/views/BackupView.vue') },
      { path: 'restore', name: 'restore', component: () => import('@/views/RestoreView.vue') },
      { path: 'settings/:panel?', name: 'settings', component: () => import('@/views/SettingsView.vue'), props: true },
      { path: 'account/:panel?', name: 'account', component: () => import('@/views/AccountView.vue'), props: true },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    if (to.name === 'login' && auth.isAuthenticated) return '/backup'
    return true
  }
  try {
    if (!auth.user) await auth.fetchMe()
    if (to.name === 'mfa-setup' || (!auth.user?.is_mfa_enabled && auth.mfaSetup)) {
      if (to.path !== '/mfa-setup') return '/mfa-setup'
    }
    return true
  } catch {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
})

export default router
