<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Save, SlidersHorizontal } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../services/api'
import { densityLabel, recommendedParameters, reusableParameters, type Preset, type Parameters } from '../services/studio'
const route = useRoute(), router = useRouter()
const presets = ref<Preset[]>([]), loading = ref(false), saving = ref(false), error = ref(''), editing = ref<number|null>(null)
const name = ref(''), projectType = ref<'anime_character'|'object_model'>('anime_character'), parameters = ref<Parameters>(recommendedParameters()), imported = ref('')
async function load() { loading.value = true; error.value = ''; try { presets.value = (await api.get<Preset[]>('/studio/presets')).data } catch (cause:any) { error.value = cause.message } finally { loading.value = false } }
function reset() { editing.value = null; name.value = ''; projectType.value = 'anime_character'; parameters.value = recommendedParameters(); imported.value = '' }
function edit(preset:Preset) { editing.value = preset.id; name.value = preset.name; projectType.value = preset.project_type; parameters.value = { ...preset.parameters }; imported.value = ''; document.getElementById('preset-name')?.focus() }
async function save() {
  saving.value = true
  try {
    const body = { name:name.value.trim(), project_type:projectType.value, parameters:parameters.value }
    if (editing.value) await api.put(`/studio/presets/${editing.value}`,body)
    else await api.post('/studio/presets',body)
    ElMessage.success(editing.value ? '预设已更新' : '预设已保存到账号'); reset(); await load()
  } catch (cause:any) { ElMessage.error(cause.message) }
  finally { saving.value = false }
}
async function archive(preset:Preset) {
  try { await ElMessageBox.confirm(`归档“${preset.name}”？已有任务不受影响。`, '归档预设', { confirmButtonText:'归档', cancelButtonText:'取消' }); await api.delete(`/studio/presets/${preset.id}`); await load(); ElMessage.success('预设已归档') }
  catch (cause:any) { if (!['cancel','close'].includes(cause)) ElMessage.error(cause.message) }
}
onMounted(async () => {
  await load()
  if (route.query.task) {
    try {
      // The authenticated asset endpoint limits imports to the account's own completed tasks.
      let found:any
      for (let offset = 0; ; offset += 100) {
        const { data } = await api.get('/studio/assets',{ params:{ offset,limit:100 } })
        found = data.find((asset:any) => asset.id === Number(route.query.task))
        if (found || data.length < 100) break
      }
      if (!found) throw new Error('找不到此账号的完成模型')
      parameters.value = reusableParameters(found.parameters); name.value = `${found.name} 参数`.slice(0,120); projectType.value = found.project_type; imported.value = `已从任务 #${found.id} 读取受支持的参数，保存后可用于新的参考图。`
    } catch (cause:any) { imported.value = cause.message }
  }
})
</script>
<template>
  <main class="page library-page"><header class="library-heading"><div><p class="eyebrow">参数复用</p><h1>生成预设</h1><p>保存常用的类型、纹理和面数配置，下次上传图片时直接应用。</p></div><button class="library-button" @click="reset"><Plus :size="15" />新建预设</button></header>
    <p v-if="error" class="library-error" role="alert">{{ error }}</p>
    <div class="preset-layout"><div><section class="library-panel preset-card" style="margin-bottom:20px"><span class="preset-badge">本机推荐</span><h2>Pixal3D · 标准质量</h2><p>1024px 纹理 · 中面数 · GLB · PBR<br>适合作为本机生成的起点，实际效果取决于参考图。</p><div class="library-actions"><RouterLink class="library-button primary-action" to="/generate?preset=recommended">应用并上传图片</RouterLink><button class="library-button quiet" @click="reset(); name = '我的标准质量预设'">复制到我的预设</button></div></section>
      <h2 style="font-size:17px;font-weight:500;margin:26px 0 16px">我的预设 <span class="library-note">{{ presets.length }}</span></h2><p v-if="loading" class="library-note">正在读取账号预设…</p><div v-else-if="presets.length" class="preset-cards"><article v-for="preset in presets" :key="preset.id" class="library-panel preset-card"><SlidersHorizontal :size="19" style="color:#a9c7e8;margin-bottom:14px" /><h2>{{ preset.name }}</h2><p>{{ preset.project_type === 'anime_character' ? '动漫角色' : '物品模型' }} · {{ preset.parameters.texture_resolution }}px<br>{{ densityLabel(preset.parameters.mesh_density) }} · PBR</p><span v-if="preset.parameters.texture_resolution === '2048'" class="preset-badge">2048px 实验配置</span><div class="library-actions"><button class="library-button" @click="router.push({ name:'generate',query:{ preset:preset.id } })">应用</button><button class="library-button quiet" @click="edit(preset)">编辑</button><button class="library-button quiet" @click="archive(preset)">归档</button></div></article></div><div v-else class="library-empty"><h2>{{ error ? '预设暂时无法加载' : '保存你的第一套参数' }}</h2><span>在右侧填写，或从模型资产导入一次生成的参数。</span><RouterLink class="text-link" to="/library">从已有模型创建预设</RouterLink></div></div>
      <aside class="library-panel"><h2>{{ editing ? '编辑预设' : '新建我的预设' }}</h2><p v-if="imported" class="library-note" role="status">{{ imported }}</p><form class="library-form" @submit.prevent="save"><label for="preset-name">预设名称<input id="preset-name" v-model="name" class="library-input" maxlength="120" required placeholder="例如：角色展示 · 中面数" /></label><label>模型类型<select v-model="projectType" class="library-select"><option value="anime_character">动漫角色</option><option value="object_model">物品模型</option></select></label><label>纹理分辨率<select v-model="parameters.texture_resolution" class="library-select"><option value="1024">1024px · 推荐</option><option value="2048">2048px · 实验</option></select></label><label>面数预设<select v-model="parameters.mesh_density" class="library-select"><option value="low">低 · 约 30 万面</option><option value="medium">中 · 约 50 万面</option><option value="high">高 · 约 70 万面</option></select></label><p class="library-note">当前运行器使用高质量模式、GLB 和 PBR 材质。2048px 尚未完成整链路验证，可能超过本机显存。</p><div class="library-actions"><button class="library-button primary-action" :disabled="saving || !name.trim()"><Save :size="14" />{{ saving ? '保存中…' : '保存预设' }}</button><button v-if="editing" class="library-button quiet" type="button" @click="reset">取消编辑</button></div></form></aside>
    </div>
  </main>
</template>
