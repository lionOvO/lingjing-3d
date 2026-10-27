<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElButton, ElDropdown, ElDropdownItem, ElDropdownMenu, ElEmpty, ElMessage, ElOption, ElProgress, ElSelect, ElSlider, ElSwitch, ElTabs, ElTabPane, ElTooltip } from 'element-plus'
import { Box, ChevronDown, ChevronLeft, ChevronRight, Download, Expand, Grid2X2, ImageDown, Info, Lightbulb, Maximize2, Moon, RotateCcw, Settings2, Sparkles } from 'lucide-vue-next'
import ThreePreview, { type DisplayMode, type ModelTransformMode, type ViewerBackground } from '../components/ThreePreview.vue'
import api from '../services/api'
import { useTaskStore } from '../stores/task'
type Metadata = { vertex_count?: number; face_count?: number; texture_resolution?: string; has_pbr?: boolean; file_size_mb?: number }
const route = useRoute(); const router = useRouter(); const tasks = useTaskStore(); const viewer = ref<InstanceType<typeof ThreePreview>>(); const modelUrl = ref(''); const metadata = ref<Metadata | null>(null); const busy = ref(false); const error = ref(''); const leftOpen = ref(true); const rightOpen = ref(true); const bottomOpen = ref(true); const displayMode = ref<DisplayMode>('material'); const background = ref<ViewerBackground>('inspection'); const autoRotate = ref(false); const showGrid = ref(false); const modelMoveMode = ref(false); const modelTransformMode = ref<ModelTransformMode>('translate'); const tab = ref('material'); const roughness = ref(1); const metalness = ref(1); const ambientIntensity = ref(1.1); const keyLightIntensity = ref(2.8); const requestedFormat = ref('glb')
// Prefer the task id encoded by the route so historical models can be opened
// directly from a project without depending on the global recent-task cache.
const taskId = computed(() => String(route.params.taskId || route.query.taskId || tasks.current?.id || '')); const completed = computed(() => tasks.current?.status === 'completed' && Boolean(tasks.current?.output_model_url)); const inWorkflow = computed(() => route.name === 'workflow'); const taskLabel = computed(() => taskId.value ? `#${taskId.value}` : '未选择任务'); const format = computed(() => String(tasks.current?.output_format || 'glb').toUpperCase()); const textures = computed<string[]>(() => tasks.current?.texture_urls || []); const progress = computed(() => tasks.current?.status === 'completed' ? 100 : tasks.current?.status === 'failed' ? 0 : 42); const statusText = computed(() => tasks.current?.status === 'completed' ? '模型已完成' : tasks.current?.status === 'failed' ? '任务生成失败' : '模型正在生成'); const canPreview = computed(() => completed.value && Boolean(modelUrl.value))
function sameOriginAssetUrl(url: unknown, task: string) {
  // The API builds absolute URLs from its own container port (8000). The
  // browser must use the frontend gateway (8080) so GLTFLoader gets the same
  // origin, proxy headers and WebSocket/CORS behaviour as the rest of the UI.
  if (typeof url !== 'string' || !url) return `/api/v1/models/${task}/content`
  try {
    const parsed = new URL(url, window.location.origin)
    if (parsed.pathname.startsWith('/api/v1/models/')) return `${parsed.pathname}${parsed.search}`
  } catch { /* Fall through to the safe task endpoint below. */ }
  return url
}
function number(value?: number) { return typeof value === 'number' ? value.toLocaleString('zh-CN') : '暂无数据' }; function textureName(url: string, index: number) { try { return decodeURIComponent(new URL(url).pathname.split('/').pop() || `纹理 ${index + 1}`) } catch { return `纹理 ${index + 1}` } }
async function fetchPreview() { if (!taskId.value || !completed.value) return; try { const { data } = await api.get(`/models/${taskId.value}/preview`); modelUrl.value = sameOriginAssetUrl(data.download_url, taskId.value); error.value = ''; try { metadata.value = (await api.get(`/models/${taskId.value}`)).data } catch { metadata.value = null } } catch (exception: any) { error.value = exception?.message || '模型预览信息获取失败，请稍后重试'; modelUrl.value = ''; ElMessage.error(error.value) } }
async function initialise() {
  let requestedTaskId = taskId.value
  if (!requestedTaskId) {
    const cache = localStorage.getItem('moonlit_recent_task')
    try {
      const cachedTask = cache ? JSON.parse(cache) : null
      if (cachedTask && Number.isInteger(cachedTask.id) && cachedTask.id > 0) requestedTaskId = String(cachedTask.id)
      else localStorage.removeItem('moonlit_recent_task')
    } catch {
      localStorage.removeItem('moonlit_recent_task')
    }
  }
  if (!requestedTaskId) return
  busy.value = true
  try {
    await tasks.fetch(requestedTaskId)
    tasks.startProgress(requestedTaskId)
    if (completed.value) await fetchPreview()
  } catch (exception: any) {
    error.value = exception?.message || '无法读取任务信息，请返回任务中心后重试'
  } finally {
    busy.value = false
  }
}
async function downloadModel() { if (!taskId.value || !completed.value) return; try { const { data } = await api.get(`/models/${taskId.value}/download`); const link = document.createElement('a'); link.href = sameOriginAssetUrl(data.download_url, taskId.value); link.download = `moonlit-model-${taskId.value}.${format.value.toLowerCase()}`; link.click() } catch (exception: any) { ElMessage.error(exception?.message || '模型下载失败') } }
function downloadTexture(url: string) { window.open(url, '_blank', 'noopener') }
async function convertModel() { if (!taskId.value || !completed.value) return; busy.value = true; try { await api.post(`/models/${taskId.value}/convert`, { output_format: requestedFormat.value }); ElMessage.success(`已提交 ${requestedFormat.value.toUpperCase()} 格式转换`); await tasks.fetch(taskId.value); await fetchPreview() } catch (exception: any) { ElMessage.error(exception?.message || '格式转换失败') } finally { busy.value = false } }
function rerun() { if (taskId.value) router.push({ path: '/generate', query: { retryTask: taskId.value } }) }; function previousWorkflowStep() { void router.push({ name: 'workflow', params: taskId.value ? { taskId: taskId.value } : {}, query: { step: 'task' } }) }; function restartWorkflow() { void router.push({ name: 'workflow', query: { step: 'upload' } }) }; function onViewerError(message: string) { if (modelUrl.value) error.value = message }
function handleViewerAction(command: string) {
  if (command === 'record') previousWorkflowStep()
  else if (command === 'compare') void router.push({ path: '/compare', query: { a: taskId.value } })
  else if (command === 'preset') void router.push({ path: '/presets', query: { task: taskId.value } })
  else if (command === 'rerun') rerun()
}
watch(() => tasks.current?.status, (status) => { if (status === 'completed' && !modelUrl.value) fetchPreview() }); onMounted(initialise); onBeforeUnmount(() => tasks.stopProgress())
</script>
<template>
  <main class="model-workbench">
    <header class="viewer-head viewer-action-head">
      <div class="viewer-heading">
        <RouterLink class="viewer-flow-button viewer-back-link" to="/library"><ChevronLeft :size="16" />返回资产</RouterLink>
        <div class="viewer-identity"><Moon :size="18" /><strong>模型检视</strong><small>{{ taskLabel }}</small></div>
      </div>
      <div class="viewer-head-end">
        <div class="viewer-status"><span :class="['status-dot', tasks.current?.status]"></span>{{ statusText }}</div>
        <RouterLink v-if="completed" class="viewer-flow-button viewer-repair-link" :to="`/repair/${taskId}`">检查与修复</RouterLink>
        <ElDropdown v-if="taskId" trigger="click" placement="bottom-end" @command="handleViewerAction">
          <button class="viewer-flow-button viewer-more-button">更多操作<ChevronDown :size="14" /></button>
          <template #dropdown><ElDropdownMenu>
            <ElDropdownItem v-if="inWorkflow" command="record">查看生成记录</ElDropdownItem>
            <ElDropdownItem command="compare" :disabled="!completed">对比模型</ElDropdownItem>
            <ElDropdownItem command="preset" :disabled="!completed">参数存为预设</ElDropdownItem>
            <ElDropdownItem command="rerun" divided>重新生成</ElDropdownItem>
          </ElDropdownMenu></template>
        </ElDropdown>
        <button class="viewer-flow-button viewer-flow-next" @click="restartWorkflow">新建生成<ChevronRight :size="16" /></button>
      </div>
    </header>
    <section class="viewer-shell" :class="{ 'left-closed': !leftOpen, 'right-closed': !rightOpen, 'bottom-closed': !bottomOpen }">
      <aside class="viewer-side viewer-left"><div class="side-head"><h1>模型信息</h1><ElTooltip :content="leftOpen ? '收起模型信息' : '展开模型信息'"><button class="viewer-icon" @click="leftOpen = !leftOpen"><ChevronLeft v-if="leftOpen" :size="18" /><ChevronRight v-else :size="18" /></button></ElTooltip></div><template v-if="leftOpen"><div class="info-scroll"><dl class="model-facts"><div><dt>任务编号</dt><dd>{{ taskLabel }}</dd></div><div><dt>输出格式</dt><dd>{{ format }}</dd></div><div><dt>顶点数</dt><dd>{{ number(metadata?.vertex_count) }}</dd></div><div><dt>面数</dt><dd>{{ number(metadata?.face_count) }}</dd></div><div><dt>文件大小</dt><dd>{{ metadata?.file_size_mb ? `${metadata.file_size_mb.toFixed(2)} MB` : '暂无数据' }}</dd></div><div><dt>质量评分</dt><dd>{{ tasks.current?.quality_score ? `${Math.round(tasks.current.quality_score * 100)} / 100` : '等待评分' }}</dd></div></dl></div></template></aside>
      <section class="viewer-stage"><div class="stage-top-tools"><ElSelect v-model="displayMode" aria-label="材质显示方式" size="small" :teleported="false"><ElOption label="材质显示" value="material" /><ElOption label="实体显示" value="solid" /><ElOption label="线框显示" value="wireframe" /><ElOption label="平面着色" value="normals" /></ElSelect><ElSelect v-model="background" aria-label="检视背景" style="width:140px" size="small" :teleported="false"><ElOption label="中性灰（推荐）" value="inspection" /><ElOption label="深灰背景" value="night" /><ElOption label="浅灰背景" value="studio" /><ElOption label="透明背景" value="transparent" /></ElSelect><label class="auto-rotate"><span>自动旋转</span><ElSwitch v-model="autoRotate" aria-label="自动旋转" size="small" /></label></div><ThreePreview ref="viewer" :model-url="canPreview ? modelUrl : ''" :model-format="format.toLowerCase()" :display-mode="displayMode" :background="background" :auto-rotate="autoRotate" :show-grid="showGrid" :model-move-mode="modelMoveMode" :model-transform-mode="modelTransformMode" :roughness="roughness" :metalness="metalness" :ambient-intensity="ambientIntensity" :key-light-intensity="keyLightIntensity" @error="onViewerError" /><div v-if="busy || (!completed && taskId)" class="generation-overlay"><ElProgress type="circle" :percentage="progress" :width="58" color="#a9c7e8" /><strong>{{ busy ? '正在读取模型信息…' : statusText }}</strong><span>{{ tasks.current?.error_message || '任务完成后会自动载入 3D 模型。' }}</span></div><div v-if="!taskId" class="generation-overlay"><ElEmpty description="尚未选择需要预览的模型任务"><ElButton class="viewer-primary" @click="router.push('/tasks')">前往任务中心</ElButton></ElEmpty></div><div class="stage-actions" role="toolbar" aria-label="视角与截图工具"><ElTooltip content="显示辅助网格"><button :class="['viewer-icon',{active:showGrid}]" aria-label="显示辅助网格" :aria-pressed="showGrid" @click="showGrid=!showGrid"><Grid2X2 :size="17"/></button></ElTooltip><ElTooltip content="全屏检视"><button class="viewer-icon" aria-label="全屏检视" @click="viewer?.toggleFullscreen()"><Expand :size="17" /></button></ElTooltip><ElTooltip content="重置视角"><button class="viewer-icon" aria-label="重置视角" @click="viewer?.resetCamera()"><RotateCcw :size="17" /></button></ElTooltip><ElTooltip content="保存截图"><button class="viewer-icon" aria-label="保存截图" @click="viewer?.capture()"><ImageDown :size="17" /></button></ElTooltip></div><div v-if="error" class="viewer-error"><Info :size="16" /><span>{{ error }}</span><button @click="fetchPreview">重试</button></div></section>
      <aside class="viewer-side viewer-right"><div class="side-head"><h2>纹理贴图</h2><ElTooltip :content="rightOpen ? '收起纹理贴图' : '展开纹理贴图'"><button class="viewer-icon" @click="rightOpen = !rightOpen"><ChevronRight v-if="rightOpen" :size="18" /><ChevronLeft v-else :size="18" /></button></ElTooltip></div><template v-if="rightOpen"><div v-if="textures.length" class="texture-list"><article v-for="(texture, index) in textures" :key="texture" class="texture-item"><div class="texture-thumb"><img :src="texture" :alt="textureName(texture, index)" @error="($event.target as HTMLImageElement).style.display = 'none'" /><Box :size="20" /></div><div><strong>{{ textureName(texture, index) }}</strong><small>{{ metadata?.texture_resolution || '纹理文件' }}</small></div><ElTooltip content="下载纹理"><button class="texture-download" @click="downloadTexture(texture)"><Download :size="15" /></button></ElTooltip></article></div><div v-else class="texture-empty"><Sparkles :size="23" /><span>{{ metadata?.has_pbr ? 'PBR 贴图已内嵌于 GLB，随模型一同下载。' : '该模型暂未返回独立纹理贴图' }}</span></div></template></aside>
      <section class="viewer-bottom"><div class="bottom-head"><button class="bottom-label" @click="bottomOpen = !bottomOpen"><Settings2 :size="17" />模型控制 <ChevronDown :class="{ flipped: !bottomOpen }" :size="16" /></button><span v-if="bottomOpen">参数只影响当前浏览器预览，不会改动原始模型</span></div><template v-if="bottomOpen"><ElTabs v-model="tab" class="viewer-tabs"><ElTabPane label="PBR 材质" name="material"><div class="control-grid"><label>粗糙度倍率 <ElSlider v-model="roughness" :min="0" :max="1" :step=".01" /><output>{{ roughness.toFixed(2) }}</output></label><label>金属度倍率 <ElSlider v-model="metalness" :min="0" :max="1" :step=".01" /><output>{{ metalness.toFixed(2) }}</output></label></div></ElTabPane><ElTabPane label="光照设置" name="light"><div class="control-grid"><label>环境光 <ElSlider v-model="ambientIntensity" :min="0" :max="3" :step=".1" /><output>{{ ambientIntensity.toFixed(1) }}</output></label><label>主光强度 <ElSlider v-model="keyLightIntensity" :min="0" :max="6" :step=".1" /><output>{{ keyLightIntensity.toFixed(1) }}</output></label></div></ElTabPane><ElTabPane label="变换工具" name="transform"><div class="viewer-transform-settings"><label><ElSwitch v-model="modelMoveMode" aria-label="启用三轴变换工具"/>启用三轴变换工具</label><ElSelect v-model="modelTransformMode" :disabled="!modelMoveMode" aria-label="三轴变换方式" :teleported="false"><ElOption label="移动模型" value="translate"/><ElOption label="旋转模型" value="rotate"/></ElSelect><p>仅在需要调整模型摆放时开启。日常检视可直接旋转和平移视角，无需开启。</p></div></ElTabPane><ElTabPane label="操作提示" name="help"><div class="help-grid"><span><Box :size="16" />单击模型即可选中并显示包围框</span><span><RotateCcw :size="16" />左键拖拽旋转视角</span><span><Maximize2 :size="16" />右键 / 中键 / Shift + 左键拖拽平移视角</span><span><Lightbulb :size="16" />调整参数仅用于本地预览</span></div></ElTabPane></ElTabs></template></section>
    </section>
    <footer class="viewer-footer viewer-export-bar" aria-label="模型导出">
      <div class="viewer-export-info"><strong>{{ format }} 模型<span v-if="metadata?.file_size_mb"> · {{ metadata.file_size_mb.toFixed(2) }} MB</span></strong><small>{{ metadata?.has_pbr && !textures.length && format === 'GLB' ? 'PBR 贴图已内嵌，随模型一起下载' : '导出当前模型文件' }}</small></div>
      <div class="viewer-export-actions">
        <label class="viewer-format-control"><span>格式转换</span><ElSelect v-model="requestedFormat" aria-label="模型格式转换" size="small" :disabled="!completed || busy" @change="convertModel"><ElOption label="GLB" value="glb" /><ElOption label="OBJ" value="obj" /><ElOption label="FBX" value="fbx" /><ElOption label="STL" value="stl" /></ElSelect></label>
        <ElButton v-if="textures.length" class="viewer-secondary" @click="textures.forEach(downloadTexture)"><Download :size="16" />下载独立贴图</ElButton>
        <ElButton class="viewer-primary" :disabled="!completed || busy" @click="downloadModel"><Download :size="16" />下载模型 · {{ format }}</ElButton>
      </div>
    </footer>
  </main>
</template>

<style scoped>
.viewer-stage{background:#2b3036}.viewer-side,.viewer-bottom,.viewer-footer{background:#23374b;backdrop-filter:none}.stage-top-tools{width:max-content;max-width:calc(100% - 24px);flex-wrap:wrap;justify-content:center;background:#202a35;backdrop-filter:none;box-shadow:0 4px 14px #10182040}.stage-top-tools :deep(.el-select__wrapper){background:#36414b;box-shadow:0 0 0 1px #65727f inset}.stage-top-tools :deep(.el-select__selected-item),.stage-top-tools :deep(.el-select__caret){color:#edf4ff}.viewer-transform-settings{display:flex;align-items:center;gap:18px;flex-wrap:wrap;padding:14px 0}.viewer-transform-settings label{display:flex;align-items:center;gap:10px;color:#d4e0ec;font-size:12px}.viewer-transform-settings .el-select{width:140px}.viewer-transform-settings p{margin:0;font-size:12px;color:#b9cadb}.stage-actions{background:#202a35;backdrop-filter:none}.viewer-stage :deep(.canvas-selection-status){top:72px}.viewer-stage :deep(.canvas-interaction-hint){background:#202a35}.viewer-stage :deep(canvas){cursor:grab}.viewer-stage :deep(canvas:active){cursor:grabbing}
.viewer-action-head{height:auto;min-height:68px;padding:14px 22px;gap:20px;flex-wrap:wrap;background:#23374b;border-bottom:1px solid #a9c7e826}
.viewer-heading{display:flex;align-items:center;gap:20px;min-width:0}
.viewer-identity{gap:8px;white-space:nowrap}.viewer-identity small{display:inline-flex}
.viewer-action-head .viewer-head-end{gap:10px;flex-wrap:wrap}.viewer-status{margin-right:6px;white-space:nowrap;font-size:12px}
.viewer-flow-button{gap:6px;min-height:36px;white-space:nowrap;flex-shrink:0;text-decoration:none}
.viewer-back-link{background:transparent;border-color:transparent;padding-left:0}
.viewer-flow-next{background:#b4cfe9;color:#21384f;border-color:#b4cfe9;font-weight:600}
.viewer-more-button{color:#d4e0ec;background:transparent}
.viewer-flow-button:focus-visible,.stage-actions .viewer-icon:focus-visible{outline:2px solid #b4cfe9;outline-offset:3px}
.info-scroll{justify-content:flex-start}
.stage-actions{gap:6px;padding:7px 9px;border-radius:12px}
.stage-actions .viewer-icon{width:36px;height:36px;border-radius:7px}
.stage-actions .viewer-icon:last-child{border-left:1px solid #b4cfe930;border-radius:0 7px 7px 0;margin-left:2px;padding-left:9px;width:44px}
.viewer-export-bar{min-height:88px;padding:18px 22px;gap:20px;flex-wrap:wrap}
.viewer-export-bar .viewer-export-info{display:flex;flex-direction:column;align-items:flex-start;gap:5px}
.viewer-export-info strong{font-size:13px;color:#e2ebf5;font-weight:600}.viewer-export-info strong span{font-weight:400;color:#b9cadb}
.viewer-export-info small{font-size:12px;color:#b9cadb}
.viewer-export-bar .viewer-export-actions{display:flex;align-items:center;gap:12px;margin-left:auto;flex-wrap:wrap}
.viewer-format-control{display:flex;align-items:center;gap:10px;padding-right:16px;border-right:1px solid #b4cfe930}
.viewer-format-control>span{font-size:12px;color:#b9cadb;white-space:nowrap}
.viewer-export-bar .el-select{width:96px}
.viewer-format-control :deep(.el-select__wrapper){min-height:38px;background:#2c435a;box-shadow:0 0 0 1px #718ba5 inset}
.viewer-format-control :deep(.el-select__selected-item),.viewer-format-control :deep(.el-select__caret){color:#e2ebf5}
.viewer-export-bar .el-button{height:40px;margin:0;gap:6px;padding:0 18px}
.viewer-export-bar .el-button :deep(>span){gap:6px}
@media(max-width:1050px){.viewer-action-head{gap:12px}.viewer-action-head .viewer-status{display:none}}
@media(max-width:720px){
  .viewer-action-head{padding:12px 14px;gap:12px}
  .viewer-heading{gap:12px;width:100%;justify-content:space-between}
  .viewer-identity{font-size:12px}.viewer-identity>svg{display:none}
  .viewer-action-head .viewer-head-end{width:100%;margin:0;justify-content:flex-end;gap:8px}
  .viewer-flow-button{font-size:12px;padding:0 10px}.viewer-back-link{padding-left:0;margin-right:auto}
  .viewer-stage :deep(.canvas-selection-status){top:64px}
  .viewer-export-bar{align-items:stretch;padding:16px 14px;gap:14px}
  .viewer-export-bar .viewer-export-info{width:100%;align-items:flex-start}
  .viewer-export-bar .viewer-export-actions{width:100%;margin:0;justify-content:flex-end;gap:10px}
  .viewer-format-control{margin-right:auto;padding-right:0;border:0;gap:8px}
  .viewer-export-bar .el-button{padding:0 14px;font-size:12px}
  .viewer-export-bar .viewer-secondary{display:inline-flex}
}
@media(max-width:420px){.viewer-export-bar .viewer-export-actions:has(.viewer-secondary) .viewer-format-control{width:100%}}
</style>
