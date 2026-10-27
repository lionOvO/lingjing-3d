<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ImagePlus, ArrowLeft } from 'lucide-vue-next'
import ImagePreparation from '../components/ImagePreparation.vue'
import { useImageDraft } from '../stores/imageDraft'
const file=ref<File|null>(null), error=ref(''), draft=useImageDraft(),router=useRouter()
function choose(event:Event) { const value=(event.target as HTMLInputElement).files?.[0];error.value=''; if(!value)return;if(!['image/png','image/jpeg','image/webp'].includes(value.type)||value.size>20*1024*1024){error.value='请选择 20MB 以内的 PNG、JPG 或 WEBP 图片';return};file.value=value }
function apply(value:File) { draft.image=value;void router.push('/generate') }
onMounted(()=>{const image=draft.take();if(image)file.value=image})
</script>
<template><main class="page tool-page"><header class="library-heading"><div><p class="eyebrow">生成前的准备</p><h1>参考图处理</h1><p>保留人物原貌，检查轮廓与细节，整理更适合重建的构图。</p></div><RouterLink class="library-button quiet" to="/generate"><ArrowLeft :size="15" />返回生成</RouterLink></header><div class="tool-card"><div class="library-toolbar"><label class="library-button"><ImagePlus :size="16" />{{file?'更换原图':'选择参考图片'}}<input class="tool-file" type="file" accept="image/png,image/jpeg,image/webp" @change="choose" /></label><RouterLink class="text-link" to="/guide#reference">什么样的图片更合适？ →</RouterLink><RouterLink class="text-link" to="/guide#cases">从我的生成案例选择图片 →</RouterLink></div><p v-if="error" class="library-error" role="alert">{{error}}</p><ImagePreparation v-if="file" :file="file" @apply="apply" /><div v-else class="prepare-empty"><ImagePlus :size="38" /><h2>先给灵感一个清楚的轮廓</h2><p>选择本地图片后，即可查看原图与处理结果。<br />应用后会带入生成页，仍需你确认参数并开始生成。</p></div></div></main></template>
