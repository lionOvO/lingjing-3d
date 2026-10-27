import { ref, type Ref } from 'vue'
import api from './api'

export type Parameters = { generation_mode:'high_quality'; texture_resolution:'1024'|'2048'; mesh_density:'low'|'medium'|'high'; pbr_enabled:true; seed?:number }
export type Preset = { id:number; name:string; project_type:'anime_character'|'object_model'; parameters:Parameters }
export type Asset = { id:number; project_id:number; project_name:string; name:string; tags:string[]; project_type:'anime_character'|'object_model'; format:string; created_at:string; quality_score:number|null; preview_available:boolean; parameters:Record<string,any>; metadata:{ vertex_count?:number; face_count?:number; file_size_mb?:number; texture_resolution?:string; has_pbr?:boolean } }
export const recommendedParameters = ():Parameters => ({ generation_mode:'high_quality', texture_resolution:'1024', mesh_density:'medium', pbr_enabled:true, seed:109020838 })
export function reusableParameters(source:Record<string,any>):Parameters {
  if (source.generation_mode !== 'high_quality' || !['1024','2048'].includes(String(source.texture_resolution)) || !['low','medium','high'].includes(source.mesh_density) || source.pbr_enabled !== true) throw new Error('此记录未保存完整的受支持参数，请手动配置预设')
  return { generation_mode:'high_quality', texture_resolution:String(source.texture_resolution) as Parameters['texture_resolution'], mesh_density:source.mesh_density, pbr_enabled:true, ...(Number.isInteger(source.seed)&&source.seed>=0&&source.seed<=2147483647?{seed:source.seed}:{}) }
}
export const densityLabel = (value:unknown) => ({ low:'低 · 约 30 万面', medium:'中 · 约 50 万面', high:'高 · 约 70 万面' })[String(value)] || '未记录'
export const metric = (value:unknown) => typeof value === 'number' ? value.toLocaleString('zh-CN') : '未记录'
export function useAssets(options?:{deleted?:Ref<boolean>}) {
  const assets = ref<Asset[]>([]), loading = ref(false), error = ref('')
  let request=0
  async function load() {
    const current=++request,deleted=options?.deleted?.value||false
    loading.value = true; error.value = ''
    try {
      const records:Asset[] = []
      for (let offset = 0; ; offset += 100) {
        const { data } = await api.get<Asset[]>('/studio/assets', { params:{ offset, limit:100, ...(deleted?{deleted:true}:{}) } })
        records.push(...data)
        if (data.length < 100) break
      }
      if(current===request)assets.value = records
    } catch (cause:any) { if(current===request){error.value = cause.message; assets.value = []} }
    finally { if(current===request)loading.value = false }
  }
  return { assets, loading, error, load }
}
export async function downloadAsset(asset:Asset) {
  const { data } = await api.get(`/studio/assets/${asset.id}/file`, { responseType:'blob', params:{ download:true }, timeout:60000 })
  const url = URL.createObjectURL(data), link = document.createElement('a')
  link.href = url; link.download = `lingjing-model-${asset.id}.${asset.format}`; link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 30000)
}
