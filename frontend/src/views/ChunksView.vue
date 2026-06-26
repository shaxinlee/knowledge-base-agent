<script setup lang="ts">
import { ArrowLeft, CopyDocument, Picture, Refresh, Search } from '@element-plus/icons-vue'
import { ElButton, ElDialog, ElIcon, ElInput, ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getAccessToken, getFile, getFileStatus, listFileChunks } from '@/api/client'
import type { Chunk, FileItem, FileStatusResponse } from '@/api/types'
import AppLayout from '@/components/AppLayout.vue'
import PageHeader from '@/components/PageHeader.vue'
import { parseMarkdownDisplayBlocks, type MarkdownDisplayBlock } from '@/utils/markdownTables'

interface SelectedChunkImage {
  src: string
  alt: string
}

const route = useRoute()
const router = useRouter()
const file = ref<FileItem | null>(null)
const fileStatus = ref<FileStatusResponse | null>(null)
const chunks = ref<Chunk[]>([])
const loading = ref(false)
const errorMessage = ref('')
const chunkKeyword = ref('')
const locatorKeyword = ref('')
const chunkImageUrls = ref<Record<string, string>>({})
const chunkImageLoading = ref<Record<string, boolean>>({})
const chunkImageErrors = ref<Record<string, string>>({})
const selectedImage = ref<SelectedChunkImage | null>(null)

const fileId = computed(() => {
  const value = route.query.file_id
  return typeof value === 'string' ? value : ''
})

const filteredChunks = computed(() => {
  const chunkTerm = chunkKeyword.value.trim().toLowerCase()
  const locatorTerm = locatorKeyword.value.trim().toLowerCase()
  return chunks.value.filter((chunk) => {
    const searchable = [
      chunk.id,
      chunk.content,
      chunk.description ?? '',
      chunk.source_locator,
      ...chunk.asset_paths,
      ...chunk.document_block_types,
    ]
      .join('\n')
      .toLowerCase()
    const matchesChunk = !chunkTerm || searchable.includes(chunkTerm)
    const matchesLocator = !locatorTerm || chunk.source_locator.toLowerCase().includes(locatorTerm)
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

onBeforeUnmount(() => {
  revokeChunkImageUrls()
})

watch(fileId, async () => {
  await loadChunks()
})

async function loadChunks(): Promise<void> {
  revokeChunkImageUrls()
  selectedImage.value = null
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
    await preloadChunkImages(chunkResponse.items)
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

function modalityLabel(chunk: Chunk): string {
  if (chunk.modality === 'image') return '图片'
  if (chunk.modality === 'table') return '表格'
  return '文本'
}

function modalityClass(chunk: Chunk): string {
  if (chunk.modality === 'image') return 'image'
  if (chunk.modality === 'table') return 'table'
  return 'text'
}

function visibleImageUrls(chunk: Chunk): string[] {
  return chunk.image_urls.slice(0, 3)
}

function chunkImageKey(chunk: Chunk, sourceUrl: string, index: number): string {
  return `${chunk.id}:${index}:${sourceUrl}`
}

function chunkImageObjectUrl(chunk: Chunk, sourceUrl: string, index: number): string {
  return chunkImageUrls.value[chunkImageKey(chunk, sourceUrl, index)] ?? ''
}

function chunkImageError(chunk: Chunk, sourceUrl: string, index: number): string {
  return chunkImageErrors.value[chunkImageKey(chunk, sourceUrl, index)] ?? ''
}

function isChunkImageLoading(chunk: Chunk, sourceUrl: string, index: number): boolean {
  return Boolean(chunkImageLoading.value[chunkImageKey(chunk, sourceUrl, index)])
}

async function preloadChunkImages(items: Chunk[]): Promise<void> {
  const imageItems = items.flatMap((chunk) =>
    visibleImageUrls(chunk).map((sourceUrl, index) => ({ chunk, sourceUrl, index })),
  )
  await Promise.all(
    imageItems.map(async ({ chunk, sourceUrl, index }) => {
      const key = chunkImageKey(chunk, sourceUrl, index)
      chunkImageLoading.value = { ...chunkImageLoading.value, [key]: true }
      try {
        const objectUrl = await loadAuthorizedAssetObjectUrl(sourceUrl)
        chunkImageUrls.value = { ...chunkImageUrls.value, [key]: objectUrl }
      } catch {
        chunkImageErrors.value = { ...chunkImageErrors.value, [key]: '图片无法加载' }
      } finally {
        chunkImageLoading.value = { ...chunkImageLoading.value, [key]: false }
      }
    }),
  )
}

async function loadAuthorizedAssetObjectUrl(sourceUrl: string): Promise<string> {
  if (sourceUrl.startsWith('data:image/')) {
    return sourceUrl
  }
  const token = getAccessToken()
  const response = await fetch(sourceUrl, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    throw new Error('Image request failed.')
  }
  return URL.createObjectURL(await response.blob())
}

function revokeChunkImageUrls(): void {
  Object.values(chunkImageUrls.value).forEach((url) => {
    if (url.startsWith('blob:')) {
      URL.revokeObjectURL(url)
    }
  })
  chunkImageUrls.value = {}
  chunkImageLoading.value = {}
  chunkImageErrors.value = {}
}

function openImagePreview(src: string, alt: string): void {
  selectedImage.value = { src, alt }
}

function handleImageDialogOpenChange(open: boolean): void {
  if (!open) {
    selectedImage.value = null
  }
}

function displayBlocks(chunk: Chunk): MarkdownDisplayBlock[] {
  return parseMarkdownDisplayBlocks(chunk.content.split(/\r?\n/), normalizeDisplayText)
}

function normalizeDisplayText(content: string): string {
  return decodeHtmlEntities(stripHtmlTags(content))
}

function decodeHtmlEntities(content: string): string {
  const textarea = document.createElement('textarea')
  textarea.innerHTML = content
  return textarea.value
}

function stripHtmlTags(content: string): string {
  return content
    .replace(/<\s*br\s*\/?\s*>/gi, '\n')
    .replace(/<\/\s*(p|div|section|article|tr|h[1-6])\s*>/gi, '\n')
    .replace(/<\/\s*(td|th)\s*>\s*<\s*(td|th)\b[^>]*>/gi, ' | ')
    .replace(/<[^>]+>/g, '')
    .trim()
}

function metadataEntries(chunk: Chunk): Array<{ label: string; value: string }> {
  const metadata = chunk.metadata ?? {}
  return [
    { label: '描述状态', value: stringifyMetadataValue(metadata.description_status) },
    { label: '描述模型', value: stringifyMetadataValue(metadata.description_model) },
    { label: '描述错误', value: stringifyMetadataValue(metadata.description_error) },
    { label: '切分原因', value: stringifyMetadataValue(metadata.split_reason) },
    { label: '来源文件', value: stringifyMetadataValue(metadata.source_name) },
  ].filter((item) => item.value)
}

function stringifyMetadataValue(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return ''
  }
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join(', ')
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

function metadataJson(chunk: Chunk): string {
  return JSON.stringify(chunk.metadata ?? {}, null, 2)
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
        subtitle="查看文件解析后生成的切片、source locator、图片、表格和描述。"
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
          <strong :class="['ka-status', statusClass(file?.status)]">{{
            file?.status ?? '-'
          }}</strong>
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
        <el-input
          v-model="chunkKeyword"
          placeholder="Chunk ID、内容、描述或资源路径搜索"
          class="toolbar-search"
          size="large"
        >
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
            <header class="chunk-header">
              <div>
                <h2>{{ formatChunkTitle(chunk) }}</h2>
                <span class="locator">{{ chunk.source_locator }}</span>
              </div>
              <span :class="['modality-tag', modalityClass(chunk)]">
                {{ modalityLabel(chunk) }}
              </span>
            </header>

            <div class="chunk-meta">
              <span>{{ chunk.token_count }} tokens</span>
              <span>{{ chunk.is_active ? 'active' : 'inactive' }}</span>
              <span>{{ chunk.id }}</span>
            </div>

            <section v-if="visibleImageUrls(chunk).length" class="chunk-section">
              <h3>
                <el-icon><Picture /></el-icon>
                图片
              </h3>
              <div class="image-grid">
                <div
                  v-for="(sourceUrl, index) in visibleImageUrls(chunk)"
                  :key="chunkImageKey(chunk, sourceUrl, index)"
                  class="image-preview"
                >
                  <button
                    v-if="chunkImageObjectUrl(chunk, sourceUrl, index)"
                    type="button"
                    @click="
                      openImagePreview(
                        chunkImageObjectUrl(chunk, sourceUrl, index),
                        chunk.image_alt || chunk.source_locator,
                      )
                    "
                  >
                    <img
                      :src="chunkImageObjectUrl(chunk, sourceUrl, index)"
                      :alt="chunk.image_alt || chunk.source_locator"
                    />
                  </button>
                  <div v-else class="image-state">
                    {{
                      isChunkImageLoading(chunk, sourceUrl, index)
                        ? '图片加载中'
                        : chunkImageError(chunk, sourceUrl, index) || '图片无法加载'
                    }}
                  </div>
                </div>
              </div>
            </section>

            <section v-if="chunk.description" class="chunk-section description-section">
              <h3>关联描述</h3>
              <p>{{ chunk.description }}</p>
            </section>

            <section class="chunk-section">
              <h3>{{ chunk.modality === 'table' ? '表格 / 原文' : '内容' }}</h3>
              <template v-for="block in displayBlocks(chunk)" :key="block.key">
                <p v-if="block.type === 'paragraph'" class="content-paragraph">
                  {{ block.text }}
                </p>
                <p v-else-if="block.type === 'heading'" class="content-heading">
                  {{ block.text }}
                </p>
                <ul v-else-if="block.type === 'list'" class="content-list">
                  <li v-for="(item, index) in block.items" :key="index">
                    {{ item }}
                  </li>
                </ul>
                <blockquote v-else-if="block.type === 'quote'" class="content-quote">
                  <p v-for="(line, index) in block.lines" :key="index">
                    {{ line }}
                  </p>
                </blockquote>
                <pre v-else-if="block.type === 'code'" class="content-code"><code>{{ block.code }}</code></pre>
                <div v-else-if="block.type === 'table'" class="chunk-table-wrap">
                  <table class="chunk-table">
                    <thead>
                      <tr>
                        <th v-for="(header, headerIndex) in block.headers" :key="headerIndex">
                          {{ header }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, rowIndex) in block.rows" :key="rowIndex">
                        <td v-for="(cell, cellIndex) in row" :key="cellIndex">
                          {{ cell }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </template>
            </section>
          </div>

          <aside class="chunk-side">
            <div class="chunk-actions">
              <button class="ka-link-button" @click="copyText(chunk.id)">
                <el-icon><CopyDocument /></el-icon>
                复制 Chunk ID
              </button>
              <button class="ka-link-button" @click="copyText(chunk.source_locator)">
                <el-icon><CopyDocument /></el-icon>
                复制 Source Locator
              </button>
              <button
                v-if="chunk.description"
                class="ka-link-button"
                @click="copyText(chunk.description)"
              >
                <el-icon><CopyDocument /></el-icon>
                复制描述
              </button>
            </div>

            <section class="related-panel">
              <h3>关联信息</h3>
              <dl>
                <template v-if="chunk.asset_paths.length">
                  <dt>asset paths</dt>
                  <dd>
                    <code v-for="assetPath in chunk.asset_paths" :key="assetPath">
                      {{ assetPath }}
                    </code>
                  </dd>
                </template>
                <template v-if="chunk.document_block_types.length">
                  <dt>block types</dt>
                  <dd>
                    <span
                      v-for="blockType in chunk.document_block_types"
                      :key="blockType"
                      class="info-pill"
                    >
                      {{ blockType }}
                    </span>
                  </dd>
                </template>
                <template v-for="item in metadataEntries(chunk)" :key="item.label">
                  <dt>{{ item.label }}</dt>
                  <dd>{{ item.value }}</dd>
                </template>
              </dl>
              <details class="metadata-details">
                <summary>完整 metadata</summary>
                <pre>{{ metadataJson(chunk) }}</pre>
              </details>
              <button class="ka-link-button" @click="copyText(metadataJson(chunk))">
                <el-icon><CopyDocument /></el-icon>
                复制 metadata
              </button>
            </section>
          </aside>
        </article>
      </section>

      <el-dialog
        :model-value="Boolean(selectedImage)"
        @update:model-value="handleImageDialogOpenChange"
        title="图片预览"
        width="min(900px, 92vw)"
        class="chunk-image-dialog"
      >
        <img
          v-if="selectedImage"
          class="dialog-image"
          :src="selectedImage.src"
          :alt="selectedImage.alt"
        />
      </el-dialog>
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
  grid-template-columns: minmax(0, 1fr) minmax(260px, 320px);
  gap: 24px;
  padding: 22px 24px;
}

.chunk-header {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.chunk-main h2 {
  margin: 0 0 8px;
  font-size: 16px;
}

.locator {
  display: inline-flex;
  max-width: 100%;
  padding: 4px 10px;
  overflow-wrap: anywhere;
  border-radius: 999px;
  color: var(--ka-primary);
  background: #e8f0ff;
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

.modality-tag {
  flex: 0 0 auto;
  min-width: 42px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  text-align: center;
}

.modality-tag.text {
  color: var(--ka-text-secondary);
  background: #eef0f5;
}

.modality-tag.table {
  color: #7a4a00;
  background: #fff3d6;
}

.modality-tag.image {
  color: var(--ka-primary);
  background: #e8f0ff;
}

.chunk-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  margin: 14px 0;
  color: var(--ka-placeholder);
  font-size: 12px;
}

.chunk-section {
  display: grid;
  gap: 10px;
  margin-top: 18px;
}

.chunk-section h3,
.related-panel h3 {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  margin: 0;
  color: var(--ka-text);
  font-size: 14px;
}

.description-section {
  padding: 14px;
  border: 1px solid #d8e4ff;
  border-radius: 8px;
  background: #f7faff;
}

.description-section p,
.content-paragraph {
  margin: 0;
  color: var(--ka-text-secondary);
  line-height: 1.7;
  white-space: pre-wrap;
}

.content-heading {
  margin: 10px 0 6px;
  color: var(--ka-text);
  font-weight: 800;
  line-height: 1.4;
}

.content-list {
  display: grid;
  gap: 6px;
  margin: 0;
  padding-left: 20px;
  color: var(--ka-text-secondary);
  line-height: 1.6;
}

.content-quote {
  margin: 0;
  padding: 8px 12px;
  border-left: 3px solid var(--ka-primary);
  color: var(--ka-text-secondary);
  background: #f7f9ff;
}

.content-quote p {
  margin: 0 0 4px;
}

.content-quote p:last-child {
  margin-bottom: 0;
}

.content-code {
  max-width: 100%;
  margin: 0;
  padding: 10px 12px;
  overflow-x: auto;
  border-radius: 6px;
  color: var(--ka-text-secondary);
  background: #f4f5f8;
  font-size: 12px;
  line-height: 1.55;
}

.content-code code {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  white-space: pre;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.image-preview {
  min-height: 132px;
  border: 1px solid var(--ka-border);
  border-radius: 8px;
  background: #f8f9fc;
}

.image-preview button {
  display: block;
  width: 100%;
  height: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
}

.image-preview img {
  display: block;
  width: 100%;
  height: 180px;
  object-fit: contain;
}

.image-state {
  display: grid;
  min-height: 132px;
  place-items: center;
  padding: 16px;
  color: var(--ka-text-secondary);
  font-size: 13px;
}

.chunk-table-wrap {
  max-width: 100%;
  overflow-x: auto;
}

.chunk-table {
  width: 100%;
  min-width: 420px;
  border-collapse: collapse;
  font-size: 13px;
  line-height: 1.5;
  background: #fff;
}

.chunk-table th,
.chunk-table td {
  padding: 8px 10px;
  border: 1px solid var(--ka-border);
  text-align: left;
  vertical-align: top;
}

.chunk-table th {
  color: var(--ka-text);
  font-weight: 700;
  background: #eef1ff;
}

.chunk-table td {
  color: var(--ka-text-secondary);
}

.chunk-side {
  display: grid;
  align-content: start;
  gap: 18px;
}

.chunk-actions {
  display: grid;
  gap: 12px;
}

.related-panel {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--ka-border);
  border-radius: 8px;
  background: #fafbff;
}

.related-panel dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

.related-panel dt {
  color: var(--ka-placeholder);
  font-size: 12px;
}

.related-panel dd {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  color: var(--ka-text-secondary);
  overflow-wrap: anywhere;
  font-size: 13px;
}

.related-panel code,
.info-pill {
  padding: 3px 7px;
  border-radius: 4px;
  color: var(--ka-text-secondary);
  background: #eef0f5;
  font-size: 12px;
}

.metadata-details summary {
  color: var(--ka-primary);
  cursor: pointer;
}

.metadata-details pre {
  max-height: 220px;
  padding: 10px;
  overflow: auto;
  border-radius: 6px;
  color: var(--ka-text-secondary);
  background: #f4f5f8;
  font-size: 12px;
  white-space: pre-wrap;
}

.empty-card {
  padding: 30px;
  color: var(--ka-text-secondary);
  text-align: center;
}

.dialog-image {
  display: block;
  max-width: 100%;
  max-height: 72vh;
  margin: 0 auto;
  object-fit: contain;
}

@media (max-width: 1080px) {
  .file-summary,
  .chunk-card {
    grid-template-columns: 1fr;
  }
}
</style>
