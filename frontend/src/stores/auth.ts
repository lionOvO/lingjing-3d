import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import api from '../services/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('moonlit_access_token') || '')
  const user = ref<any>(null)
  const loading = ref(false)
  const hydrated = ref(false)
  const error = ref('')
  const isAuthenticated = computed(() => Boolean(token.value && user.value))

  async function hydrate(): Promise<boolean> {
    if (!token.value) {
      user.value = null
      hydrated.value = true
      return false
    }
    try {
      user.value = (await api.get('/auth/me')).data
      hydrated.value = true
      return true
    } catch (cause: any) {
      // A token without a valid user must never be treated as a successful login.
      console.error('[auth] failed to hydrate current user', {
        status: cause?.response?.status,
        message: cause?.message,
      })
      logout()
      hydrated.value = true
      return false
    }
  }
  async function authenticate(endpoint: string, payload: Record<string, string>) {
    loading.value = true; error.value = ''
    try {
      const { data } = await api.post(endpoint, payload)
      token.value = data.access_token
      localStorage.setItem('moonlit_access_token', token.value)
      if (!(await hydrate())) {
        error.value = '登录状态校验失败，请确认服务正常后重试'
        return false
      }
      return true
    } catch (e: any) { error.value = e.message; return false } finally { loading.value = false }
  }
  async function login(usernameOrEmail: string, password: string) {
    return authenticate('/auth/login', { username_or_email: usernameOrEmail.trim(), password })
  }
  async function loginPhone(phone: string, code: string) {
    return authenticate('/auth/login/phone', { phone: phone.trim(), code: code.trim() })
  }
  async function register(phone: string, code: string, email: string, password: string) {
    loading.value = true; error.value = ''
    try { await api.post('/auth/register', { phone:phone.trim(), code:code.trim(), email:email.trim(), password }); return true } catch (e: any) { error.value = e.message; return false } finally { loading.value = false }
  }
  function logout() { token.value = ''; user.value = null; localStorage.removeItem('moonlit_access_token') }
  window.addEventListener('moonlit:auth-expired', logout)
  return { token, user, loading, hydrated, error, isAuthenticated, hydrate, login, loginPhone, register, logout }
})
