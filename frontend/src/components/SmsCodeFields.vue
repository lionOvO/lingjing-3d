<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import api from '../services/api'
const props = defineProps<{ purpose:'reset'|'bind_phone'; disabled?:boolean }>()
const phone = defineModel<string>('phone', { default:'' }), code = defineModel<string>('code', { default:'' })
const available = ref(false), loading = ref(true), sending = ref(false), error = ref(''), notice = ref('')
const retryAt = ref(0), now = ref(Date.now())
const remaining = computed(() => Math.max(0,Math.ceil((retryAt.value-now.value)/1000)))
const phoneValid = computed(() => /^1[3-9][0-9]{9}$/.test(phone.value))
const timer = window.setInterval(() => { now.value = Date.now() },1000)
onUnmounted(() => window.clearInterval(timer))
watch(phone, () => { code.value = ''; notice.value = '' })
async function load() { loading.value = true; error.value = ''; try { available.value = (await api.get('/auth/options')).data.sms_available } catch (e:any) { error.value = e.message } finally { loading.value = false } }
async function send() {
  if (!phoneValid.value || remaining.value || sending.value || !available.value) return
  sending.value = true; error.value = ''; notice.value = ''
  try { const {data} = await api.post('/auth/sms/send',{phone:phone.value,purpose:props.purpose}); retryAt.value = Date.now()+data.retry_after*1000; notice.value = data.message; code.value = '' }
  catch (e:any) { error.value = e.message; retryAt.value = Date.now()+60000 }
  finally { now.value = Date.now(); sending.value = false }
}
onMounted(load)
</script>
<template><div class="tool-fields"><label>手机号码<input v-model="phone" class="library-input" required type="tel" inputmode="numeric" autocomplete="tel-national" maxlength="11" pattern="1[3-9][0-9]{9}" :disabled="disabled || sending" :placeholder="purpose === 'reset' ? '已注册的手机号码' : '新的手机号码'" /></label><label>短信验证码<div class="tool-code-row"><input v-model="code" class="library-input" required inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" placeholder="6 位验证码" :disabled="disabled" /><button type="button" class="library-button quiet" :disabled="disabled || loading || !available || !phoneValid || sending || remaining > 0" @click="send">{{ sending ? '发送中…' : remaining ? `${remaining} 秒后重发` : '获取验证码' }}</button></div></label><p v-if="!loading && !available" class="tool-hint">短信服务暂不可用。<button type="button" class="text-link" @click="load">重新连接</button></p><p v-if="notice" class="tool-success" role="status">{{ notice }}</p><p v-if="error" class="library-error" role="alert">{{ error }}</p></div></template>
