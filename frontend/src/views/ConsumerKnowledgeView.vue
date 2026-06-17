<script setup lang="ts">
import { BookOpen, FileText, MessageCircle, RefreshCw, Search } from '@lucide/vue'
import { ElButton, ElInput } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getAccessToken, listFiles, listKnowledgeBases } from '@/api/client'
import type { FileItem, KnowledgeBase } from '@/api/types'
import AppLayout from '@/components/AppLayout.vue'

const router = useRouter()
const knowledgeBases = ref<KnowledgeBase[]>([])
const files = ref<FileItem[]>([])
const activeKnowledgeBaseId = ref('')
const keyword = ref('')
const loading = ref(false)
const filesLoading = ref(false)
const errorMessage = ref('')

const filteredKnowledgeBases = computed(() => {
  const value = keyword.value.trim().toLocaleLowerCase()
  if (!value) {
    return knowledgeBases.value
  }
  return knowledgeBases.value.filter((knowledgeBase) =>
    [knowledgeBase.name, knowledgeBase.description ?? '']
      .join('\n')
      .toLocaleLowerCase()
      .includes(value),
  )
})

const activeKnowledgeBase = computed(
  () => knowledgeBases.value.find((item) => item.id === activeKnowledgeBaseId.value) ?? null,
)
const totalFileCount = computed(() =>
  knowledgeBases.value.reduce((total, item) => total + item.file_count, 0),
)
const totalChunkCount = computed(() =>
  knowledgeBases.value.reduce((total, item) => total + item.chunk_count, 0),
)

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
    const response = await listKnowledgeBases({ page: 1, page_size: 50 })
    knowledgeBases.value = response.items.filter((item) => item.status === 'active')
    activeKnowledgeBaseId.value = knowledgeBases.value[0]?.id ?? ''
    if (activeKnowledgeBaseId.value) {
      await loadFilesForActiveKnowledgeBase()
    } else {
      files.value = []
    }
  } catch (error) {
    handleError(error)
  } finally {
    loading.value = false
  }
}

async function selectKnowledgeBase(knowledgeBaseId: string): Promise<void> {
  activeKnowledgeBaseId.value = knowledgeBaseId
  await loadFilesForActiveKnowledgeBase()
}

async function loadFilesForActiveKnowledgeBase(): Promise<void> {
  if (!activeKnowledgeBaseId.value) {
    files.value = []
    return
  }
  filesLoading.value = true
  errorMessage.value = ''
  try {
    const response = await listFiles(activeKnowledgeBaseId.value, { page: 1, page_size: 50 })
    files.value = response.items
  } catch (error) {
    handleError(error)
  } finally {
    filesLoading.value = false
  }
}

async function openChat(knowledgeBaseId: string): Promise<void> {
  await router.push({ name: 'chat', query: { knowledge_base_id: knowledgeBaseId } })
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

function statusClass(status: string): string {
  if (status === 'indexed') return 'success'
  if (status === 'failed' || status === 'deleted') return 'danger'
  if (status === 'partially_indexed') return 'warning'
  if (status === 'uploaded' || status === 'queued') return 'muted'
  return 'processing'
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    uploaded: '已上传',
    queued: '排队中',
    parsing: '解析中',
    parsed: '已解析',
    chunking: '切分中',
    embedded: '已向量化',
    indexed: '已索引',
    partially_indexed: '部分索引',
    failed: '失败',
    deleted: '已删除',
  }
  return labels[status] ?? status
}

function handleError(error: unknown): void {
  errorMessage.value = error instanceof Error ? error.message : '操作失败，请稍后重试。'
}
</script>

<template>
  <AppLayout>
    <template #top-left>
      <div class="kb-switcher">
        <BookOpen class="lucide-icon" />
        <span>知识库</span>
      </div>
    </template>

    <section class="consumer-knowledge-page">
      <header class="page-heading">
        <h1>知识库</h1>
        <el-button :loading="loading" @click="loadKnowledgeBases">
          <RefreshCw class="lucide-icon" />
          刷新
        </el-button>
      </header>

      <section class="knowledge-hero">
        <div class="hero-card">
          <p>知识库已就绪</p>
          <h2>{{ knowledgeBases.length }} 个知识库可用于问答</h2>
          <span>查看管理员维护的已有知识，并进入问答页面基于单个知识库提问。</span>
        </div>
        <div class="usage-card">
          <span>已索引内容</span>
          <strong>{{ totalChunkCount }}</strong>
          <p>{{ totalFileCount }} 个文件</p>
          <div class="usage-bar">
            <i :style="{ width: knowledgeBases.length ? '68%' : '0%' }"></i>
          </div>
        </div>
      </section>

      <div class="knowledge-toolbar">
        <h2>我的知识库</h2>
        <el-input
          v-model="keyword"
          class="knowledge-search"
          placeholder="搜索知识库名称或描述..."
          size="large"
          clearable
        >
          <template #prefix>
            <Search class="input-icon" />
          </template>
        </el-input>
      </div>

      <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

      <section v-if="knowledgeBases.length === 0 && !loading" class="empty-state">
        <BookOpen class="empty-icon" />
        <h2>暂无可用知识库</h2>
        <p>请联系管理员维护知识库。</p>
      </section>

      <section v-else class="knowledge-grid" aria-label="知识库列表">
        <article
          v-for="knowledgeBase in filteredKnowledgeBases"
          :key="knowledgeBase.id"
          :class="['knowledge-card', { active: knowledgeBase.id === activeKnowledgeBaseId }]"
        >
          <button
            class="knowledge-main"
            type="button"
            @click="selectKnowledgeBase(knowledgeBase.id)"
          >
            <div class="knowledge-icon">
              <BookOpen class="lucide-icon" />
            </div>
            <div class="knowledge-copy">
              <span class="knowledge-status">已启用</span>
              <h2>{{ knowledgeBase.name }}</h2>
              <p>{{ knowledgeBase.description || '暂无描述' }}</p>
            </div>
          </button>
          <dl class="knowledge-metrics">
            <div>
              <dt>文件数</dt>
              <dd>{{ knowledgeBase.file_count }}</dd>
            </div>
            <div>
              <dt>Chunk 数</dt>
              <dd>{{ knowledgeBase.chunk_count }}</dd>
            </div>
            <div>
              <dt>更新时间</dt>
              <dd>{{ formatTime(knowledgeBase.updated_at) }}</dd>
            </div>
          </dl>
          <el-button type="primary" @click="openChat(knowledgeBase.id)">
            <MessageCircle class="lucide-icon" />
            进入问答
          </el-button>
        </article>
      </section>

      <section class="files-section">
        <div class="section-heading">
          <div>
            <h2>{{ activeKnowledgeBase?.name ?? '知识库文件' }}</h2>
            <p>只读查看当前知识库包含的文件。</p>
          </div>
          <el-button
            :loading="filesLoading"
            :disabled="!activeKnowledgeBaseId"
            @click="loadFilesForActiveKnowledgeBase"
          >
            <RefreshCw class="lucide-icon" />
            刷新文件
          </el-button>
        </div>

        <div class="files-card ka-card">
          <table class="ka-table">
            <thead>
              <tr>
                <th>文件名</th>
                <th>类型</th>
                <th>大小</th>
                <th>文件状态</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!activeKnowledgeBaseId">
                <td colspan="5" class="empty-cell">暂无可用知识库，请联系管理员维护知识库。</td>
              </tr>
              <tr v-else-if="files.length === 0">
                <td colspan="5" class="empty-cell">
                  {{ filesLoading ? '正在加载文件...' : '当前知识库暂无文件。' }}
                </td>
              </tr>
              <tr v-for="file in files" :key="file.id">
                <td>
                  <span class="file-name">
                    <FileText class="lucide-icon" />
                    <strong>{{ file.file_name }}</strong>
                  </span>
                </td>
                <td>{{ file.file_ext }}</td>
                <td>{{ formatBytes(file.size_bytes) }}</td>
                <td>
                  <span :class="['ka-status', statusClass(file.status)]">
                    {{ statusLabel(file.status) }}
                  </span>
                </td>
                <td>{{ formatTime(file.updated_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </section>
  </AppLayout>
</template>

<style scoped>
.kb-switcher {
  display: inline-flex;
  gap: 10px;
  align-items: center;
  min-height: 40px;
  padding: 0 14px;
  border-radius: 8px;
  color: var(--ka-text);
  background: var(--ka-surface-container);
  font-weight: 700;
}

.consumer-knowledge-page {
  display: grid;
  gap: 20px;
  padding: 24px 30px 40px;
  background:
    linear-gradient(90deg, rgb(15 118 110 / 4%) 0 1px, transparent 1px 100%),
    linear-gradient(180deg, #f7f8f6 0%, #eef1ef 100%);
  background-size:
    28px 100%,
    auto;
}

.page-heading {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.section-heading {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.page-heading h1,
.section-heading h2,
.knowledge-card h2,
.empty-state h2 {
  margin: 0;
  color: var(--ka-text);
}

.page-heading h1 {
  color: var(--ka-text);
  font-size: 28px;
  font-weight: 800;
  line-height: 36px;
}

.page-heading p,
.section-heading p,
.knowledge-card p,
.empty-state p {
  margin: 6px 0 0;
  color: var(--ka-text-secondary);
  line-height: 1.6;
}

.knowledge-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
}

.hero-card,
.usage-card {
  border: 1px solid var(--ka-border);
  border-radius: 8px;
  box-shadow: 0 12px 28px rgb(23 32 29 / 5%);
}

.hero-card {
  min-height: 128px;
  padding: 24px 26px;
  color: var(--ka-text);
  background: rgb(255 255 255 / 84%);
}

.hero-card p,
.hero-card h2,
.hero-card span,
.usage-card p {
  margin: 0;
}

.hero-card p {
  color: var(--ka-primary);
  font-size: 14px;
  font-weight: 800;
}

.hero-card h2 {
  margin-top: 10px;
  font-size: 26px;
  font-weight: 800;
  line-height: 34px;
}

.hero-card span {
  display: block;
  max-width: 650px;
  margin-top: 8px;
  color: var(--ka-text-secondary);
  font-size: 15px;
  line-height: 1.6;
}

.usage-card {
  display: grid;
  align-content: center;
  min-height: 128px;
  padding: 22px 24px;
  color: var(--ka-text);
  background: var(--ka-primary-soft);
}

.usage-card span {
  color: var(--ka-primary-deep);
  font-size: 15px;
  font-weight: 800;
}

.usage-card strong {
  margin-top: 10px;
  font-size: 42px;
  font-weight: 800;
  line-height: 1;
}

.usage-card p {
  margin-top: 8px;
  color: var(--ka-text-secondary);
}

.usage-bar {
  height: 8px;
  margin-top: 18px;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(15 118 110 / 14%);
}

.usage-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--ka-primary);
}

.knowledge-toolbar {
  display: flex;
  gap: 18px;
  align-items: center;
  justify-content: space-between;
}

.knowledge-toolbar h2 {
  margin: 0;
  color: var(--ka-text);
  font-size: 22px;
  font-weight: 800;
}

.knowledge-search {
  width: min(520px, 100%);
}

.error-message {
  padding: 12px 14px;
  border: 1px solid #ffd3cc;
  border-radius: 8px;
  margin: 0;
  color: var(--ka-error);
  background: #fff0ed;
}

.empty-state {
  display: grid;
  min-height: 260px;
  place-items: center;
  padding: 42px;
  border: 1px solid var(--ka-border);
  border-radius: 8px;
  background: rgb(255 255 255 / 76%);
  box-shadow: 0 12px 28px rgb(23 32 29 / 5%);
  text-align: center;
}

.empty-state .el-icon {
  color: var(--ka-primary);
  font-size: 42px;
}

.knowledge-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.knowledge-card {
  display: grid;
  gap: 16px;
  align-content: space-between;
  min-height: 238px;
  padding: 18px;
  border: 1px solid var(--ka-border);
  border-radius: 8px;
  background: rgb(255 255 255 / 88%);
  box-shadow: 0 10px 24px rgb(23 32 29 / 4%);
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.knowledge-card.active {
  border-color: var(--ka-primary);
  box-shadow: 0 12px 28px rgb(15 118 110 / 12%);
  transform: translateY(-2px);
}

.knowledge-main {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 14px;
  width: 100%;
  padding: 0;
  border: 0;
  color: inherit;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.knowledge-icon {
  display: grid;
  width: 56px;
  height: 56px;
  place-items: center;
  border-radius: 8px;
  color: var(--ka-primary-deep);
  background: var(--ka-primary-soft);
  font-size: 24px;
}

.knowledge-copy {
  min-width: 0;
}

.knowledge-card h2 {
  overflow: hidden;
  margin-top: 14px;
  font-size: 18px;
  line-height: 26px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-status {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 12px;
  border-radius: 6px;
  color: var(--ka-primary-deep);
  background: var(--ka-primary-soft);
  font-size: 12px;
  font-weight: 900;
}

.knowledge-card p {
  display: -webkit-box;
  min-height: 44px;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.knowledge-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.knowledge-metrics div {
  min-width: 0;
  padding: 12px;
  border-radius: 8px;
  background: #f4f7f5;
}

.knowledge-metrics dt {
  color: var(--ka-text-secondary);
  font-size: 12px;
}

.knowledge-metrics dd {
  overflow: hidden;
  margin: 4px 0 0;
  color: var(--ka-text);
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.files-section {
  display: grid;
  gap: 14px;
  margin-top: 6px;
}

.files-card {
  overflow: hidden;
  border-radius: 8px;
  background: rgb(255 255 255 / 84%);
  box-shadow: 0 10px 24px rgb(23 32 29 / 4%);
}

.files-card :deep(.ka-table th) {
  background: #f0f5f2;
}

.file-name {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.file-name .el-icon {
  flex: 0 0 auto;
  color: var(--ka-primary);
}

.empty-cell {
  padding: 38px 16px;
  color: var(--ka-text-secondary);
  text-align: center;
}

@media (max-width: 760px) {
  .consumer-knowledge-page {
    padding: 18px;
  }

  .knowledge-hero {
    grid-template-columns: 1fr;
  }

  .usage-card {
    min-height: 150px;
  }

  .page-heading,
  .section-heading,
  .knowledge-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .knowledge-metrics {
    grid-template-columns: 1fr;
  }

  .files-card {
    overflow-x: auto;
  }
}

/* User-facing shadcn/v0 visual layer. Scoped to the read-only consumer page. */
.lucide-icon,
.input-icon {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  stroke-width: 2;
}

.kb-switcher {
  min-height: 40px;
  border: 1px solid var(--ka-border);
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 8px 20px rgb(24 24 27 / 4%);
  font-weight: 600;
}

.consumer-knowledge-page {
  gap: 22px;
  min-height: calc(100vh - var(--ka-header-height));
  padding: 28px;
  background: #fafafa;
}

.page-heading h1 {
  color: #18181b;
  font-size: 28px;
  font-weight: 750;
}

.page-heading :deep(.el-button),
.section-heading :deep(.el-button),
.knowledge-card :deep(.el-button) {
  min-height: 38px;
  border-radius: 10px;
  transition:
    background 0.16s ease,
    border-color 0.16s ease,
    color 0.16s ease;
}

.page-heading :deep(.el-button:not(.el-button--primary)),
.section-heading :deep(.el-button:not(.el-button--primary)) {
  border-color: var(--ka-border);
  color: var(--ka-text-secondary);
  background: #fff;
}

.page-heading :deep(.el-button:not(.el-button--primary):hover),
.section-heading :deep(.el-button:not(.el-button--primary):hover) {
  border-color: var(--ka-border-strong);
  color: var(--ka-text);
  background: #f4f4f5;
}

.knowledge-card :deep(.el-button--primary) {
  --el-button-bg-color: #18181b;
  --el-button-border-color: #18181b;
  --el-button-hover-bg-color: #27272a;
  --el-button-hover-border-color: #27272a;
  width: 100%;
  font-weight: 700;
}

.knowledge-hero {
  grid-template-columns: minmax(0, 1fr) 320px;
}

.hero-card,
.usage-card,
.empty-state,
.knowledge-card,
.files-card {
  border: 1px solid var(--ka-border);
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(24 24 27 / 4%);
}

.hero-card {
  min-height: 126px;
  color: #18181b;
}

.hero-card p {
  color: var(--ka-text-secondary);
  font-size: 13px;
}

.hero-card h2 {
  font-size: 26px;
  font-weight: 750;
}

.usage-card {
  color: #fff;
  background: #18181b;
}

.usage-card span,
.usage-card p {
  color: #a1a1aa;
}

.usage-card strong {
  color: #fff;
}

.usage-bar {
  background: #27272a;
}

.usage-bar i {
  background: #fff;
}

.knowledge-search :deep(.el-input__wrapper) {
  min-height: 42px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 0 0 1px var(--ka-border) inset;
}

.empty-state {
  min-height: 250px;
}

.empty-icon {
  width: 42px;
  height: 42px;
  color: var(--ka-text-secondary);
  stroke-width: 1.8;
}

.knowledge-grid {
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
}

.knowledge-card {
  min-height: 230px;
  padding: 18px;
  transition:
    border-color 0.16s ease,
    background 0.16s ease,
    transform 0.16s ease,
    box-shadow 0.16s ease;
}

.knowledge-card:hover {
  border-color: var(--ka-border-strong);
  transform: translateY(-1px);
}

.knowledge-card.active {
  border-color: #18181b;
  box-shadow: 0 14px 36px rgb(24 24 27 / 8%);
}

.knowledge-icon {
  width: 48px;
  height: 48px;
  border: 1px solid var(--ka-border);
  border-radius: 14px;
  color: #18181b;
  background: #f4f4f5;
}

.knowledge-status {
  min-height: 24px;
  border: 1px solid var(--ka-border);
  border-radius: 999px;
  color: var(--ka-text-secondary);
  background: #fff;
}

.knowledge-metrics div {
  border: 1px solid var(--ka-border);
  border-radius: 12px;
  background: #fafafa;
}

.files-card {
  overflow: hidden;
}

.files-card :deep(.ka-table th) {
  background: #f4f4f5;
}

.files-card :deep(.ka-table tr:hover td) {
  background: #fafafa;
}

.file-name .lucide-icon {
  color: var(--ka-text-secondary);
}

@media (max-width: 760px) {
  .consumer-knowledge-page {
    padding: 18px 14px;
  }

  .knowledge-hero {
    grid-template-columns: 1fr;
  }
}
</style>
