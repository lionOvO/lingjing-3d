<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {useTaskStore} from '../stores/task'
import {useImageDraft} from '../stores/imageDraft'
import api from '../services/api'
const route=useRoute(),router=useRouter(),tasks=useTaskStore(),draft=useImageDraft()
const taskId=computed(()=>String(route.params.taskId||tasks.current?.id||'')),params=computed(()=>tasks.current?.generation_params||{}),details=computed(()=>params.value.image_preparation as Record<string,any>|undefined)
const original=ref(''),input=ref(''),kind=ref(''),error=ref(''),loading=ref(false),inputBlob=ref<Blob|null>(null),originalBlob=ref<Blob|null>(null)
let request=0
function clear(){for(const value of [original.value,input.value])if(value)URL.revokeObjectURL(value);original.value='';input.value='';inputBlob.value=null;originalBlob.value=null}
async function load(){const current=++request;clear();error.value='';loading.value=true;try{
 await tasks.loadDetail(taskId.value)
 const results=await Promise.allSettled([api.get(`/studio/tasks/${taskId.value}/input`,{responseType:'blob'}),api.get(`/studio/tasks/${taskId.value}/input`,{responseType:'blob',params:{original:true}})])
 if(current!==request)return
 const result=results[0];if(result.status==='rejected')throw new Error('此任务的输入图片暂时不可用')
 inputBlob.value=result.value.data;input.value=URL.createObjectURL(result.value.data);kind.value=result.value.headers['x-input-kind']||'snapshot'
 if(results[1].status==='fulfilled'){originalBlob.value=results[1].value.data;original.value=URL.createObjectURL(results[1].value.data)}
}catch(e:any){if(current===request)error.value=e.message}finally{if(current===request)loading.value=false}}
function prepareAgain(useOriginal=false){const source=useOriginal?originalBlob.value:inputBlob.value;if(!source)return;draft.image=new File([source],'reference.png',{type:source.type});void router.push('/generate')}
onMounted(load);watch(taskId,load);onUnmounted(()=>{request++;clear()})
</script>
<template><main class="page tool-page preprocessing-stage"><header class="library-heading"><div><p class="eyebrow">TASK #{{taskId}} · 输入记录</p><h1>参考图预处理</h1><p>查看此任务保留的图片；已经开始的生成不会因浏览此页改变输入。</p></div><span class="tool-badge">{{details?'预处理已确认':'历史输入记录'}}</span></header><p v-if="error" class="library-error" role="alert">{{error}}</p><p v-if="loading" class="tool-hint" role="status">正在读取生成输入…</p><section v-else class="tool-card"><div class="prepare-comparison"><figure><div class="preprocess-record-image"><img v-if="original" :src="original" alt="本次任务原始参考图" /><span v-else class="tool-hint">历史任务未保留独立原图，不补造处理前效果。</span></div><figcaption>原始参考图</figcaption></figure><figure><div class="preprocess-record-image"><img v-if="input" :src="input" alt="本次任务生成输入" /></div><figcaption>{{kind==='snapshot'?'本次任务实际提交的图片':'项目当前参考图（可能与历史输入不同）'}}</figcaption></figure></div><p class="tool-hint" v-if="details">{{details.mode==='original'?'保留原图':details.background==='white'?'白底 PNG':details.background==='neutral'?'中性灰底 PNG':details.background==='transparent'?'透明底 PNG':details.background_removed?'按透明轮廓整理':'保留原背景整理'}} · {{details.mode==='original'?'保持原图尺寸':'1024 × 1024'}} · 后台不再重复抠图。</p><p v-else class="tool-hint">此旧任务未记录人物整理的确认信息，不代表已经完成预处理。后端可能执行过其原有图像处理流程。</p><div class="library-actions"><button class="library-button" :disabled="!originalBlob" @click="prepareAgain(true)">用原始参考图重新生成</button><button class="library-button quiet" :disabled="!inputBlob" @click="prepareAgain(false)">用本次输入创建新的生成</button><RouterLink class="library-button quiet" :to="`/workflow/${taskId}?step=task`">查看任务进度</RouterLink></div></section></main></template>
