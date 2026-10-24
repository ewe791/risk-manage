import { createRouter, createWebHashHistory } from 'vue-router'
import { TOKEN_KEY } from '@/api/client'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginPage.vue'),
      meta: { public: true }
    },
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        { path: '', redirect: '/check' },
        { path: 'check', name: 'check', component: () => import('@/views/CheckPage.vue') },
        { path: 'workbench', name: 'workbench', component: () => import('@/views/ChatWorkbench.vue') },
        { path: 'rules', name: 'rules', component: () => import('@/views/RulesPage.vue') },
        { path: 'cases', name: 'cases', component: () => import('@/views/CasesPage.vue') },
        { path: 'blacklist', name: 'blacklist', component: () => import('@/views/BlacklistPage.vue') },
        { path: 'profile', name: 'profile', component: () => import('@/views/ProfilePage.vue') },
        { path: 'dashboard', name: 'dashboard', component: () => import('@/views/DashboardPage.vue') }
      ]
    }
  ]
})

router.beforeEach((to) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (!to.meta.public && !token) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.name === 'login' && token) return { name: 'workbench' }
  return true
})

export default router
