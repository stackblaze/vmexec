<template>
  <div class="flex min-h-screen items-center justify-center bg-app px-4">
    <div class="w-full max-w-md rounded-lg border border-border bg-card p-8 shadow-card">
      <h1 class="mb-2 text-2xl font-bold">VMExec</h1>
      <p class="mb-6 text-sm text-muted">Sign in to manage backups</p>

      <form v-if="step === 'password'" @submit.prevent="onLogin">
        <label class="mb-1 block text-xs font-semibold uppercase text-muted">Username</label>
        <input v-model="username" class="mb-4 w-full px-3 py-2" required autocomplete="username" />
        <label class="mb-1 block text-xs font-semibold uppercase text-muted">Password</label>
        <input v-model="password" type="password" class="mb-4 w-full px-3 py-2" required autocomplete="current-password" />
        <p v-if="error" class="mb-3 text-sm text-red-400">{{ error }}</p>
        <button
          type="submit"
          class="inline-flex w-full items-center justify-center gap-1.5 rounded-md border-0 bg-brand py-2 font-semibold text-white hover:bg-brand-hover disabled:opacity-55"
          :disabled="auth.loading"
        >
          {{ auth.loading ? 'Signing in…' : 'Sign in' }}
        </button>
      </form>

      <form v-else @submit.prevent="onMfa">
        <p class="mb-4 text-sm text-muted">
          Enter the code from your authenticator for <strong>{{ auth.mfaPendingUser }}</strong>
        </p>
        <label class="mb-1 block text-xs font-semibold uppercase text-muted">Authenticator code</label>
        <input
          v-model="mfaCode"
          class="mb-4 w-full px-3 py-2 font-mono tracking-widest"
          maxlength="6"
          required
          autocomplete="one-time-code"
        />
        <p v-if="error" class="mb-3 text-sm text-red-400">{{ error }}</p>
        <button
          type="submit"
          class="inline-flex w-full items-center justify-center gap-1.5 rounded-md border-0 bg-brand py-2 font-semibold text-white hover:bg-brand-hover disabled:opacity-55"
        >
          Verify
        </button>
        <button
          type="button"
          class="mt-2 inline-flex w-full items-center justify-center gap-1.5 rounded-md border border-btn-sec-border bg-btn-sec py-2 text-btn-sec-text hover:bg-btn-sec-hover"
          @click="step = 'password'; error = ''"
        >
          Back
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const mfaCode = ref('')
const step = ref('password')
const error = ref('')

async function onLogin() {
  error.value = ''
  try {
    const result = await auth.login(username.value, password.value)
    if (result === 'mfa') {
      step.value = 'mfa'
      return
    }
    if (result === 'setup') {
      router.push('/mfa-setup')
      return
    }
    router.push(route.query.redirect || '/backup')
  } catch (e) {
    error.value = e.message
  }
}

async function onMfa() {
  error.value = ''
  try {
    await auth.submitMfa(mfaCode.value)
    router.push(route.query.redirect || '/backup')
  } catch (e) {
    error.value = e.message
  }
}
</script>
