<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Cuboid, FolderKanban, Plus, Trash2, TriangleAlert } from 'lucide-vue-next'
import { ElButton, ElCard, ElMessage, ElMessageBox, ElTag } from 'element-plus'
import { useDashboardStore, type ProjectRecord } from '../stores/dashboard'

const store = useDashboardStore()
const router = useRouter()
const deletingIds = ref<number[]>([])
const labels: Record<string, string> = { draft: '草稿', processing: '处理中', completed: '已完成', failed: '失败' }

function openProject(project: ProjectRecord) {
  router.push({ name: 'project-detail', params: { projectId: project.id } })
}

function handleProjectKeydown(event: KeyboardEvent, project: ProjectRecord) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    openProject(project)
  }
}

async function removeProject(event: MouseEvent, project: ProjectRecord) {
  event.stopPropagation()
  if (deletingIds.value.includes(project.id)) return
  try {
    await ElMessageBox.confirm(
      h('div', { class: 'moonlit-confirm-content' }, [
        h('div', { class: 'moonlit-confirm-alert', role: 'alert' }, [
          h(TriangleAlert, { size: 18, 'aria-hidden': 'true' }),
          h('span', {}, '删除后无法恢复'),
        ]),
        h('p', { class: 'moonlit-confirm-lead' }, '确定要永久删除这个项目吗？'),
        h('div', { class: 'moonlit-confirm-project' }, [
          h(Cuboid, { size: 18 }),
          h('span', { class: 'moonlit-confirm-project-name' }, project.name),
        ]),
        h('p', { class: 'moonlit-confirm-note' }, '项目及其生成任务记录会一并移除。'),
      ]),
      '确认删除',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '暂不删除',
        type: 'warning',
        customClass: 'moonlit-confirm',
        distinguishCancelAndClose: true,
      },
    )
    deletingIds.value = [...deletingIds.value, project.id]
    await store.deleteProject(project.id)
    ElMessage.success('项目已删除')
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(error?.message || '项目删除失败，请稍后重试')
  } finally {
    deletingIds.value = deletingIds.value.filter((id) => id !== project.id)
  }
}

onMounted(() => store.load())
</script>

<template>
  <main class="page projects-page">
    <div class="section-heading">
      <div>
        <p class="eyebrow"><FolderKanban :size="15" />PROJECT ARCHIVE</p>
        <h1>项目管理</h1>
      </div>
      <ElButton class="primary" @click="router.push('/generate')"><Plus :size="16" />新建项目</ElButton>
    </div>
    <div v-if="store.projects.length" class="projects-grid">
      <ElCard
        v-for="project in store.projects"
        :key="project.id"
        class="project-card project-card-clickable glass-card"
        role="button"
        tabindex="0"
        :aria-label="`查看项目：${project.name}`"
        @click="openProject(project)"
        @keydown="handleProjectKeydown($event, project)"
      >
        <div class="project-thumb">
          <Cuboid :size="38" />
          <ElTag :class="['moonlit-status', `moonlit-${project.status}`]" effect="plain">{{ labels[project.status] || project.status }}</ElTag>
        </div>
        <div class="project-card-copy">
          <h2>{{ project.name }}</h2>
          <p>{{ project.description || '等待生成任务加入' }}</p>
        </div>
        <div class="project-card-footer">
          <span class="project-card-action">查看项目 <ArrowRight :size="14" /></span>
          <ElButton text class="project-delete-button" :loading="deletingIds.includes(project.id)" aria-label="删除项目" title="删除项目" @click="removeProject($event, project)" @keydown.stop>
            <Trash2 :size="15" />
          </ElButton>
        </div>
      </ElCard>
    </div>
    <div v-else class="empty-state glass-card">
      <FolderKanban :size="38" />
      <h2>项目库还是空的</h2>
      <p>先上传一张图片，系统会自动为它创建项目。</p>
      <ElButton class="primary" @click="router.push('/generate')">新建生成任务</ElButton>
    </div>
  </main>
</template>
