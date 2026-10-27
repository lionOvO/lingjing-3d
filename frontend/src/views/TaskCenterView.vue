<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, CheckCircle2, Clock3, ListChecks, RefreshCw, Search, TriangleAlert } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth'
import api from '../services/api'
import { formatApiDate } from '../utils/date'

type Task = { id:number; project_id:number; status:string; output_format:string; created_at:string; progress?:number }
type Project = { id:number; name:string }
const auth = useAuthStore()
const tasks = ref<(Task & { projectName:string })[]>([])
const loading = ref(false)
const error = ref('')
const query = ref('')
const filter = ref('all')
const page = ref(1)
const pageSize = 12
const statusLabels: Record<string,string> = { pending:'排队中', analyzing:'图像分析', retrieving:'知识检索', generating:'模型生成', evaluating:'质量检测', postprocessing:'后处理', completed:'已完成', failed:'失败' }
const inProgress = (task:Task) => !['completed','failed'].includes(task.status)
const counts = computed(() => ({ all:tasks.value.length, active:tasks.value.filter(inProgress).length, completed:tasks.value.filter(t => t.status === 'completed').length, failed:tasks.value.filter(t => t.status === 'failed').length }))
const filters = [{ key:'all', label:'全部任务' }, { key:'active', label:'进行中' }, { key:'completed', label:'已完成' }, { key:'failed', label:'失败' }] as const
const filtered = computed(() => tasks.value.filter(task => (filter.value === 'all' || (filter.value === 'active' ? inProgress(task) : task.status === filter.value)) && `${task.id} ${task.projectName}`.toLowerCase().includes(query.value.trim().toLowerCase())))
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)))
const visible = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize))
function selectFilter(value:string) { filter.value = value; page.value = 1 }
async function load() {
  if (loading.value) return
  loading.value = true; error.value = ''; tasks.value = []
  try {
    if (!auth.user && !(await auth.hydrate())) throw new Error('请重新登录后查看任务')
    const projects:Project[] = []
    for (let offset = 0; ; offset += 100) {
      const { data } = await api.get<Project[]>('/projects', { params:{ user_id:auth.user.id, limit:100, offset } })
      projects.push(...data)
      if (data.length < 100) break
    }
    let failed = 0
    // Bound requests while loading the actual history of the signed-in user's projects.
    for (let start = 0; start < projects.length; start += 5) {
      const batch = projects.slice(start, start + 5)
      const results = await Promise.allSettled(batch.map(async project => {
        const { data } = await api.get<Task[]>(`/projects/${project.id}/tasks`)
        return data.map(task => ({ ...task, projectName:project.name }))
      }))
      for (const result of results) {
        if (result.status === 'fulfilled') tasks.value.push(...result.value)
        else failed++
      }
    }
    tasks.value.sort((a,b) => b.id - a.id)
    if (failed) error.value = `${failed} 个项目的任务暂时加载失败，当前仅显示已加载记录。请刷新重试。`
    page.value = 1
  } catch (cause:any) { error.value = cause.message || '任务加载失败，请刷新重试' }
  finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <main class="page task-center-page">
    <header class="task-center-heading"><div><p class="eyebrow">生成记录</p><h1>生成任务</h1><p>追踪每次生成，从参考图到交付模型。</p></div><button class="task-center-refresh" :disabled="loading" @click="load"><RefreshCw :size="15" :class="{ spinning:loading }" />{{ loading ? '加载中' : '刷新记录' }}</button></header>
    <section class="task-center-summary" aria-label="任务统计"><div><ListChecks :size="18" /><span>全部任务<strong>{{ loading ? '—' : counts.all }}</strong></span></div><div><Clock3 :size="18" /><span>进行中<strong>{{ loading ? '—' : counts.active }}</strong></span></div><div><CheckCircle2 :size="18" /><span>已完成<strong>{{ loading ? '—' : counts.completed }}</strong></span></div><div><TriangleAlert :size="18" /><span>失败记录<strong>{{ loading ? '—' : counts.failed }}</strong></span></div></section>
    <p v-if="error" class="task-center-error" role="alert">{{ error }}</p>
    <section class="task-center-history" aria-label="生成历史">
      <div class="task-center-toolbar"><div class="task-center-filters" role="group" aria-label="按状态筛选"><button v-for="item in filters" :key="item.key" :class="{ selected:filter === item.key }" :aria-pressed="filter === item.key" @click="selectFilter(item.key)">{{ item.label }}<span>{{ loading ? '—' : counts[item.key] }}</span></button></div><label class="task-center-search"><Search :size="15" /><input v-model="query" aria-label="搜索任务或项目名称" placeholder="搜索任务或项目名称" @input="page = 1" /></label></div>
      <p v-if="loading" class="task-center-empty" role="status">正在读取你的项目与生成记录…</p>
      <template v-else-if="filtered.length"><div class="task-center-table-wrap"><table class="task-center-table"><thead><tr><th>任务 / 项目</th><th>状态</th><th>格式</th><th>创建时间</th><th><span class="sr-only">操作</span></th></tr></thead><tbody><tr v-for="task in visible" :key="task.id"><td><RouterLink :to="`/tasks/${task.id}`" class="task-center-title">{{ task.projectName }}</RouterLink><small>#{{ task.id }}</small></td><td><span class="task-center-state" :class="task.status">{{ statusLabels[task.status] || task.status }}</span></td><td class="task-center-format">{{ task.output_format?.toUpperCase() || '—' }}</td><td class="task-center-date">{{ formatApiDate(task.created_at) }}</td><td><RouterLink v-if="task.status === 'completed'" class="task-center-open" :to="`/workflow/${task.id}?step=preview`">查看模型<ArrowRight :size="14" /></RouterLink><RouterLink v-else class="task-center-open" :to="`/tasks/${task.id}`">查看详情<ArrowRight :size="14" /></RouterLink></td></tr></tbody></table></div><div class="task-center-pagination"><span>共 {{ filtered.length }} 条记录 · 第 {{ page }} / {{ totalPages }} 页</span><div><button :disabled="page <= 1" @click="page--">上一页</button><button :disabled="page >= totalPages" @click="page++">下一页</button></div></div></template>
      <div v-else class="task-center-empty"><ListChecks :size="28" /><h2>{{ tasks.length ? '没有匹配的任务' : error ? '暂时无法读取任务' : '还没有生成任务' }}</h2><p>{{ tasks.length ? '试试其他状态，或调整搜索关键词。' : error ? '请刷新记录重试。' : '上传第一张参考图，生成进度和结果会保留在这里。' }}</p><RouterLink v-if="!tasks.length && !error" class="studio-create" to="/generate">开始生成</RouterLink></div>
    </section>
  </main>
</template>

<style scoped>
.task-center-page{max-width:1440px;min-height:calc(100vh - 64px)}.task-center-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:8px 0 30px}.task-center-heading .eyebrow{margin-bottom:10px}.task-center-heading h1{font-size:32px;font-weight:600;letter-spacing:.02em;margin:0}.task-center-heading p:not(.eyebrow){font-size:13px;color:var(--mist);margin:12px 0 0}.task-center-refresh{display:flex;align-items:center;gap:8px;color:#c8d8eb;background:#243853;border:1px solid #ffffff26;border-radius:7px;padding:10px 14px;font-size:12px;white-space:nowrap}.task-center-refresh:disabled{opacity:.6;cursor:wait}.task-center-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:30px;border:1px solid #ffffff20;border-radius:10px;background:#162740a6}.task-center-summary>div{display:flex;gap:14px;padding:22px;align-items:flex-start;color:#abc5df}.task-center-summary>div+div{border-left:1px solid #ffffff15}.task-center-summary span{font-size:11px;color:#a9bbd2}.task-center-summary strong{display:block;font:500 28px ui-monospace,Consolas,monospace;color:#f1f7ff;margin-top:10px}.task-center-history{border:1px solid #ffffff20;border-radius:10px;background:#14243bd9;overflow:hidden}.task-center-toolbar{padding:18px;display:flex;justify-content:space-between;align-items:center;gap:15px;border-bottom:1px solid #ffffff15}.task-center-filters{display:flex;gap:4px;flex-wrap:wrap}.task-center-filters button{padding:8px 10px;border-radius:6px;background:transparent;color:#a9bbd2;font-size:12px}.task-center-filters button.selected{background:#304963;color:#eef6ff}.task-center-filters span{margin-left:8px;font-size:10px;opacity:.7}.task-center-search{display:flex;align-items:center;gap:8px;padding:0 10px;min-height:35px;border:1px solid #ffffff25;border-radius:6px;color:#9fb5ce}.task-center-search input{background:none;border:0;color:#eef6ff;font-size:11px;width:145px;min-width:0}.task-center-search input::placeholder{color:#9fb5ce}.task-center-table-wrap{overflow-x:auto}.task-center-table{width:100%;border-collapse:collapse;text-align:left;white-space:nowrap}.task-center-table th{padding:14px 20px;font-size:10px;font-weight:400;color:#90a6c1;background:#ffffff03}.task-center-table td{padding:17px 20px;border-top:1px solid #ffffff0d;font-size:12px}.task-center-table tr:hover td{background:#ffffff03}.task-center-title{display:block;color:#e2edfb;font-size:12px;text-decoration:none;max-width:270px;overflow:hidden;text-overflow:ellipsis}.task-center-title:hover{text-decoration:underline}.task-center-table small{display:block;color:#859cba;font:10px ui-monospace,monospace;margin-top:6px}.task-center-date,.task-center-format{color:#a4b8d1;font-size:11px!important}.task-center-state{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:#abc7e4}.task-center-state:before{content:'';width:5px;height:5px;background:currentColor;border-radius:50%}.task-center-state.completed{color:#a1d4c5}.task-center-state.failed{color:#d6a3ac}.task-center-open{display:inline-flex;gap:7px;align-items:center;font-size:11px;color:#b8d2eb;text-decoration:none}.task-center-open:hover{color:#fff}.task-center-error{padding:14px;color:#f2c9c9;background:#743a452e;border:1px solid #e0a0a033;font-size:12px;border-radius:7px}.task-center-empty{min-height:280px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:30px;color:var(--mist);font-size:13px}.task-center-empty h2{font-size:18px;color:#e2edfb;font-weight:500}.task-center-empty p{font-size:12px;line-height:1.8}.task-center-empty .studio-create{padding:0 25px;margin:14px 0 0}.task-center-pagination{display:flex;justify-content:space-between;align-items:center;padding:17px 20px;border-top:1px solid #ffffff15;color:#92a9c4;font-size:11px;gap:12px}.task-center-pagination button{padding:7px 10px;background:#253a53;color:#c6d8ec;border-radius:5px;margin-left:8px;font-size:11px}.task-center-pagination button:disabled{opacity:.35;cursor:default}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}.spinning{animation:task-center-spin 1s linear infinite}@keyframes task-center-spin{to{transform:rotate(360deg)}}@media(max-width:900px){.task-center-toolbar{align-items:flex-start;flex-direction:column}.task-center-search{width:100%}.task-center-search input{width:100%}.task-center-summary>div{padding:18px 12px;gap:9px}}@media(max-width:480px){.task-center-heading h1{font-size:28px}.task-center-heading{gap:10px}.task-center-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.task-center-summary>div:nth-child(3){border-left:0;border-top:1px solid #ffffff15}.task-center-summary>div:nth-child(4){border-top:1px solid #ffffff15}.task-center-pagination{align-items:flex-start;flex-direction:column}}@media(prefers-reduced-motion:reduce){.spinning{animation:none}}
</style>
