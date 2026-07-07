import { fetchMe, login as loginApi, register as registerApi } from '@/api/auth'
import type { User } from '@/types'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<User | null>(null)

  const isLoggedIn = computed(() => !!token.value)
  const role = computed(() => user.value?.role ?? 'guest')
  const isAdmin = computed(() => role.value === 'admin')

  function setToken(newToken: string) {
    token.value = newToken
    localStorage.setItem('token', newToken)
  }

  async function login(username: string, password: string) {
    const resp = await loginApi({ username, password })
    setToken(resp.access_token)
    await loadUser()
  }

  async function register(username: string, email: string, password: string) {
    await registerApi({ username, email, password })
    await login(username, password)
  }

  async function loadUser() {
    if (!token.value) return
    try {
      user.value = await fetchMe()
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
  }

  return { token, user, isLoggedIn, role, isAdmin, setToken, login, register, loadUser, logout }
})
