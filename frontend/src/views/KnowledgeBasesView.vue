<script setup lang="ts">
import { ChatDotRound, Delete, Edit, FolderOpened, Plus, Search, Upload } from '@element-plus/icons-vue'
import {
  ElButton,
  ElDialog,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElOption,
  ElSelect,
} from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  getAccessToken,
  listKnowledgeBases,
  updateKnowledgeBase,
} from '@/api/client'
import type { KnowledgeBase, KnowledgeBaseStatus } from '@/api/types'
import AppLayout from '@/components/AppLayout.vue'
import PageHeader from '@/components/PageHeader.vue'

const router = useRouter()
const knowledgeBases = ref<KnowledgeBase[]>([])
const keyword = ref('')
const statusFilter = ref<'all' | KnowledgeBaseStatus>('all')
const loading = ref(false)
const saving = ref(false)
const errorMessage = ref('')
const dialogVisible = ref(false)
const editingKnowledgeBase = ref<KnowledgeBase | null>(null)
const form = reactive({
  name: '',
  description: '',
})

const totalFiles = computed(() =>
  knowledgeBases.value.reduce((total, item) => total + item.file_count, 0),
)
const totalChunks = computed(() =>
  knowledgeBases.value.reduce((total, item) => total + item.chunk_count, 0),
)
const activeCount = computed(
  () => knowledgeBases.value.filter((item) => item.status === 'active').length,
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
    const response = await listKnowledgeBases({
      page: 1,
      page_size: 50,
      keyword: keyword.value.trim() || undefined,
      status: statusFilter.value === 'all' ? undefined : statusFilter.value,
    })
    knowledgeBases.value = response.items
  } catch (error) {
    handleError(error)
  } finally {
    loading.value = false
  }
}

function openCreateDialog(): void {
  editingKnowledgeBase.value = null
  form.name = ''
  form.description = ''
  dialogVisible.value = true
}

function openEditDialog(knowledgeBase: KnowledgeBase): void {
  editingKnowledgeBase.value = knowledgeBase
  form.name = knowledgeBase.name
  form.description = knowledgeBase.description ?? ''
  dialogVisible.value = true
}

async function saveKnowledgeBase(): Promise<void> {
  const name = form.name.trim()
  if (!name) {
    errorMessage.value = '知识库名称不能为空。'
    return
  }
  saving.value = true
  errorMessage.value = ''
  try {
    if (editingKnowledgeBase.value) {
      await updateKnowledgeBase(editingKnowledgeBase.value.id, {
        name,
        description: form.description.trim() || undefined,
      })
      ElMessage.success('知识库已更新')
    } else {
      await createKnowledgeBase({
        name,
        description: form.description.trim() || undefined,
      })
      ElMessage.success('知识库已创建')
    }
    dialogVisible.value = false
    await loadKnowledgeBases()
  } catch (error) {
    handleError(error)
  } finally {
    saving.value = false
  }
}

async function removeKnowledgeBase(knowledgeBase: KnowledgeBase): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除 ${knowledgeBase.name}？`, '删除知识库', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deleteKnowledgeBase(knowledgeBase.id)
    ElMessage.success('知识库已删除')
    await loadKnowledgeBases()
  } catch (error) {
    if (error !== 'cancel') {
      handleError(error)
    }
  }
}

function resetFilters(): void {
  keyword.value = ''
  statusFilter.value = 'all'
  void loadKnowledgeBases()
}

function statusClass(status: KnowledgeBaseStatus): string {
  if (status === 'active') return 'success'
  if (status === 'deleting') return 'warning'
  return 'danger'
}

function formatStatus(status: KnowledgeBaseStatus): string {
  const labels: Record<KnowledgeBaseStatus, string> = {
    active: 'active',
    deleting: 'deleting',
    deleted: 'deleted',
  }
  return labels[status]
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function handleError(error: unknown): void {
  errorMessage.value = error instanceof Error ? error.message : '操作失败，请稍后重试。'
}
</script>

<template>
  <AppLayout>
    <section class="content-page">
      <PageHeader title="知识库管理" subtitle="创建、维护和软删除知识库空间。">
        <template #actions>
          <el-button type="primary" @click="openCreateDialog">
            <el-icon><Plus /></el-icon>
            新建知识库
          </el-button>
        </template>
      </PageHeader>

      <section class="overview-card ka-card">
        <div>
          <h2>知识库概览</h2>
          <p>当前页面展示来自后端 KnowledgeBase API 的实时数据。</p>
        </div>
        <div class="metric-row">
          <div class="metric-box">
            <span>知识库数量</span>
            <strong>{{ knowledgeBases.length }}</strong>
          </div>
          <div class="metric-box">
            <span>active 空间</span>
            <strong>{{ activeCount }}</strong>
          </div>
          <div class="metric-box">
            <span>文件总数</span>
            <strong>{{ totalFiles }}</strong>
          </div>
          <div class="metric-box">
            <span>Chunk 总数</span>
            <strong>{{ totalChunks }}</strong>
          </div>
        </div>
      </section>

      <div class="ka-toolbar">
        <el-input
          v-model="keyword"
          placeholder="搜索知识库名称或描述..."
          class="toolbar-search"
          size="large"
          @keyup.enter="loadKnowledgeBases"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select v-model="statusFilter" size="large" class="status-select">
          <el-option label="active" value="all" />
          <el-option label="deleting" value="deleting" />
          <el-option label="deleted" value="deleted" />
        </el-select>
        <el-button @click="resetFilters">重置</el-button>
        <el-button type="primary" :loading="loading" @click="loadKnowledgeBases">查询</el-button>
      </div>

      <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

      <section class="kb-grid">
        <article v-if="knowledgeBases.length === 0" class="empty-card ka-card">
          {{ loading ? '正在加载知识库...' : '当前筛选条件下没有知识库' }}
        </article>
        <article v-for="kb in knowledgeBases" :key="kb.id" class="kb-card ka-card">
          <div class="kb-card-head">
            <div class="kb-icon">
              <el-icon><FolderOpened /></el-icon>
            </div>
            <span :class="['ka-status', statusClass(kb.status)]">{{ formatStatus(kb.status) }}</span>
          </div>
          <h3>{{ kb.name }}</h3>
          <p>{{ kb.description || '暂无描述' }}</p>
          <div class="kb-meta">
            <div>
              <span>文件数</span>
              <strong>{{ kb.file_count }} 份</strong>
            </div>
            <div>
              <span>Chunks</span>
              <strong>{{ kb.chunk_count }}</strong>
            </div>
            <div>
              <span>更新于</span>
              <strong>{{ formatTime(kb.updated_at) }}</strong>
            </div>
          </div>
          <div class="kb-actions">
            <RouterLink class="ka-link-button" to="/chat">
              <el-icon><ChatDotRound /></el-icon>
              问答
            </RouterLink>
            <RouterLink class="ka-link-button" to="/files">
              <el-icon><Upload /></el-icon>
              文件
            </RouterLink>
            <button class="ka-link-button" @click="openEditDialog(kb)">
              <el-icon><Edit /></el-icon>
              编辑
            </button>
            <button class="ka-link-button ka-danger-link" @click="removeKnowledgeBase(kb)">
              <el-icon><Delete /></el-icon>
              删除
            </button>
          </div>
        </article>
        <article class="kb-card create-card" @click="openCreateDialog">
          <el-icon><Plus /></el-icon>
          <strong>新建知识库</strong>
          <p>创建新的知识库空间后，可进入文件管理上传资料。</p>
        </article>
      </section>

      <el-dialog
        v-model="dialogVisible"
        :title="editingKnowledgeBase ? '编辑知识库' : '新建知识库'"
        width="520px"
      >
        <el-form label-position="top">
          <el-form-item label="名称">
            <el-input v-model="form.name" maxlength="255" show-word-limit />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="form.description" type="textarea" :rows="4" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveKnowledgeBase">保存</el-button>
        </template>
      </el-dialog>
    </section>
  </AppLayout>
</template>

<style scoped>
.content-page {
  padding: 24px;
}

.overview-card {
  padding: 24px;
  margin-bottom: 18px;
}

h2,
h3,
p {
  margin: 0;
}

.overview-card h2 {
  font-size: 18px;
  line-height: 26px;
}

.overview-card p,
.kb-card p {
  margin-top: 8px;
  color: var(--ka-text-secondary);
  line-height: 1.6;
}

.metric-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-top: 22px;
}

.metric-box {
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--ka-border);
  border-radius: 4px;
  background: #f4f5ff;
}

.metric-box span {
  display: block;
  color: var(--ka-text-secondary);
  font-size: 13px;
}

.metric-box strong {
  display: inline-block;
  margin-top: 8px;
  font-size: 26px;
  line-height: 32px;
}

.toolbar-search {
  flex: 1 1 360px;
}

.status-select {
  width: 160px;
}

.error-message {
  margin: 16px 0 0;
  color: #b42318;
}

.kb-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
  margin-top: 20px;
}

.kb-card {
  display: grid;
  gap: 18px;
  min-height: 250px;
  padding: 24px;
}

.kb-card-head {
  display: flex;
  gap: 12px;
  align-items: center;
}

.kb-icon {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border-radius: 6px;
  color: var(--ka-primary);
  background: var(--ka-surface-container);
  font-weight: 800;
}

.kb-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--ka-border);
}

.kb-meta span {
  display: block;
  color: var(--ka-placeholder);
  font-size: 12px;
}

.kb-meta strong {
  overflow-wrap: anywhere;
}

.kb-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
  margin-top: auto;
}

.create-card {
  place-items: center;
  border: 2px dashed #d8dbe8;
  color: var(--ka-text-secondary);
  background: transparent;
  text-align: center;
  cursor: pointer;
}

.create-card:hover {
  border-color: var(--ka-primary);
  background: var(--ka-surface-high);
}

.create-card .el-icon {
  color: var(--ka-primary);
  font-size: 34px;
}

.empty-card {
  grid-column: 1 / -1;
  padding: 36px;
  color: var(--ka-text-secondary);
  text-align: center;
}

@media (max-width: 1180px) {
  .kb-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .metric-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .kb-grid,
  .metric-row {
    grid-template-columns: 1fr;
  }
}
</style>
