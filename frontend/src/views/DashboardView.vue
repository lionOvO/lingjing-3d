<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Box, CheckCircle2, Clock3, Cuboid, FolderKanban, ImagePlus, Moon, Sparkles, Stars, UploadCloud } from 'lucide-vue-next'
import { ElCard, ElProgress, ElTag, ElButton, ElSkeleton } from 'element-plus'
import { useAuthStore } from '../stores/auth'; import { useDashboardStore } from '../stores/dashboard'
const router = useRouter(); const auth = useAuthStore(); const dashboard = useDashboardStore()
const workflowStages = ['图像分析', '知识检索', '3D 生成', '确定性质量检测', '后处理']
const workflowStageIndex: Record<string, number> = { pending: 0, analyzing: 0, retrieving: 1, generating: 2, evaluating: 3, postprocessing: 4, completed: 4, failed: 0 }
const workflowActiveIndex = computed(() => {
  const status = dashboard.recentTask?.status
  return status ? (workflowStageIndex[status] ?? -1) : -1
})
function workflowStageState(index: number) {
  const task = dashboard.recentTask
  if (!task || workflowActiveIndex.value < 0) return 'idle'
  if (task.status === 'completed') return 'complete'
  if (index < workflowActiveIndex.value) return 'complete'
  if (index === workflowActiveIndex.value) return task.status === 'failed' ? 'failed' : 'active'
  return 'idle'
}
let dashboardRefreshTimer: number | null = null
onMounted(() => {
  void dashboard.load()
  dashboardRefreshTimer = window.setInterval(() => {
    if (!dashboard.loading) void dashboard.load()
  }, 5000)
})
onBeforeUnmount(() => {
  if (dashboardRefreshTimer !== null) window.clearInterval(dashboardRefreshTimer)
})
const statusLabel: Record<string,string> = { pending:'排队中', analyzing:'图像分析', retrieving:'知识检索', generating:'3D 生成', evaluating:'质量评估', postprocessing:'后处理', completed:'已完成', failed:'失败' }
function statusType(status: string) { return status === 'completed' ? 'success' : status === 'failed' ? 'danger' : 'warning' }
</script>
<template>
  <main class="page dashboard-page">
    <section class="dashboard-hero">
      <div class="hero-copy"><p class="eyebrow"><Stars :size="15" />MOONLIT SAKURA STUDIO</p><h1>晚上好，{{ auth.user?.username || '创作者' }}<br><span>让想象在月光里成形</span></h1><p class="hero-description">把一张图片交给智能体工作流，完成分析、检索、生成与后处理，交付属于你的 3D 模型。</p><div class="hero-actions"><ElButton class="primary large" @click="router.push({ name:'generate', query:{ type:'anime_character' }})"><ImagePlus :size="19" />上传动漫角色</ElButton><ElButton class="secondary large" @click="router.push({ name:'generate', query:{ type:'object_model' }})"><Box :size="19" />上传物品照片</ElButton></div><p class="quiet-note"><UploadCloud :size="14" /> 支持 PNG / JPG / WEBP · 单文件最大 20MB</p></div>
      <div class="three-preview dashboard-preview" aria-label="灵境造物三维创作展示">
        <div class="dashboard-orbit orbit-one"></div><div class="dashboard-orbit orbit-two"></div>
        <div class="dashboard-seed"><Sparkles :size="42" /><span>AI · 3D</span></div>
        <div class="dashboard-preview-label">MOONLIT CREATION SPACE</div>
        <div class="dashboard-preview-caption"><strong>从一张灵感图开始</strong><span>分析 · 检索 · 建模 · 交付</span></div>
      </div>
    </section>
    <section class="metric-row"><ElCard class="metric-card"><div class="metric-icon pink"><FolderKanban :size="19" /></div><div><span>项目总数</span><strong>{{ dashboard.projects.length }}</strong></div></ElCard><ElCard class="metric-card"><div class="metric-icon violet"><Clock3 :size="19" /></div><div><span>进行中的任务</span><strong>{{ dashboard.recentTask && !['completed','failed'].includes(dashboard.recentTask.status) ? 1 : 0 }}</strong></div></ElCard><ElCard class="metric-card"><div class="metric-icon green"><CheckCircle2 :size="19" /></div><div><span>已交付模型</span><strong>{{ dashboard.projects.filter(p => p.status === 'completed').length }}</strong></div></ElCard></section>
    <section class="dashboard-grid">
      <ElCard class="panel project-panel"><div class="panel-head"><div><p class="eyebrow">YOUR STUDIO</p><h2>最近的月光项目</h2></div><ElButton text class="text-link" @click="router.push('/projects')">查看全部 <ArrowRight :size="16" /></ElButton></div><ElSkeleton v-if="dashboard.loading" :rows="3" animated /><div v-else-if="dashboard.projects.length" class="project-strip"><article v-for="project in dashboard.projects.slice(0,3)" :key="project.id" class="project-card"><div class="project-thumb"><Cuboid :size="34" /><ElTag :class="['moonlit-status', `moonlit-${project.status}`]" effect="plain">{{ statusLabel[project.status] || project.status }}</ElTag></div><h3>{{ project.name }}</h3><p>{{ project.project_type === 'anime_character' ? '动漫角色' : '物品建模' }}</p></article></div><div v-else class="empty-inline"><Moon :size="24" /><span>第一个 3D 项目会在这里出现。</span><ElButton text class="text-link" @click="router.push('/generate')">开始生成</ElButton></div></ElCard>
      <ElCard class="panel task-panel"><div class="panel-head"><div><p class="eyebrow">WORKFLOW STATUS</p><h2>当前任务</h2></div><ElTag v-if="dashboard.recentTask" :class="['moonlit-status', `moonlit-${dashboard.recentTask.status}`]" effect="dark">{{ statusLabel[dashboard.recentTask.status] || dashboard.recentTask.status }}</ElTag></div><template v-if="dashboard.recentTask"><div class="task-id">#{{ dashboard.recentTask.id }} · {{ dashboard.recentTask.output_format?.toUpperCase() }}</div><ElProgress :percentage="dashboard.recentTask.progress || (dashboard.recentTask.status === 'completed' ? 100 : 12)" :stroke-width="8" color="#a9c7e8" /><p class="task-hint">{{ statusLabel[dashboard.recentTask.status] || '智能体正在处理' }}，状态会通过 WebSocket 实时同步。</p><ElButton class="secondary task-cta" @click="router.push(`/tasks/${dashboard.recentTask.id}`)">查看任务轨迹 <ArrowRight :size="15" /></ElButton></template><div v-else class="empty-task"><Sparkles :size="24" /><p>还没有进行中的生成任务</p><ElButton class="primary" @click="router.push('/generate')">开始一次创作</ElButton></div></ElCard>
    </section>
    <section class="workflow-overview panel"><div class="panel-head"><div><p class="eyebrow">AGENT FLOW</p><h2>智能体工作流概览</h2></div><ElButton text class="text-link" @click="router.push('/knowledge')">探索知识库 <ArrowRight :size="16" /></ElButton></div><div class="flow-steps"><div v-for="(item,index) in workflowStages" :key="item" :class="['flow-step', workflowStageState(index)]"><span>{{ String(index+1).padStart(2,'0') }}</span><strong>{{ item }}</strong><i :class="workflowStageState(index)"></i></div></div></section>
  </main>
</template>
