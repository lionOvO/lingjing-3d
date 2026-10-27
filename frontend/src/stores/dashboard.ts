import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import api from '../services/api'
import { useAuthStore } from './auth'

export interface ProjectRecord {
  id: number
  user_id: number
  name: string
  description: string | null
  project_type: 'anime_character' | 'object_model'
  status: 'draft' | 'processing' | 'completed' | 'failed'
  source_image_url: string | null
  created_at: string
  updated_at: string
}

export const useDashboardStore = defineStore('dashboard', () => {
  const projects = ref<ProjectRecord[]>([])
  const currentProject = ref<ProjectRecord | null>(null)
  const recentTask = ref<any>(null)
  const loading = ref(false)
  const error = ref('')
  const activeProjects = computed(() => projects.value)

  function clearRecentTask() {
    recentTask.value = null
    localStorage.removeItem('moonlit_recent_task')
  }

  async function load() {
    const auth = useAuthStore(); if (!auth.isAuthenticated) return
    loading.value = true; error.value = ''
    try {
      const ownedProjects: ProjectRecord[] = []
      for (let offset = 0; ; offset += 100) {
        const { data } = await api.get<ProjectRecord[]>('/projects', { params: { user_id: auth.user.id, offset, limit: 100 } })
        ownedProjects.push(...data)
        if (data.length < 100) break
      }
      projects.value = ownedProjects
      const saved = localStorage.getItem('moonlit_recent_task')
      if (saved) {
        try {
          const cachedTask = JSON.parse(saved)
          recentTask.value = cachedTask
            && Number.isInteger(cachedTask.id)
            && cachedTask.id > 0
            ? cachedTask
            : null
          if (!recentTask.value) clearRecentTask()
        } catch {
          clearRecentTask()
        }
      } else {
        recentTask.value = null
      }
      if (recentTask.value?.id) {
        try {
          recentTask.value = (await api.get(`/tasks/${recentTask.value.id}`)).data
          localStorage.setItem('moonlit_recent_task', JSON.stringify(recentTask.value))
        } catch (cause: any) {
          // A deleted project removes its tasks. Never render a stale cached task.
          if (cause?.response?.status === 404 || cause?.response?.status === 401) clearRecentTask()
          else recentTask.value = null
        }
      }
    } catch (e: any) { error.value = e.message || '项目加载失败' } finally { loading.value = false }
  }
  async function fetchProject(id: string | number) {
    loading.value = true
    error.value = ''
    currentProject.value = null
    try {
      const { data } = await api.get<ProjectRecord>(`/projects/${id}`)
      currentProject.value = data
      return data
    } catch (e: any) {
      error.value = e.message || '项目详情加载失败'
      throw e
    } finally {
      loading.value = false
    }
  }
  async function deleteProject(id: number) {
    await api.delete(`/projects/${id}`)
    projects.value = projects.value.filter((project) => project.id !== id)
    if (currentProject.value?.id === id) currentProject.value = null
    if (recentTask.value?.project_id === id) clearRecentTask()
  }
  return { projects, currentProject, recentTask, loading, error, activeProjects, load, fetchProject, deleteProject, clearRecentTask }
})
