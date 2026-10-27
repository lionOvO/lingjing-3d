<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElButton, ElMessage, ElMessageBox, ElProgress, ElSlider, ElTag, ElTooltip } from 'element-plus'
import { AlertTriangle, Box, Check, CloudUpload, Info, Link2, RefreshCw, Rocket, Sparkles, Stars, Trash2, UserRound, X } from 'lucide-vue-next'
import api from '../services/api'
import ImagePreparation from '../components/ImagePreparation.vue'
import { useImageDraft } from '../stores/imageDraft'
const props=withDefaults(defineProps<{preprocess?:boolean}>(),{preprocess:false})
const emit=defineEmits<{ready:[value:boolean]}>()
const originalSafe=ref(false),samplingSeed=ref(109020838)
const confirmedFile=ref<File|null>(null), processing=ref(false), preparationDetails=ref<Record<string,unknown>>({})
const imageDraft = useImageDraft()
function invalidatePreparation(){confirmedFile.value=null}
async function confirmAndGenerate(value:File,details:Record<string,unknown>){
 if(processing.value||busy.value)return
 confirmedFile.value=value;preparationDetails.value=details
 await createGeneration()
}
async function useOriginal(){
 if(!file.value||processing.value||busy.value)return
 const selected=file.value
 if(!originalSafe.value){
  try{await ElMessageBox.confirm('原图包含背景或编辑器界面，直接生成可能把背景、网格或工具栏一起建成模型。若要保留全部原始部件，可以继续；更推荐先修补抠图。','保留原图直接生成？',{confirmButtonText:'接受背景风险，使用原图',cancelButtonText:'返回修补',type:'warning'})}catch{return}
 }
 if(file.value!==selected||processing.value||busy.value)return
 await confirmAndGenerate(selected,{version:4,mode:'original',strategy:'original',background:'original',background_removed:false,
  background_risk_accepted:!originalSafe.value,assessment:{background_kind:originalSafe.value?'simple':'complex'}})
}

import { useAuthStore } from '../stores/auth'
import { useTaskStore } from '../stores/task'
import { recommendedParameters, reusableParameters, type Preset } from '../services/studio'

const ACCEPTED = ['image/png', 'image/jpeg', 'image/webp']; const MAX_SIZE = 20 * 1024 * 1024
const route = useRoute(); const router = useRouter(); const auth = useAuthStore(); const tasks = useTaskStore()
const fileInput = ref<HTMLInputElement | null>(null)
const type = ref<'anime_character' | 'object_model'>((route.query.type as any) === 'object_model' ? 'object_model' : 'anime_character')
const format = ref('glb'); const sourceMode = ref<'file' | 'url'>('file'); const file = ref<File | null>(null); const imageUrl = ref(''); const preview = ref(''); const imageWidth = ref(0); const imageHeight = ref(0); const dragging = ref(false); const error = ref(''); const busy = ref(false); const uploadProgress = ref(0); const uploadedUrl = ref(''); const customFaces = ref(180000); const meshDensity = ref('medium'); const textureResolution = ref('1024'); const generationMode = ref<'fast' | 'balanced' | 'high_quality'>('high_quality'); const pbrEnabled = ref(true); const ragApplied = ref(false)
watch([confirmedFile,processing,busy],()=>emit('ready',!!confirmedFile.value&&!processing.value&&!busy.value),{immediate:true})
let objectUrl = ''
const capabilities = ref<{ available_modes: string[]; pbr_required: boolean; texture_resolutions: string[]; default_seed?:number } | null>(null)
const capabilityError = ref('')
const presetLabel = ref('')
const presetError = ref(false)
async function applyPreset() {
  presetLabel.value = ''
  presetError.value = false
  if (!route.query.preset) return
  try {
    const preset = route.query.preset === 'recommended' ? { name:'Pixal3D · 标准质量', project_type:type.value, parameters:recommendedParameters() } : (await api.get<Preset[]>('/studio/presets')).data.find(item => item.id === Number(route.query.preset))
    if (!preset) throw new Error('预设不存在或已归档，请重新选择')
    const params = reusableParameters(preset.parameters)
    if (!capabilities.value?.available_modes.includes(params.generation_mode) || !capabilities.value.texture_resolutions.includes(params.texture_resolution)) throw new Error('本机当前不支持此预设，请检查生成服务或更换预设')
    type.value = preset.project_type as typeof type.value; generationMode.value = params.generation_mode; textureResolution.value = params.texture_resolution; meshDensity.value = params.mesh_density; pbrEnabled.value = params.pbr_enabled; presetLabel.value = preset.name; samplingSeed.value=params.seed??109020838
  } catch (cause:any) { error.value = cause.message; presetError.value = true }
}
function clearPreset() { error.value = ''; void router.replace({ query:{ ...route.query, preset:undefined } }) }
async function saveCurrentPreset() {
  try {
    const { value } = await ElMessageBox.prompt('保存当前生成参数，下次可从生成预设中应用。', '保存生成预设', { inputPlaceholder:'预设名称', inputValidator:value => Boolean(value?.trim()) && value.trim().length <= 120 || '请输入 1–120 字的名称', confirmButtonText:'保存', cancelButtonText:'取消' })
    await api.post('/studio/presets', { name:value.trim(), project_type:type.value, parameters:{ generation_mode:generationMode.value, texture_resolution:textureResolution.value, mesh_density:meshDensity.value, pbr_enabled:pbrEnabled.value, seed:samplingSeed.value } }); ElMessage.success('已保存到生成预设')
  } catch (cause:any) { if (!['cancel','close'].includes(cause)) ElMessage.error(cause.message) }
}
onMounted(async () => {
  const prepared = imageDraft.take(); if (prepared) setFile(prepared)
  await loadCapabilities()
  await applyPreset()
})
async function loadCapabilities(){
  try { capabilities.value = (await api.get('/generation/capabilities', { timeout: 12000 })).data }
  catch (cause: any) { capabilityError.value = cause.message || '生成服务尚未就绪，请稍后刷新页面' }
  if(capabilities.value)capabilityError.value=''
}
watch(() => route.query.preset, applyPreset)
const isObject = computed(() => type.value === 'object_model'); const existingProjectId = computed(() => { const raw = String(route.query.projectId || ''); return /^\d+$/.test(raw) && Number(raw) > 0 ? Number(raw) : null }); const qualityWarning = computed(() => imageWidth.value > 0 && (imageWidth.value < 768 || imageHeight.value < 768) ? '分辨率较低，可能影响生成质量' : ''); const fileSize = computed(() => file.value ? `${(file.value.size / 1024 / 1024).toFixed(2)} MB` : ''); const fileResolution = computed(() => imageWidth.value ? `${imageWidth.value} × ${imageHeight.value}` : '等待检测'); const faceLabel = computed(() => meshDensity.value === 'custom' ? `${customFaces.value.toLocaleString()} 面` : ({ low: '低面数', medium: '中面数', high: '高面数' } as any)[meshDensity.value])
function clearPreview() { invalidatePreparation(); if (objectUrl) URL.revokeObjectURL(objectUrl); objectUrl = ''; file.value = null; preview.value = ''; imageWidth.value = 0; imageHeight.value = 0; uploadedUrl.value = ''; uploadProgress.value = 0; error.value = '' }
function inspectImage(src: string) { const image = new Image(); image.onload = () => { imageWidth.value = image.naturalWidth; imageHeight.value = image.naturalHeight }; image.onerror = () => { error.value = '图片无法预览，请更换文件或使用可访问的 URL' }; image.src = src }
function setFile(next: File | undefined) { error.value = ''; uploadedUrl.value = ''; if (!next) return; if (!ACCEPTED.includes(next.type)) { error.value = '仅支持 PNG、JPG、JPEG 或 WEBP 图片'; return }; if (next.size > MAX_SIZE) { error.value = '图片不能超过 20MB，请压缩后重试'; return }; clearPreview(); file.value = next; objectUrl = URL.createObjectURL(next); preview.value = objectUrl; inspectImage(objectUrl) }
function choose(event: Event) { setFile((event.target as HTMLInputElement).files?.[0]) }; function openFilePicker() { fileInput.value?.click() }; function drop(event: DragEvent) { dragging.value = false; setFile(event.dataTransfer?.files?.[0]) }; function paste(event: ClipboardEvent) { const pasted = Array.from(event.clipboardData?.files || []).find((item) => ACCEPTED.includes(item.type)); if (pasted) { event.preventDefault(); setFile(pasted) } }; function keyboardChoose(event: KeyboardEvent) { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openFilePicker() } }
function switchSource(mode: 'file' | 'url') { sourceMode.value = mode; uploadedUrl.value = ''; uploadProgress.value = 0; error.value = ''; if (mode === 'file') { imageUrl.value = ''; preview.value = file.value ? preview.value : '' } else { clearPreview() } }
function applyRag() { ragApplied.value = true; setGenerationMode('high_quality'); ElMessage.success('已应用灵境造物推荐参数') }; function setType(next: 'anime_character' | 'object_model') { type.value = next; if (next === 'object_model' && meshDensity.value === 'custom') meshDensity.value = 'medium'; ragApplied.value = false }; function setGenerationMode(mode: 'fast' | 'balanced' | 'high_quality') { generationMode.value = mode; format.value = 'glb'; if (mode === 'fast') { textureResolution.value = '512'; meshDensity.value = 'low'; pbrEnabled.value = false } else if (mode === 'balanced') { textureResolution.value = '1024'; meshDensity.value = 'medium'; pbrEnabled.value = false } else { textureResolution.value = '1024'; meshDensity.value = 'medium'; pbrEnabled.value = true } }; function setTextureResolution(value: string) { if (generationMode.value === 'high_quality' || generationMode.value === 'balanced') textureResolution.value = value }; function setMeshDensity(value: string) { if (['low', 'medium', 'high'].includes(value)) meshDensity.value = value }
async function createGeneration() { if(busy.value)return; if(!Number.isInteger(samplingSeed.value)||samplingSeed.value<0||samplingSeed.value>2147483647){error.value='随机种子须为 0–2147483647 的整数';return}; if(!capabilities.value){busy.value=true;try{await loadCapabilities()}finally{busy.value=false}}; if (presetError.value) return; if (!capabilities.value) { error.value = capabilityError.value || '正在确认生成服务状态，请稍候'; return }; if (!auth.user) { router.push({ name: 'auth', query: { redirect: '/workflow' } }); return }; if (sourceMode.value === 'file' && !file.value) { error.value = '请选择一张图片后再开始生成'; return }; if (sourceMode.value === 'url' && !imageUrl.value.trim()) { error.value = '请输入可访问的图片链接'; return }; busy.value = true; error.value = ''; uploadProgress.value = 0; try { if(!confirmedFile.value || processing.value)throw new Error('请先确认预处理结果');
const originalBody=new FormData();originalBody.append('image',file.value!);const original=(await api.post('/uploads',originalBody)).data;
let source=original.url;
if(confirmedFile.value!==file.value){const body=new FormData();body.append('image',confirmedFile.value);source=(await api.post('/uploads',body)).data.url}
 const project = existingProjectId.value ? (await api.patch(`/projects/${existingProjectId.value}`, { source_image_url: source })).data : (await api.post('/projects', { user_id: auth.user.id, name: `${isObject.value ? '物品' : '角色'}模型 · ${new Date().toLocaleDateString('zh-CN')}`, description: '由灵境造物工作流创建', project_type: type.value, source_image_url: source })).data; const generationParams = { theme: 'moonlit_sakura', input_preprocessed:true, vision_analysis:false, image_preparation:{version:2,...preparationDetails.value}, _original_source_object_name:original.object_name, texture_resolution: textureResolution.value, mesh_density: meshDensity.value, custom_faces: meshDensity.value === 'custom' ? customFaces.value : undefined, generation_mode: generationMode.value, pbr_enabled: pbrEnabled.value, seed:samplingSeed.value }; const task = (await api.post('/tasks', { project_id: project.id, task_type: type.value, source_image_url: source, output_format: format.value, generation_params: generationParams })).data; tasks.setTask(task); tasks.startProgress(task.id); ElMessage.success(existingProjectId.value ? '图片已上传，项目已创建新的生成任务' : '图片已上传，任务已进入生成队列'); await router.replace({ name: 'workflow', params: { taskId: String(task.id) }, query: { step: 'task' } }) } catch (exception: any) { error.value = exception?.message || '上传或任务提交失败，请稍后重试' } finally { busy.value = false } }
async function beginPreparation(){
 if(busy.value)return;
 if(presetError.value){error.value='请确认生成参数';return}
 if(!auth.user){void router.push('/auth?redirect=/generate');return}
 error.value='';busy.value=true;
 try{
  if(sourceMode.value==='url'){
   const response=await api.post('/studio/images/import-url',{url:imageUrl.value.trim()},{responseType:'blob',timeout:90000});
   setFile(new File([response.data],'reference.png',{type:response.data.type||'image/png'}));sourceMode.value='file';
  }
  if(!file.value)throw new Error('请先选择参考图');
  await router.push({name:'generate',query:{...route.query,step:'standardize'}})
 }catch(e:any){error.value=e.response?.data instanceof Blob?'图片链接无法读取，请下载后本地上传':e.message}finally{busy.value=false}
}
function submit(){return props.preprocess?createGeneration():beginPreparation()}
defineExpose({next:submit})
onBeforeUnmount(() => { if (objectUrl) URL.revokeObjectURL(objectUrl);invalidatePreparation() })
</script>

<template>
  <main class="page generate-page" @paste="paste"><div v-show="!preprocess">
    <div class="generate-breadcrumb"><span>开始生成</span><b>/</b><strong>{{ isObject ? '物品建模' : '动漫角色' }}</strong></div>
    <div class="library-toolbar"><span class="library-note">{{ presetLabel ? `参数载入自：${presetLabel}` : '上传参考图，并配置这次生成的参数。' }}</span><div class="library-actions"><button v-if="presetError" class="library-button quiet" @click="clearPreset">清除无效预设</button><RouterLink class="library-button quiet" to="/presets">选择生成预设</RouterLink><button class="library-button quiet" :disabled="!capabilities || busy" @click="saveCurrentPreset">保存当前参数</button></div></div>
    <div class="page-title generate-title"><p class="eyebrow"><Sparkles :size="15" />CREATE A MODEL</p><h1>{{ isObject ? '让物品在光域中重生' : '让角色在灵境中成形' }}</h1><p>先整理人物范围、构图与图像细节，再确认适合重建的生成输入。</p></div>
    <div class="generate-layout">
      <section class="generate-source glass-card">
        <div class="source-head"><div><p class="eyebrow">01 · SOURCE IMAGE</p><h2>选择一张参考图</h2></div><ElTag effect="plain">{{ sourceMode === 'file' ? '本地上传' : '图片链接' }}</ElTag></div>
        <div class="mode-tabs"><button :class="{ active: sourceMode === 'file' }" @click="switchSource('file')"><CloudUpload :size="15" />本地图片</button><button :class="{ active: sourceMode === 'url' }" @click="switchSource('url')"><Link2 :size="15" />图片链接</button></div>
        <div v-if="sourceMode === 'file'" class="source-dropzone" :class="{ dragging, 'has-preview': preview }" tabindex="0" role="button" aria-label="上传参考图片" @click="openFilePicker" @keydown="keyboardChoose" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="drop"><input ref="fileInput" type="file" accept="image/png,image/jpeg,image/webp" @click.stop @change="choose" /><template v-if="preview"><img :src="preview" alt="参考图片预览" /><div class="preview-overlay"><span>{{ fileResolution }} · {{ fileSize }}</span><ElTag v-if="uploadedUrl" type="success" effect="dark"><Check :size="13" />已上传</ElTag></div></template><template v-else><CloudUpload :size="48" /><strong>拖拽图片到此处</strong><span>或 <em>点击选择</em> / <em>Ctrl+V 粘贴</em></span><small>支持 PNG / JPG / WEBP · 单文件最大 20MB</small></template></div>
        <div v-else class="url-source"><label>图片 URL<input v-model="imageUrl" type="url" placeholder="https://example.com/character.png" @input="preview = imageUrl" /></label><div v-if="imageUrl" class="url-preview"><img :src="imageUrl" alt="链接图片预览" /><span>链接预览</span></div><p>链接需要公开可访问，服务端会在上传时校验格式。</p></div>
        <div v-if="preview && sourceMode === 'file'" class="quality-row"><span v-if="qualityWarning" class="quality warning"><AlertTriangle :size="15" />{{ qualityWarning }}</span><span v-else class="quality"><Check :size="15" />图片分辨率符合推荐值</span><div class="preview-actions"><button class="remove-action" @click="clearPreview"><Trash2 :size="14" />删除</button><label class="replace-action"><RefreshCw :size="14" />更换<input type="file" accept="image/png,image/jpeg,image/webp" @change="choose" /></label></div></div>
        <div v-if="busy" class="upload-progress"><div><span>{{ uploadedUrl ? '上传完成，正在创建任务…' : '正在上传图片…' }}</span><strong>{{ uploadProgress }}%</strong></div><ElProgress :percentage="uploadProgress" :show-text="false" color="#a9c7e8" /></div>
        <p v-if="file" class="tool-hint">下一步可自动抠图、精细修补并确认生成输入。<RouterLink class="text-link" to="/guide#reference">参考图准备指南 →</RouterLink></p><div class="sample-strip"><button v-for="sample in (isObject ? ['电子产品','家具','手办'] : ['日式萌系','幻想少女','机甲角色'])" :key="sample" type="button" @click="router.push('/guide#cases')"><span class="sample-orb"><Sparkles :size="17" /></span><small>{{ sample }}</small></button></div>
      </section>
      <section class="generate-settings glass-card">
        <div class="source-head"><div><p class="eyebrow">02 · PARAMETERS</p><h2>生成参数配置</h2></div><ElTooltip content="所选纹理分辨率和目标面数会提交给本机工作流" placement="top"><Info :size="17" /></ElTooltip></div>
        <p v-if="capabilityError" role="alert">{{ capabilityError }}。可以先准备图片，开始生成前需恢复服务。<button class="text-link" @click="loadCapabilities">重新检查服务</button></p><p v-else-if="!capabilities" role="status">正在检查本机生成服务…</p><p v-if="capabilities" class="mode-hint">下一步先处理参考图，确认后才会创建生成任务。</p>
        <div class="type-switch"><button :class="{ selected: type === 'anime_character' }" @click="setType('anime_character')"><UserRound :size="17" />动漫角色</button><button :class="{ selected: type === 'object_model' }" @click="setType('object_model')"><Box :size="17" />物品建模</button></div>
        <div class="parameter-grid"><fieldset><legend>输出格式</legend><div class="choice-row"><button class="selected" type="button">GLB</button></div><small class="mode-hint">本机 Pixal3D 工作流输出带内嵌纹理的 GLB。</small></fieldset><fieldset><legend>纹理分辨率</legend><div class="choice-row"><button v-for="item in (capabilities?.texture_resolutions || ['1024'])" :key="item" :class="{ selected: textureResolution === item, risky: item === '2048' && generationMode === 'high_quality' }" :disabled="generationMode === 'fast' && item !== '512'" type="button" @click="setTextureResolution(item)">{{ item }} px</button></div><small class="mode-hint">{{ generationMode === 'high_quality' ? (textureResolution === '2048' ? '实验值：纹理阶段可能超过 6GB 显存' : '推荐值：已验证的 1024px 配置') : '由当前档位控制' }}</small></fieldset><fieldset><legend>{{ isObject ? '模型复杂度' : '面数控制' }}</legend><div class="choice-row"><button v-for="item in [{v:'low',l:'低'},{v:'medium',l:'中'},{v:'high',l:'高'}]" :key="item.v" :class="{ selected: meshDensity === item.v }" type="button" @click="setMeshDensity(item.v)">{{ item.l }}</button></div><small class="mode-hint">低/中/高目标上限约为 30万/50万/70万面，实际面数由模型决定；推荐中面数。</small></fieldset><fieldset><legend>生成模式</legend><div class="choice-row"><button v-for="item in [{v:'fast',l:'快速'},{v:'balanced',l:'平衡'},{v:'high_quality',l:'高质量'}]" :key="item.v" :class="{ selected: generationMode === item.v }" :disabled="!capabilities?.available_modes.includes(item.v)" :title="capabilities?.available_modes.includes(item.v) ? '' : '当前运行器未接入该模式'" @click="setGenerationMode(item.v as 'fast' | 'balanced' | 'high_quality')">{{ item.l }}</button></div><small class="mode-hint">{{ generationMode === 'fast' ? '本地 TripoSR · 512px：快速查看轮廓' : generationMode === 'balanced' ? '本地 TripoSR · 1024px：细节与速度平衡' : '本机 ComfyUI · Pixal3D；快速/平衡暂未接入' }}</small></fieldset></div>
        <label class="sampling-seed-field">随机种子（用于复现）<input v-model.number="samplingSeed" class="library-input" type="number" min="0" max="2147483647" step="1" /></label><label class="pbr-toggle"><span><strong>PBR 材质</strong><small>当前高质量工作流固定生成基础色与金属度/粗糙度；不保证独立法线贴图</small></span><input v-model="pbrEnabled" type="checkbox" :disabled="generationMode === 'high_quality'" /><i aria-hidden="true"></i></label>
        <div v-if="isObject" class="print-options"><strong>3D 打印优化</strong><small>当前工作流未接入悬空和壁厚检查。打印前请在切片软件中检查与修复。</small></div>
        <div class="rag-recommendation"><div class="rag-accent"></div><div class="rag-content"><div class="rag-head"><Stars :size="19" /><strong>本机已验证参数</strong><ElTag effect="plain">Pixal3D · 1024</ElTag></div><ul><li>1024px 纹理 + 中面数，对应已验证工作流</li><li>PBR 材质开启；2048px 仅建议在显存充足时尝试</li></ul><ElButton text class="rag-apply" :class="{ applied: ragApplied }" @click="applyRag">{{ ragApplied ? '已应用推荐参数' : '应用推荐参数' }} <Check v-if="ragApplied" :size="15" /></ElButton></div></div>
        <div class="submit-zone"><ElButton class="generate-submit" :disabled="busy || presetError" @click="submit"><Rocket :size="19" />{{ busy ? '正在准备图片…' : '下一步：预处理参考图' }}</ElButton><p>本机完整流程曾用时约 22 分钟，耗时随图片与机器负载变化；生成期间请保持 ComfyUI 运行。</p><p v-if="error" class="form-error"><X :size="14" />{{ error }}</p></div>
      </section>
    </div>
  </div><section v-if="preprocess" class="tool-page preprocessing-stage"><header class="library-heading"><div><p class="eyebrow">确认输入，再开始生成</p><h1>参考图预处理</h1><p>保留主体原貌，检查部件与轮廓，确认输入后再交给 Pixal3D。</p></div><span class="tool-badge">尚未创建生成任务</span></header><template v-if="file"><fieldset :disabled="busy" class="tool-card preprocess-editor"><ImagePreparation :file="file" allow-original :submitting="busy" :submission-error="error" apply-label="确认图片并开始生成 3D" @apply="confirmAndGenerate" @original="useOriginal" @change="invalidatePreparation" @busy="processing=$event" @original-safe="originalSafe=$event" /></fieldset></template><div v-else class="tool-card prepare-empty"><p>当前没有待处理图片，刷新页面后需重新选择原图。</p><RouterLink class="library-button" to="/generate">返回选择图片</RouterLink></div></section></main>
</template>
