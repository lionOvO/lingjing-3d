<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight, CalendarDays, CheckCircle2, CircleAlert, Clock3, Cuboid, Eye, FolderKanban, ImageOff, Play, RefreshCw, Sparkles } from 'lucide-vue-next'
import { ElButton, ElCard, ElMessage, ElSkeleton, ElTag } from 'element-plus'
import api from '../services/api'
import { useDashboardStore, type ProjectRecord } from '../stores/dashboard'
import { formatApiDate } from '../utils/date'

const route = useRoute()
const router = useRouter()
const store = useDashboardStore()
const imageFailed = ref(false)
const project = computed(() => store.currentProject)
const projectId = computed(() => String(route.params.projectId || ''))
const isValidId = computed(() => /^\d+$/.test(projectId.value) && Number(projectId.value) > 0)
type TaskRecord = {
  id: number
  project_id: number
  task_type: ProjectRecord['project_type']
  status: 'pending' | 'analyzing' | 'retrieving' | 'generating' | 'evaluating' | 'postprocessing' | 'completed' | 'failed'
  output_model_url: string | null
  quality_score: number | null
  created_at: string
  completed_at: string | null
}
const projectTasks = ref<TaskRecord[]>([])
const tasksLoading = ref(false)
const tasksError = ref('')
const statusLabels: Record<ProjectRecord['status'], string> = { draft: '草稿', processing: '处理中', completed: '已完成', failed: '失败' }
const typeLabels: Record<ProjectRecord['project_type'], string> = { anime_character: '动漫角色', object_model: '物品建模' }
const taskStatusLabels: Record<TaskRecord['status'], string> = { pending: '等待处理', analyzing: '图像分析中', retrieving: '知识检索中', generating: '正在生成', evaluating: '质量检查中', postprocessing: '后处理', completed: '已完成', failed: '生成失败' }
const loadError = computed(() => !isValidId.value ? '项目编号无效，请从项目列表重新选择。' : store.error || '项目详情暂时无法打开，请稍后重试。')
const latestTask = computed(() => projectTasks.value[0] || null)
const previewTask = computed(() => projectTasks.value.find((task) => task.status === 'completed' && Boolean(task.output_model_url)) || null)

function goGenerate() {
  if (project.value) router.push({ name: 'generate', query: { type: project.value.project_type, projectId: project.value.id } })
}

function openPreview(task: TaskRecord) {
  router.push({ name: 'workflow', params: { taskId: String(task.id) }, query: { step: 'preview' } })
}

function openTask(task: TaskRecord) {
  router.push({ name: 'workflow', params: { taskId: String(task.id) }, query: { step: task.status === 'completed' && task.output_model_url ? 'preview' : 'task' } })
}

async function loadTasks() {
  if (!isValidId.value) return
  tasksLoading.value = true
  tasksError.value = ''
  try {
    const { data } = await api.get<TaskRecord[]>(`/projects/${projectId.value}/tasks`)
    projectTasks.value = Array.isArray(data) ? data : []
  } catch (error: any) {
    projectTasks.value = []
    tasksError.value = error?.message || '生成记录加载失败'
  } finally {
    tasksLoading.value = false
  }
}

async function load() {
  imageFailed.value = false
  projectTasks.value = []
  tasksError.value = ''
  if (!isValidId.value) {
    store.currentProject = null
    store.error = '项目编号无效，请从项目列表重新选择。'
    return
  }
  try {
    await store.fetchProject(projectId.value)
    await loadTasks()
  } catch (error: any) {
    ElMessage.error(error?.message || '项目详情加载失败')
  }
}

onMounted(load)
watch(projectId, load)
</script>

<template>
  <main class="page project-detail-page">
    <div class="project-detail-topline">
      <ElButton text class="project-back" @click="router.push({ name: 'projects' })"><ArrowLeft :size="16" />返回我的项目</ElButton>
      <ElButton class="secondary" @click="router.push('/generate')"><Sparkles :size="16" />新建生成</ElButton>
    </div>

    <ElSkeleton v-if="store.loading && !project" :rows="8" animated class="project-detail-skeleton" />
    <div v-else-if="!project" class="project-detail-empty glass-card">
      <CircleAlert :size="38" />
      <h1>项目详情暂时无法打开</h1>
      <p>{{ loadError }}</p>
      <div class="project-detail-empty-actions">
        <ElButton class="secondary" @click="router.push({ name: 'projects' })">返回项目列表</ElButton>
        <ElButton class="primary" :loading="store.loading" @click="load"><RefreshCw :size="16" />重新加载</ElButton>
      </div>
    </div>

    <template v-else>
      <section class="project-detail-hero">
        <div>
          <p class="eyebrow"><FolderKanban :size="15" />PROJECT ARCHIVE · #{{ project.id }}</p>
          <div class="project-detail-heading">
            <h1>{{ project.name }}</h1>
            <ElTag :class="['moonlit-status', `moonlit-${project.status}`]" effect="plain">{{ statusLabels[project.status] }}</ElTag>
          </div>
          <p class="project-detail-subtitle">{{ typeLabels[project.project_type] }} · 创建于 {{ formatApiDate(project.created_at) }}</p>
        </div>
        <div class="project-detail-actions"><RouterLink v-if="previewTask" class="library-button quiet" :to="`/compare?project=${project.id}`">对比项目版本</RouterLink>
          <ElButton v-if="previewTask" class="primary" @click="openPreview(previewTask)"><Eye :size="16" />查看已生成模型</ElButton>
          <ElButton v-else-if="latestTask" class="primary" @click="openTask(latestTask)"><Clock3 :size="16" />查看生成进度</ElButton>
          <ElButton :class="previewTask || latestTask ? 'secondary' : 'primary'" @click="goGenerate"><Play :size="16" />继续生成</ElButton>
        </div>
      </section>

      <div class="project-detail-grid">
        <ElCard class="project-source-card glass-card">
          <div class="project-card-head"><div><p class="eyebrow">SOURCE IMAGE</p><h2>项目参考图</h2></div><Cuboid :size="20" /></div>
          <div class="project-source-preview">
            <img v-if="project.source_image_url && !imageFailed" :src="project.source_image_url" alt="项目参考图" @error="imageFailed = true" />
            <div v-else class="project-source-fallback"><ImageOff :size="30" /><span>{{ project.source_image_url ? '参考图暂时无法加载' : '尚未上传参考图' }}</span></div>
          </div>
        </ElCard>

        <aside class="project-meta-column">
          <ElCard class="project-meta-card glass-card">
            <div class="project-card-head"><div><p class="eyebrow">PROJECT PROFILE</p><h2>项目概览</h2></div><CheckCircle2 :size="20" /></div>
            <dl class="project-facts">
              <div><dt>项目类型</dt><dd>{{ typeLabels[project.project_type] }}</dd></div>
              <div><dt>项目状态</dt><dd><ElTag :class="['moonlit-status', `moonlit-${project.status}`]" effect="plain">{{ statusLabels[project.status] }}</ElTag></dd></div>
              <div><dt>创建时间</dt><dd><CalendarDays :size="14" />{{ formatApiDate(project.created_at) }}</dd></div>
              <div><dt>最后更新</dt><dd><CalendarDays :size="14" />{{ formatApiDate(project.updated_at) }}</dd></div>
            </dl>
          </ElCard>
          <ElCard class="project-next-card glass-card">
            <Sparkles :size="22" />
            <h2>继续完善这个项目</h2>
            <p>沿用当前项目的风格方向，上传新的参考图并创建下一次生成任务。</p>
            <ElButton class="secondary" @click="goGenerate">进入生成页面 <ArrowRight :size="15" /></ElButton>
          </ElCard>
        </aside>
      </div>

      <section class="project-history-section">
        <div class="project-history-heading">
          <div><p class="eyebrow">GENERATION HISTORY</p><h2>生成记录</h2></div>
          <ElButton v-if="tasksError" text class="project-retry-history" :loading="tasksLoading" @click="loadTasks"><RefreshCw :size="15" />重新加载</ElButton>
        </div>
        <ElSkeleton v-if="tasksLoading" :rows="3" animated class="project-history-skeleton" />
        <p v-else-if="tasksError" class="project-history-error">{{ tasksError }}</p>
        <div v-else-if="projectTasks.length" class="project-history-list">
          <button v-for="task in projectTasks.slice(0, 3)" :key="task.id" class="project-history-item" type="button" @click="openTask(task)">
            <span class="project-history-icon"><Eye v-if="task.status === 'completed' && task.output_model_url" :size="17" /><Clock3 v-else :size="17" /></span>
            <span class="project-history-copy"><strong>任务 #{{ task.id }}</strong><small>{{ formatApiDate(task.completed_at || task.created_at) }}</small></span>
            <ElTag :class="['moonlit-status', `moonlit-${task.status}`]" effect="plain">{{ taskStatusLabels[task.status] }}</ElTag>
            <ArrowRight :size="16" class="project-history-arrow" />
          </button>
        </div>
        <div v-else class="project-history-empty"><Cuboid :size="20" /><span>这个项目还没有生成记录。</span><ElButton text @click="goGenerate">开始生成</ElButton></div>
      </section>
    </template>
  </main>
</template>
