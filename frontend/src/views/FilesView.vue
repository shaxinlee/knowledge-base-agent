<script setup lang="ts">
import { Delete, RefreshRight, Search, Upload, View, Warning } from '@element-plus/icons-vue'
import { ElButton, ElIcon, ElInput, ElMessage, ElMessageBox, ElOption, ElSelect } from 'element-plus'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  ApiClientError,
  deleteFile,
  getAccessToken,
  getFileStatus,
  getFileSummary,
  listFiles,
  listKnowledgeBases,
  retryParseFile,
  retryFileSummary,
  uploadFiles,
} from '@/api/client'
import type {
  DocumentSummary,
  FileItem,
  FileStatus,
  FileStatusResponse,
  KnowledgeBase,
} from '@/api/types'
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
const summaryDrawerOpen = ref(false)
const summaryLoading = ref(false)
const summaryActionLoading = ref(false)
const summaryFile = ref<FileItem | null>(null)
const documentSummary = ref<DocumentSummary | null>(null)
let summaryPollTimer: number | null = null

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

onUnmounted(() => {
  stopSummaryPolling()
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

async function openFileSummary(file: FileItem): Promise<void> {
  summaryFile.value = file
  documentSummary.value = null
  summaryDrawerOpen.value = true
  await loadFileSummary()
}

async function loadFileSummary(showMessage = false): Promise<void> {
  if (!summaryFile.value) return
  summaryLoading.value = true
  try {
    documentSummary.value = await getFileSummary(summaryFile.value.id)
    if (showMessage) {
      ElMessage.success('摘要状态已刷新')
    }
    updateSummaryPolling()
  } catch (error) {
    stopSummaryPolling()
    handleError(error)
  } finally {
    summaryLoading.value = false
  }
}

async function triggerSummaryRetry(force: boolean): Promise<void> {
  if (!summaryFile.value) return
  if (force) {
    try {
      await ElMessageBox.confirm(
        '这会重新处理当前文档的全部 Chunk，并覆盖当前摘要结果。确认继续？',
        '重新生成摘要',
        {
          confirmButtonText: '重新生成',
          cancelButtonText: '取消',
          type: 'warning',
        },
      )
    } catch (error) {
      if (error === 'cancel') return
      throw error
    }
  }
  summaryActionLoading.value = true
  try {
    documentSummary.value = await retryFileSummary(summaryFile.value.id, force)
    ElMessage.success(force ? '已提交全文重新生成' : '已提交失败项重试')
    updateSummaryPolling()
  } catch (error) {
    handleError(error)
  } finally {
    summaryActionLoading.value = false
  }
}

function handleSummaryDrawerClosed(): void {
  stopSummaryPolling()
  summaryFile.value = null
  documentSummary.value = null
}

function updateSummaryPolling(): void {
  stopSummaryPolling()
  if (
    summaryDrawerOpen.value &&
    documentSummary.value &&
    ['pending', 'running'].includes(documentSummary.value.status)
  ) {
    summaryPollTimer = window.setTimeout(() => {
      void loadFileSummary()
    }, 4000)
  }
}

function stopSummaryPolling(): void {
  if (summaryPollTimer !== null) {
    window.clearTimeout(summaryPollTimer)
    summaryPollTimer = null
  }
}

function summaryStatusLabel(status: DocumentSummary['status']): string {
  const labels: Record<DocumentSummary['status'], string> = {
    pending: '等待处理',
    running: '并发抽取中',
    completed: '摘要完成',
    partially_completed: '部分完成',
    failed: '处理失败',
    not_ready: '等待 Chunk',
  }
  return labels[status]
}

function summaryStatusClass(status: DocumentSummary['status']): string {
  if (status === 'completed') return 'complete'
  if (status === 'partially_completed') return 'partial'
  if (status === 'failed') return 'failed'
  if (status === 'running') return 'running'
  return 'waiting'
}

function summaryProgress(summary: DocumentSummary): number {
  if (summary.chunk_total <= 0) return 0
  return Math.min(100, Math.round((summary.chunk_completed / summary.chunk_total) * 100))
}

function formatFullTime(value: string | null | undefined): string {
  if (!value) return '-'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value))
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
                <button class="file-name-button" @click="openFileSummary(file)">
                  {{ file.file_name }}
                </button>
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
                  <button class="ka-link-button summary-link" @click="openFileSummary(file)">
                    <el-icon><View /></el-icon>
                    查看摘要
                  </button>
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

    <el-drawer
      v-model="summaryDrawerOpen"
      class="summary-drawer"
      size="min(720px, 92vw)"
      :with-header="false"
      destroy-on-close
      @closed="handleSummaryDrawerClosed"
    >
      <div class="summary-panel">
        <header class="summary-panel-header">
          <div>
            <span class="summary-eyebrow">DOCUMENT INTELLIGENCE</span>
            <h2>{{ summaryFile?.file_name ?? '文档摘要' }}</h2>
            <p>逐 Chunk 并发抽取后，按原始顺序归并生成。</p>
          </div>
          <button
            class="summary-close"
            aria-label="关闭摘要"
            @click="summaryDrawerOpen = false"
          >
            ×
          </button>
        </header>

        <div v-if="summaryLoading && !documentSummary" class="summary-loading">
          <span class="summary-loader"></span>
          <strong>正在读取摘要任务</strong>
          <p>正在确认文档的 Chunk 处理进度。</p>
        </div>

        <template v-else-if="documentSummary">
          <section
            :class="['summary-status-rail', summaryStatusClass(documentSummary.status)]"
          >
            <div class="summary-status-copy">
              <span class="summary-status-dot"></span>
              <div>
                <strong>{{ summaryStatusLabel(documentSummary.status) }}</strong>
                <p v-if="documentSummary.status === 'running'">
                  已完成 {{ documentSummary.chunk_completed }} /
                  {{ documentSummary.chunk_total }} 个 Chunk
                </p>
                <p v-else-if="documentSummary.status === 'partially_completed'">
                  {{ documentSummary.chunk_failed }} 个 Chunk 未能成功抽取，摘要基于其余内容生成
                </p>
                <p v-else-if="documentSummary.status === 'not_ready'">
                  文档尚未生成可用 Chunk，解析完成后会自动开始
                </p>
                <p v-else>结构化抽取与文档归并状态</p>
              </div>
            </div>
            <span class="summary-percentage">{{ summaryProgress(documentSummary) }}%</span>
            <div class="summary-progress-track">
              <span :style="{ width: `${summaryProgress(documentSummary)}%` }"></span>
            </div>
          </section>

          <section class="summary-metrics">
            <div>
              <span>总 Chunk</span>
              <strong>{{ documentSummary.chunk_total }}</strong>
            </div>
            <div>
              <span>抽取成功</span>
              <strong>{{ documentSummary.chunk_succeeded }}</strong>
            </div>
            <div>
              <span>抽取失败</span>
              <strong>{{ documentSummary.chunk_failed }}</strong>
            </div>
            <div>
              <span>归并层级</span>
              <strong>{{ documentSummary.reduction_level }}</strong>
            </div>
          </section>

          <section v-if="documentSummary.summary" class="summary-reading">
            <div class="summary-reading-label">
              <span>文档摘要</span>
              <small>{{ documentSummary.model_name || '默认 LLM' }}</small>
            </div>
            <article>{{ documentSummary.summary }}</article>
          </section>

          <section
            v-else-if="documentSummary.status === 'pending' || documentSummary.status === 'running'"
            class="summary-awaiting"
          >
            <span class="summary-loader"></span>
            <div>
              <strong>摘要正在形成</strong>
              <p>多个 Chunk 正在并发抽取。已完成结果会即时保存，刷新或重启不会从头开始。</p>
            </div>
          </section>

          <section v-if="documentSummary.error_message" class="summary-error">
            <strong>{{ documentSummary.error_code || 'SUMMARY_FAILED' }}</strong>
            <p>{{ documentSummary.error_message }}</p>
          </section>

          <dl class="summary-details">
            <div>
              <dt>模型</dt>
              <dd>{{ documentSummary.model_name || '-' }}</dd>
            </div>
            <div>
              <dt>Chunk Prompt</dt>
              <dd>{{ documentSummary.chunk_prompt_version }}</dd>
            </div>
            <div>
              <dt>文档 Prompt</dt>
              <dd>{{ documentSummary.document_prompt_version }}</dd>
            </div>
            <div>
              <dt>更新时间</dt>
              <dd>{{ formatFullTime(documentSummary.updated_at) }}</dd>
            </div>
          </dl>

          <footer class="summary-actions">
            <el-button :loading="summaryLoading" @click="loadFileSummary(true)">
              刷新状态
            </el-button>
            <el-button
              v-if="documentSummary.status === 'failed' || documentSummary.status === 'partially_completed'"
              :loading="summaryActionLoading"
              @click="triggerSummaryRetry(false)"
            >
              重试失败项
            </el-button>
            <el-button
              v-if="documentSummary.status === 'completed' || documentSummary.status === 'partially_completed'"
              type="primary"
              :loading="summaryActionLoading"
              @click="triggerSummaryRetry(true)"
            >
              重新生成
            </el-button>
          </footer>
        </template>
      </div>
    </el-drawer>
  </AppLayout>
</template>

<style scoped>
.content-page {
  padding: 24px;
}

.file-input {
  display: none;
}

.file-name-button {
  display: block;
  max-width: 280px;
  padding: 0;
  border: 0;
  color: var(--ka-text);
  background: transparent;
  font: inherit;
  font-weight: 700;
  text-align: left;
  cursor: pointer;
}

.file-name-button:hover {
  color: var(--ka-primary);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.summary-link {
  color: var(--ka-primary);
}

:global(.summary-drawer .el-drawer__body) {
  padding: 0;
  background: #f4f3ee;
}

.summary-panel {
  min-height: 100%;
  color: #20231f;
  background:
    linear-gradient(rgba(31, 36, 31, 0.035) 1px, transparent 1px),
    #f4f3ee;
  background-size: 100% 28px;
}

.summary-panel-header {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 32px 36px 28px;
  border-bottom: 1px solid #d8d7ce;
  background: rgba(250, 249, 244, 0.94);
}

.summary-eyebrow {
  color: #657264;
  font-family: 'Courier New', monospace;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

.summary-panel-header h2 {
  max-width: 560px;
  margin: 8px 0 6px;
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 26px;
  line-height: 1.35;
}

.summary-panel-header p {
  margin: 0;
  color: #71766e;
  font-size: 13px;
}

.summary-close {
  width: 36px;
  height: 36px;
  border: 1px solid #c9c9bf;
  border-radius: 50%;
  color: #464b45;
  background: transparent;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
}

.summary-close:hover {
  border-color: #20231f;
  background: #20231f;
  color: #fff;
}

.summary-status-rail {
  position: relative;
  margin: 28px 36px 18px;
  padding: 20px 22px 24px;
  overflow: hidden;
  border: 1px solid #d1d2c9;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.76);
}

.summary-status-copy {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.summary-status-copy strong {
  font-size: 15px;
}

.summary-status-copy p {
  margin: 4px 0 0;
  color: #6d736b;
  font-size: 13px;
}

.summary-status-dot {
  width: 10px;
  height: 10px;
  margin-top: 5px;
  border-radius: 50%;
  background: #8b9489;
  box-shadow: 0 0 0 5px rgba(139, 148, 137, 0.12);
}

.summary-status-rail.running .summary-status-dot {
  background: #2e77d0;
  box-shadow: 0 0 0 5px rgba(46, 119, 208, 0.14);
  animation: summary-pulse 1.5s ease-in-out infinite;
}

.summary-status-rail.complete .summary-status-dot {
  background: #2d8a5f;
}

.summary-status-rail.partial .summary-status-dot {
  background: #b87822;
}

.summary-status-rail.failed .summary-status-dot {
  background: #c84c40;
}

.summary-percentage {
  position: absolute;
  top: 20px;
  right: 22px;
  font-family: 'Courier New', monospace;
  font-size: 20px;
  font-weight: 700;
}

.summary-progress-track {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 4px;
  background: #e0e0d8;
}

.summary-progress-track span {
  display: block;
  height: 100%;
  background: #2e77d0;
  transition: width 500ms ease;
}

.complete .summary-progress-track span {
  background: #2d8a5f;
}

.partial .summary-progress-track span {
  background: #b87822;
}

.failed .summary-progress-track span {
  background: #c84c40;
}

.summary-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  margin: 0 36px 24px;
  border-top: 1px solid #d6d6ce;
  border-left: 1px solid #d6d6ce;
}

.summary-metrics div {
  display: grid;
  gap: 7px;
  padding: 14px 16px;
  border-right: 1px solid #d6d6ce;
  border-bottom: 1px solid #d6d6ce;
  background: rgba(255, 255, 255, 0.5);
}

.summary-metrics span,
.summary-reading-label span {
  color: #777c74;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.summary-metrics strong {
  font-family: 'Courier New', monospace;
  font-size: 21px;
}

.summary-reading {
  margin: 0 36px 24px;
  padding: 26px 28px 30px;
  border: 1px solid #cfcec4;
  border-left: 4px solid #314f3c;
  background: #fffef9;
  box-shadow: 0 14px 36px rgba(50, 56, 49, 0.08);
}

.summary-reading-label {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e2e0d6;
}

.summary-reading-label small {
  color: #8a8d86;
  font-family: 'Courier New', monospace;
}

.summary-reading article {
  margin-top: 20px;
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 16px;
  line-height: 2;
  white-space: pre-wrap;
}

.summary-awaiting,
.summary-loading {
  display: flex;
  gap: 16px;
  align-items: center;
  margin: 28px 36px;
  padding: 26px;
  border: 1px dashed #bfc3ba;
  background: rgba(255, 255, 255, 0.55);
}

.summary-loading {
  display: grid;
  min-height: 180px;
  place-items: center;
  text-align: center;
}

.summary-awaiting p,
.summary-loading p {
  margin: 5px 0 0;
  color: #72776f;
  line-height: 1.6;
}

.summary-loader {
  display: block;
  width: 24px;
  height: 24px;
  border: 2px solid #c8ccc3;
  border-top-color: #2e77d0;
  border-radius: 50%;
  animation: summary-spin 900ms linear infinite;
}

.summary-error {
  margin: 0 36px 24px;
  padding: 18px 20px;
  border: 1px solid #e2bbb5;
  background: #fff3f1;
  color: #8f3028;
}

.summary-error p {
  margin: 6px 0 0;
  line-height: 1.6;
  word-break: break-word;
}

.summary-details {
  margin: 0 36px 24px;
  border-top: 1px solid #d6d6ce;
}

.summary-details div {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  padding: 11px 0;
  border-bottom: 1px solid #d6d6ce;
}

.summary-details dt {
  color: #777c74;
  font-size: 12px;
}

.summary-details dd {
  margin: 0;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  word-break: break-all;
}

.summary-actions {
  position: sticky;
  bottom: 0;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 18px 36px;
  border-top: 1px solid #d4d3ca;
  background: rgba(250, 249, 244, 0.96);
  backdrop-filter: blur(12px);
}

@keyframes summary-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes summary-pulse {
  50% {
    box-shadow: 0 0 0 9px rgba(46, 119, 208, 0.04);
  }
}

@media (max-width: 680px) {
  .summary-panel-header,
  .summary-actions {
    padding-right: 20px;
    padding-left: 20px;
  }

  .summary-status-rail,
  .summary-metrics,
  .summary-reading,
  .summary-awaiting,
  .summary-loading,
  .summary-error,
  .summary-details {
    margin-right: 20px;
    margin-left: 20px;
  }

  .summary-metrics {
    grid-template-columns: repeat(2, 1fr);
  }
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
