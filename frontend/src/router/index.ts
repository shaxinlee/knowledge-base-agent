import { createRouter, createWebHistory } from 'vue-router'

import { clearAuthTokens, getAccessToken, getCurrentUser } from '@/api/client'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/login',
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('@/views/ChatView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/knowledge',
      name: 'consumer-knowledge',
      component: () => import('@/views/ConsumerKnowledgeView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/knowledge-bases',
      name: 'knowledge-bases',
      component: () => import('@/views/KnowledgeBasesView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/files',
      name: 'files',
      component: () => import('@/views/FilesView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/chunks',
      name: 'chunks',
      component: () => import('@/views/ChunksView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/users',
      name: 'users',
      component: () => import('@/views/UsersView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/audit-logs',
      name: 'audit-logs',
      component: () => import('@/views/AuditLogsView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('@/views/ProfileView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/forbidden',
      name: 'forbidden',
      component: () => import('@/views/ForbiddenView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  const token = getAccessToken()
  const requiresAuth = Boolean(to.meta.requiresAuth)

  if (!token) {
    if (requiresAuth) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    return true
  }

  try {
    const currentUser = await getCurrentUser()

    if (to.name === 'login') {
      return { name: currentUser.role === 'admin' ? 'knowledge-bases' : 'chat' }
    }

    if (to.meta.requiresAdmin && currentUser.role !== 'admin') {
      return { name: 'forbidden' }
    }

    return true
  } catch {
    clearAuthTokens()
    if (requiresAuth) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    return true
  }
})

export default router
