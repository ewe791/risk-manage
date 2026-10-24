import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi } from '@/api'
import { OPERATOR_KEY, TOKEN_KEY } from '@/api/client'

export interface Operator {
  operator_id: string
  username: string
  role: string
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const operator = ref<Operator | null>(
    localStorage.getItem(OPERATOR_KEY) ? JSON.parse(localStorage.getItem(OPERATOR_KEY) as string) : null
  )

  async function login(username: string, password: string) {
    const result = await authApi.login(username, password)
    token.value = result.access_token
    operator.value = {
      operator_id: result.operator_id,
      username: result.username,
      role: result.role
    }
    localStorage.setItem(TOKEN_KEY, token.value)
    localStorage.setItem(OPERATOR_KEY, JSON.stringify(operator.value))
    return result
  }

  function logout() {
    token.value = ''
    operator.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(OPERATOR_KEY)
  }

  return { token, operator, login, logout }
})
