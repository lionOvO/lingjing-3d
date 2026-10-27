<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Search, BookOpen, ExternalLink, LoaderCircle } from 'lucide-vue-next'
import { ElButton, ElMessage, ElPagination } from 'element-plus'
import api from '../services/api'

type KnowledgeEntry = {
  id: number | string
  collection_name: string
  title: string
  content?: string | null
  tags?: string[] | null
  source?: string | null
  verification?: string
  references?: { title: string; document: string }[]
}

const query = ref('')
const results = ref<KnowledgeEntry[]>([])
const loading = ref(false)
const searched = ref(false)
const activeCollection = ref('generation_failures')
const currentPage = ref(1)
const total = ref(0)
const pageSize = 5
const collections = [
  { value: 'generation_failures', label: '生成故障' },
  { value: 'all', label: '全部建模知识' },
  { value: 'generation_params_collection', label: '建模规范' },
  { value: 'character_style_collection', label: '角色策略' },
  { value: 'material_reference_collection', label: '材质参考' },
]

const collectionLabel = computed(() => Object.fromEntries(collections.map(({ value, label }) => [value, label])))
const visibleTags = (entry: KnowledgeEntry) => (entry.tags || []).filter((tag) => !tag.startsWith('seed_key=')).slice(0, 4)
const rangeStart = computed(() => results.value.length ? ((currentPage.value - 1) * pageSize) + 1 : 0)
const rangeEnd = computed(() => Math.min(currentPage.value * pageSize, total.value))
const countLabel = computed(() => {
  if (loading.value) return '正在检索'
  if (!total.value) return '共 0 条'
  return `第 ${rangeStart.value}-${rangeEnd.value} 条，共 ${total.value} 条`
})

async function loadLibrary() {
  loading.value = true
  try {
    if (activeCollection.value === 'generation_failures') {
      const { data } = await api.get('/studio/diagnosis/knowledge')
      const keyword = query.value.trim().toLowerCase()
      const entries = data.entries.filter((entry: any) => !keyword || JSON.stringify(entry).toLowerCase().includes(keyword))
      total.value = entries.length
      results.value = entries.slice((currentPage.value - 1) * pageSize, currentPage.value * pageSize).map((entry: any) => ({
        id: entry.id, collection_name: 'generation_failures', title: entry.title,
        content: `${entry.content}\n适用条件：${entry.applicability}\n处理建议：\n${entry.actions.map((action: string) => `• ${action}`).join('\n')}`,
        verification: entry.verification, references: entry.sources, tags: ['失败诊断', '有适用条件'],
      }))
      return
    }
    const params: Record<string, string | number> = { limit: pageSize, offset: (currentPage.value - 1) * pageSize }
    if (activeCollection.value !== 'all') params.collection_name = activeCollection.value
    const response = await api.get<KnowledgeEntry[]>('/rag/entries', { params })
    results.value = response.data
    total.value = Number(response.headers['x-total-count'] || response.data.length)
  } catch (error: any) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

async function search() {
  if (activeCollection.value === 'generation_failures') { searched.value = Boolean(query.value.trim()); await loadLibrary(); return }
  const keyword = query.value.trim()
  if (!keyword) {
    searched.value = false
    await loadLibrary()
    return
  }
  loading.value = true
  searched.value = true
  try {
    const params: Record<string, string | number> = { query: keyword, top_k: pageSize, offset: (currentPage.value - 1) * pageSize }
    if (activeCollection.value !== 'all') params.collection_name = activeCollection.value
    const response = await api.get<KnowledgeEntry[]>('/rag/search', { params })
    results.value = response.data
    total.value = Number(response.headers['x-total-count'] || response.data.length)
    if (currentPage.value === 1) ElMessage.success(total.value ? `找到 ${total.value} 条知识` : '未找到匹配知识')
  } catch (error: any) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

async function changeCollection(collection: string) {
  activeCollection.value = collection
  currentPage.value = 1
  if (query.value.trim()) await search()
  else await loadLibrary()
}

async function beginSearch() {
  currentPage.value = 1
  await search()
}

async function changePage(page: number) {
  currentPage.value = page
  if (query.value.trim()) await search()
  else await loadLibrary()
}

onMounted(loadLibrary)
</script>

<template>
  <main class="page knowledge-page">
    <div class="section-heading">
      <div><p class="eyebrow"><BookOpen :size="15" />KNOWLEDGE LIBRARY</p><h1>创作知识库</h1></div>
      <span class="knowledge-count">{{ countLabel }}</span>
    </div>
    <div class="search-card glass-card">
      <Search :size="20" />
      <input v-model="query" :disabled="loading" @keyup.enter="beginSearch" placeholder="例如：显存不足、引擎断连、参考图；也可切换到建模知识" />
      <ElButton class="primary" :loading="loading" @click="beginSearch">搜索</ElButton>
    </div>
    <div class="knowledge-tabs" aria-label="知识分类">
      <button v-for="collection in collections" :key="collection.value" :class="{ active: activeCollection === collection.value }" @click="changeCollection(collection.value)">{{ collection.label }}</button>
    </div>
    <div v-if="loading" class="empty-state glass-card"><LoaderCircle :size="32" class="knowledge-loading" /><h2>正在检索知识库</h2></div>
    <section v-else-if="results.length" class="rag-list" aria-live="polite">
      <article v-for="entry in results" :key="entry.id" class="rag-card glass-card">
        <span class="rag-icon"><BookOpen :size="20" /></span>
        <div>
          <p class="eyebrow">{{ collectionLabel[entry.collection_name] || entry.collection_name }}</p>
          <h2>{{ entry.title }}</h2>
          <p>{{ entry.content || '该条知识尚未提供摘要。' }}</p>
          <p v-if="entry.verification" class="knowledge-verification">验证范围：{{ entry.verification }}</p>
          <details v-if="entry.references?.length" class="knowledge-references"><summary>查看资料来源</summary><p v-for="reference in entry.references" :key="reference.document">{{ reference.title }}<br /><code>{{ reference.document }}</code></p></details>
          <div v-if="visibleTags(entry).length" class="tag-row"><span v-for="tag in visibleTags(entry)" :key="tag">{{ tag }}</span></div>
        </div>
        <a v-if="entry.source" class="knowledge-source" :href="entry.source" target="_blank" rel="noreferrer" title="查看来源"><ExternalLink :size="17" /></a>
      </article>
    </section>
    <div v-if="!loading && total > pageSize" class="knowledge-pagination" aria-label="知识库分页">
      <ElPagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        :pager-count="5"
        layout="prev, pager, next"
        @current-change="changePage"
      />
    </div>
    <div v-if="!loading && !results.length" class="empty-state glass-card">
      <BookOpen :size="38" />
      <h2>{{ searched ? '未找到匹配知识' : '知识库暂时为空' }}</h2>
      <p>{{ searched ? '换一个更具体的建模、修饰符或材质关键词再试。' : '知识入库后会在这里展示。' }}</p>
    </div>
  </main>
</template>

<style scoped>
.rag-card p{white-space:pre-line;overflow-wrap:anywhere}.knowledge-verification{padding-top:10px;border-top:1px solid rgba(169,199,232,.2)}.knowledge-references{margin-top:12px;font-size:12px;color:var(--mist)}.knowledge-references summary{cursor:pointer;padding:6px 0}.knowledge-references code{font-size:11px;overflow-wrap:anywhere}
</style>
