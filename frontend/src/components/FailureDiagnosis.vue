<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { Download, RefreshCw, ScanSearch, ChevronDown } from 'lucide-vue-next'
import api from '../services/api'
import { formatApiDate } from '../utils/date'

const props = defineProps<{ taskId: number | string; failureKey: string }>()
type Knowledge = { id: string; title: string; content: string; applicability: string; verification: string; sources: { title: string; document: string }[] }
type Report = {
  task_id: number; captured_at: string; classification: { title: string; summary: string; certainty: string }
  evidence: { scope: string; label: string; value: string }[]; actions: string[]; knowledge: Knowledge[]
  related_failures: { task_id: number; label: string }[]; limitations: string[]
}
const report = ref<Report | null>(null), loading = ref(false), error = ref('')
let requestVersion = 0
let controller: AbortController | null = null
async function diagnose() {
  const version = ++requestVersion
  controller?.abort()
  controller = new AbortController()
  loading.value = true
  error.value = ''
  // A refreshed snapshot must not show old evidence if the request fails.
  report.value = null
  try {
    const { data } = await api.get<Report>(`/studio/tasks/${props.taskId}/diagnosis`, { signal: controller.signal, timeout: 12000, _startupRetryCount: 6 })
    if (version === requestVersion) report.value = data
  } catch (exception: any) {
    if (version === requestVersion) error.value = exception?.message || '暂时无法获取诊断，请重新检测'
  } finally {
    if (version === requestVersion) loading.value = false
  }
}
function exportReport() {
  if (!report.value) return
  const url = URL.createObjectURL(new Blob([JSON.stringify(report.value, null, 2)], { type: 'application/json' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `task-${props.taskId}-diagnosis.json`
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
watch(() => [props.taskId, props.failureKey], diagnose, { immediate: true })
onBeforeUnmount(() => { requestVersion++; controller?.abort() })
</script>

<template>
  <section class="failure-diagnosis glass-card" aria-labelledby="diagnosis-heading" aria-live="polite" :aria-busy="loading">
    <header class="diagnosis-head">
      <div><p class="eyebrow"><ScanSearch :size="15" />失败诊断</p><h2 id="diagnosis-heading">先查原因，再决定重试</h2></div>
      <button type="button" class="diagnosis-button" :disabled="loading" @click="diagnose"><RefreshCw :size="15" :class="{ spinning: loading }" />{{ loading ? '正在检测' : '重新检测' }}</button>
    </header>
    <p v-if="loading" class="diagnosis-note" role="status">正在核对任务错误、引擎状态和适用的处理知识；不会启动生成。</p>
    <p v-else-if="error" class="diagnosis-note diagnosis-warning" role="alert">{{ error }}。原任务记录仍然保留。</p>
    <template v-else-if="report">
      <div class="diagnosis-conclusion"><span>{{ report.classification.certainty }}</span><h3>{{ report.classification.title }}</h3><p>{{ report.classification.summary }}</p></div>
      <div class="diagnosis-evidence">
        <section v-for="scope in ['failure', 'current']" :key="scope">
          <h3>{{ scope === 'failure' ? '失败时的记录' : '现在检测到的状态' }}</h3>
          <small v-if="scope === 'current'">检测于 {{ formatApiDate(report.captured_at) }}</small>
          <dl><div v-for="(item, index) in report.evidence.filter(item => item.scope === scope)" :key="index"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div></dl>
        </section>
      </div>
      <section v-if="report.actions.length" class="diagnosis-next"><h3>建议按这个顺序处理</h3><ol><li v-for="action in report.actions" :key="action">{{ action }}</li></ol></section>
      <details class="diagnosis-details"><summary>处理依据与检测范围 · {{ report.knowledge.length }} 条适用知识<ChevronDown :size="15" /></summary>
        <article v-for="entry in report.knowledge" :key="entry.id"><h4>{{ entry.title }}</h4><p>{{ entry.content }}</p><p><b>适用条件：</b>{{ entry.applicability }}</p><p><b>验证范围：</b>{{ entry.verification }}</p><ul><li v-for="source in entry.sources" :key="source.document">{{ source.title }}<code>{{ source.document }}</code></li></ul></article>
        <p v-if="!report.knowledge.length">暂无适用案例，系统没有用无关知识补齐答案。</p>
        <ul class="diagnosis-limits"><li v-for="limit in report.limitations" :key="limit">{{ limit }}</li></ul>
        <p v-if="report.related_failures.length">同账号同类失败记录：{{ report.related_failures.map(item => `#${item.task_id}`).join('、') }}。同类错误不代表相同根因。</p>
      </details>
      <footer class="diagnosis-footer"><span>只读检测 · 不会更改参数或自动重试</span><button type="button" class="diagnosis-button" @click="exportReport"><Download :size="15" />导出诊断记录</button></footer>
    </template>
  </section>
</template>

<style scoped>
.failure-diagnosis{padding:26px;min-width:0;color:var(--white);border:1px solid rgba(169,199,232,.35)}
.diagnosis-head,.diagnosis-footer{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}.diagnosis-head .eyebrow{display:flex;align-items:center;gap:7px;margin:0 0 8px}.diagnosis-head h2{font-size:22px;margin:0;line-height:1.4}.diagnosis-button{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:38px;padding:8px 12px;border:1px solid rgba(169,199,232,.4);border-radius:8px;background:rgba(169,199,232,.09);color:var(--white);font:inherit;font-size:12px;cursor:pointer;flex:none}.diagnosis-button:hover:not(:disabled){background:rgba(169,199,232,.18)}.diagnosis-button:focus-visible{outline:2px solid var(--pink);outline-offset:3px}.diagnosis-button:disabled{opacity:.6;cursor:wait}.diagnosis-note{font-size:13px;line-height:1.8;margin:20px 0 0;color:var(--mist)}.diagnosis-warning{color:#f3c4bc}.diagnosis-conclusion{margin-top:22px;padding:18px 20px;border-left:3px solid #b4cee8;background:rgba(15,34,52,.4);border-radius:0 9px 9px 0}.diagnosis-conclusion span{font-size:11px;color:#d9c9a3}.diagnosis-conclusion h3{font-size:18px;margin:8px 0}.diagnosis-conclusion p,.diagnosis-details p{font-size:13px;line-height:1.8;margin:6px 0;color:var(--mist)}.diagnosis-evidence{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:22px;margin-top:24px}.diagnosis-evidence h3,.diagnosis-next h3{font-size:14px;margin:0 0 8px}.diagnosis-evidence small{font-size:11px;color:var(--mist)}.diagnosis-evidence dl{margin:10px 0 0}.diagnosis-evidence dl div{padding:10px 0;border-top:1px solid rgba(169,199,232,.15)}.diagnosis-evidence dt{font-size:11px;color:var(--mist);margin-bottom:6px}.diagnosis-evidence dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;line-height:1.8}.diagnosis-next{margin-top:20px;padding-top:18px;border-top:1px solid rgba(169,199,232,.2)}.diagnosis-next ol{padding-left:22px;margin:10px 0}.diagnosis-next li{padding:5px 0 5px 3px;line-height:1.8;font-size:13px}.diagnosis-next li::marker{color:#b4cee8;font-weight:700}.diagnosis-details{margin-top:20px;border-top:1px solid rgba(169,199,232,.2)}.diagnosis-details summary{display:flex;align-items:center;justify-content:space-between;gap:10px;cursor:pointer;font-size:12px;padding:16px 0;list-style:none}.diagnosis-details article{padding:12px 0;border-top:1px solid rgba(169,199,232,.15)}.diagnosis-details h4{font-size:14px;margin:0 0 8px}.diagnosis-details ul{padding-left:18px;line-height:1.8;font-size:12px;color:var(--mist)}.diagnosis-details code{display:block;font:11px/1.7 ui-monospace,Consolas,monospace;overflow-wrap:anywhere}.diagnosis-footer{border-top:1px solid rgba(169,199,232,.2);margin-top:8px;padding-top:16px}.diagnosis-footer span{font-size:11px;color:var(--mist)}.spinning{animation:diagnosis-spin 1s linear infinite}@keyframes diagnosis-spin{to{transform:rotate(360deg)}}@media(max-width:760px){.failure-diagnosis{padding:20px}.diagnosis-evidence{grid-template-columns:minmax(0,1fr);gap:16px}.diagnosis-head h2{font-size:20px}}@media(prefers-reduced-motion:reduce){.spinning{animation:none}}
</style>
