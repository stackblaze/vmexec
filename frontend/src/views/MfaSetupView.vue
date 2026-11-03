<template>
  <div class="flex min-h-screen items-center justify-center bg-app px-4">
    <div class="w-full max-w-md rounded-lg border border-border bg-card p-8 shadow-card">
      <h1 class="mb-2 text-xl font-bold">Set up MFA</h1>
      <p class="mb-4 text-sm text-muted">Scan this QR code with Google Authenticator or similar.</p>
      <div class="mb-4 flex justify-center">
        <img
          v-if="qr"
          :src="'data:image/png;base64,' + qr"
          alt="MFA QR"
          class="rounded border border-border"
        />
      </div>
      <p class="mb-4 break-all rounded bg-app p-2 font-mono text-xs text-muted">{{ secret }}</p>
      <form @submit.prevent="onVerify">
        <label class="mb-1 block text-xs font-semibold uppercase text-muted">Verification code</label>
        <input v-model="code" class="mb-4 w-full px-3 py-2 font-mono" maxlength="6" required />
        <p v-if="error" class="mb-3 text-sm text-red-400">{{ error }}</p>
        <button
          type="submit"
          class="inline-flex w-full items-center justify-center gap-1.5 rounded-md border-0 bg-brand py-2 font-semibold text-white hover:bg-brand-hover disabled:opacity-55"
        >
          Enable MFA &amp; continue
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/client'

const auth = useAuthStore()
const router = useRouter()
const qr = ref(auth.mfaSetup?.qr_code || '')
const secret = ref(auth.mfaSetup?.secret || '')
const code = ref('')
const error = ref('')

onMounted(async () => {
  if (!qr.value) {
    try {
      const res = await authApi.mfaSetupStart()
      qr.value = res.qr_code
      secret.value = res.secret
      auth.mfaSetup = res
    } catch (e) {
      error.value = e.message
    }
  }
})

async function onVerify() {
  error.value = ''
  try {
    await auth.completeMfaSetup(code.value)
    router.push('/backup')
  } catch (e) {
    error.value = e.message
  }
}
</script>
