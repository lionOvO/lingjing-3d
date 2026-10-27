<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight } from 'lucide-vue-next'
import GenerateView from './GenerateView.vue'
import StandardizeView from './StandardizeView.vue'
import TasksView from './TasksView.vue'
import ModelView from './ModelView.vue'
import { useTaskStore } from '../stores/task'

type Step = 'upload' | 'standardize' | 'task' | 'preview'

const route = useRoute()
const router = useRouter()
const tasks = useTaskStore()
const isGenerateRoute = computed(() => route.name === 'generate')
const requested = computed(() => String(route.query.step || ''))
// /generate is the clean entry for a new upload. Do not reuse the last task
// kept in Pinia/localStorage, otherwise opening a project can jump straight
// into an unrelated old preview step.
// A historical task is always identified by the route. The store is only a
// fallback for legacy links without an explicit task id.
const routeTaskId = computed(() => String(route.params.taskId || route.query.taskId || ''))
const taskId = computed(() => isGenerateRoute.value ? '' : routeTaskId.value || String(tasks.current?.id || ''))
const currentStep = ref<Step>('upload')
const generator=ref<InstanceType<typeof GenerateView>>(), inputReady=ref(false)
const steps = [
  { key: 'upload' as Step, label: '上传与配置' },
  { key: 'standardize' as Step, label: '参考图预处理' },
  { key: 'task' as Step, label: '生成与质检' },
  { key: 'preview' as Step, label: '预览与交付' },
]
const taskReady = computed(() => !isGenerateRoute.value && Boolean(tasks.current && taskId.value))
const completed = computed(() => tasks.current?.status === 'completed')
const readyForNext = computed(() => !isGenerateRoute.value || currentStep.value !== 'standardize' || inputReady.value)

function canEnter(step: Step) {
  if (step === 'upload') return true
  if (isGenerateRoute.value) return step === 'standardize'
  if (step === 'standardize' || step === 'task') return taskReady.value
  return taskReady.value && completed.value
}

function setStep(step: Step, replace = false) {
  if (!canEnter(step)) {
    ElMessage.info(step === 'task' ? '请先上传图片并创建生成任务' : '模型生成完成后才能进入预览')
    return
  }
  currentStep.value = step
  const method = replace ? router.replace : router.push
  if(isGenerateRoute.value){void method.call(router,{name:'generate',query:{...route.query,step}});return}
  void method.call(router, {
    name: 'workflow',
    params: taskId.value ? { taskId: taskId.value } : {},
    query: { step },
  })
}

function next() {
  if(isGenerateRoute.value){void generator.value?.next();return}
  if (currentStep.value === 'upload') return setStep('task')
  if (currentStep.value === 'standardize') return setStep('task')
  if (currentStep.value === 'task') return completed.value ? setStep('preview') : ElMessage.info('任务尚未完成，请等待处理结束')
  return setStep('upload')
}

function previous() {
  if (currentStep.value === 'preview') return setStep('task')
  if (currentStep.value === 'task') return setStep('standardize')
  if (currentStep.value === 'standardize') return setStep('upload')
  return router.push('/')
}

function syncStep() {
  if (isGenerateRoute.value) {
    currentStep.value = requested.value === 'standardize' ? 'standardize' : 'upload'
    return
  }
  const wanted = requested.value as Step
  if (wanted && canEnter(wanted)) {
    currentStep.value = wanted
    return
  }
  if (taskReady.value) currentStep.value = completed.value ? 'preview' : 'task'
  else currentStep.value = 'upload'
}

watch([requested, taskId, completed, isGenerateRoute], syncStep)
watch(completed, (isDone, wasDone) => {
  if (isDone && !wasDone && currentStep.value === 'task') setStep('preview', true)
})
watch(isGenerateRoute, (freshEntry) => {
  if (freshEntry) tasks.stopProgress()
})

watch(routeTaskId, async (id) => {
  if (!id || isGenerateRoute.value || String(tasks.current?.id || '') === id) return
  try {
    await tasks.fetch(id)
  } catch {
    // The task page renders the request failure with recovery actions.
  }
  syncStep()
})

onMounted(async () => {
  if (taskId.value && String(tasks.current?.id || '') !== taskId.value) {
    try {
      await tasks.fetch(taskId.value)
    } catch {
      // The task page renders the request failure with recovery actions.
    }
  }
  syncStep()
})

onBeforeUnmount(() => tasks.stopProgress())
</script>

<template>
  <main class="workflow-page">
    <nav class="workflow-index" aria-label="生成流程步骤">
      <span class="workflow-index-label">生成流程</span>
      <div class="workflow-tabs" role="tablist">
        <button
          v-for="(step, index) in steps"
          :key="step.key"
          class="workflow-tab"
          :class="{ active: currentStep === step.key, complete: index < steps.findIndex((item) => item.key === currentStep), disabled: !canEnter(step.key) }"
          :disabled="!canEnter(step.key)"
          role="tab"
          :aria-selected="currentStep === step.key"
          @click="setStep(step.key)"
        >
          <span>{{ String(index + 1).padStart(2, '0') }}</span>{{ step.label }}
        </button>
      </div>
      <small v-if="taskId" class="workflow-task-id">任务 #{{ taskId }}</small>
    </nav>

    <div v-if="currentStep === 'upload' || currentStep === 'standardize' || currentStep === 'task'" class="workflow-top-actions">
      <button class="flow-secondary" @click="previous"><ArrowLeft :size="16" />{{ currentStep === 'upload' ? '返回首页' : '上一步' }}</button>
      <button v-if="!isGenerateRoute && currentStep !== 'task'" class="flow-primary" :disabled="!readyForNext" @click="next">{{isGenerateRoute?(currentStep==='upload'?'下一步：预处理参考图':'确认并开始生成 3D'):'查看生成与质检'}}<ArrowRight :size="16" /></button>
    </div>

    <div class="workflow-content" :class="`${currentStep}-content`">
      <GenerateView v-if="isGenerateRoute || currentStep === 'upload'" ref="generator" :preprocess="isGenerateRoute && currentStep==='standardize'" @ready="inputReady=$event" />
      <StandardizeView v-else-if="currentStep === 'standardize'" />
      <TasksView v-else-if="currentStep === 'task'" />
      <ModelView v-else />
    </div>

  </main>
</template>

<style scoped>
.workflow-page{position:relative;z-index:1;min-width:0}.workflow-index{display:flex;align-items:center;gap:18px;max-width:1260px;margin:0 auto;padding:18px clamp(18px,4vw,56px) 0;border-bottom:1px solid rgba(255,255,255,.13)}.workflow-index-label{flex:none;color:var(--mist);font-size:11px;font-weight:700;letter-spacing:.14em}.workflow-tabs{display:flex;align-items:stretch;min-width:0}.workflow-tab{position:relative;display:inline-flex;align-items:center;gap:8px;min-height:42px;padding:0 15px;border-bottom:2px solid transparent;background:transparent;color:var(--mist);font-size:13px;transition:color .2s,border-color .2s}.workflow-tab span{color:inherit;font:10px ui-monospace,SFMono-Regular,Consolas,monospace}.workflow-tab:hover:not(:disabled){color:var(--white)}.workflow-tab.active{color:var(--white);border-bottom-color:var(--pink);background:rgba(169,199,232,.06)}.workflow-tab.complete span{color:#bcebd5}.workflow-tab.disabled{cursor:not-allowed;opacity:.45}.workflow-task-id{margin-left:auto;color:var(--mist);font:11px ui-monospace,SFMono-Regular,Consolas,monospace;white-space:nowrap}.workflow-content{min-width:0}.workflow-top-actions,.workflow-actions{display:flex;align-items:center;justify-content:space-between;gap:14px;max-width:1260px;margin:0 auto;padding:18px clamp(18px,4vw,56px)}.workflow-top-actions{padding-top:16px;padding-bottom:4px}.workflow-actions{padding-top:2px;padding-bottom:34px}.flow-primary,.flow-secondary{display:inline-flex;align-items:center;gap:8px;border-radius:999px;padding:10px 17px;font:700 12px inherit;transition:background-color .18s ease,border-color .18s ease,color .18s ease,box-shadow .18s ease,transform .18s ease}.flow-primary{color:var(--violet);background:linear-gradient(135deg,var(--white),var(--pink));box-shadow:0 8px 22px rgba(169,199,232,.22)}.flow-primary:disabled{opacity:.45;cursor:not-allowed;box-shadow:none}.flow-secondary{color:var(--white);background:rgba(244,248,255,.08);border:1px solid rgba(244,248,255,.24);box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 6px 18px rgba(8,12,34,.16)}.flow-secondary:hover:not(:disabled){color:var(--white);background:rgba(169,199,232,.13);border-color:rgba(169,199,232,.76);box-shadow:inset 0 1px 0 rgba(255,255,255,.1),0 8px 22px rgba(8,12,34,.24);transform:translateY(-1px)}.flow-secondary:active:not(:disabled){background:rgba(169,199,232,.2);transform:translateY(0);box-shadow:inset 0 1px 4px rgba(8,12,34,.24)}.flow-secondary:focus-visible{outline:2px solid rgba(169,199,232,.86);outline-offset:3px}@media(max-width:680px){.workflow-index{gap:8px;padding-top:10px;overflow-x:auto}.workflow-index-label,.workflow-task-id{display:none}.workflow-tabs{min-width:max-content}.workflow-tab{min-height:40px;padding:0 10px;font-size:12px}.workflow-top-actions{padding-top:12px;padding-bottom:2px}.workflow-actions{padding-bottom:24px}.flow-primary,.flow-secondary{padding:10px 13px}}
.workflow-tab:hover:not(:disabled),.workflow-tab.active{background:transparent}
.flow-primary,.flow-secondary{font-size:12px;font-weight:700;appearance:none;cursor:pointer}
.flow-secondary:disabled{cursor:not-allowed;opacity:.5}
.workflow-top-actions{padding-top:28px}
.workflow-top-actions{max-width:1340px}
@media(max-width:680px){.workflow-top-actions{padding-top:20px}}

/* Completed steps use the same cold-blue accent as the homepage. */
.workflow-page .workflow-tab.complete span{color:var(--pink)}
</style>
