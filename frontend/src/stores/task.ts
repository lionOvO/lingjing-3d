import { ref } from 'vue'
import { defineStore } from 'pinia'
import api from '../services/api'

export type TaskStatus = 'pending' | 'analyzing' | 'retrieving' | 'generating' | 'evaluating' | 'postprocessing' | 'completed' | 'failed'

export interface GenerationTask {
  id: number
  project_id: number
  task_type: 'anime_character' | 'object_model'
  status: TaskStatus
  output_format: string
  celery_task_id?: string | null
  analysis_result?: Record<string, unknown> | null
  retrieved_params?: Record<string, unknown> | null
  generation_params?: Record<string, unknown> | null
  quality_score?: number | null
  output_model_url?: string | null
  texture_urls?: string[] | null
  error_message?: string | null
  retry_count: number
  created_at: string
  completed_at?: string | null
  progress?: number
}

export interface WorkflowSnapshot { task_id: number; status: TaskStatus; state: Record<string, unknown> }
export interface ModelMetadata { id: number; task_id: number; vertex_count?: number | null; face_count?: number | null; texture_resolution?: string | null; has_pbr: boolean; file_size_mb?: number | null; bounding_box?: Record<string, unknown> | null }

export const useTaskStore = defineStore('task', () => {
  const current = ref<GenerationTask | null>(null)
  const workflow = ref<WorkflowSnapshot | null>(null)
  const metadata = ref<ModelMetadata | null>(null)
  const loading = ref(false)
  const error = ref('')
  const polling = ref<number | null>(null)
  const socket = ref<WebSocket | null>(null)

  function setTask(task: GenerationTask | null) {
    current.value = task
    if (task) localStorage.setItem('moonlit_recent_task', JSON.stringify(task))
    else localStorage.removeItem('moonlit_recent_task')
  }
  async function fetch(id: string | number) {
    try {
      const { data } = await api.get<GenerationTask>(`/tasks/${id}`)
      setTask(data)
      return data
    } catch (cause: any) {
      // A project deletion removes its tasks. Do not leave an older task in
      // Pinia/localStorage when a detail refresh receives a 404.
      if (cause?.response?.status === 404) setTask(null)
      throw cause
    }
  }
  async function loadDetail(id: string | number) {
    loading.value = true; error.value = ''; workflow.value = null; metadata.value = null
    try {
      const task = await fetch(id)
      const requests: Promise<void>[] = [api.get<WorkflowSnapshot>(`/agents/workflow/${id}`).then(({ data }) => { workflow.value = data })]
      if (task.status === 'completed') requests.push(api.get<ModelMetadata>(`/models/${id}`).then(({ data }) => { metadata.value = data }).catch(() => undefined))
      await Promise.all(requests)
      if (task.status !== 'completed' && task.status !== 'failed') startProgress(id)
      return task
    } catch (exception: any) { error.value = exception?.message || '无法读取任务详情，请稍后重试'; throw exception } finally { loading.value = false }
  }
  async function refreshWorkflow(id: string | number) {
    try {
      const { data } = await api.get<WorkflowSnapshot>(`/agents/workflow/${id}`)
      workflow.value = data
      return data
    } catch {
      // The task endpoint remains the source of truth when a diagnostic
      // snapshot is temporarily unavailable.
      return null
    }
  }
  function startProgress(id: string | number) {
    stopProgress()
    if (current.value?.status === 'completed' || current.value?.status === 'failed') return
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    try {
      const ws = new WebSocket(`${protocol}://${location.host}/api/v1/tasks/${id}/progress`); socket.value = ws
      ws.onmessage = (event) => {
        try {
          const update = JSON.parse(event.data) as Partial<GenerationTask>
          const currentStatus = current.value?.status
          // The current server's compatibility socket emits one "pending" event before it
          // closes. Never let that bootstrap event overwrite a state fetched from the API.
          if (currentStatus && currentStatus !== 'pending' && update.status === 'pending') return
          if (currentStatus && ['completed', 'failed'].includes(currentStatus)) return
          setTask({ ...(current.value || {} as GenerationTask), ...update } as GenerationTask)
          // Stage payloads are persisted by the worker separately from the
          // compact websocket event. Refresh them so the detail panel reveals
          // analysis and retrieval results as soon as each node commits.
          void refreshWorkflow(id)
        } catch { /* Ignore malformed live progress payloads. */ }
      }
      ws.onerror = () => startPolling(id); ws.onclose = () => { if (current.value?.status !== 'completed' && current.value?.status !== 'failed') startPolling(id) }
    } catch { startPolling(id) }
  }
  function startPolling(id: string | number) {
    if (polling.value) return
    polling.value = window.setInterval(() => {
      fetch(id).catch(() => undefined)
      void refreshWorkflow(id)
    }, 4000)
  }
  function stopProgress() { if (socket.value) { socket.value.close(); socket.value = null }; if (polling.value) { clearInterval(polling.value); polling.value = null } }
  async function retry(id: string | number) { const { data } = await api.post(`/tasks/${id}/retry`); setTask(data); startProgress(id); return data }
  async function cancel(id: string | number) { const { data } = await api.delete<GenerationTask>(`/tasks/${id}`); setTask(data); stopProgress(); return data }
  return { current, workflow, metadata, loading, error, setTask, fetch, loadDetail, refreshWorkflow, startProgress, stopProgress, retry, cancel }
})
