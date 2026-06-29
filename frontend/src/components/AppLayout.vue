<script setup lang="ts">
import {
  ChatDotRound,
  Collection,
  DataAnalysis,
  FolderOpened,
  Refresh,
  Share,
  SwitchButton,
  User,
} from '@element-plus/icons-vue'
import {
  BookOpen,
  Bot,
  LogOut,
  MessageCircle,
  Network,
  Plus,
  RefreshCw,
  UserCircle,
} from '@lucide/vue'
import { ElButton, ElIcon } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  clearAuthTokens,
  getAccessToken,
  getCachedCurrentUser,
  getCurrentUser,
  getRefreshToken,
  logout,
} from '@/api/client'
import type { User as AuthUser } from '@/api/types'

const props = withDefaults(
  defineProps<{
    consumerSidebarActive?: boolean
  }>(),
  {
    consumerSidebarActive: false,
  },
)

const consumerNavItems = [
  { label: '对话问答', path: '/chat', icon: MessageCircle },
  { label: '知识库', path: '/knowledge', icon: BookOpen },
  { label: '知识地图', path: '/knowledge-map', icon: Network },
  { label: '个人资料', path: '/profile', icon: UserCircle },
]

const adminNavItems = [
  { label: '对话问答', path: '/chat', icon: ChatDotRound },
  { label: '知识库管理', path: '/knowledge-bases', icon: Collection },
  { label: '文件管理', path: '/files', icon: FolderOpened },
  { label: '知识地图', path: '/knowledge-map', icon: Share },
  { label: 'Chunk 调试', path: '/chunks', icon: Collection },
  { label: '用户管理', path: '/users', icon: User },
  { label: '审计日志', path: '/audit-logs', icon: DataAnalysis },
  { label: '个人资料', path: '/profile', icon: User },
]

const route = useRoute()
const router = useRouter()
const currentUser = ref<AuthUser | null>(getCachedCurrentUser())
const authReady = ref(Boolean(currentUser.value) || !getAccessToken())

const displayName = computed(
  () => currentUser.value?.display_name || currentUser.value?.username || '未登录',
)
const roleLabel = computed(() => {
  if (currentUser.value?.role === 'admin') return '管理员'
  if (currentUser.value?.role === 'user') return '普通用户'
  return '-'
})
const isAdmin = computed(() => currentUser.value?.role === 'admin')
const navItems = computed(() => (isAdmin.value ? adminNavItems : consumerNavItems))
const brandSubtitle = computed(() => (isAdmin.value ? '管理后台' : '用户问答'))
const brandHomePath = computed(() => (isAdmin.value ? '/knowledge-bases' : '/chat'))
const isConsumerChatRoute = computed(() => !isAdmin.value && route.path === '/chat')
const showConsumerSidebarMain = computed(
  () => Boolean(currentUser.value) && !isAdmin.value && props.consumerSidebarActive,
)
const avatarText = computed(() => {
  const source = displayName.value.trim() || currentUser.value?.username || 'KB'
  return source.slice(0, 2).toUpperCase()
})

onMounted(async () => {
  if (!getAccessToken()) {
    authReady.value = true
    return
  }
  try {
    currentUser.value = await getCurrentUser()
    authReady.value = true
  } catch {
    clearAuthTokens()
    await router.push('/login')
  }
})

async function handleLogout(): Promise<void> {
  const refreshToken = getRefreshToken()
  try {
    if (refreshToken && getAccessToken()) {
      await logout({ refresh_token: refreshToken })
    }
  } catch {
    // Local cleanup still matters if the access token has already expired.
  } finally {
    clearAuthTokens()
    await router.push('/login')
  }
}

function reloadPage(): void {
  router.go(0)
}
</script>

<template>
  <div v-if="!authReady" class="auth-shell-loading" aria-busy="true" aria-label="正在加载用户信息">
    <aside class="auth-shell-loading__sidebar">
      <div class="auth-shell-loading__brand"></div>
      <div v-for="index in 6" :key="index" class="auth-shell-loading__nav"></div>
    </aside>
    <div class="auth-shell-loading__body">
      <div class="auth-shell-loading__topbar"></div>
      <div class="auth-shell-loading__content"></div>
    </div>
  </div>
  <div
    v-else
    :class="[
      'app-shell',
      isAdmin ? 'admin-shell' : 'consumer-shell',
      {
        'consumer-chat-shell':
          isConsumerChatRoute && showConsumerSidebarMain && $slots['consumer-sidebar-main'],
      },
    ]"
  >
    <aside class="side-nav">
      <template v-if="showConsumerSidebarMain && $slots['consumer-sidebar-main']">
        <slot name="consumer-sidebar-main" />
      </template>
      <template v-else>
        <RouterLink class="brand" :to="brandHomePath">
          <span class="brand-mark">
            <Bot v-if="!isAdmin" class="consumer-icon" />
            <el-icon v-else><ChatDotRound /></el-icon>
          </span>
          <span class="brand-copy">
            <strong>知识库 Agent</strong>
            <span>{{ brandSubtitle }}</span>
          </span>
        </RouterLink>

        <RouterLink v-if="!isAdmin" class="consumer-start" to="/chat">
          <Plus class="consumer-icon" />
          <span>新建问答</span>
        </RouterLink>

        <nav class="nav-list">
          <RouterLink v-for="item in navItems" :key="item.path" class="nav-item" :to="item.path">
            <component :is="item.icon" v-if="!isAdmin" class="consumer-icon" />
            <el-icon v-else :size="22">
              <component :is="item.icon" />
            </el-icon>
            <span>{{ item.label }}</span>
          </RouterLink>
        </nav>
      </template>

      <div class="side-user">
        <div class="avatar">{{ avatarText }}</div>
        <div class="side-user-text">
          <strong>{{ displayName }}</strong>
          <span>{{ roleLabel }}</span>
        </div>
        <button class="logout" type="button" aria-label="退出登录" @click="handleLogout">
          <LogOut v-if="!isAdmin" class="consumer-icon" />
          <el-icon v-else>
            <SwitchButton />
          </el-icon>
        </button>
      </div>
    </aside>

    <header class="top-bar">
      <slot name="top-left">
        <div class="kb-switcher">
          <BookOpen v-if="!isAdmin" class="consumer-icon" />
          <el-icon v-else>
            <Collection />
          </el-icon>
          <span>{{ isAdmin ? 'Agent-Assistant' : '知识库助手' }}</span>
        </div>
      </slot>

      <div class="top-actions">
        <el-button link class="top-icon-button" @click="reloadPage">
          <RefreshCw v-if="!isAdmin" class="consumer-icon" />
          <el-icon v-else>
            <Refresh />
          </el-icon>
          刷新
        </el-button>
        <div class="top-user">
          <span>当前用户：</span>
          <strong>{{ displayName }}</strong>
        </div>
        <button class="top-logout" type="button" aria-label="退出登录" @click="handleLogout">
          <LogOut v-if="!isAdmin" class="consumer-icon" />
          <el-icon v-else>
            <SwitchButton />
          </el-icon>
        </button>
      </div>
    </header>

    <main class="app-main">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.auth-shell-loading {
  display: grid;
  grid-template-columns: 174px minmax(0, 1fr);
  min-height: 100vh;
  background: #f3f7f5;
}

.auth-shell-loading__sidebar {
  padding: 22px 16px;
  border-right: 1px solid #dce7e2;
  background: #fff;
}

.auth-shell-loading__brand,
.auth-shell-loading__nav,
.auth-shell-loading__topbar,
.auth-shell-loading__content {
  background: linear-gradient(90deg, #e9efec 25%, #f7faf8 50%, #e9efec 75%);
  background-size: 200% 100%;
  animation: auth-loading-shimmer 1.2s ease-in-out infinite;
}

.auth-shell-loading__brand {
  width: 126px;
  height: 34px;
  margin-bottom: 42px;
  border-radius: 6px;
}

.auth-shell-loading__nav {
  height: 34px;
  margin-bottom: 10px;
  border-radius: 4px;
}

.auth-shell-loading__body {
  min-width: 0;
}

.auth-shell-loading__topbar {
  height: 56px;
  border-bottom: 1px solid #dce7e2;
}

.auth-shell-loading__content {
  height: 180px;
  margin: 28px 20px;
  border-radius: 6px;
}

@keyframes auth-loading-shimmer {
  from {
    background-position: 200% 0;
  }
  to {
    background-position: -200% 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .auth-shell-loading__brand,
  .auth-shell-loading__nav,
  .auth-shell-loading__topbar,
  .auth-shell-loading__content {
    animation: none;
  }
}

.app-shell {
  min-height: 100vh;
  background: var(--ka-background);
}

.consumer-shell {
  --ka-primary: #18181b;
  --ka-primary-deep: #09090b;
  --ka-primary-soft: #f4f4f5;
  --ka-accent: #0f766e;
  --ka-accent-soft: #ecfdf5;
  --ka-surface: #fafafa;
  --ka-surface-lowest: #ffffff;
  --ka-surface-container: #f4f4f5;
  --ka-surface-high: #e4e4e7;
  --ka-background: #fafafa;
  --ka-border: #e4e4e7;
  --ka-border-strong: #d4d4d8;
  --ka-text: #18181b;
  --ka-text-secondary: #71717a;
  --ka-placeholder: #a1a1aa;
  --ka-success: #16a34a;
  --ka-warning: #a16207;
  --ka-error: #dc2626;
  --consumer-sidebar-width: 288px;
  color: var(--ka-text);
  background: #fafafa;
}

.admin-shell {
  --ka-admin-sidebar-width: max(var(--ka-sidebar-width), var(--ka-sidebar-min-width));
}

.consumer-chat-shell {
  --consumer-sidebar-width: 360px;
}

.side-nav {
  position: fixed;
  z-index: 20;
  top: 0;
  bottom: 0;
  left: 0;
  display: flex;
  flex-direction: column;
  width: var(--ka-admin-sidebar-width, var(--ka-sidebar-width));
  border-right: 1px solid var(--ka-border);
  background: var(--ka-surface);
}

.consumer-shell .side-nav {
  width: var(--consumer-sidebar-width);
  padding: 16px;
  border-right: 1px solid var(--ka-border);
  background: rgb(255 255 255 / 84%);
  box-shadow: 1px 0 0 rgb(24 24 27 / 2%);
  backdrop-filter: blur(14px);
}

.consumer-chat-shell .side-nav {
  padding: 18px 16px 14px;
  background: #fff;
}

.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 28px 24px 24px;
}

.brand-copy {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.brand-mark {
  display: grid;
  flex: 0 0 auto;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 8px;
  color: #fff;
  background: var(--ka-primary);
  box-shadow: 0 10px 20px rgb(15 118 110 / 18%);
  font-size: 22px;
}

.brand-copy strong {
  color: var(--ka-primary-deep);
  font-size: 20px;
  font-weight: 800;
  line-height: 26px;
  white-space: nowrap;
}

.brand-copy span {
  color: var(--ka-text-secondary);
  font-size: 13px;
}

.consumer-start {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  margin: 8px 0 20px;
  border: 1px solid #27272a;
  border-radius: 12px;
  color: #fff;
  background: #18181b;
  box-shadow: 0 12px 28px rgb(24 24 27 / 10%);
  font-size: 14px;
  font-weight: 700;
  transition:
    background 0.16s ease,
    transform 0.16s ease;
}

.consumer-start:hover {
  background: #27272a;
  transform: translateY(-1px);
}

.nav-list {
  display: grid;
  gap: 8px;
  padding: 24px 12px;
}

.consumer-shell .nav-list {
  gap: 6px;
  padding: 0;
}

.consumer-shell .brand {
  gap: 12px;
  padding: 4px 4px 18px;
}

.nav-item {
  position: relative;
  display: flex;
  gap: 12px;
  align-items: center;
  min-height: 48px;
  padding: 0 16px;
  border-radius: 4px;
  color: #344054;
  font-weight: 600;
}

.consumer-shell .nav-item {
  min-height: 42px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--ka-text-secondary);
  font-size: 14px;
  font-weight: 600;
  transition:
    color 0.16s ease,
    background 0.16s ease,
    border-color 0.16s ease;
}

.consumer-shell .nav-item:hover {
  color: var(--ka-text);
  border-color: #eeeeef;
  background: #f4f4f5;
}

.nav-item:hover {
  background: var(--ka-surface-container);
}

.nav-item.router-link-active {
  color: var(--ka-primary);
  background: var(--ka-surface-high);
}

.consumer-shell .nav-item.router-link-active {
  color: var(--ka-text);
  border-color: var(--ka-border);
  background: #f4f4f5;
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 70%);
}

.nav-item.router-link-active::after {
  position: absolute;
  top: 0;
  right: 0;
  width: 4px;
  height: 100%;
  border-radius: 999px;
  background: var(--ka-primary);
  content: '';
}

.consumer-shell .nav-item.router-link-active::after {
  display: none;
}

.side-user {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-top: auto;
  padding: 16px 20px;
  border-top: 1px solid var(--ka-border);
}

.consumer-shell .side-user {
  margin: auto 0 0;
  padding: 12px;
  border: 1px solid var(--ka-border);
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 8px 24px rgb(24 24 27 / 4%);
}

.consumer-chat-shell .side-user {
  margin-top: 14px;
}

.avatar {
  display: grid;
  flex: 0 0 auto;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 50%;
  color: #fff;
  background: var(--ka-primary);
  font-size: 12px;
  font-weight: 800;
}

.consumer-shell .avatar {
  width: 40px;
  height: 40px;
  border: 1px solid var(--ka-border);
  border-radius: 12px;
  color: var(--ka-text);
  background: #f4f4f5;
}

.side-user-text {
  display: grid;
  min-width: 0;
  font-size: 13px;
  line-height: 18px;
}

.side-user-text span {
  color: var(--ka-text-secondary);
}

button.logout,
button.top-logout {
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
}

.logout {
  margin-left: auto;
  color: var(--ka-text-secondary);
}

.consumer-shell .logout,
.consumer-shell .top-logout {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--ka-text-secondary);
  transition:
    color 0.16s ease,
    background 0.16s ease,
    border-color 0.16s ease;
}

.consumer-shell .logout:hover,
.consumer-shell .top-logout:hover {
  color: var(--ka-error);
  border-color: #fee2e2;
  background: #fef2f2;
}

.top-bar {
  position: fixed;
  z-index: 15;
  top: 0;
  right: 0;
  left: var(--ka-admin-sidebar-width, var(--ka-sidebar-width));
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--ka-header-height);
  padding: 0 24px;
  border-bottom: 1px solid var(--ka-border);
  background: var(--ka-surface-lowest);
}

.consumer-shell .top-bar {
  left: var(--consumer-sidebar-width);
  height: 64px;
  border-bottom: 1px solid var(--ka-border);
  background: rgb(250 250 250 / 86%);
  backdrop-filter: blur(14px);
}

.kb-switcher {
  display: inline-flex;
  gap: 10px;
  align-items: center;
  min-height: 40px;
  padding: 0 14px;
  border-radius: 4px;
  color: var(--ka-text);
  background: var(--ka-surface-container);
  font-weight: 700;
}

.consumer-shell .kb-switcher {
  min-height: 40px;
  border: 1px solid var(--ka-border);
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 8px 20px rgb(24 24 27 / 4%);
}

.kb-switcher .el-icon {
  color: var(--ka-primary);
}

.consumer-icon {
  width: 18px;
  height: 18px;
  stroke-width: 2;
}

.brand-mark .consumer-icon {
  width: 22px;
  height: 22px;
}

.consumer-shell .brand-mark {
  width: 40px;
  height: 40px;
  border: 1px solid var(--ka-border);
  border-radius: 12px;
  color: var(--ka-text);
  background: #fff;
  box-shadow: 0 8px 20px rgb(24 24 27 / 5%);
}

.consumer-shell .brand-copy strong {
  color: var(--ka-text);
  font-size: 16px;
  line-height: 22px;
}

.consumer-shell .brand-copy span {
  color: var(--ka-text-secondary);
  font-size: 12px;
}

.top-actions {
  display: flex;
  gap: 18px;
  align-items: center;
}

.top-icon-button {
  color: #344054;
  font-weight: 600;
}

.consumer-shell .top-icon-button {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  min-height: 36px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--ka-text-secondary);
  transition:
    color 0.16s ease,
    background 0.16s ease,
    border-color 0.16s ease;
}

.consumer-shell .top-icon-button:hover {
  color: var(--ka-text);
  border-color: var(--ka-border);
  background: #fff;
}

.top-user {
  padding-left: 18px;
  border-left: 1px solid var(--ka-border);
  font-size: 14px;
}

.consumer-shell .top-user {
  padding: 8px 12px;
  border: 1px solid var(--ka-border);
  border-radius: 999px;
  background: #fff;
  color: var(--ka-text);
}

.top-user span {
  color: var(--ka-text-secondary);
}

.top-logout {
  color: #344054;
}

.app-main {
  min-height: 100vh;
  margin-left: var(--ka-admin-sidebar-width, var(--ka-sidebar-width));
  padding-top: var(--ka-header-height);
}

.consumer-shell .app-main {
  margin-left: var(--consumer-sidebar-width);
  padding-top: 64px;
  background: #fafafa;
}

@media (max-width: 960px) {
  .side-nav {
    width: 76px;
  }

  .consumer-shell .side-nav {
    width: 76px;
    padding: 14px;
  }

  .brand-copy span,
  .nav-item span,
  .side-user-text,
  .consumer-start span,
  .top-user {
    display: none;
  }

  .brand {
    padding-inline: 16px;
  }

  .consumer-start {
    width: 46px;
    min-height: 46px;
    margin: 8px 0 20px;
    border-radius: 12px;
  }

  .nav-item {
    justify-content: center;
    padding: 0;
  }

  .top-bar,
  .app-main {
    left: 76px;
    margin-left: 76px;
  }

  .consumer-shell .top-bar,
  .consumer-shell .app-main {
    left: 76px;
    margin-left: 76px;
  }
}

@media (max-width: 700px) {
  .consumer-shell .side-nav {
    display: none;
  }

  .consumer-shell .top-bar {
    left: 0;
    padding: 0 14px;
  }

  .consumer-shell .app-main {
    margin-left: 0;
  }

  .consumer-shell .top-actions {
    gap: 8px;
  }
}
</style>
