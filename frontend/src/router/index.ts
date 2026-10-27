import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import AuthView from '../views/AuthView.vue'
import ProjectsView from '../views/ProjectsView.vue'
import ProjectDetailView from '../views/ProjectDetailView.vue'
import TasksView from '../views/TasksView.vue'
import TaskCenterView from '../views/TaskCenterView.vue'
import KnowledgeView from '../views/KnowledgeView.vue'
import ModelView from '../views/ModelView.vue'
import WorkflowView from '../views/WorkflowView.vue'
import StandardizeView from '../views/StandardizeView.vue'

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.hash) return { el:to.hash, top:88 }
    if (to.path !== from.path) return { left: 0, top: 0 }
    return false
  },
  routes: [
    { path: '/', name: 'home', component: () => import('../views/ProductHomeView.vue'), meta: { public: true } },
    { path: '/workspace', name: 'dashboard', component: DashboardView },
    { path: '/auth', name: 'auth', component: AuthView, meta: { public: true } },
    { path: '/reset-password', name: 'reset-password', component: () => import('../views/ResetPasswordView.vue'), meta: { public: true } },
    { path: '/account', name: 'account', component: () => import('../views/AccountView.vue') },
    { path: '/prepare', name: 'prepare', component: () => import('../views/PrepareImageView.vue') },
    { path: '/repair/:taskId?', name: 'repair', component: () => import('../views/RepairView.vue') },
    { path: '/guide', name: 'guide', component: () => import('../views/GuideView.vue'), meta: { public: true } },
    { path: '/library', name: 'assets', component: () => import('../views/AssetsView.vue') },
    { path: '/compare', name: 'compare', component: () => import('../views/CompareView.vue') },
    { path: '/presets', name: 'presets', component: () => import('../views/PresetsView.vue') },
    { path: '/generate', name: 'generate', component: WorkflowView },
    { path: '/workflow/:taskId?', name: 'workflow', component: WorkflowView },
    { path: '/standardize/:taskId', name: 'standardize', component: StandardizeView },
    { path: '/projects', name: 'projects', component: ProjectsView },
    { path: '/projects/:projectId', name: 'project-detail', component: ProjectDetailView },
    { path: '/tasks', name: 'task-center', component: TaskCenterView },
    { path: '/tasks/:taskId', name: 'tasks', component: TasksView },
    { path: '/knowledge', name: 'knowledge', component: KnowledgeView },
    { path: '/model', name: 'model', component: ModelView },
  ],
})
router.beforeEach((to) => {
  const token = localStorage.getItem('moonlit_access_token')
  if (!to.meta.public && !token) return { name: 'auth', query: { redirect: to.fullPath } }
  return true
})
window.addEventListener('moonlit:auth-expired', () => {
  const current = router.currentRoute.value
  if (!current.meta.public) void router.replace({ name:'auth', query:{ redirect:current.fullPath } })
})
export default router
