<script setup lang="ts">
import { Refresh } from '@element-plus/icons-vue'
import { ElButton, ElIcon, ElInput } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { clearAuthTokens, getAccessToken, getCurrentUser } from '@/api/client'
import type { User } from '@/api/types'
import AppLayout from '@/components/AppLayout.vue'
import PageHeader from '@/components/PageHeader.vue'

const router = useRouter()
const currentUser = ref<User | null>(null)
const loading = ref(false)
const errorMessage = ref('')

const avatarText = computed(() => {
  const source = currentUser.value?.display_name || currentUser.value?.username || 'KB'
  return source.slice(0, 2).toUpperCase()
})
const statusLabel = computed(() => {
  if (!currentUser.value) {
    return '-'
  }
  return currentUser.value.is_active ? '启用' : '禁用'
})

onMounted(async () => {
  if (!getAccessToken()) {
    await router.push('/login')
    return
  }
  await loadProfile()
})

async function loadProfile(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    currentUser.value = await getCurrentUser()
  } catch (error) {
    clearAuthTokens()
    errorMessage.value = error instanceof Error ? error.message : '读取个人资料失败。'
    await router.push('/login')
  } finally {
    loading.value = false
  }
}

function formatTime(value: string | null): string {
  if (!value) {
    return '-'
  }
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}
</script>

<template>
  <AppLayout>
    <section class="content-page">
      <PageHeader title="个人资料" subtitle="查看当前登录账号信息。">
        <template #actions>
          <el-button :loading="loading" @click="loadProfile">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </template>
      </PageHeader>

      <section class="profile-card ka-card">
        <div class="profile-avatar">{{ avatarText }}</div>
        <div class="profile-form">
          <label>
            用户名
            <el-input :model-value="currentUser?.username ?? '-'" disabled size="large" />
          </label>
          <label>
            显示名
            <el-input :model-value="currentUser?.display_name ?? '-'" disabled size="large" />
          </label>
          <label>
            角色
            <el-input :model-value="currentUser?.role ?? '-'" disabled size="large" />
          </label>
          <label>
            账号状态
            <el-input :model-value="statusLabel" disabled size="large" />
          </label>
          <label>
            创建时间
            <el-input :model-value="formatTime(currentUser?.created_at ?? null)" disabled size="large" />
          </label>
          <label>
            最近登录
            <el-input
              :model-value="formatTime(currentUser?.last_login_at ?? null)"
              disabled
              size="large"
            />
          </label>
          <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
        </div>
      </section>
    </section>
  </AppLayout>
</template>

<style scoped>
.content-page {
  padding: 24px;
}

.profile-card {
  display: grid;
  grid-template-columns: 160px minmax(0, 560px);
  gap: 28px;
  padding: 32px;
}

.profile-avatar {
  display: grid;
  width: 96px;
  height: 96px;
  place-items: center;
  border-radius: 16px;
  color: #fff;
  background: var(--ka-primary);
  font-size: 26px;
  font-weight: 800;
}

.profile-form {
  display: grid;
  gap: 18px;
}

label {
  display: grid;
  gap: 8px;
  color: var(--ka-text);
  font-weight: 700;
}

.error-message {
  margin: 0;
  color: #b42318;
}

@media (max-width: 760px) {
  .profile-card {
    grid-template-columns: 1fr;
  }
}
</style>
