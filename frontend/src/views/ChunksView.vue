<script setup lang="ts">
import { ArrowLeft, CopyDocument, Refresh, Search } from '@element-plus/icons-vue'
import { ElButton, ElIcon, ElInput, ElMessage } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getAccessToken, getFile, getFileStatus, listFileChunks } from '@/api/client'
import type { Chunk, FileItem, FileStatusResponse } from '@/api/types'
import AppLayout from '@/components/AppLayout.vue'
import PageHeader from '@/components/PageHeader.vue'

const route = useRoute()
const router = useRouter()
const file = ref<FileItem | null>(null)
const fileStatus = ref<FileStatusResponse | null>(null)
const chunks = ref<Chunk[]>([])
const loading = ref(false)
const errorMessage = ref('')
const chunkKeyword = ref('')
const locatorKeyword = ref('')

const fileId = computed(() => {
  const value = route.query.file_id
  return typeof value === 'string' ? value : ''
})

const filteredChunks = computed(() => {
  const chunkTerm = chunkKeyword.value.trim().toLowerCase()
  const locatorTerm = locatorKeyword.value.trim().toLowerCase()
  return chunks.value.filter((chunk) => {
    const matchesChunk =
      !chunkTerm ||
      chunk.id.toLowerCase().includes(chunkTerm) ||
      chunk.content.toLowerCase().includes(chunkTerm)
    const matchesLocator =
      !locatorTerm || chunk.source_locator.toLowerCase().includes(locatorTerm)
    return matchesChunk && matchesLocator
  })
})

onMounted(async () => {
  if (!getAccessToken()) {
    await router.push('/login')
    return
  }
  await loadChunks()
})

watch(fileId, async () => {
  await loadChunks()
})

async function loadChunks(): Promise<void> {
  if (!fileId.value) {
    file.value = null
    fileStatus.value = null
    chunks.value = []
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const [fileResponse, statusResponse, chunkResponse] = await Promise.all([
      getFile(fileId.value),
      getFileStatus(fileId.value),
      listFileChunks(fileId.value, 1, 100),
    ])
    file.value = fileResponse
    fileStatus.value = statusResponse
    chunks.value = chunkResponse.items
  } catch (error) {
    handleError(error)
  } finally {
    loading.value = false
  }
}

function resetFilters(): void {
  chunkKeyword.value = ''
  locatorKeyword.value = ''
}

async function copyText(value: string): Promise<void> {
  await navigator.clipboard.writeText(value)
  ElMessage.success('已复制')
}

function statusClass(status: string | null | undefined): string {
  if (status === 'indexed') return 'success'
  if (status === 'failed' || status === 'cancelled' || status === 'deleted') return 'danger'
  if (status === 'partially_indexed') return 'warning'
  if (status === 'uploaded' || status === 'queued') return 'muted'
  return 'processing'
}

function parseStatus(): string {
  return fileStatus.value?.latest_parse_job?.status ?? '未查询'
}

function formatChunkTitle(chunk: Chunk): string {
  return `chunk-${chunk.id.slice(0, 8)}`
}

function handleError(error: unknown): void {
  errorMessage.value = error instanceof Error ? error.message : '操作失败，请稍后重试。'
}
</script>

<template>
  <AppLayout>
    <section class="content-page">
      <PageHeader
        title="Chunk 调试"
        subtitle="查看文件解析后生成的切片、source locator 和引用原文片段。"
      >
        <template #actions>
          <RouterLink to="/files">
            <el-button>
              <el-icon><ArrowLeft /></el-icon>
              返回文件列表
            </el-button>
          </RouterLink>
          <el-button type="primary" :loading="loading" :disabled="!fileId" @click="loadChunks">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </template>
      </PageHeader>

      <section v-if="!fileId" class="empty-card ka-card">
        请从文件列表选择一个文件查看 chunks。
      </section>

      <section v-else class="file-summary ka-card">
        <div>
          <span>文件名</span>
          <strong>{{ file?.file_name ?? '加载中' }}</strong>
        </div>
        <div>
          <span>文件状态</span>
          <strong :class="['ka-status', statusClass(file?.status)]">{{ file?.status ?? '-' }}</strong>
        </div>
        <div>
          <span>解析任务状态</span>
          <strong :class="['ka-status', statusClass(parseStatus())]">{{ parseStatus() }}</strong>
        </div>
        <div>
          <span>Chunk 总数</span>
          <strong>{{ chunks.length }}</strong>
        </div>
      </section>

      <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

      <div class="ka-toolbar">
        <el-input v-model="chunkKeyword" placeholder="Chunk ID 或内容搜索" class="toolbar-search" size="large">
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-input
          v-model="locatorKeyword"
          placeholder="source locator 搜索"
          class="toolbar-search"
          size="large"
        />
        <el-button @click="resetFilters">重置</el-button>
        <el-button type="primary" :loading="loading" @click="loadChunks">查询</el-button>
      </div>

      <section class="chunk-list">
        <article v-if="fileId && filteredChunks.length === 0" class="empty-card ka-card">
          {{ loading ? '正在加载 chunks...' : '当前文件暂无 active chunks' }}
        </article>
        <article v-for="chunk in filteredChunks" :key="chunk.id" class="chunk-card ka-card">
          <div class="chunk-main">
            <div>
              <h2>{{ formatChunkTitle(chunk) }}</h2>
              <span class="locator">{{ chunk.source_locator }}</span>
            </div>
            <div class="chunk-meta">
              <span>{{ chunk.token_count }} tokens</span>
              <span>{{ chunk.is_active ? 'active' : 'inactive' }}</span>
              <span>{{ chunk.id }}</span>
            </div>
            <p>{{ chunk.content }}</p>
          </div>
          <div class="chunk-actions">
            <button class="ka-link-button" @click="copyText(chunk.id)">
              <el-icon><CopyDocument /></el-icon>
              复制 Chunk ID
            </button>
            <button class="ka-link-button" @click="copyText(chunk.source_locator)">
              <el-icon><CopyDocument /></el-icon>
              复制 Source Locator
            </button>
          </div>
        </article>
      </section>
    </section>
  </AppLayout>
</template>

<style scoped>
.content-page {
  padding: 24px;
}

.file-summary {
  display: grid;
  grid-template-columns: 1.4fr repeat(3, minmax(0, 1fr));
  gap: 16px;
  padding: 20px 24px;
  margin-bottom: 18px;
}

.file-summary div {
  display: grid;
  gap: 8px;
}

.file-summary span {
  color: var(--ka-text-secondary);
  font-size: 12px;
}

.error-message {
  margin: 0 0 16px;
  color: #b42318;
}

.toolbar-search {
  flex: 1 1 260px;
}

.chunk-list {
  display: grid;
  gap: 16px;
  margin-top: 18px;
}

.chunk-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  padding: 22px 24px;
}

.chunk-main h2 {
  margin: 0 0 8px;
  font-size: 16px;
}

.locator {
  display: inline-flex;
  padding: 4px 10px;
  border-radius: 999px;
  color: var(--ka-primary);
  background: #e8f0ff;
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

.chunk-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  margin: 14px 0;
  color: var(--ka-placeholder);
  font-size: 12px;
}

.chunk-main p {
  margin: 0;
  color: var(--ka-text-secondary);
  line-height: 1.7;
}

.chunk-actions {
  display: grid;
  align-content: center;
  gap: 12px;
}

.empty-card {
  padding: 30px;
  color: var(--ka-text-secondary);
  text-align: center;
}

@media (max-width: 1080px) {
  .file-summary,
  .chunk-card {
    grid-template-columns: 1fr;
  }
}
</style>
