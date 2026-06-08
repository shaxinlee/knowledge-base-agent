<script setup lang="ts">
import { CopyDocument, Search } from '@element-plus/icons-vue'
import { ElButton, ElDialog, ElIcon, ElInput, ElMessage, ElOption, ElSelect } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getAccessToken, listAuditLogs } from '@/api/client'
import type { AuditLog } from '@/api/types'
import AppLayout from '@/components/AppLayout.vue'
import PageHeader from '@/components/PageHeader.vue'

const router = useRouter()
const logs = ref<AuditLog[]>([])
const actorId = ref('')
const action = ref('')
const resourceType = ref('')
const loading = ref(false)
const errorMessage = ref('')
const selectedLog = ref<AuditLog | null>(null)
const detailDialogVisible = ref(false)

const actionOptions = computed(() =>
  Array.from(new Set(logs.value.map((log) => log.action))).sort(),
)
const resourceTypeOptions = computed(() =>
  Array.from(new Set(logs.value.map((log) => log.resource_type))).sort(),
)

onMounted(async () => {
  if (!getAccessToken()) {
    await router.push('/login')
    return
  }
  await loadAuditLogs()
})

async function loadAuditLogs(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await listAuditLogs({
      page: 1,
      page_size: 50,
      actor_id: actorId.value.trim() || undefined,
      action: action.value || undefined,
      resource_type: resourceType.value || undefined,
    })
    logs.value = response.items
  } catch (error) {
    handleError(error)
  } finally {
    loading.value = false
  }
}

function resetFilters(): void {
  actorId.value = ''
  action.value = ''
  resourceType.value = ''
  void loadAuditLogs()
}

async function copyText(value: string): Promise<void> {
  await navigator.clipboard.writeText(value)
  ElMessage.success('已复制')
}

function openDetails(log: AuditLog): void {
  selectedLog.value = log
  detailDialogVisible.value = true
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value))
}

function formatDetails(details: Record<string, unknown>): string {
  return JSON.stringify(details, null, 2)
}

function formatAction(action: string): string {
  const labels: Record<string, string> = {
    create_knowledge_base: '创建知识库',
    update_knowledge_base: '更新知识库',
    delete_knowledge_base: '删除知识库',
    upload_file: '上传文件',
    delete_file: '删除文件',
    create_user: '创建用户',
    update_user: '更新用户',
    disable_user: '禁用用户',
    enable_user: '启用用户',
    reset_user_password: '重置密码',
  }
  return labels[action] ?? action
}

function formatResourceType(resourceType: string): string {
  const labels: Record<string, string> = {
    knowledge_base: '知识库',
    file: '文件',
    user: '用户',
  }
  return labels[resourceType] ?? resourceType
}

function shortId(value: string | null): string {
  if (!value) {
    return '-'
  }
  return value.length > 12 ? `${value.slice(0, 12)}...` : value
}

function handleError(error: unknown): void {
  errorMessage.value = error instanceof Error ? error.message : '操作失败，请稍后重试。'
}
</script>

<template>
  <AppLayout>
    <section class="content-page">
      <PageHeader title="审计日志" subtitle="查看系统高危操作记录，辅助安全追踪和问题排查。" />

      <div class="ka-toolbar">
        <el-input
          v-model="actorId"
          placeholder="Actor ID"
          class="toolbar-input"
          size="large"
          @keyup.enter="loadAuditLogs"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select v-model="action" clearable size="large" class="toolbar-input" placeholder="操作类型">
          <el-option
            v-for="item in actionOptions"
            :key="item"
            :label="formatAction(item)"
            :value="item"
          />
        </el-select>
        <el-select
          v-model="resourceType"
          clearable
          size="large"
          class="toolbar-input"
          placeholder="资源类型"
        >
          <el-option
            v-for="item in resourceTypeOptions"
            :key="item"
            :label="formatResourceType(item)"
            :value="item"
          />
        </el-select>
        <el-button @click="resetFilters">重置</el-button>
        <el-button type="primary" :loading="loading" @click="loadAuditLogs">查询</el-button>
      </div>

      <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

      <section class="table-card ka-card">
        <table class="ka-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>操作人</th>
              <th>操作类型</th>
              <th>资源类型</th>
              <th>资源 ID</th>
              <th>日志 ID</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="logs.length === 0">
              <td colspan="7" class="empty-cell">
                {{ loading ? '正在加载审计日志...' : '当前筛选条件下没有审计日志' }}
              </td>
            </tr>
            <tr v-for="log in logs" :key="log.id">
              <td>{{ formatTime(log.created_at) }}</td>
              <td>
                <code>{{ shortId(log.actor_id) }}</code>
              </td>
              <td>
                <span class="action-label">{{ formatAction(log.action) }}</span>
                <code v-if="formatAction(log.action) !== log.action">{{ log.action }}</code>
              </td>
              <td>{{ formatResourceType(log.resource_type) }}</td>
              <td>{{ shortId(log.resource_id) }}</td>
              <td>{{ shortId(log.id) }}</td>
              <td>
                <div class="ka-actions">
                  <button class="ka-link-button" @click="openDetails(log)">查看详情</button>
                  <button class="ka-link-button" @click="copyText(log.id)">
                    <el-icon><CopyDocument /></el-icon>
                    复制日志 ID
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <el-dialog v-model="detailDialogVisible" title="审计详情" width="620px">
        <dl v-if="selectedLog" class="detail-list">
          <dt>日志 ID</dt>
          <dd>{{ selectedLog.id }}</dd>
          <dt>操作人</dt>
          <dd>{{ selectedLog.actor_id }}</dd>
          <dt>操作类型</dt>
          <dd>
            <span class="action-label">{{ formatAction(selectedLog.action) }}</span>
            <code v-if="formatAction(selectedLog.action) !== selectedLog.action">
              {{ selectedLog.action }}
            </code>
          </dd>
          <dt>资源</dt>
          <dd>
            {{ formatResourceType(selectedLog.resource_type) }}
            <code>{{ selectedLog.resource_type }}</code>
            / {{ selectedLog.resource_id ?? '-' }}
          </dd>
          <dt>详情</dt>
          <dd>
            <pre>{{ formatDetails(selectedLog.details) }}</pre>
          </dd>
        </dl>
      </el-dialog>
    </section>
  </AppLayout>
</template>

<style scoped>
.content-page {
  padding: 24px;
}

.toolbar-input {
  width: 220px;
}

.table-card {
  overflow: auto;
  margin-top: 18px;
}

.error-message {
  margin: 16px 0 0;
  color: #b42318;
}

.empty-cell {
  padding: 36px;
  color: var(--ka-text-secondary);
  text-align: center;
}

code {
  color: var(--ka-primary);
  font-family: 'Courier New', monospace;
}

.action-label {
  display: inline-block;
  margin-right: 8px;
  color: var(--ka-text);
  font-weight: 700;
}

.detail-list {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 12px 16px;
  margin: 0;
}

.detail-list dt {
  color: var(--ka-text-secondary);
  font-weight: 700;
}

.detail-list dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
}

pre {
  max-height: 260px;
  padding: 12px;
  overflow: auto;
  border-radius: 6px;
  background: #f8f9fc;
  white-space: pre-wrap;
}
</style>
