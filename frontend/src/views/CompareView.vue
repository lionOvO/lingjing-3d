<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeftRight, RotateCcw } from 'lucide-vue-next'
import AssetPreview from '../components/AssetPreview.vue'
import { densityLabel, metric, useAssets } from '../services/studio'
import type { DisplayMode } from '../components/ThreePreview.vue'
const route = useRoute(), router = useRouter(), { assets, loading, error, load } = useAssets()
const left = ref(Number(route.query.a)||0), right = ref(Number(route.query.b)||0), mode = ref<DisplayMode>('material')
const leftViewer = ref<InstanceType<typeof AssetPreview>>(), rightViewer = ref<InstanceType<typeof AssetPreview>>()
const a = computed(() => assets.value.find(asset => asset.id === left.value)), b = computed(() => assets.value.find(asset => asset.id === right.value))
const project = ref(String(route.query.project || 'all')), choices = computed(() => assets.value.filter(asset => project.value === 'all' || asset.project_id === Number(project.value)))
const projects = computed(() => Array.from(new Map(assets.value.map(asset => [asset.project_id,asset.project_name])).entries()))
const rows = computed(() => [
  ['任务编号',a.value ? `#${a.value.id}` : '—',b.value ? `#${b.value.id}` : '—'],
  ['所属项目',a.value?.project_name || '—',b.value?.project_name || '—'],
  ['输出格式',a.value?.format.toUpperCase() || '—',b.value?.format.toUpperCase() || '—'],
  ['顶点数',metric(a.value?.metadata.vertex_count),metric(b.value?.metadata.vertex_count)],
  ['实际面数',metric(a.value?.metadata.face_count),metric(b.value?.metadata.face_count)],
  ['文件大小',a.value?.metadata.file_size_mb ? `${a.value.metadata.file_size_mb.toFixed(2)} MB` : '未记录',b.value?.metadata.file_size_mb ? `${b.value.metadata.file_size_mb.toFixed(2)} MB` : '未记录'],
  ['请求纹理分辨率',a.value?.parameters.texture_resolution ? `${a.value.parameters.texture_resolution}px` : '未记录',b.value?.parameters.texture_resolution ? `${b.value.parameters.texture_resolution}px` : '未记录'],
  ['记录的纹理尺寸',a.value?.metadata.texture_resolution || '未记录',b.value?.metadata.texture_resolution || '未记录'],
  ['面数预设',densityLabel(a.value?.parameters.mesh_density),densityLabel(b.value?.parameters.mesh_density)],
  ['随机种子',String(a.value?.parameters.seed ?? '未记录'),String(b.value?.parameters.seed ?? '未记录')],
  ['实际生成方式',a.value?.parameters.provider || '未记录',b.value?.parameters.provider || '未记录'],
  ['结构检查通过比例',typeof a.value?.quality_score === 'number' ? `${Math.round(a.value.quality_score*100)}%` : '未记录',typeof b.value?.quality_score === 'number' ? `${Math.round(b.value.quality_score*100)}%` : '未记录'],
])
function syncSelection() {
  if (left.value === right.value && left.value) right.value = choices.value.find(asset => asset.id !== left.value)?.id || 0
  void router.replace({ name:'compare', query:{ ...(project.value !== 'all' ? { project:project.value } : {}), ...(left.value ? { a:left.value } : {}), ...(right.value ? { b:right.value } : {}) } })
}
watch(project, () => { left.value = choices.value[0]?.id || 0; right.value = choices.value[1]?.id || 0; syncSelection() })
onMounted(async () => { await load(); if (!a.value) left.value = choices.value[0]?.id || 0; if (!b.value || left.value === right.value) right.value = choices.value.find(asset => asset.id !== left.value)?.id || 0; syncSelection() })
</script>
<template>
  <main class="page library-page"><header class="library-heading"><div><p class="eyebrow">结果评估</p><h1>模型对比</h1><p>并排检查纹理和轮廓，比较实际生成参数与模型数据。</p></div><RouterLink class="library-button quiet" to="/library">返回模型资产</RouterLink></header>
    <p v-if="error" class="library-error" role="alert">{{ error }}</p><div v-if="loading" class="library-empty">正在读取可对比的模型…</div>
    <template v-else-if="assets.length"><div class="library-toolbar"><div class="library-actions"><select v-model="project" class="library-select" aria-label="按项目选择版本"><option value="all">全部项目</option><option v-for="[id,name] in projects" :key="id" :value="String(id)">{{ name }} · #{{ id }}</option></select><select v-model="mode" class="library-select" aria-label="对比显示方式"><option value="material">材质对比</option><option value="solid">轮廓对比</option><option value="wireframe">线框对比</option></select></div><div class="library-actions"><button class="library-button quiet" :disabled="!a || !b" @click="[left,right] = [right,left]; syncSelection()"><ArrowLeftRight :size="14" />交换位置</button><button class="library-button quiet" @click="leftViewer?.reset(); rightViewer?.reset()"><RotateCcw :size="14" />重置视角</button></div></div>
      <p class="library-note">{{ a && b ? (a.project_id === b.project_id ? '正在对比同一项目的两个生成版本。' : '当前为不同项目的模型，仅作对照查看，不代表同一参考图的版本。') : '此项目暂时只有一个完成模型。继续在同一项目生成后，即可比较不同版本。' }} 两侧视角可分别拖动，显示方式统一切换。</p>
      <div class="compare-slots"><section class="compare-slot"><div class="compare-slot-head"><label for="compare-left">A</label><select id="compare-left" v-model="left" class="library-select" @change="syncSelection"><option :value="0">选择模型</option><option v-for="asset in choices" :key="asset.id" :value="asset.id">{{ asset.name }}</option></select></div><div class="compare-canvas"><AssetPreview v-if="a" ref="leftViewer" :task-id="a.id" :format="a.format" :available="a.preview_available" :display-mode="mode" /><div v-else class="library-empty">选择左侧模型</div></div><div class="compare-caption"><RouterLink v-if="a" class="text-link" :to="`/workflow/${a.id}?step=preview`">打开 A 的完整预览</RouterLink></div></section><section class="compare-slot"><div class="compare-slot-head"><label for="compare-right">B</label><select id="compare-right" v-model="right" class="library-select" @change="syncSelection"><option :value="0">选择模型</option><option v-for="asset in choices" :key="asset.id" :value="asset.id" :disabled="asset.id === left">{{ asset.name }}</option></select></div><div class="compare-canvas"><AssetPreview v-if="b" ref="rightViewer" :task-id="b.id" :format="b.format" :available="b.preview_available" :display-mode="mode" /><div v-else class="library-empty">选择另一个完成模型</div></div><div class="compare-caption"><RouterLink v-if="b" class="text-link" :to="`/workflow/${b.id}?step=preview`">打开 B 的完整预览</RouterLink></div></section></div>
      <div class="comparison-table-wrap"><table class="comparison-table"><thead><tr><th>对比项</th><th>模型 A</th><th>模型 B</th></tr></thead><tbody><tr v-for="row in rows" :key="row[0]"><th>{{ row[0] }}</th><td :class="{ different:row[1] !== row[2] }">{{ row[1] }}</td><td :class="{ different:row[1] !== row[2] }">{{ row[2] }}</td></tr></tbody></table></div><p class="library-note">结构检查通过比例不代表外观相似度；未记录的历史参数不会推算补齐。</p>
    </template><div v-else class="library-empty"><h2>还没有可对比的模型</h2><RouterLink class="library-button" to="/generate">开始生成</RouterLink></div>
  </main>
</template>
