<script setup lang="ts">
import { Refresh } from '@element-plus/icons-vue'
import { RefreshCw, ShieldCheck, UserCircle } from '@lucide/vue'
import { ElButton, ElIcon, ElInput, ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  clearAuthTokens,
  getAccessToken,
  getAssistantProfile,
  getCurrentUser,
  updateAssistantProfile,
} from '@/api/client'
import type { AssistantProfile, User } from '@/api/types'
import AppLayout from '@/components/AppLayout.vue'
import PageHeader from '@/components/PageHeader.vue'

const router = useRouter()
const currentUser = ref<User | null>(null)
const loading = ref(false)
const profileSaving = ref(false)
const errorMessage = ref('')
const profileErrorMessage = ref('')
const assistantProfile = reactive<AssistantProfile>({
  name: '',
  identity_answer: '',
  capability_answer: '',
  greeting_answer: '',
  thanks_answer: '',
  usage_answer: '',
  handoff_answer: '',
  fallback_casual_answer: '',
})

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
const isAdmin = computed(() => currentUser.value?.role === 'admin')

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
    if (isAdmin.value) {
      await loadAssistantProfile()
    }
  } catch (error) {
    clearAuthTokens()
    errorMessage.value = error instanceof Error ? error.message : '读取个人资料失败。'
    await router.push('/login')
  } finally {
    loading.value = false
  }
}

async function loadAssistantProfile(): Promise<void> {
  profileErrorMessage.value = ''
  try {
    assignAssistantProfile(await getAssistantProfile())
  } catch (error) {
    profileErrorMessage.value =
      error instanceof Error ? error.message : '读取助手配置失败。'
  }
}

async function saveAssistantProfile(): Promise<void> {
  const payload = buildAssistantProfilePayload()
  if (Object.values(payload).some((value) => value.length === 0)) {
    profileErrorMessage.value = '助手配置字段不能为空。'
    return
  }
  profileSaving.value = true
  profileErrorMessage.value = ''
  try {
    assignAssistantProfile(await updateAssistantProfile(payload))
    ElMessage.success('助手配置已保存')
  } catch (error) {
    profileErrorMessage.value =
      error instanceof Error ? error.message : '保存助手配置失败。'
  } finally {
    profileSaving.value = false
  }
}

function assignAssistantProfile(profile: AssistantProfile): void {
  Object.assign(assistantProfile, profile)
}

function buildAssistantProfilePayload(): AssistantProfile {
  return {
    name: assistantProfile.name.trim(),
    identity_answer: assistantProfile.identity_answer.trim(),
    capability_answer: assistantProfile.capability_answer.trim(),
    greeting_answer: assistantProfile.greeting_answer.trim(),
    thanks_answer: assistantProfile.thanks_answer.trim(),
    usage_answer: assistantProfile.usage_answer.trim(),
    handoff_answer: assistantProfile.handoff_answer.trim(),
    fallback_casual_answer: assistantProfile.fallback_casual_answer.trim(),
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
    <section :class="['content-page', { 'consumer-profile-page': !isAdmin }]">
      <PageHeader v-if="isAdmin" title="个人资料" subtitle="查看当前登录账号信息。">
        <template #actions>
          <el-button :loading="loading" @click="loadProfile">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </template>
      </PageHeader>

      <header v-else class="consumer-profile-header">
        <div>
          <p>账户</p>
          <h1>个人资料</h1>
          <span>查看当前登录账号信息。</span>
        </div>
        <el-button :loading="loading" @click="loadProfile">
          <RefreshCw class="lucide-icon" />
          刷新
        </el-button>
      </header>

      <section class="profile-card ka-card">
        <div class="profile-avatar">
          <UserCircle v-if="!isAdmin" class="avatar-icon" />
          <span>{{ avatarText }}</span>
        </div>
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
            <div v-if="!isAdmin" class="status-pill">
              <ShieldCheck class="lucide-icon" />
              {{ statusLabel }}
            </div>
            <el-input v-else :model-value="statusLabel" disabled size="large" />
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

      <section v-if="isAdmin" class="assistant-profile-card ka-card">
        <div class="section-heading">
          <div>
            <h2>助手配置</h2>
            <p>配置常用问候、身份、能力和使用说明回答。</p>
          </div>
          <div class="section-actions">
            <el-button :disabled="profileSaving" @click="loadAssistantProfile">重载</el-button>
            <el-button type="primary" :loading="profileSaving" @click="saveAssistantProfile">
              保存
            </el-button>
          </div>
        </div>

        <div class="assistant-profile-form">
          <label>
            助手名称
            <el-input v-model="assistantProfile.name" size="large" />
          </label>
          <label>
            身份回答
            <el-input
              v-model="assistantProfile.identity_answer"
              type="textarea"
              :rows="3"
            />
          </label>
          <label>
            能力回答
            <el-input
              v-model="assistantProfile.capability_answer"
              type="textarea"
              :rows="3"
            />
          </label>
          <label>
            问候回答
            <el-input
              v-model="assistantProfile.greeting_answer"
              type="textarea"
              :rows="3"
            />
          </label>
          <label>
            感谢回答
            <el-input
              v-model="assistantProfile.thanks_answer"
              type="textarea"
              :rows="3"
            />
          </label>
          <label>
            使用说明回答
            <el-input
              v-model="assistantProfile.usage_answer"
              type="textarea"
              :rows="3"
            />
          </label>
          <label>
            转人工回答
            <el-input
              v-model="assistantProfile.handoff_answer"
              type="textarea"
              :rows="3"
            />
          </label>
          <label>
            闲聊兜底回答
            <el-input
              v-model="assistantProfile.fallback_casual_answer"
              type="textarea"
              :rows="3"
            />
          </label>
          <p v-if="profileErrorMessage" class="error-message">{{ profileErrorMessage }}</p>
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

.assistant-profile-card {
  display: grid;
  gap: 22px;
  margin-top: 24px;
  padding: 28px 32px;
}

.section-heading {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.section-heading h2 {
  margin: 0;
  font-size: 20px;
}

.section-heading p {
  margin: 6px 0 0;
  color: var(--ka-text-secondary);
}

.section-actions {
  display: flex;
  gap: 10px;
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

.assistant-profile-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
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

  .assistant-profile-form,
  .section-heading {
    grid-template-columns: 1fr;
  }

  .section-heading {
    display: grid;
  }
}

.consumer-profile-page {
  display: grid;
  gap: 22px;
  min-height: calc(100vh - var(--ka-header-height));
  padding: 28px;
  background: #fafafa;
}

.consumer-profile-header {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  width: min(100%, 960px);
}

.consumer-profile-header p,
.consumer-profile-header h1,
.consumer-profile-header span {
  margin: 0;
}

.consumer-profile-header p {
  color: var(--ka-text-secondary);
  font-size: 13px;
  font-weight: 700;
}

.consumer-profile-header h1 {
  margin-top: 4px;
  color: var(--ka-text);
  font-size: 28px;
  font-weight: 750;
  line-height: 36px;
}

.consumer-profile-header span {
  display: block;
  margin-top: 4px;
  color: var(--ka-text-secondary);
}

.consumer-profile-header :deep(.el-button) {
  min-height: 38px;
  border-color: var(--ka-border);
  border-radius: 10px;
  color: var(--ka-text-secondary);
  background: #fff;
  transition:
    background 0.16s ease,
    border-color 0.16s ease,
    color 0.16s ease;
}

.consumer-profile-header :deep(.el-button:hover) {
  border-color: var(--ka-border-strong);
  color: var(--ka-text);
  background: #f4f4f5;
}

.consumer-profile-page .profile-card {
  width: min(100%, 960px);
  grid-template-columns: 180px minmax(0, 1fr);
  border: 1px solid var(--ka-border);
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(24 24 27 / 4%);
}

.consumer-profile-page .profile-avatar {
  width: 112px;
  height: 112px;
  border: 1px solid var(--ka-border);
  border-radius: 20px;
  color: var(--ka-text);
  background: #f4f4f5;
  font-size: 18px;
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 80%);
}

.consumer-profile-page .profile-avatar span {
  margin-top: -18px;
  font-size: 16px;
}

.avatar-icon {
  width: 34px;
  height: 34px;
  margin-bottom: -16px;
  color: var(--ka-text-secondary);
  stroke-width: 1.8;
}

.consumer-profile-page label {
  color: var(--ka-text);
  font-size: 13px;
  font-weight: 650;
}

.consumer-profile-page :deep(.el-input__wrapper) {
  min-height: 42px;
  border-radius: 12px;
  background: #fafafa;
  box-shadow: 0 0 0 1px var(--ka-border) inset;
}

.status-pill {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  width: fit-content;
  min-height: 38px;
  padding: 0 12px;
  border: 1px solid var(--ka-border);
  border-radius: 999px;
  color: var(--ka-text);
  background: #fafafa;
  font-size: 14px;
  font-weight: 650;
}

.lucide-icon {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  stroke-width: 2;
}

@media (max-width: 760px) {
  .consumer-profile-page {
    padding: 18px 14px;
  }

  .consumer-profile-header {
    align-items: stretch;
    flex-direction: column;
  }

  .consumer-profile-page .profile-card {
    grid-template-columns: 1fr;
  }
}
</style>
