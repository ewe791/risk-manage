import axios, { AxiosError } from 'axios'

export class ApiError extends Error {
  code: number
  constructor(message: string, code = -1) {
    super(message)
    this.code = code
  }
}

export const TOKEN_KEY = 'risk_agent_token'
export const OPERATOR_KEY = 'risk_agent_operator'

const http = axios.create({ baseURL: '/api', timeout: 180000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (response) => {
    const body = response.data
    if (body && typeof body.code === 'number' && body.code !== 0) {
      return Promise.reject(new ApiError(body.message || '请求失败', body.code))
    }
    return body.data
  },
  (error: AxiosError<any>) => {
    const body = error.response?.data
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(OPERATOR_KEY)
      if (!location.hash.includes('/login')) location.hash = '#/login'
      return Promise.reject(new ApiError('登录已过期，请重新登录', 401))
    }
    const message = (body && (body.message || body.detail)) || error.message || '网络异常'
    return Promise.reject(new ApiError(String(message), error.response?.status ?? -1))
  }
)

export default http
