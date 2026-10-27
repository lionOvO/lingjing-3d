<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElButton, ElCard, ElEmpty, ElMessage, ElProgress, ElSkeleton, ElTag, ElTooltip } from 'element-plus'
import { ArrowRight, BadgeCheck, Box, CircleAlert, Clock3, Download, FolderKanban, Image, LoaderCircle, Moon, Orbit, Play, RefreshCw, RotateCcw, Sparkles, WandSparkles, X } from 'lucide-vue-next'
import api from '../services/api'
import { useTaskStore, type TaskStatus } from '../stores/task'
import { formatApiDate } from '../utils/date'
import FailureDiagnosis from '../components/FailureDiagnosis.vue'

const route = useRoute()
const router = useRouter()
const tasks = useTaskStore()
const imageOnly=computed(()=>tasks.current?.generation_params?.vision_analysis===false)
const stages = computed(()=>[
  { key: 'analyzing', label: imageOnly.value?'输入确认':'图像分析', description: imageOnly.value?'使用你确认的参考图，不额外调用视觉语言模型。':'提取参考图的主体、轮廓与风格线索。' },
  { key: 'retrieving', label: imageOnly.value?'参数准备':'知识检索', description: imageOnly.value?'沿用所选生成参数，不根据未识别的属性检索。':'匹配知识库中的材质与建模参数。' },
  { key: 'generating', label: '3D 生成', description: '构建网格、纹理与基础材质。' },
  { key: 'evaluating', label: '确定性质量检测', description: '用网格、拓扑、面数与纹理规则检查输出。' },
  { key: 'postprocessing', label: '后处理', description: '整理模型文件并准备交付。' },
] as const)
const labels: Record<TaskStatus, string> = { pending: '排队中', analyzing: '正在图像分析', retrieving: '正在检索知识库', generating: '正在生成模型', evaluating: '正在质量评估', postprocessing: '正在后处理', completed: '已完成', failed: '已失败' }
const taskId = computed(() => String(route.params.taskId || tasks.current?.id || ''))
const task = computed(() => tasks.current)
const terminal = computed(() => ['completed', 'failed'].includes(task.value?.status || ''))
const failedStageIndex = computed(() => {
  const message = `${task.value?.error_message || ''} ${tasks.workflow?.state?.error_message || ''}`.toLowerCase()
  if (!message) return 0
  if (message.includes('analysis') || message.includes('analy') || message.includes('character normalization')) return 0
  if (message.includes('retrieval') || message.includes('rag') || message.includes('knowledge')) return 1
  if (message.includes('generation') || message.includes('model generation') || message.includes('3d')) return 2
  if (message.includes('quality') || message.includes('evaluation')) return 3
  if (message.includes('postprocess')) return 4
  return 0
})
const activeIndex = computed(() => { if (!task.value || task.value.status === 'pending') return -1; if (task.value.status === 'completed') return stages.value.length; if (task.value.status === 'failed') return failedStageIndex.value; return stages.value.findIndex((stage) => stage.key === task.value?.status) })
const progress = computed(() => { if (!task.value) return 0; if (task.value.status === 'completed') return 100; if (task.value.status === 'failed') return 55; if (typeof task.value.progress === 'number') return task.value.progress; return task.value.status === 'pending' ? 5 : Math.max(12, Math.round(((activeIndex.value + 1) / stages.value.length) * 100)) })
const taskType = computed(() => task.value?.task_type === 'object_model' ? '物品建模' : '动漫角色')
const stageLabel = computed(() => task.value ? imageOnly.value&&task.value.status==='analyzing'?'正在确认输入':imageOnly.value&&task.value.status==='retrieving'?'正在准备参数':labels[task.value.status] : '等待选择任务')
const quality = computed(() => typeof task.value?.quality_score === 'number' ? `${Math.round(task.value.quality_score * 100)} / 100` : '完成后生成')
const parameterRows = computed(() => { const params = task.value?.generation_params || {}; const provider = params.provider === 'local_comfyui' ? '本机 ComfyUI Trellis2' : params.provider === 'huggingface_space' ? 'Hugging Face TRELLIS.2' : params.provider === 'local_runner' ? '本地命令运行器' : params.provider || '未记录'; return [['输出格式', task.value?.output_format?.toUpperCase() || '-'], ['生成模式', formatValue(params.generation_mode || params.mode) || '未指定'], ['实际引擎', params.engine || '未记录'], ['实际提供方', provider], ['纹理分辨率', params.texture_resolution ? `${params.texture_resolution}px` : '智能推荐'], ['网格密度', formatValue(params.mesh_density) || '智能推荐'], ['PBR 材质', params.pbr_enabled === undefined ? '智能决定' : params.pbr_enabled ? '已开启' : '未开启'], ['重试次数', `${task.value?.retry_count || 0} 次`]] })
type DataRecord = Record<string, any>
function asRecord(value: unknown): DataRecord { return value && typeof value === 'object' && !Array.isArray(value) ? value as DataRecord : {} }
const valueLabels: Record<string, string> = { female: '女性', male: '男性', anime_humanoid: '动漫人形', human: '人类', standing: '站立', sitting: '坐姿', front: '正面', profile: '侧面', silver: '银色', blonde: '金色', white: '白色', black: '黑色', brown: '棕色', red: '红色', blue: '蓝色', long_straight: '长直发', straight: '直发', short: '短发', twintails: '双马尾', ponytail: '马尾', curly: '卷发', wavy: '波浪卷' }
const fieldLabels: Record<string, string> = { character_type: '角色类型', gender: '性别', hair: '头发特征', face: '面部特征', outfit: '服装特征', pose: '姿态', style_tags: '风格标签' }
function readable(value: unknown, fallback = '未识别') {
  if (value === null || value === undefined || value === '' || value === 'unknown') return fallback
  if (Array.isArray(value)) return value.length ? value.map((item) => readable(item)).join('、') : fallback
  if (typeof value === 'object') return Object.values(value as DataRecord).map((item) => readable(item)).join(' · ') || fallback
  const text = String(value)
  return valueLabels[text.toLowerCase()] || text
}
function readableField(value: unknown) { const text = String(value); return fieldLabels[text] || readable(text) }
function readableError(value: unknown) {
  let text = String(value || '该处理节点未能完成')
  text = text.replace(/^Character analysis failed:\s*/i, '图像分析失败：')
    .replace(/^Character normalization failed:\s*/i, '角色信息规范化失败：')
    .replace(/^Model generation failed:\s*/i, '3D 模型生成失败：')
    .replace(/^Quality check failed:\s*/i, '质量检查失败：')
    .replace(/^Task queue unavailable:\s*/i, '任务队列不可用：')
    .replace(/Server error ['"]502 Bad Gateway['"] for url ['"][^'"]+['"]/i, '视觉服务返回 502（网关错误）')
    .replace(/For more information check:\s*https?:\/\/\S+/i, '')
  return text.trim()
}
function json(value: unknown) { return JSON.stringify(value || {}, null, 2) }
const analysis = computed<DataRecord>(() => asRecord(task.value?.analysis_result || tasks.workflow?.state?.analysis_result))
const rawAnalysis = computed<DataRecord>(() => asRecord(analysis.value.raw_analysis || tasks.workflow?.state?.raw_character_analysis))
const hasAnalysis = computed(() => Object.keys(analysis.value).length > 0)
const analysisConfidence = computed<number | null>(() => { if (analysis.value.confidence === null || analysis.value.confidence === undefined || analysis.value.confidence === '') return null; const value = Number(analysis.value.confidence); return Number.isFinite(value) ? Math.round(Math.max(0, Math.min(1, value)) * 100) : null })
const uncertainFields = computed(() => Array.isArray(analysis.value.uncertain_fields) ? analysis.value.uncertain_fields : [])
const hair = computed(() => asRecord(analysis.value.hair))
const face = computed(() => asRecord(analysis.value.face))
const outfit = computed(() => asRecord(analysis.value.outfit))
const analysisFields = computed(() => [
  ['角色类型', analysis.value.character_type], ['性别', analysis.value.gender], ['姿态', analysis.value.pose],
  ['发色', hair.value.color], ['发型', hair.value.style], ['眼睛', face.value.eye_color],
  ['表情', face.value.expression], ['服装', outfit.value.description || outfit.value.top],
  ['配饰', outfit.value.accessories], ['风格标签', analysis.value.style_tags],
])
const retrieval = computed<DataRecord>(() => asRecord(task.value?.retrieved_params || tasks.workflow?.state?.retrieved_params))
const qualityRecord = computed<DataRecord>(() => asRecord(task.value?.retrieved_params || tasks.workflow?.state?.retrieved_params))
const qualityChecks = computed<DataRecord>(() => asRecord(qualityRecord.value.quality_checks || tasks.workflow?.state?.quality_checks))
const qualityRepairSuggestions = computed<DataRecord[]>(() => Array.isArray(qualityRecord.value.quality_repair_suggestions || tasks.workflow?.state?.quality_repair_suggestions) ? (qualityRecord.value.quality_repair_suggestions || tasks.workflow?.state?.quality_repair_suggestions) as DataRecord[] : [])
const qualityRepairSources = computed<DataRecord[]>(() => Array.isArray(qualityRecord.value.quality_repair_sources || tasks.workflow?.state?.quality_repair_sources) ? (qualityRecord.value.quality_repair_sources || tasks.workflow?.state?.quality_repair_sources) as DataRecord[] : [])
const qualityRepairDegraded = computed(() => Boolean(qualityRecord.value.quality_repair_degraded || tasks.workflow?.state?.quality_repair_degraded))
const qualityCheckRows = computed(() => Object.entries(qualityChecks.value).map(([key, passed]) => ({ key, passed: Boolean(passed), label: ({ watertight: '水密性', manifold: '流形拓扑', face_count_ok: '面数范围', no_degenerate: '无退化面', texture_resolution_ok: '纹理分辨率' } as Record<string, string>)[key] || key })))
const retrievalSources = computed<DataRecord[]>(() => Array.isArray(retrieval.value.sources) ? retrieval.value.sources.map(asRecord) : [])
const retrievalContext = computed<DataRecord[]>(() => Array.isArray(retrieval.value.context) ? retrieval.value.context.map(asRecord) : [])
const retrievalQuery = computed(() => String(retrieval.value.query || tasks.workflow?.state?.retrieval_query || ''))
const hasRetrieval = computed(() => Boolean(retrievalQuery.value || retrievalSources.value.length || retrievalContext.value.length || retrieval.value.degraded))
const hasRetrievalHistory = computed(() => Boolean(retrievalQuery.value || retrievalSources.value.length || retrievalContext.value.length))
const sourceImage = ref('')
const sourceImageFailed = ref(false)
const analysisStateLabel = computed(() => imageOnly.value ? '已确认输入' : hasAnalysis.value ? '已提取' : task.value?.status === 'failed' ? '未完成' : '等待分析')
const analysisStateClass = computed(() => imageOnly.value || hasAnalysis.value ? 'ready' : task.value?.status === 'failed' ? 'failed' : 'waiting')
function formatValue(value: unknown) { if (typeof value !== 'string') return ''; return ({ fast: '快速', quick_preview: '快速', preview: '快速', quick: '快速', balanced: '平衡', standard: '平衡', high_quality: '高质量', quality: '高质量', high: '高质量', low: '低', medium: '中', custom: '自定义' } as Record<string, string>)[value] || value }
function stageState(index: number) { if (!task.value) return 'waiting'; if (task.value.status === 'completed' || index < activeIndex.value) return 'complete'; if (index === activeIndex.value && task.value.status === 'failed') return 'failed'; if (index === activeIndex.value) return 'current'; return 'waiting' }
function stageDetail(stage: typeof stages.value[number]) { const state = tasks.workflow?.state || {}; const index = stages.value.indexOf(stage); if (task.value?.status === 'failed' && index === activeIndex.value) return readableError(task.value.error_message); if(imageOnly.value && ['analyzing','retrieving'].includes(stage.key))return stage.description; if (stage.key === 'analyzing' && hasAnalysis.value) return `已提取 ${analysisFields.value.filter(([, value]) => readable(value, '')).length} 项特征，置信度 ${analysisConfidence.value === null ? '未提供' : `${analysisConfidence.value}%`}`; if (stage.key === 'retrieving' && hasRetrieval.value) return retrievalSources.value.length ? `已匹配 ${retrievalSources.value.length} 条知识库记录` : '已完成检索，暂无高相似度记录'; if (stage.key === 'generating' && state.generated_model_url) return '已返回模型文件'; if (stage.key === 'evaluating' && typeof state.quality_score === 'number') return `质量评分 ${Math.round((state.quality_score as number) * 100)} / 100`; return stage.description }
async function loadSourceImage(_projectId: number) { if(sourceImage.value)URL.revokeObjectURL(sourceImage.value);sourceImage.value = ''; sourceImageFailed.value = false; try { const {data}=await api.get(`/studio/tasks/${taskId.value}/input`,{responseType:'blob'});sourceImage.value=URL.createObjectURL(data) } catch { /* The diagnostic panel still works without a preview image. */ } }
async function load() { if (!taskId.value) return; try { const loaded = await tasks.loadDetail(taskId.value); await loadSourceImage(loaded.project_id) } catch { /* The store provides the user-facing error. */ } }
async function refresh() { if (!taskId.value) return; try { await tasks.loadDetail(taskId.value); ElMessage.success('任务状态已刷新') } catch { ElMessage.error(tasks.error || '任务状态刷新失败') } }
async function retry() { if (!task.value) return; try { await tasks.retry(task.value.id); await tasks.loadDetail(task.value.id); ElMessage.success('已重新提交生成任务') } catch (exception: any) { ElMessage.error(exception?.message || '任务重试失败') } }
async function cancel() { if (!task.value) return; try { await tasks.cancel(task.value.id); ElMessage.success('已取消任务') } catch (exception: any) { ElMessage.error(exception?.message || '任务取消失败') } }
async function download() { if (!task.value) return; try { const { data } = await api.get(`/models/${task.value.id}/download`); window.open(data.download_url, '_blank', 'noopener') } catch (exception: any) { ElMessage.error(exception?.message || '模型下载失败') } }
function openViewer() { if (task.value) router.push({ name: 'workflow', params: { taskId: String(task.value.id) }, query: { step: 'preview' } }) }
watch(() => route.params.taskId, load)
onMounted(load)
onBeforeUnmount(() => {tasks.stopProgress();if(sourceImage.value)URL.revokeObjectURL(sourceImage.value)})
</script>

<template>
  <main class="page task-detail-page">
    <div v-if="!taskId" class="task-empty-shell glass-card"><Moon :size="36" /><h1>还没有要追踪的任务</h1><p>上传一张参考图片后，这里会记录每一步生成进展。</p><ElButton class="primary" @click="router.push('/generate')"><WandSparkles :size="17" />开始一次创作</ElButton></div>
    <template v-else>
      <ElSkeleton v-if="tasks.loading && !task" :rows="8" animated class="task-detail-skeleton" />
      <div v-else-if="tasks.error && !task" class="task-empty-shell glass-card task-load-error"><CircleAlert :size="36" /><h1>任务详情暂时无法打开</h1><p>{{ tasks.error }}</p><div><ElButton class="secondary" @click="router.push('/tasks')">返回任务中心</ElButton><ElButton class="primary" @click="refresh">重新加载</ElButton></div></div>
      <template v-else-if="task">
        <section class="task-detail-hero"><div><p class="eyebrow"><Orbit :size="15" />TASK ORBIT · #{{ task.id }}</p><div class="task-detail-heading"><h1>任务的月相轨迹</h1><ElTag :class="['moonlit-status', `moonlit-${task.status}`]" effect="plain">{{ stageLabel }}</ElTag></div><p class="task-detail-subtitle">{{ taskType }} · {{ task.output_format.toUpperCase() }} · 创建于 {{ formatApiDate(task.created_at) }}</p></div><div class="task-hero-actions"><div class="task-detail-actions"><span v-if="!terminal" class="task-live"><i></i>实时同步中</span><ElTooltip content="重新读取任务状态" :show-after="450" :disabled="tasks.loading"><ElButton circle class="task-refresh" :loading="tasks.loading" @click="refresh"><RefreshCw v-if="!tasks.loading" :size="16" /></ElButton></ElTooltip></div><ElButton v-if="task.status === 'completed'" class="secondary" @click="download"><Download :size="16" />下载 {{ task.output_format.toUpperCase() }}</ElButton><ElButton v-if="task.status === 'completed'" class="primary" @click="openViewer"><Play :size="16" />打开 3D 预览</ElButton><ElButton v-else-if="task.status === 'failed'" class="primary" @click="retry"><RotateCcw :size="16" />重新生成</ElButton><ElButton v-else class="secondary" @click="cancel"><X :size="16" />取消任务</ElButton></div></section>
        <div class="task-detail-grid"><section class="task-main-column"><ElCard class="task-progress-card glass-card"><div class="task-card-head"><div><p class="eyebrow">LIVE PROGRESS</p><h2>{{ task.status === 'completed' ? '模型已准备就绪' : task.status === 'failed' ? '任务在生成中断开' : stageLabel }}</h2></div><strong>{{ progress }}%</strong></div><ElProgress :percentage="progress" :show-text="false" :stroke-width="8" color="#a9c7e8" /><p class="task-progress-note">{{ task.status === 'completed' ? `已于 ${formatApiDate(task.completed_at)} 完成，可进入预览器检查模型。` : task.status === 'failed' ? '查看失败原因后可重新提交，本次参数将被保留。' : '任务状态通过 WebSocket 接收；连接中断时会自动回退为轮询。' }}</p><ol class="task-stage-list"><li v-for="(stage, index) in stages" :key="stage.key" :class="stageState(index)"><div class="stage-marker"><BadgeCheck v-if="stageState(index) === 'complete'" :size="17" /><LoaderCircle v-else-if="stageState(index) === 'current'" :size="17" /><CircleAlert v-else-if="stageState(index) === 'failed'" :size="17" /><span v-else>{{ String(index + 1).padStart(2, '0') }}</span></div><div><strong>{{ stage.label }}</strong><p>{{ stageDetail(stage) }}</p></div><span class="stage-state">{{ stageState(index) === 'complete' ? '已完成' : stageState(index) === 'current' ? '进行中' : stageState(index) === 'failed' ? '已中断' : '等待中' }}</span></li></ol></ElCard><ElCard v-if="task.error_message" class="task-error-card glass-card"><CircleAlert :size="21" /><div><strong>{{ task.status === 'failed' ? '任务未能完成' : '任务提示' }}</strong><p>{{ readableError(task.error_message) }}</p></div><ElButton v-if="task.status === 'failed'" text @click="retry">重新生成 <ArrowRight :size="14" /></ElButton></ElCard><FailureDiagnosis v-if="task.status === 'failed'" :task-id="task.id" :failure-key="task.error_message || ''" /><ElCard class="task-params-card glass-card"><div class="task-card-head"><div><p class="eyebrow">GENERATION SETTINGS</p><h2>生成参数</h2></div><Sparkles :size="20" /></div><dl class="task-parameter-grid"><div v-for="([label, value]) in parameterRows" :key="label"><dt>{{ label }}</dt><dd>{{ value }}</dd></div></dl></ElCard></section><aside class="task-side-column">
          <ElCard class="task-input-card task-insight-card glass-card">
            <div class="task-card-head input-card-head">
              <div><p class="eyebrow">GENERATION INPUT</p><h2>本次生成输入</h2></div>
              <span :class="['insight-state', analysisStateClass]">{{ analysisStateLabel }}</span>
            </div>
            <figure v-if="sourceImage && !sourceImageFailed" class="task-input-preview">
              <img :src="sourceImage" alt="本次任务实际使用的生成输入图" @error="sourceImageFailed = true" />
              <figcaption>实际送入生成引擎的图片</figcaption>
            </figure>
            <p v-else class="insight-empty task-input-unavailable">输入图暂时无法加载，任务记录仍然保留。</p>
            <p class="task-input-note">{{ imageOnly ? '使用你确认的参考图和生成参数。' : '使用本次任务的参考图；已记录的分析结果可在下方查看。' }}</p>
            <details v-if="hasAnalysis && !imageOnly" class="raw-details task-input-history">
              <summary>查看历史图像分析</summary>
              <dl class="analysis-fields"><div v-for="([label, value]) in analysisFields" :key="label" class="analysis-field"><dt>{{ label }}</dt><dd>{{ readable(value) }}</dd></div></dl>
              <div class="confidence-line"><span>识别置信度</span><strong>{{ analysisConfidence === null ? '未提供' : analysisConfidence + '%' }}</strong></div>
              <div v-if="uncertainFields.length" class="uncertain-line"><span>需要复核</span><em v-for="field in uncertainFields" :key="field">{{ readableField(field) }}</em></div>
              <details class="raw-details"><summary>查看原始识别数据</summary><pre>{{ json(rawAnalysis) }}</pre></details>
            </details>
            <details v-if="!imageOnly && hasRetrievalHistory" class="raw-details task-input-history">
              <summary>查看历史参数检索记录</summary>
              <div v-if="retrievalQuery" class="retrieval-query"><span>当时的检索语句</span><p>{{ retrievalQuery }}</p></div>
              <div v-if="retrievalSources.length" class="retrieval-sources"><div v-for="(source, index) in retrievalSources.slice(0, 5)" :key="`${source.collection}-${source.id || index}`" class="retrieval-source"><span>{{ String(index + 1).padStart(2, '0') }}</span><div><strong>{{ readable(source.title || source.style_name || source.object_type || source.material_type, '知识库记录') }}</strong><small>{{ readable(source.collection, '知识库') }}</small></div></div></div>
              <p class="task-input-note">这是任务当时保存的记录，不代表当前故障诊断的检索结果。</p>
              <details v-if="retrievalContext.length" class="raw-details"><summary>查看完整命中数据（{{ retrievalContext.length }} 条）</summary><pre>{{ json(retrievalContext) }}</pre></details>
            </details>
          </ElCard>
<ElCard class="task-result-card glass-card" :class="{ ready: task.status === 'completed' }"><div class="result-orbit"><Box :size="33" /></div><p class="eyebrow">DELIVERY</p><h2>{{ task.status === 'completed' ? '模型已交付' : '模型正在成形' }}</h2><p>{{ task.status === 'completed' ? '模型和纹理已准备好，可进入预览器检查或直接下载。' : '生成完成后，这里会提供模型预览、下载与格式转换。' }}</p><div class="result-facts"><span><Image :size="15" />{{ task.texture_urls?.length || 0 }} 张纹理</span><span><BadgeCheck :size="15" />质量 {{ quality }}</span></div><ElButton class="primary" :disabled="task.status !== 'completed'" @click="openViewer"><Play :size="16" />预览模型</ElButton><ElButton class="result-download" text :disabled="task.status !== 'completed'" @click="download"><Download :size="15" />下载源文件</ElButton></ElCard><ElCard class="task-record-card glass-card"><div class="task-card-head"><div><p class="eyebrow">TASK RECORD</p><h2>任务记录</h2></div><Clock3 :size="19" /></div><dl><div><dt>项目编号</dt><dd>#{{ task.project_id }}</dd></div><div><dt>队列编号</dt><dd :title="task.celery_task_id || ''">{{ task.celery_task_id || '等待分配' }}</dd></div><div><dt>完成时间</dt><dd>{{ formatApiDate(task.completed_at) }}</dd></div></dl><ElButton text class="task-project-link" @click="router.push('/projects')"><FolderKanban :size="15" />查看项目 <ArrowRight :size="14" /></ElButton></ElCard></aside></div>
        <ElCard v-if="qualityCheckRows.length || task.status === 'evaluating' || task.status === 'completed' || qualityRepairSuggestions.length" class="quality-inspection-card glass-card">
          <div class="task-card-head"><div><p class="eyebrow">DETERMINISTIC INSPECTION</p><h2 class="insight-title">确定性质量检测</h2></div><ElTag effect="plain">检测器判定</ElTag></div>
          <p class="quality-boundary-note">以下结果由网格 / 纹理检测器计算；RAG 仅提供修复建议，不参与通过或失败判定。</p>
          <div class="quality-check-grid"><div v-for="check in qualityCheckRows" :key="check.key" :class="['quality-check-item', check.passed ? 'passed' : 'failed']"><BadgeCheck v-if="check.passed" :size="16" /><CircleAlert v-else :size="16" /><span>{{ check.label }}</span><strong>{{ check.passed ? '通过' : '失败' }}</strong></div></div>
          <div v-if="qualityRepairSuggestions.length || qualityRepairDegraded" class="repair-suggestion-box"><div class="insight-section-head"><div><strong>RAG 修复建议</strong><small>仅供下一次生成参数参考</small></div><span class="insight-state" :class="qualityRepairDegraded ? 'waiting' : 'ready'">{{ qualityRepairDegraded ? '服务降级' : '已生成' }}</span></div><ul v-if="qualityRepairSuggestions.length"><li v-for="(item, index) in qualityRepairSuggestions.slice(0, 3)" :key="index">{{ typeof item.suggestion === 'object' ? json(item.suggestion) : String(item.suggestion || '建议调整生成参数') }}</li></ul><p v-else>未获取到可用建议，检测结果仍然有效。</p><small v-if="qualityRepairSources.length">参考 {{ qualityRepairSources.length }} 条历史修复案例</small></div>
        </ElCard>
      </template>
    </template>
  </main>
</template>
