<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Box, Download, GitCompareArrows, Pencil, Plus, RefreshCw, Trash2, Undo2, CheckSquare } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import AssetPreview from '../components/AssetPreview.vue'
import { downloadAsset, metric, useAssets, type Asset } from '../services/studio'
import api from '../services/api'
import { formatApiDate } from '../utils/date'
const showTrash=ref(false),managing=ref(false),deleting=ref(false),deleteSelection=ref<number[]>([])
const router = useRouter(), { assets, loading, error, load } = useAssets({deleted:showTrash})
const search = ref(''), type = ref('all'), format = ref('all'), page = ref(1), selected = ref<number[]>([])
const editing = ref<Asset|null>(null), name = ref(''), tags = ref(''), saving = ref(false)
const filtered = computed(() => assets.value.filter(asset => (type.value === 'all' || asset.project_type === type.value) && (format.value === 'all' || asset.format === format.value) && `${asset.name} ${asset.project_name} ${asset.id} ${asset.tags.join(' ')}`.toLowerCase().includes(search.value.toLowerCase().trim())))
const formats = computed(() => [...new Set(assets.value.map(asset => asset.format))])
const pages = computed(() => Math.max(1,Math.ceil(filtered.value.length/6))), visible = computed(() => filtered.value.slice((page.value-1)*6,page.value*6))
watch([search,type,format], () => { page.value = 1 })
watch(pages,value=>{page.value=Math.min(page.value,value)})
watch(assets,value=>{const ids=new Set(value.map(item=>item.id));selected.value=selected.value.filter(id=>ids.has(id));deleteSelection.value=deleteSelection.value.filter(id=>ids.has(id))})
watch(showTrash,()=>{page.value=1;selected.value=[];deleteSelection.value=[];managing.value=false;void load()})
function toggleManagement(){managing.value=!managing.value;deleteSelection.value=[];selected.value=[]}
function selectPage(){deleteSelection.value=[...new Set([...deleteSelection.value,...visible.value.map(asset=>asset.id)])]}
async function remove(ids:number[]){
 if(deleting.value||!ids.length)return
 try{await ElMessageBox.confirm(`将这 ${ids.length} 个模型移入回收站？可以随时恢复，原模型文件、项目和生成记录会保留。`,'删除模型',{type:'warning',confirmButtonText:'移入回收站',cancelButtonText:'取消'})}catch{return}
 deleting.value=true
 const results=await Promise.allSettled(ids.map(id=>api.delete(`/studio/assets/${id}`)))
 const failed=ids.filter((_,i)=>results[i].status==='rejected')
 await load();deleteSelection.value=failed;deleting.value=false
 if(failed.length)ElMessage.error(`${ids.length-failed.length} 个已移入回收站，${failed.length} 个未完成，请重试。`)
 else{ElMessage.success(`已将 ${ids.length} 个模型移入回收站`);managing.value=false}
}
async function restore(asset:Asset){
 if(deleting.value)return
 deleting.value=true
 try{await api.post(`/studio/assets/${asset.id}/restore`);await load();ElMessage.success('模型已恢复到资产列表')}catch(cause:any){ElMessage.error(cause.message)}finally{deleting.value=false}
}
function edit(asset:Asset) { editing.value = asset; name.value = asset.name; tags.value = asset.tags.join('，') }
async function save() {
  if (!editing.value) return
  saving.value = true
  try { await api.put(`/studio/assets/${editing.value.id}`, { name:name.value.trim(), tags:tags.value.split(/[,，]/).map(value => value.trim()).filter(Boolean) }); editing.value = null; await load(); ElMessage.success('模型信息已保存') }
  catch (cause:any) { ElMessage.error(cause.message) }
  finally { saving.value = false }
}
async function download(asset:Asset) { try { await downloadAsset(asset) } catch (cause:any) { ElMessage.error(cause.message) } }
function compare() { void router.push({ name:'compare', query:{ a:selected.value[0], b:selected.value[1] } }) }
onMounted(load)
</script>
<template>
  <main class="page library-page">
    <header class="library-heading"><div><p class="eyebrow">作品与交付</p><h1>模型资产</h1><p>管理已完成的模型，查看材质与结构，并复用生成参数。</p></div><RouterLink class="library-button primary-action" to="/generate"><Plus :size="16" />生成新模型</RouterLink></header>
    <div class="asset-library-tabs" role="group" aria-label="资产与回收站"><button :aria-pressed="!showTrash" :disabled="loading||deleting" @click="showTrash=false">模型资产</button><button :aria-pressed="showTrash" :disabled="loading||deleting" @click="showTrash=true"><Trash2 :size="15"/>回收站</button></div>
    <div class="library-toolbar"><div class="library-actions"><input v-model="search" class="library-input" aria-label="搜索模型名称或标签" placeholder="搜索模型、项目或标签" /><select v-model="type" class="library-select" aria-label="筛选模型类型"><option value="all">全部类型</option><option value="anime_character">动漫角色</option><option value="object_model">物品模型</option></select><select v-model="format" class="library-select" aria-label="筛选模型格式"><option value="all">全部格式</option><option v-for="item in formats" :key="item" :value="item">{{ item.toUpperCase() }}</option></select></div><div class="library-actions"><button class="library-button quiet" :disabled="loading||deleting" @click="load"><RefreshCw :size="14" />刷新</button><button v-if="!showTrash&&!managing" class="library-button" :disabled="selected.length !== 2" @click="compare"><GitCompareArrows :size="15" />对比所选 {{ selected.length }}/2</button><button v-if="!showTrash" class="library-button quiet" :disabled="loading||deleting||!assets.length" :aria-pressed="managing" @click="toggleManagement"><CheckSquare :size="15"/>{{managing?'退出批量删除':'批量删除'}}</button></div></div>
    <div v-if="managing" class="asset-delete-bar" role="group" aria-label="批量删除模型"><strong>已选 {{deleteSelection.length}} 个模型</strong><div><button class="library-button quiet" :disabled="deleting" @click="selectPage">全选本页</button><button class="library-button quiet" :disabled="deleting||!deleteSelection.length" @click="deleteSelection=[]">清空选择</button><button class="library-button asset-danger" :disabled="deleting||!deleteSelection.length" @click="remove([...deleteSelection])"><Trash2 :size="15"/>{{deleting?'正在删除…':'移入回收站'}}</button></div></div>
    <p class="library-note">{{showTrash?`回收站中共 ${filtered.length} 个模型 · 可恢复到资产列表；原文件与生成记录仍保留。`:managing?'勾选要删除的模型，再移入回收站；切换页码可继续选择。':`共 ${filtered.length} 个模型 · 可打开检视、选择两个模型对比，或批量删除。`}}</p>
    <p v-if="error" class="library-error" role="alert">{{ error }}</p>
    <div v-if="loading" class="library-empty" role="status">正在读取你的模型资产…</div>
    <div v-else-if="!filtered.length" class="library-empty"><Box :size="30" /><h2>{{assets.length?'没有匹配的模型':showTrash?'回收站为空':'还没有模型资产'}}</h2><span>{{assets.length?'调整筛选条件，或尝试其他关键词。':showTrash?'移入回收站的模型会显示在这里，可随时恢复。':'完成一次生成后，模型会自动出现在这里。'}}</span><RouterLink v-if="!showTrash&&!assets.length && !error" class="library-button" to="/generate">开始生成</RouterLink></div>
    <div v-else class="library-grid"><article v-for="asset in visible" :key="asset.id" class="asset-card" :class="{ selected:managing?deleteSelection.includes(asset.id):selected.includes(asset.id) }"><div class="asset-card-preview"><AssetPreview :task-id="asset.id" :format="asset.format" :available="asset.preview_available" /></div><div class="asset-card-body"><div class="asset-card-head"><h2>{{ asset.name }}</h2><label v-if="managing" class="library-note asset-delete-select"><input v-model="deleteSelection" type="checkbox" :value="asset.id" :disabled="deleting" :aria-label="`选择删除模型 ${asset.id}`"/>选择</label><label v-else-if="!showTrash" class="library-note"><input v-model="selected" type="checkbox" :value="asset.id" :disabled="selected.length === 2 && !selected.includes(asset.id)" :aria-label="`选择模型 ${asset.id} 进行对比`" />对比</label></div><p>#{{ asset.id }} · {{ asset.format.toUpperCase() }} · {{ metric(asset.metadata.face_count) }} 面<br>{{ formatApiDate(asset.created_at) }}</p><div class="asset-tags"><span>{{ asset.project_type === 'anime_character' ? '动漫角色' : '物品模型' }}</span><span v-for="tag in asset.tags" :key="tag">{{ tag }}</span></div><div v-if="showTrash" class="library-actions"><button class="library-button" :disabled="deleting" @click="restore(asset)"><Undo2 :size="14"/>恢复模型</button></div><div v-else class="library-actions"><RouterLink class="library-button" :to="`/workflow/${asset.id}?step=preview`">打开模型</RouterLink><button class="library-button quiet" :aria-label="`下载模型 ${asset.id}`" @click="download(asset)"><Download :size="14" /></button><button class="library-button quiet" :aria-label="`编辑模型 ${asset.id} 的名称与标签`" @click="edit(asset)"><Pencil :size="14" /></button><RouterLink class="library-button quiet" :to="`/presets?task=${asset.id}`">存为预设</RouterLink><RouterLink v-if="asset.format==='glb' && asset.preview_available" class="library-button quiet" :to="`/repair/${asset.id}`">检查与修复</RouterLink><button class="library-button quiet asset-danger" :disabled="deleting" :aria-label="`删除模型 ${asset.id}`" @click="remove([asset.id])"><Trash2 :size="14"/>删除</button></div><p><RouterLink :to="`/projects/${asset.project_id}`" class="text-link">所属项目：{{ asset.project_name }}</RouterLink></p></div></article></div>
    <div v-if="filtered.length" class="library-pagination"><span>第 {{ page }} / {{ pages }} 页</span><div class="library-actions"><button class="library-button quiet" :disabled="page <= 1" @click="page--">上一页</button><button class="library-button quiet" :disabled="page >= pages" @click="page++">下一页</button></div></div>
    <div v-if="editing" class="library-dialog" @click.self="!saving && (editing = null)" @keydown.esc="!saving && (editing = null)"><section class="library-dialog-card" role="dialog" aria-modal="true" aria-labelledby="asset-edit-title"><h2 id="asset-edit-title">模型名称与标签</h2><form class="library-form" @submit.prevent="save"><label>模型名称<input v-model="name" class="library-input" required maxlength="120" /></label><label>标签<input v-model="tags" class="library-input" placeholder="用逗号分隔，最多 8 个标签" /></label><p class="library-note">只更新资产信息，模型文件和生成参数保持原样。</p><div class="library-actions"><button class="library-button quiet" type="button" :disabled="saving" @click="editing = null">取消</button><button class="library-button primary-action" :disabled="saving || !name.trim()">{{ saving ? '保存中…' : '保存信息' }}</button></div></form></section></div>
  </main>
</template>

<style scoped>
.asset-library-tabs{display:flex;gap:24px;border-bottom:1px solid #b5d2e94d;margin-bottom:24px}.asset-library-tabs button{display:flex;align-items:center;gap:7px;color:#c4d7e8;background:none;border-bottom:2px solid transparent;padding:12px 2px;font-size:14px}.asset-library-tabs button[aria-pressed=true]{color:#edf5fc;border-bottom-color:#b5d2e9}.asset-delete-bar{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:16px 20px;background:#243e57f5;border:1px solid #b5d2e957;border-radius:12px;margin-bottom:16px;color:#edf5fc;font-size:13px}.asset-delete-bar>div{display:flex;gap:12px;flex-wrap:wrap}.asset-danger{color:#ffd0c5;border-color:#e6afa25c}.asset-danger:hover:not(:disabled){background:#bb67512b;border-color:#e6afa2}.asset-delete-select{white-space:nowrap}.asset-card .library-actions{gap:10px;row-gap:12px}.asset-library-tabs button:focus-visible{outline:2px solid #b5d2e9;outline-offset:4px}@media(max-width:700px){.asset-delete-bar{align-items:stretch;flex-direction:column;padding:16px}.asset-delete-bar>div{gap:8px}.asset-card .library-actions .library-button{min-height:36px}.asset-library-tabs{margin-bottom:18px}}
</style>
