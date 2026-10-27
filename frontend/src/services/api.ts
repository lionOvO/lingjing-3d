import axios from 'axios'

declare module 'axios' {
  interface AxiosRequestConfig {
    /** Internal retry marker used while Docker services finish starting. */
    _startupRetryCount?: number
  }
}

export const api = axios.create({ baseURL: '/api/v1', timeout: 15000 })

const errorMessages: Record<string, string> = {
  'Invalid credentials': '账号或密码错误，请检查后重试',
  '账号或密码错误': '账号或密码错误，请检查后重试',
  'Username or email is already registered': '用户名或邮箱已注册',
  '用户名或邮箱已注册': '用户名或邮箱已注册',
  'Authentication required': '请先登录后再继续',
  'Invalid or expired access token': '登录状态已过期，请重新登录',
  'Invalid or expired refresh token': '登录状态已过期，请重新登录',
  'Generated model is not available': '模型尚未生成完成，暂时无法预览或下载',
  'Task not found': '未找到指定任务，请返回任务中心重新选择',
  'The request conflicts with existing data': '项目仍有相关数据未清理，暂时无法删除，请稍后重试',
  '项目仍有相关数据未清理，暂时无法删除，请稍后重试': '项目仍有相关数据未清理，暂时无法删除，请稍后重试',
}

// Docker's first boot can spend several seconds opening the database and
// binding the API port. Keep the login page patient for that one-time window.
const startupRetryDelays = [800, 1600, 3000, 5000, 8000, 12000]

function isStartupTransient(error: any): boolean {
  const status = error?.response?.status
  // A Vite proxy reports a backend that has not started yet as a network
  // error. Once the proxy is reachable, these gateway statuses mean the same
  // thing during the short Docker warm-up window.
  return !error?.response || [500, 502, 503, 504].includes(status)
}

function shouldRetryDuringStartup(error: any): boolean {
  const config = error?.config
  if (!config || !isStartupTransient(error)) return false
  const method = String(config.method || 'get').toLowerCase()
  const url = String(config.url || '')
  // GETs are safe to replay. Login is also safe because it only issues a
  // token and has no server-side mutation. Do not replay uploads/registers.
  return method === 'get' || /\/auth\/login(?:$|\?)/.test(url)
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function validationMessage(detail: unknown): string {
  if (!Array.isArray(detail)) return ''
  const messages = detail.map((item: { msg?: string }) => {
    if (item.msg === 'Field required') return '请填写必填项'
    if (item.msg?.startsWith('String should have at least')) return '输入内容长度不足'
    if (item.msg?.startsWith('String should have at most')) return '输入内容过长'
    return item.msg || '输入内容不符合要求'
  })
  return messages.filter(Boolean).join('；')
}

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('moonlit_access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (shouldRetryDuringStartup(error)) {
      const config = error.config
      const retryCount = config._startupRetryCount || 0
      if (retryCount < startupRetryDelays.length) {
        config._startupRetryCount = retryCount + 1
        await wait(startupRetryDelays[retryCount])
        return api.request(config)
      }
    }
    const status = error?.response?.status
    if (status === 401) {
      localStorage.removeItem('moonlit_access_token')
      window.dispatchEvent(new CustomEvent('moonlit:auth-expired'))
    }
    const detail = error?.response?.data?.detail
    const message = typeof detail === 'string'
      ? errorMessages[detail] || detail
      : validationMessage(detail)
    error.message = message || (status === 409
      ? '操作与现有数据冲突，请刷新页面后重试'
      : error?.response ? '请求失败，请稍后重试' : '服务正在启动，请稍候再试')
    return Promise.reject(error)
  },
)

export default api
