<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Moon, Menu, X, LogOut, UserRound, LayoutDashboard, ImagePlus, FolderKanban, ListChecks, BookOpen, PanelLeftClose, PanelLeftOpen, ChevronRight, Plus, Boxes, GitCompareArrows, SlidersHorizontal, Crop, Wrench, CircleHelp } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth'
import SakuraWallpaper from '../components/SakuraWallpaper.vue'
const open = ref(false)
const collapsed = ref(localStorage.getItem('lingjing_navigation_collapsed') === 'true')
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const groups = [
  { label: '开始创作', links: [
    { label: '创作概览', name: 'dashboard', icon: LayoutDashboard },
    { label: '开始生成', name: 'generate', icon: ImagePlus },
    { label: '参考图处理', name: 'prepare', icon: Crop },
    { label: '生成任务', name: 'task-center', icon: ListChecks },
  ] },
  { label: '作品管理', links: [
    { label: '模型资产', name: 'assets', icon: Boxes },
    { label: '检查与修复', name: 'repair', icon: Wrench },
    { label: '模型对比', name: 'compare', icon: GitCompareArrows },
    { label: '项目管理', name: 'projects', icon: FolderKanban },
  ] },
  { label: '创作资源', links: [
    { label: '生成预设', name: 'presets', icon: SlidersHorizontal },
    { label: '创作知识库', name: 'knowledge', icon: BookOpen },
    { label: '使用指南与案例', name: 'guide', icon: CircleHelp },
  ] },
]
function isActive(linkName: string) {
  if (linkName === 'dashboard') return route.name === 'dashboard'
  if (linkName === 'generate') return route.name === 'generate' || route.name === 'standardize' || (route.name === 'workflow' && !['preview','task'].includes(String(route.query.step)))
  if (linkName === 'assets') return route.name === 'assets' || route.name === 'model' || (route.name === 'workflow' && route.query.step === 'preview')
  if (linkName === 'projects') return route.name === 'projects' || route.name === 'project-detail'
  if (linkName === 'task-center') return route.name === 'task-center' || route.name === 'tasks' || (route.name === 'workflow' && route.query.step === 'task')
  return route.name === linkName
}
onMounted(() => auth.hydrate())
const currentLabel = computed(() => route.name === 'auth' ? '账号登录' : route.name === 'account' ? '个人中心' : groups.flatMap(group => group.links).find(link => isActive(link.name))?.label || '创作空间')
const contextLabel = computed(() => route.params.taskId ? `任务 #${route.params.taskId}` : route.params.projectId ? `项目 #${route.params.projectId}` : '')
watch(() => route.fullPath, () => { open.value = false })
watch(collapsed, value => localStorage.setItem('lingjing_navigation_collapsed', String(value)))
function closeNavigation() {
  open.value = false
}
const isPublicEntry = computed(() => ['home','auth','reset-password'].includes(String(route.name)) || (route.name === 'guide' && !auth.token))
function logout() { auth.logout(); router.push({ name: 'home' }); }
</script>
<template>
  <div class="app-shell studio-shell" :class="{ 'sidebar-collapsed': collapsed, 'navigation-open': open, 'product-entry-shell': isPublicEntry, 'cloud-entry-shell': route.name === 'home' }" @keydown.esc="closeNavigation">
    <a class="studio-skip" href="#studio-content">跳转到主要内容</a>
    <SakuraWallpaper v-if="route.name !== 'home'" />
    <button v-if="open" class="studio-backdrop" aria-label="关闭导航" @click="closeNavigation"></button>
    <aside v-if="!isPublicEntry" id="studio-navigation" class="studio-sidebar" aria-label="创作空间导航">
      <RouterLink class="brand studio-brand" to="/" aria-label="灵境造物产品首页"><span class="brand-mark"><Moon :size="19" /></span><span class="studio-brand-copy">灵境造物<small>3D 创作平台</small></span></RouterLink>
      <button class="studio-close icon-button" aria-label="关闭导航" @click="closeNavigation"><X :size="18" /></button>
      <RouterLink class="studio-create" :to="{ name: 'generate' }" title="新建生成"><Plus :size="18" /><span>新建生成</span></RouterLink>
      <nav class="studio-nav" aria-label="主导航">
        <div v-for="group in groups" :key="group.label" class="studio-nav-group">
          <p class="studio-group-label">{{ group.label }}</p>
          <RouterLink v-for="link in group.links" :key="link.name" :to="{ name: link.name }" :class="['studio-nav-link', { 'is-active': isActive(link.name) }]" :title="link.label" :aria-current="isActive(link.name) ? 'page' : undefined">
            <component :is="link.icon" :size="19" /><span>{{ link.label }}</span><i v-if="isActive(link.name)" aria-hidden="true"></i>
          </RouterLink>
        </div>
      </nav>
      <div class="studio-sidebar-bottom"><span class="studio-space-label"><Moon :size="15" /><span>你的创作空间</span></span><button class="studio-collapse" :aria-label="collapsed ? '展开导航栏' : '收起导航栏'" :aria-expanded="!collapsed" @click="collapsed = !collapsed"><PanelLeftOpen v-if="collapsed" :size="18" /><template v-else><PanelLeftClose :size="18" /><span>收起导航栏</span></template></button></div>
    </aside>
    <div class="studio-main">
      <header class="studio-topbar">
        <template v-if="isPublicEntry"><RouterLink class="brand product-brand" to="/"><span class="brand-mark"><Moon :size="19" /></span><span>灵境造物</span></RouterLink><nav class="product-topnav" aria-label="产品导航"><RouterLink to="/">产品首页</RouterLink><RouterLink to="/generate">图片建模</RouterLink><RouterLink to="/workspace">工作台</RouterLink><RouterLink to="/guide">使用指南</RouterLink></nav></template>
        <template v-else>
        <button class="studio-menu icon-button" aria-label="打开导航" aria-controls="studio-navigation" :aria-expanded="open" @click="open = !open"><Menu :size="19" /></button>
        <div class="studio-breadcrumb"><span class="studio-breadcrumb-root">创作空间</span><ChevronRight :size="14" class="studio-breadcrumb-root" /><strong>{{ currentLabel }}</strong><template v-if="contextLabel"><ChevronRight :size="14" /><span>{{ contextLabel }}</span></template></div>
        <RouterLink class="studio-product-return" to="/">产品首页</RouterLink>
        </template>
        <div class="account-actions"><template v-if="auth.isAuthenticated"><RouterLink class="avatar" to="/account" aria-label="个人中心"><UserRound :size="15" /></RouterLink><RouterLink class="account-name" to="/account" title="个人中心">{{ auth.user?.display_name || auth.user?.username }}</RouterLink><button class="text-action" @click="logout"><LogOut :size="15" /><span>退出</span></button></template><template v-else><RouterLink class="text-action" to="/auth">登录</RouterLink><RouterLink class="primary small" to="/auth?mode=register">注册</RouterLink></template></div>
      </header>
      <div id="studio-content" class="studio-content" tabindex="-1">
        <RouterView v-slot="{ Component, route: viewRoute }">
          <Transition name="studio-page">
            <component :is="Component" :key="viewRoute.path" />
          </Transition>
        </RouterView>
      </div>
    </div>
  </div>
</template>
