<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ThreePreview, { type DisplayMode } from './ThreePreview.vue'
import api from '../services/api'
const props = withDefaults(defineProps<{ taskId:number; format:string; available:boolean; displayMode?:DisplayMode; autoRotate?:boolean }>(), { displayMode:'material', autoRotate:false })
const host = ref<HTMLElement>(), url = ref(''), error = ref(''), viewer = ref<InstanceType<typeof ThreePreview>>()
let observer:IntersectionObserver|undefined, version = 0, visible = false
async function load() {
  const request = ++version
  if (url.value) URL.revokeObjectURL(url.value)
  url.value = ''; error.value = ''
  if (!props.available) { error.value = '此历史记录没有可读取的模型文件'; return }
  if (!['glb','gltf'].includes(props.format)) { error.value = '此格式请下载后查看'; return }
  try {
    const { data } = await api.get(`/studio/assets/${props.taskId}/file`, { responseType:'blob', timeout:60000 })
    if (request !== version) return
    url.value = URL.createObjectURL(data)
  } catch { if (request === version) error.value = '模型文件暂时无法加载，可重试或查看任务详情' }
}
onMounted(() => { observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) { visible = true; observer?.disconnect(); void load() } }); if (host.value) observer.observe(host.value) })
watch(() => props.taskId, () => { if (visible) void load() })
onBeforeUnmount(() => { version++; observer?.disconnect(); if (url.value) URL.revokeObjectURL(url.value) })
defineExpose({ reset:() => viewer.value?.resetCamera() })
</script>
<template><div ref="host" class="asset-preview"><ThreePreview v-if="url && !error" ref="viewer" :model-url="url" :model-format="format" :display-mode="displayMode" :auto-rotate="autoRotate" @error="error = $event" /><div v-else class="asset-preview-message"><template v-if="error"><span>{{ error }}</span><button v-if="available" @click="load">重新加载</button></template><span v-else>正在载入模型…</span></div></div></template>
<style scoped>.asset-preview{height:100%;width:100%;min-height:220px;position:relative;background:#14253e}.asset-preview :deep(.canvas-selection-status),.asset-preview :deep(.canvas-interaction-hint),.asset-preview :deep(.canvas-caption){display:none}.asset-preview-message{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column;padding:24px;text-align:center;color:#9fb6d0;font-size:12px;gap:12px}.asset-preview-message button{background:#2b4563;color:#dcecff;border-radius:5px;padding:7px 12px;font-size:11px}</style>
