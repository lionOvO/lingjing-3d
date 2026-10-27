<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, Moon, ArrowLeft, UserRound, Mail, LockKeyhole, Smartphone, ShieldCheck, Eye, EyeOff, LoaderCircle } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import api from '../services/api'
const auth = useAuthStore(); const route = useRoute(); const router = useRouter()
const mode = ref(route.query.mode === 'register' ? 'register' : 'login')
const method = ref<'password' | 'sms'>('password')
const passwordVisible = ref(false)
const registrationStep = ref(1)
const form = ref({ username:'', email:'', password:'', phone:'', code:'' })
const options = ref<{sms_available:boolean} | null>(null)
const optionError = ref(''); const notice = ref(''); const sending = ref(false)
const retryAt = ref(0); const now = ref(Date.now())
const remaining = computed(() => Math.max(0, Math.ceil((retryAt.value - now.value) / 1000)))
const phoneValid = computed(() => /^1[3-9][0-9]{9}$/.test(form.value.phone.trim()))
const isSMS = computed(() => mode.value === 'login' && method.value === 'sms')
const needsCode = computed(() => mode.value === 'register' || isSMS.value)
const codeValid = computed(() => phoneValid.value && /^[0-9]{6}$/.test(form.value.code))
const timer = window.setInterval(() => { now.value = Date.now() }, 1000)
onUnmounted(() => { window.clearInterval(timer); form.value.password = ''; form.value.code = '' })
watch(() => route.query.mode, value => { mode.value = value === 'register' ? 'register' : 'login' })
watch(mode, () => { registrationStep.value = 1 })
watch([mode, method], () => { auth.error = ''; notice.value = ''; form.value.password = ''; form.value.code = ''; passwordVisible.value = false })
watch(() => form.value.phone, () => { auth.error = ''; notice.value = ''; form.value.code = '' })
async function loadOptions() {
  optionError.value = ''
  try { options.value = (await api.get('/auth/options')).data }
  catch { optionError.value = '无法连接短信服务，请重试' }
}
onMounted(loadOptions)
async function sendCode() {
  if (sending.value || auth.loading || remaining.value || !phoneValid.value || !options.value?.sms_available) return
  sending.value = true; auth.error = ''; notice.value = ''
  try {
    const { data } = await api.post('/auth/sms/send', { phone:form.value.phone.trim(), purpose:mode.value === 'register' ? 'register' : 'login' })
    retryAt.value = Date.now() + data.retry_after * 1000; now.value = Date.now()
    notice.value = data.message; form.value.code = ''
  } catch (error:any) {
    auth.error = error.message
    retryAt.value = Date.now() + 60000; now.value = Date.now()
  } finally { sending.value = false }
}
async function submit() {
  if (auth.loading || sending.value) return
  if (mode.value === 'register') {
    if (!codeValid.value || !options.value?.sms_available) return
    if (registrationStep.value === 1) { registrationStep.value = 2; auth.error = ''; notice.value = ''; return }
    if (await auth.register(form.value.phone, form.value.code, form.value.email, form.value.password)) {
      form.value.username = form.value.phone.trim()
      ElMessage.success('账号已创建，请使用手机号登录'); mode.value = 'login'; method.value = 'password'
    }
    return
  }
  if (isSMS.value && !options.value?.sms_available) return
  const success = isSMS.value ? await auth.loginPhone(form.value.phone, form.value.code) : await auth.login(form.value.username, form.value.password)
  if (success) {
    form.value.password = ''; form.value.code = ''
    const requested = route.query.redirect
    const redirect = typeof requested === 'string' && requested.startsWith('/') && !requested.startsWith('//') && !requested.includes('\\') && !requested.startsWith('/auth') ? requested : '/workspace'
    await router.replace(redirect)
  }
}
</script>
<template>
  <section class="page auth-page auth-redesign">
    <div class="auth-entry-wrap">
      <RouterLink class="auth-back" to="/"><ArrowLeft :size="15" />返回产品首页</RouterLink>
      <div class="auth-entry-panel">
        <aside class="auth-story" aria-label="灵境造物创作空间">
          <div class="auth-story-brand"><Moon :size="20" /><span>灵境造物<small>AI 3D CREATION STUDIO</small></span></div>
          <div class="auth-story-copy"><p>让灵感拥有形状</p><h2>从一张图片，<br />走进三维世界。</h2><p class="auth-story-description">每一个想象，都值得被看见。<br />在这里，开始创作你的下一件作品。</p></div>
          <div class="auth-sculpture" aria-hidden="true"><svg viewBox="0 0 300 190" fill="none"><g stroke="currentColor" stroke-width=".8"><path d="M150 12 221 53 242 125 190 169 110 169 58 125 79 53Z"/><path d="m150 12 40 157M150 12l-40 157M79 53l163 72M221 53 58 125M58 125h184M79 53h142M110 169 221 53M190 169 79 53"/><path d="m150 12 92 113-132 44L79 53l111 116 31-116L58 125Z" opacity=".6"/><ellipse cx="150" cy="181" rx="104" ry="7" opacity=".25"/></g><g fill="currentColor"><circle cx="150" cy="12" r="2"/><circle cx="221" cy="53" r="2"/><circle cx="79" cy="53" r="2"/><circle cx="242" cy="125" r="2"/><circle cx="58" cy="125" r="2"/><circle cx="190" cy="169" r="2"/><circle cx="110" cy="169" r="2"/></g></svg><span>灵感的立体表达 · 创作示意</span></div>
          <div class="auth-story-footer"><span>图片建模</span><i></i><span>作品管理</span><i></i><span>灵感延续</span></div>
        </aside>
        <form class="auth-form-panel" @submit.prevent="submit" :aria-busy="auth.loading">
          <div class="auth-form-heading"><p class="auth-form-eyebrow">{{ mode === 'login' ? '回到你的创作空间' : '开启新的创作旅程' }}</p><h1>{{ mode === 'login' ? '欢迎回来' : '创建你的账号' }}</h1><p>{{ mode === 'login' ? '登录后，继续未完成的灵感。' : '验证手机号，拥有独立的创作空间。' }}</p></div>
          <div v-if="mode === 'login'" class="auth-login-tabs" role="group" aria-label="登录方式"><button type="button" :aria-pressed="method === 'password'" :disabled="auth.loading || sending" @click="method = 'password'">密码登录</button><button type="button" :aria-pressed="method === 'sms'" :disabled="auth.loading || sending" @click="method = 'sms'">验证码登录</button></div>
          <ol v-else class="auth-register-progress" aria-label="注册步骤"><li :aria-current="registrationStep === 1 ? 'step' : undefined"><span>1</span>填写验证码</li><li :aria-current="registrationStep === 2 ? 'step' : undefined"><span>2</span>设置账号</li></ol>
          <div v-if="mode === 'register' && registrationStep === 2" class="auth-registration-phone"><span>注册手机号 <strong>{{ form.phone }}</strong></span><button type="button" :disabled="auth.loading" @click="registrationStep = 1; auth.error = ''">返回修改</button></div>
          <div class="auth-form-fields">
            <template v-if="isSMS || (mode === 'register' && registrationStep === 1)">
              <div class="auth-field"><label for="login-phone">手机号码</label><div class="auth-input-shell"><Smartphone :size="17" aria-hidden="true" /><span class="auth-phone-prefix">+86</span><input id="login-phone" v-model="form.phone" required type="tel" inputmode="numeric" autocomplete="tel-national" pattern="1[3-9][0-9]{9}" maxlength="11" placeholder="请输入手机号码" :disabled="sending || auth.loading" aria-describedby="auth-login-note" /></div></div>
              <div class="auth-field"><label for="login-code">短信验证码</label><div class="auth-input-shell"><ShieldCheck :size="17" aria-hidden="true" /><input id="login-code" v-model="form.code" required inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" placeholder="请输入 6 位验证码" :disabled="auth.loading" /><button class="auth-send-code" type="button" :disabled="sending || auth.loading || remaining > 0 || !phoneValid || !options?.sms_available" @click="sendCode">{{ sending ? '发送中…' : remaining ? `${remaining} 秒后重发` : '获取验证码' }}</button></div></div>
            </template>
            <template v-else>
              <div v-if="mode === 'login'" class="auth-field"><label for="login-name">手机号、用户名或邮箱</label><div class="auth-input-shell"><UserRound :size="17" aria-hidden="true" /><input id="login-name" v-model="form.username" required autocomplete="username" maxlength="100" placeholder="请输入手机号、用户名或邮箱" :disabled="auth.loading" /></div></div>
              <div v-if="mode === 'register'" class="auth-field"><label for="register-email">邮箱地址</label><div class="auth-input-shell"><Mail :size="17" aria-hidden="true" /><input id="register-email" v-model="form.email" required type="email" autocomplete="email" maxlength="100" placeholder="name@example.com" :disabled="auth.loading" /></div></div>
              <div class="auth-field"><label for="login-password">密码</label><div class="auth-input-shell"><LockKeyhole :size="17" aria-hidden="true" /><input id="login-password" v-model="form.password" required :type="passwordVisible ? 'text' : 'password'" minlength="8" maxlength="128" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" :placeholder="mode === 'login' ? '请输入登录密码' : '设置 8–128 位密码'" :disabled="auth.loading" /><button class="auth-password-toggle" type="button" :aria-label="passwordVisible ? '隐藏密码' : '显示密码'" :aria-pressed="passwordVisible" :disabled="auth.loading" @click="passwordVisible = !passwordVisible"><EyeOff v-if="passwordVisible" :size="18" /><Eye v-else :size="18" /></button></div></div>
            </template>
          </div>
          <p id="auth-login-note" class="auth-form-note">{{ mode === 'register' ? registrationStep === 1 ? '验证码 5 分钟内有效。注册成功后，手机号就是你的登录账号。' : '点击创建账号时校验短信。若验证码过期，请返回重新获取。' : isSMS ? '使用已注册的手机号账号登录，验证码 5 分钟内有效。' : '支持手机号、用户名或邮箱，也可以切换验证码登录。' }}</p>
          <p v-if="needsCode && options && !options.sms_available" class="auth-form-error" role="status">{{ mode === 'register' ? '短信服务尚未配置，暂时无法注册。请稍后重试。' : '短信服务尚未配置，请先使用密码登录。' }}</p>
          <p v-if="needsCode && optionError" class="auth-form-error" role="alert">{{ optionError }} <button type="button" class="auth-retry" @click="loadOptions">重新连接</button></p>
          <p v-if="notice" class="auth-form-notice" role="status">{{ notice }}</p><p v-if="auth.error" class="auth-form-error" role="alert">{{ auth.error }}</p>
          <RouterLink v-if="mode === 'login' && method === 'password'" class="auth-forgot" to="/reset-password">忘记密码？</RouterLink><button class="auth-submit" :disabled="auth.loading || sending || (needsCode && (!options?.sms_available || !codeValid))"><LoaderCircle v-if="auth.loading" class="auth-loading-icon" :size="18" />{{ auth.loading ? '处理中…' : mode === 'login' ? '登录创作空间' : registrationStep === 1 ? '下一步：设置账号' : '验证并创建账号' }}<ArrowRight v-if="!auth.loading" :size="17" /></button>
          <p class="auth-mode-switch">{{ mode === 'login' ? '还没有账号？' : '已经拥有账号？' }} <button type="button" :disabled="auth.loading || sending" @click="mode = mode === 'login' ? 'register' : 'login'">{{ mode === 'login' ? '立即注册' : '返回登录' }}<ArrowRight :size="13" /></button></p>
        </form>
      </div>
    </div>
  </section>
</template>
