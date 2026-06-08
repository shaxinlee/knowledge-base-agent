<script setup lang="ts">
import {
  ChatDotRound,
  Collection,
  DataAnalysis,
  FolderOpened,
  Refresh,
  SwitchButton,
  User,
} from '@element-plus/icons-vue'
import { ElButton, ElIcon } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  clearAuthTokens,
  getAccessToken,
  getCurrentUser,
  getRefreshToken,
  logout,
} from '@/api/client'
import type { User as AuthUser } from '@/api/types'

const navItems = [
  { label: '对话问答', path: '/chat', icon: ChatDotRound },
  { label: '知识库', path: '/knowledge-bases', icon: Collection },
  { label: '文件管理', path: '/files', icon: FolderOpened },
  { label: '用户管理', path: '/users', icon: User },
  { label: '审计日志', path: '/audit-logs', icon: DataAnalysis },
  { label: '个人资料', path: '/profile', icon: User },
]

const router = useRouter()
const currentUser = ref<AuthUser | null>(null)

const displayName = computed(
  () => currentUser.value?.display_name || currentUser.value?.username || '未登录',
)
const roleLabel = computed(() => currentUser.value?.role ?? '-')
const avatarText = computed(() => {
  const source = displayName.value.trim() || currentUser.value?.username || 'KB'
  return source.slice(0, 2).toUpperCase()
})

onMounted(async () => {
  if (!getAccessToken()) {
    return
  }
  try {
    currentUser.value = await getCurrentUser()
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
  <div class="app-shell">
    <aside class="side-nav">
      <RouterLink class="brand" to="/chat">
        <strong>KB Agent</strong>
        <span>Enterprise SaaS</span>
      </RouterLink>

      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" class="nav-item" :to="item.path">
          <el-icon :size="22">
            <component :is="item.icon" />
          </el-icon>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="side-user">
        <div class="avatar">{{ avatarText }}</div>
        <div class="side-user-text">
          <strong>{{ displayName }}</strong>
          <span>{{ roleLabel }}</span>
        </div>
        <button class="logout" type="button" aria-label="退出登录" @click="handleLogout">
          <el-icon>
            <SwitchButton />
          </el-icon>
        </button>
      </div>
    </aside>

    <header class="top-bar">
      <slot name="top-left">
        <div class="kb-switcher">
          <el-icon>
            <Collection />
          </el-icon>
          <span>Agent-Assistant</span>
        </div>
      </slot>

      <div class="top-actions">
        <el-button link class="top-icon-button" @click="reloadPage">
          <el-icon>
            <Refresh />
          </el-icon>
          刷新
        </el-button>
        <div class="top-user">
          <span>当前用户：</span>
          <strong>{{ displayName }}</strong>
        </div>
        <button class="top-logout" type="button" aria-label="退出登录" @click="handleLogout">
          <el-icon>
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
.app-shell {
  min-height: 100vh;
  background: var(--ka-background);
}

.side-nav {
  position: fixed;
  z-index: 20;
  top: 0;
  bottom: 0;
  left: 0;
  display: flex;
  flex-direction: column;
  width: var(--ka-sidebar-width);
  border-right: 1px solid var(--ka-border);
  background: var(--ka-surface);
}

.brand {
  display: grid;
  gap: 4px;
  padding: 28px 24px 24px;
}

.brand strong {
  color: var(--ka-primary-deep);
  font-size: 20px;
  font-weight: 800;
  line-height: 26px;
}

.brand span {
  color: var(--ka-text-secondary);
  font-size: 13px;
}

.nav-list {
  display: grid;
  gap: 8px;
  padding: 24px 12px;
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

.nav-item:hover {
  background: var(--ka-surface-container);
}

.nav-item.router-link-active {
  color: var(--ka-primary);
  background: var(--ka-surface-high);
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

.side-user {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-top: auto;
  padding: 16px 20px;
  border-top: 1px solid var(--ka-border);
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

.top-bar {
  position: fixed;
  z-index: 15;
  top: 0;
  right: 0;
  left: var(--ka-sidebar-width);
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--ka-header-height);
  padding: 0 24px;
  border-bottom: 1px solid var(--ka-border);
  background: var(--ka-surface-lowest);
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

.kb-switcher .el-icon {
  color: var(--ka-primary);
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

.top-user {
  padding-left: 18px;
  border-left: 1px solid var(--ka-border);
  font-size: 14px;
}

.top-user span {
  color: var(--ka-text-secondary);
}

.top-logout {
  color: #344054;
}

.app-main {
  min-height: 100vh;
  margin-left: var(--ka-sidebar-width);
  padding-top: var(--ka-header-height);
}

@media (max-width: 960px) {
  .side-nav {
    width: 76px;
  }

  .brand span,
  .nav-item span,
  .side-user-text,
  .top-user {
    display: none;
  }

  .brand {
    padding-inline: 16px;
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
}
</style>
