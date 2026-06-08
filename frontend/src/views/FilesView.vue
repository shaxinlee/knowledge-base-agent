<script setup lang="ts">
import { Delete, RefreshRight, Search, Upload, View, Warning } from '@element-plus/icons-vue'
import { ElButton, ElIcon, ElInput, ElMessage, ElMessageBox, ElOption, ElSelect } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  ApiClientError,
  deleteFile,
  getAccessToken,
  getFileStatus,
  listFiles,
  listKnowledgeBases,
  retryParseFile,
  uploadFiles,
} from '@/api/client'
import type { FileItem, FileStatus, FileStatusResponse, KnowledgeBase } from '@/api/types'
import AppLayout from '@/components/AppLayout.vue'
import PageHeader from '@/components/PageHeader.vue'

const router = useRouter()
const knowledgeBases = ref<KnowledgeBase[]>([])
const activeKnowledgeBaseId = ref('')
const files = ref<FileItem[]>([])
const fileStatuses = ref<Record<string, FileStatusResponse>>({})
const keyword = ref('')
const statusFilter = ref<'all' | FileStatus>('all')
const loading = ref(false)
const uploading = ref(false)
const errorMessage = ref('')
const selectedFiles = ref<File[]>([])
const duplicateMessage = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

const activeKnowledgeBase = computed(
  () => knowledgeBases.value.find((item) => item.id === activeKnowledgeBaseId.value) ?? null,
)

const selectedFileSummary = computed(() => {
  if (selectedFiles.value.length === 0) {
    return '暂无待上传文件'
  }
  const totalSize = selectedFiles.value.reduce((total, file) => total + file.size, 0)
  return `${selectedFiles.value.length} 个文件，${formatBytes(totalSize)}`
})

onMounted(async () => {
  if (!getAccessToken()) {
    await router.push('/login')
    return
  }
  await loadKnowledgeBases()
})

async function loadKnowledgeBases(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await listKnowledgeBases()
    knowledgeBases.value = response.items.filter((item) => item.status === 'active')
    activeKnowledgeBaseId.value = knowledgeBases.value[0]?.id ?? ''
    if (activeKnowledgeBaseId.value) {
      await loadFiles()
    }
  } catch (error) {
    handleError(error)
  } finally {
    loading.value = false
  }
}

async function loadFiles(): Promise<void> {
  if (!activeKnowledgeBaseId.value) {
    files.value = []
    fileStatuses.value = {}
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await listFiles(activeKnowledgeBaseId.value, {
      page: 1,
      page_size: 50,
      keyword: keyword.value.trim() || undefined,
      status: statusFilter.value === 'all' ? undefined : statusFilter.value,
    })
    files.value = response.items
    await refreshVisibleStatuses(false)
  } catch (error) {
    handleError(error)
  } finally {
    loading.value = false
  }
}

async function refreshVisibleStatuses(showMessage = true): Promise<void> {
  const entries = await Promise.allSettled(files.value.map((file) => getFileStatus(file.id)))
  const nextStatuses = { ...fileStatuses.value }
  entries.forEach((entry, index) => {
    if (entry.status === 'fulfilled') {
      nextStatuses[files.value[index].id] = entry.value
    }
  })
  fileStatuses.value = nextStatuses
  if (showMessage) {
    ElMessage.success('状态已刷新')
  }
}

async function refreshFileStatus(file: FileItem): Promise<void> {
  try {
    const status = await getFileStatus(file.id)
    fileStatuses.value = {
      ...fileStatuses.value,
      [file.id]: status,
    }
    await loadFiles()
  } catch (error) {
    handleError(error)
  }
}

async function handleKnowledgeBaseChange(): Promise<void> {
  selectedFiles.value = []
  duplicateMessage.value = ''
  await loadFiles()
}

function openFilePicker(): void {
  fileInputRef.value?.click()
}

async function handleFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  selectedFiles.value = Array.from(input.files ?? [])
  duplicateMessage.value = ''
  if (selectedFiles.value.length > 0) {
    await submitUpload(false)
  }
}

async function submitUpload(force: boolean): Promise<void> {
  if (!activeKnowledgeBaseId.value || selectedFiles.value.length === 0) {
    return
  }
  uploading.value = true
  errorMessage.value = ''
  try {
    const response = await uploadFiles(activeKnowledgeBaseId.value, selectedFiles.value, force)
    duplicateMessage.value = ''
    selectedFiles.value = []
    resetFileInput()
    ElMessage.success(`已上传 ${response.uploaded.length} 个文件`)
    await loadFiles()
  } catch (error) {
    if (error instanceof ApiClientError && error.code === 'DUPLICATE_FILE_HASH') {
      duplicateMessage.value = describeDuplicateHash(error.details)
      return
    }
    handleError(error)
  } finally {
    uploading.value = false
  }
}

async function forceUpload(): Promise<void> {
  await submitUpload(true)
}

function clearSelectedFiles(): void {
  selectedFiles.value = []
  duplicateMessage.value = ''
  resetFileInput()
}

async function retryFile(file: FileItem): Promise<void> {
  try {
    await retryParseFile(file.id)
    ElMessage.success('已重新提交解析任务')
    await refreshFileStatus(file)
  } catch (error) {
    handleError(error)
  }
}

async function removeFile(file: FileItem): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除 ${file.file_name}？`, '删除文件', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deleteFile(file.id)
    ElMessage.success('文件已删除')
    await loadFiles()
  } catch (error) {
    if (error !== 'cancel') {
      handleError(error)
    }
  }
}

function resetFileInput(): void {
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

function statusClass(status: string | null | undefined): string {
  if (status === 'indexed') return 'success'
  if (status === 'failed' || status === 'cancelled' || status === 'deleted') return 'danger'
  if (status === 'partially_indexed') return 'warning'
  if (status === 'uploaded' || status === 'queued') return 'muted'
  return 'processing'
}

function parseStatus(file: FileItem): string {
  return fileStatuses.value[file.id]?.latest_parse_job?.status ?? '未查询'
}

function parseProgress(file: FileItem): number | null {
  return fileStatuses.value[file.id]?.latest_parse_job?.progress ?? null
}

function parseError(file: FileItem): string {
  const parseJob = fileStatuses.value[file.id]?.latest_parse_job
  if (!parseJob) {
    return ''
  }
  return [parseJob.error_code, parseJob.error_message].filter(Boolean).join(': ')
}

function parseDebug(file: FileItem): string {
  const logs = fileStatuses.value[file.id]?.latest_parse_job?.logs
  if (!logs) {
    return '-'
  }
  const latestState = logs.mineru_latest_state
  const parsedResult = logs.parsed_result
  if (typeof latestState === 'string') {
    return `MinerU: ${latestState}`
  }
  if (parsedResult && typeof parsedResult === 'object') {
    return 'parsed-results 已保存'
  }
  return '-'
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function describeDuplicateHash(details: Record<string, unknown>): string {
  const duplicates = details.duplicates
  if (!Array.isArray(duplicates) || duplicates.length === 0) {
    return '检测到相同内容文件，可选择强制上传。'
  }
  const first = duplicates[0] as {
    incoming_file_name?: string
    existing_file_name?: string
  }
  return `检测到 ${first.incoming_file_name ?? '待上传文件'} 与 ${first.existing_file_name ?? '已有文件'} 内容相同，可选择强制上传。`
}

function handleError(error: unknown): void {
  errorMessage.value = error instanceof Error ? error.message : '操作失败，请稍后重试。'
}
</script>

<template>
  <AppLayout>
    <template #top-left>
      <div class="kb-switcher">
        <el-icon><Upload /></el-icon>
        <el-select
          v-model="activeKnowledgeBaseId"
          placeholder="选择知识库"
          class="kb-select"
          :disabled="loading || knowledgeBases.length === 0"
          @change="handleKnowledgeBaseChange"
        >
          <el-option
            v-for="kb in knowledgeBases"
            :key="kb.id"
            :label="kb.name"
            :value="kb.id"
          />
        </el-select>
      </div>
    </template>

    <section class="content-page">
      <PageHeader
        title="文件管理"
        :subtitle="
          activeKnowledgeBase
            ? `当前知识库：${activeKnowledgeBase.name}`
            : '暂无 active 知识库'
        "
      >
        <template #actions>
          <input
            ref="fileInputRef"
            class="file-input"
            type="file"
            multiple
            accept=".pdf,.md,.docx,.txt,.xlsx,.xls,.csv,.pptx,.png,.jpg,.jpeg,.webp"
            @change="handleFileSelected"
          />
          <el-button
            type="primary"
            :loading="uploading"
            :disabled="!activeKnowledgeBaseId"
            @click="openFilePicker"
          >
            <el-icon><Upload /></el-icon>
            选择文件
          </el-button>
        </template>
      </PageHeader>

      <section class="upload-card ka-card">
        <div class="upload-zone" @click="openFilePicker">
          <el-icon><Upload /></el-icon>
          <strong>{{ selectedFileSummary }}</strong>
          <p>单文件最大 50MB，单次最多 50 个文件。</p>
          <p>支持 PDF、MD、DOCX、TXT、Excel、CSV、PPTX、PNG、JPG、JPEG、WEBP。</p>
        </div>
        <div class="upload-queue">
          <div>
            <strong>上传状态</strong>
            <span v-if="duplicateMessage" class="ka-status warning">Hash 重复</span>
            <span v-else class="ka-status muted">真实接口</span>
          </div>
          <p v-if="duplicateMessage" class="duplicate-warning">
            <el-icon><Warning /></el-icon>
            {{ duplicateMessage }}
          </p>
          <p v-else-if="errorMessage" class="error-message">{{ errorMessage }}</p>
          <p v-else>文件会保存到 MinIO，并创建 queued parse_job。</p>
          <div class="queue-actions">
            <el-button
              type="primary"
              :loading="uploading"
              :disabled="!duplicateMessage"
              @click="forceUpload"
            >
              强制上传
            </el-button>
            <el-button :disabled="selectedFiles.length === 0" @click="clearSelectedFiles">
              清空选择
            </el-button>
            <el-button :loading="loading" @click="loadFiles">刷新列表</el-button>
          </div>
        </div>
      </section>

      <div class="ka-toolbar">
        <el-input
          v-model="keyword"
          placeholder="搜索文件名..."
          class="toolbar-search"
          size="large"
          @keyup.enter="loadFiles"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select v-model="statusFilter" class="status-select" size="large">
          <el-option label="全部状态" value="all" />
          <el-option label="queued" value="queued" />
          <el-option label="processing" value="processing" />
          <el-option label="indexed" value="indexed" />
          <el-option label="partially_indexed" value="partially_indexed" />
          <el-option label="failed" value="failed" />
        </el-select>
        <el-button @click="keyword = ''; statusFilter = 'all'; loadFiles()">重置</el-button>
        <el-button type="primary" :loading="loading" @click="loadFiles">查询</el-button>
      </div>

      <section class="table-card ka-card">
        <table class="ka-table">
          <thead>
            <tr>
              <th>文件名</th>
              <th>类型</th>
              <th>大小</th>
              <th>文件状态</th>
              <th>解析任务</th>
              <th>进度</th>
              <th>解析详情</th>
              <th>错误信息</th>
              <th>更新时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="files.length === 0">
              <td colspan="10" class="empty-cell">
                {{ loading ? '正在加载文件...' : '当前知识库暂无文件' }}
              </td>
            </tr>
            <tr v-for="file in files" :key="file.id">
              <td>
                <strong>{{ file.file_name }}</strong>
                <span class="file-hash">{{ file.file_hash.slice(0, 12) }}</span>
              </td>
              <td>{{ file.file_ext }}</td>
              <td>{{ formatBytes(file.size_bytes) }}</td>
              <td>
                <span :class="['ka-status', statusClass(file.status)]">{{ file.status }}</span>
              </td>
              <td>
                <span :class="['ka-status', statusClass(parseStatus(file))]">{{
                  parseStatus(file)
                }}</span>
              </td>
              <td>{{ parseProgress(file) ?? '-' }}</td>
              <td class="debug-cell">{{ parseDebug(file) }}</td>
              <td class="error-cell">{{ parseError(file) || '-' }}</td>
              <td>{{ formatTime(file.updated_at) }}</td>
              <td>
                <div class="ka-actions">
                  <RouterLink class="ka-link-button" :to="{ name: 'chunks', query: { file_id: file.id } }">
                    <el-icon><View /></el-icon>
                    Chunk
                  </RouterLink>
                  <button class="ka-link-button" @click="refreshFileStatus(file)">
                    <el-icon><RefreshRight /></el-icon>
                    刷新状态
                  </button>
                  <button class="ka-link-button" @click="retryFile(file)">
                    <el-icon><RefreshRight /></el-icon>
                    重新解析
                  </button>
                  <button class="ka-link-button ka-danger-link" @click="removeFile(file)">
                    <el-icon><Delete /></el-icon>
                    删除
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </section>
  </AppLayout>
</template>

<style scoped>
.content-page {
  padding: 24px;
}

.file-input {
  display: none;
}

.upload-card {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 18px;
  padding: 18px;
  margin-bottom: 18px;
}

.upload-zone {
  display: grid;
  min-height: 190px;
  place-items: center;
  padding: 24px;
  border: 2px dashed #cfd4e7;
  border-radius: 8px;
  color: var(--ka-text-secondary);
  text-align: center;
  cursor: pointer;
}

.upload-zone:hover {
  border-color: var(--ka-primary);
  background: var(--ka-surface-high);
}

.upload-zone .el-icon {
  color: var(--ka-primary);
  font-size: 34px;
}

.upload-zone strong {
  color: var(--ka-text);
  font-size: 16px;
}

.upload-zone p,
.upload-queue p {
  max-width: 640px;
  margin: 0;
  line-height: 1.6;
}

.upload-queue {
  display: grid;
  align-content: center;
  gap: 16px;
  padding: 22px;
  border-radius: 8px;
  background: #fff8f1;
}

.upload-queue > div:first-child {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.duplicate-warning {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  color: #8a4b0a;
}

.error-message {
  color: #b42318;
}

.queue-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.toolbar-search {
  flex: 1 1 360px;
}

.status-select {
  width: 180px;
}

.table-card {
  overflow: auto;
  margin-top: 18px;
}

.file-hash {
  display: block;
  margin-top: 5px;
  color: var(--ka-placeholder);
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

.error-cell {
  max-width: 260px;
  color: var(--ka-text-secondary);
}

.empty-cell {
  padding: 36px;
  color: var(--ka-text-secondary);
  text-align: center;
}

@media (max-width: 1080px) {
  .upload-card {
    grid-template-columns: 1fr;
  }
}
</style>
