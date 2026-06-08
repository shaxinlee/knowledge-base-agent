<script setup lang="ts">
import {
  ChatDotRound,
  CircleCheck,
  CircleClose,
  Collection,
  Delete,
  Link,
  Plus,
  Refresh,
  Search,
  Warning,
} from '@element-plus/icons-vue'
import { ElButton, ElIcon, ElInput, ElMessage, ElMessageBox, ElOption, ElSelect } from 'element-plus'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  createConversation,
  createKnowledgeBase,
  deleteConversation,
  getAccessToken,
  getConversation,
  listConversations,
  listKnowledgeBases,
  streamConversationMessage,
  submitMessageFeedback,
} from '@/api/client'
import type { Citation, Conversation, FeedbackRating, KnowledgeBase, Message } from '@/api/types'
import AppLayout from '@/components/AppLayout.vue'

const router = useRouter()
const knowledgeBases = ref<KnowledgeBase[]>([])
const conversations = ref<Conversation[]>([])
const activeKnowledgeBaseId = ref('')
const activeConversationId = ref('')
const conversationSearchQuery = ref('')
const messages = ref<Message[]>([])
const composerText = ref('')
const loading = ref(false)
const sending = ref(false)
const creatingKnowledgeBase = ref(false)
const errorMessage = ref('')
const selectedCitation = ref<Citation | null>(null)
const messagesRef = ref<HTMLElement | null>(null)
const feedbackByMessageId = ref<Record<string, FeedbackRating>>({})
const feedbackSubmitting = ref<Record<string, boolean>>({})
const deletingConversationById = ref<Record<string, boolean>>({})

const filteredConversations = computed(() => {
  const keyword = normalizeSearchKeyword(conversationSearchQuery.value)
  if (!keyword) {
    return conversations.value
  }
  return conversations.value.filter((conversation) =>
    normalizeSearchKeyword(formatConversationTitle(conversation)).includes(keyword),
  )
})

const activeCitations = computed(() => {
  const latestAssistant = [...messages.value]
    .reverse()
    .find((message) => message.role === 'assistant' && message.citations.length > 0)
  return latestAssistant?.citations ?? []
})

const canSend = computed(
  () => Boolean(activeKnowledgeBaseId.value) && composerText.value.trim().length > 0 && !sending.value,
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
    const response = await listKnowledgeBases()
    knowledgeBases.value = response.items.filter((item) => item.status === 'active')
    activeKnowledgeBaseId.value = knowledgeBases.value[0]?.id ?? ''
    if (activeKnowledgeBaseId.value) {
      await loadConversations()
    }
  } catch (error) {
    handleError(error)
  } finally {
    loading.value = false
  }
}

async function loadConversations(): Promise<void> {
  if (!activeKnowledgeBaseId.value) {
    conversations.value = []
    messages.value = []
    return
  }
  const response = await listConversations(activeKnowledgeBaseId.value)
  conversations.value = response.items
  activeConversationId.value = conversations.value[0]?.id ?? ''
  if (activeConversationId.value) {
    await openConversation(activeConversationId.value)
  } else {
    messages.value = []
    selectedCitation.value = null
  }
}

async function handleKnowledgeBaseChange(): Promise<void> {
  activeConversationId.value = ''
  conversationSearchQuery.value = ''
  messages.value = []
  selectedCitation.value = null
  await loadConversations()
}

async function startConversation(): Promise<void> {
  if (!activeKnowledgeBaseId.value) {
    errorMessage.value = '请先创建或选择一个知识库。'
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const conversation = await createConversation({
      knowledge_base_id: activeKnowledgeBaseId.value,
      title: '新的知识库问答',
    })
    conversationSearchQuery.value = ''
    conversations.value = [conversation, ...conversations.value]
    activeConversationId.value = conversation.id
    messages.value = []
    selectedCitation.value = null
  } catch (error) {
    handleError(error)
  } finally {
    loading.value = false
  }
}

async function createKnowledgeBaseFromChat(): Promise<void> {
  creatingKnowledgeBase.value = true
  errorMessage.value = ''
  try {
    const knowledgeBase = await createKnowledgeBase({
      name: `知识库 ${new Date().toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
      })}`,
      description: '通过 Chat 页面创建的知识库空间。',
    })
    knowledgeBases.value = [knowledgeBase, ...knowledgeBases.value]
    activeKnowledgeBaseId.value = knowledgeBase.id
    conversations.value = []
    conversationSearchQuery.value = ''
    messages.value = []
    selectedCitation.value = null
  } catch (error) {
    handleError(error)
  } finally {
    creatingKnowledgeBase.value = false
  }
}

async function openConversation(conversationId: string): Promise<void> {
  if (deletingConversationById.value[conversationId]) {
    return
  }
  activeConversationId.value = conversationId
  errorMessage.value = ''
  try {
    const detail = await getConversation(conversationId)
    messages.value = detail.messages
    syncFeedbackState(detail.messages)
    selectedCitation.value = activeCitations.value[0] ?? null
    await scrollToBottom()
  } catch (error) {
    handleError(error)
  }
}

async function removeConversation(conversation: Conversation): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除 ${formatConversationTitle(conversation)}？`, '删除会话', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    deletingConversationById.value = {
      ...deletingConversationById.value,
      [conversation.id]: true,
    }
    errorMessage.value = ''
    await deleteConversation(conversation.id)
    ElMessage.success('会话已删除')
    conversations.value = conversations.value.filter((item) => item.id !== conversation.id)
    if (activeConversationId.value === conversation.id) {
      const nextConversationId = filteredConversations.value[0]?.id ?? ''
      activeConversationId.value = nextConversationId
      if (nextConversationId) {
        await openConversation(nextConversationId)
      } else {
        messages.value = []
        selectedCitation.value = null
      }
    }
  } catch (error) {
    if (error !== 'cancel') {
      handleError(error)
    }
  } finally {
    deletingConversationById.value = {
      ...deletingConversationById.value,
      [conversation.id]: false,
    }
  }
}

async function sendMessage(): Promise<void> {
  if (!canSend.value) {
    return
  }
  sending.value = true
  errorMessage.value = ''
  const content = composerText.value.trim()
  composerText.value = ''
  let streamStarted = false
  try {
    if (!activeConversationId.value) {
      await startConversation()
    }
    if (!activeConversationId.value) {
      return
    }
    let assistantMessageId = ''
    await streamConversationMessage(
      activeConversationId.value,
      {
        content,
        stream: true,
      },
      {
        onMessageCreated(event) {
          streamStarted = true
          assistantMessageId = event.assistant_message.id
          messages.value = [...messages.value, event.user_message, event.assistant_message]
        },
        onToken(event) {
          messages.value = messages.value.map((message) =>
            message.id === assistantMessageId
              ? { ...message, content: `${message.content}${event.text}` }
              : message,
          )
        },
        onDone(event) {
          messages.value = messages.value.map((message) =>
            message.id === event.message_id
              ? { ...message, content: event.answer, citations: event.citations }
              : message,
          )
          selectedCitation.value = event.citations[0] ?? null
        },
      },
    )
    await refreshConversationList()
    await scrollToBottom()
  } catch (error) {
    if (!streamStarted) {
      composerText.value = content
    }
    handleError(error)
  } finally {
    sending.value = false
  }
}

async function refreshConversationList(): Promise<void> {
  if (!activeKnowledgeBaseId.value) {
    return
  }
  const previousActiveConversationId = activeConversationId.value
  const response = await listConversations(activeKnowledgeBaseId.value)
  conversations.value = response.items
  if (
    previousActiveConversationId &&
    conversations.value.some((conversation) => conversation.id === previousActiveConversationId)
  ) {
    activeConversationId.value = previousActiveConversationId
  } else {
    activeConversationId.value = conversations.value[0]?.id ?? ''
  }
}

async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

function handleError(error: unknown): void {
  errorMessage.value = error instanceof Error ? error.message : '操作失败，请稍后重试。'
}

function formatConversationTitle(conversation: Conversation): string {
  return conversation.title || '未命名对话'
}

function normalizeSearchKeyword(value: string): string {
  return value.trim().toLocaleLowerCase()
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function syncFeedbackState(items: Message[]): void {
  feedbackByMessageId.value = items.reduce<Record<string, FeedbackRating>>((acc, message) => {
    if (message.role === 'assistant' && message.feedback_rating) {
      acc[message.id] = message.feedback_rating
    }
    return acc
  }, {})
}

async function submitFeedback(message: Message, rating: FeedbackRating): Promise<void> {
  feedbackSubmitting.value = {
    ...feedbackSubmitting.value,
    [message.id]: true,
  }
  errorMessage.value = ''
  try {
    const feedback = await submitMessageFeedback(message.id, { rating })
    feedbackByMessageId.value = {
      ...feedbackByMessageId.value,
      [message.id]: feedback.rating,
    }
    messages.value = messages.value.map((item) =>
      item.id === message.id ? { ...item, feedback_rating: feedback.rating } : item,
    )
  } catch (error) {
    handleError(error)
  } finally {
    feedbackSubmitting.value = {
      ...feedbackSubmitting.value,
      [message.id]: false,
    }
  }
}
</script>

<template>
  <AppLayout>
    <template #top-left>
      <div class="kb-switcher">
        <el-icon><Collection /></el-icon>
        <el-select
          v-model="activeKnowledgeBaseId"
          data-testid="knowledge-base-select"
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

    <section class="chat-page" data-testid="chat-demo-page">
      <aside class="conversation-panel" data-testid="conversation-panel">
        <el-button
          type="primary"
          class="new-chat"
          size="large"
          data-testid="new-conversation-button"
          :loading="loading"
          @click="startConversation"
        >
          <el-icon><Plus /></el-icon>
          新建对话
        </el-button>
        <el-button
          class="refresh-button"
          size="large"
          data-testid="refresh-knowledge-bases-button"
          :loading="loading"
          @click="loadKnowledgeBases"
        >
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-input
          v-model="conversationSearchQuery"
          data-testid="conversation-search-input"
          placeholder="搜索历史会话..."
          size="large"
          class="search-input"
          clearable
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <div v-if="knowledgeBases.length === 0" class="panel-empty">
          <el-icon><Warning /></el-icon>
          <span>暂无可用知识库</span>
          <el-button size="small" :loading="creatingKnowledgeBase" @click="createKnowledgeBaseFromChat">
            创建
          </el-button>
        </div>
        <div v-else-if="conversations.length === 0" class="panel-empty">
          <el-icon><ChatDotRound /></el-icon>
          <span>暂无历史会话</span>
        </div>
        <div v-else-if="filteredConversations.length === 0" class="panel-empty">
          <el-icon><Search /></el-icon>
          <span>没有匹配会话</span>
        </div>

        <div
          v-for="conversation in filteredConversations"
          :key="conversation.id"
          :class="['conversation', { active: conversation.id === activeConversationId }]"
          data-testid="conversation-row"
        >
          <button
            class="conversation-main"
            type="button"
            data-testid="conversation-open-button"
            :disabled="deletingConversationById[conversation.id]"
            @click="openConversation(conversation.id)"
          >
            <strong>{{ formatConversationTitle(conversation) }}</strong>
            <span>{{ formatTime(conversation.updated_at) }}</span>
          </button>
          <button
            class="conversation-delete"
            type="button"
            data-testid="conversation-delete-button"
            :disabled="deletingConversationById[conversation.id] || sending"
            :aria-label="`删除 ${formatConversationTitle(conversation)}`"
            @click.stop="removeConversation(conversation)"
          >
            <el-icon><Delete /></el-icon>
          </button>
        </div>
      </aside>

      <section class="message-panel" data-testid="message-panel">
        <div ref="messagesRef" class="messages ka-scrollbar" data-testid="message-list">
          <div v-if="errorMessage" class="error-banner" data-testid="chat-error-banner">
            {{ errorMessage }}
          </div>

          <div v-if="messages.length === 0" class="welcome-state" data-testid="chat-welcome-state">
            <div class="bot-icon large">
              <el-icon><ChatDotRound /></el-icon>
            </div>
            <h2>向当前知识库提问</h2>
            <p>回答会基于已索引的 chunks，并在右侧展示引用来源。</p>
          </div>

          <template v-for="message in messages" :key="message.id">
            <div :class="['bubble-row', message.role === 'user' ? 'user' : 'ai']">
              <div v-if="message.role !== 'user'" class="bot-icon">
                <el-icon><ChatDotRound /></el-icon>
              </div>
              <article
                :class="['chat-bubble', message.role === 'user' ? 'user-bubble' : 'ai-bubble']"
                :data-testid="`message-bubble-${message.role}`"
              >
                <p v-for="line in message.content.split('\n')" :key="line || message.id">
                  {{ line }}
                </p>
              </article>
            </div>

            <div
              v-if="message.role === 'assistant' && message.citations.length"
              class="citation-chips"
              data-testid="citation-chip-list"
            >
              <button
                v-for="citation in message.citations"
                :key="citation.chunk_id"
                type="button"
                data-testid="citation-chip"
                :data-citation-index="citation.index"
                @click="selectedCitation = citation"
              >
                [{{ citation.index }}] {{ citation.file_name }}
              </button>
            </div>
            <div v-if="message.role === 'assistant'" class="feedback-row">
              <button
                :class="['feedback-button', feedbackByMessageId[message.id] === 'helpful' ? 'active' : '']"
                type="button"
                data-testid="feedback-helpful-button"
                :disabled="feedbackSubmitting[message.id]"
                @click="submitFeedback(message, 'helpful')"
              >
                <el-icon><CircleCheck /></el-icon>
                有帮助
              </button>
              <button
                :class="['feedback-button', feedbackByMessageId[message.id] === 'unhelpful' ? 'active' : '']"
                type="button"
                data-testid="feedback-unhelpful-button"
                :disabled="feedbackSubmitting[message.id]"
                @click="submitFeedback(message, 'unhelpful')"
              >
                <el-icon><CircleClose /></el-icon>
                没帮助
              </button>
            </div>
          </template>
        </div>

        <div class="composer">
          <textarea
            v-model="composerText"
            data-testid="message-composer"
            placeholder="向知识库提问..."
            @keydown.enter.exact.prevent="sendMessage"
          />
          <div class="composer-footer">
            <div class="composer-tools">
              <el-icon><Link /></el-icon>
            </div>
            <el-button
              type="primary"
              data-testid="send-message-button"
              :disabled="!canSend"
              :loading="sending"
              @click="sendMessage"
            >
              发送
            </el-button>
          </div>
        </div>
        <p class="ai-note">回答基于当前知识库检索结果，请核实重要信息。</p>
      </section>

      <aside class="citation-panel" data-testid="citation-panel">
        <header>
          <h2>引用详情</h2>
          <span>{{ activeCitations.length }}</span>
        </header>

        <article v-if="selectedCitation" class="reference-card" data-testid="citation-detail">
          <div class="reference-title">
            <span class="ref-index">{{ selectedCitation.index }}</span>
            <strong data-testid="citation-detail-file-name">{{ selectedCitation.file_name }}</strong>
          </div>
          <blockquote data-testid="citation-detail-excerpt">{{ selectedCitation.excerpt }}</blockquote>
          <footer>
            <span data-testid="citation-detail-source-locator">
              {{ selectedCitation.source_locator }}
            </span>
          </footer>
        </article>

        <div v-else class="reference-empty">
          <span>i</span>
          <p>点击回答中的引用编号<br />即可查看对应原文内容</p>
        </div>
      </aside>
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
  border-radius: 4px;
  color: var(--ka-text);
  background: var(--ka-surface-container);
  font-weight: 700;
}

.kb-select {
  width: 260px;
}

.chat-page {
  display: grid;
  grid-template-columns: 360px minmax(420px, 1fr) 380px;
  height: calc(100vh - var(--ka-header-height));
  background: #fff;
}

.conversation-panel,
.citation-panel {
  border-right: 1px solid var(--ka-border);
  background: #fbfaff;
}

.conversation-panel {
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 18px;
}

.new-chat,
.refresh-button {
  width: 100%;
  height: 48px;
}

.conversation {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 36px;
  align-items: center;
  width: 100%;
  border: 1px solid transparent;
  border-radius: 8px;
  color: var(--ka-text);
  background: transparent;
}

.conversation-main {
  display: grid;
  gap: 8px;
  min-width: 0;
  min-height: 72px;
  padding: 14px 0 14px 16px;
  border: 0;
  color: inherit;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.conversation-main:disabled,
.conversation-delete:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.conversation-delete {
  display: grid;
  width: 32px;
  height: 32px;
  margin-right: 10px;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 4px;
  color: var(--ka-text-secondary);
  background: transparent;
  cursor: pointer;
}

.conversation-delete:hover:not(:disabled) {
  color: var(--ka-error);
  border-color: #ffd3cc;
  background: #fff0ed;
}

.conversation.active {
  border-color: #c3c6d7;
  background: #ededf8;
}

.conversation strong {
  overflow: hidden;
  font-size: 15px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation span {
  color: var(--ka-text-secondary);
  font-size: 13px;
}

.panel-empty,
.welcome-state,
.error-banner {
  border: 1px solid var(--ka-border);
  border-radius: 8px;
}

.panel-empty {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 14px;
  color: var(--ka-text-secondary);
  background: #fff;
}

.message-panel {
  position: relative;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto auto;
  padding: 24px 26px 16px;
  border-right: 1px solid var(--ka-border);
}

.messages {
  overflow: auto;
  padding: 10px 18px 24px;
}

.error-banner {
  padding: 12px 14px;
  margin-bottom: 16px;
  color: var(--ka-error);
  background: #fff0ed;
}

.welcome-state {
  display: grid;
  justify-items: center;
  gap: 10px;
  padding: 48px 24px;
  color: var(--ka-text-secondary);
  background: #fbfcff;
  text-align: center;
}

.welcome-state h2,
.welcome-state p {
  margin: 0;
}

.bubble-row {
  display: flex;
  gap: 14px;
  margin-bottom: 18px;
}

.bubble-row.user {
  justify-content: flex-end;
}

.chat-bubble {
  max-width: min(680px, 76%);
  padding: 16px 20px;
  font-size: 15px;
  line-height: 1.7;
}

.chat-bubble p {
  margin: 0 0 8px;
}

.chat-bubble p:last-child {
  margin-bottom: 0;
}

.user-bubble {
  border-radius: 12px 12px 2px;
  color: #fff;
  background: var(--ka-primary-deep);
}

.ai-bubble {
  border: 1px solid var(--ka-border);
  border-radius: 2px 12px 12px;
  background: #f7f8ff;
}

.bot-icon {
  display: grid;
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 4px;
  color: #fff;
  background: var(--ka-primary);
}

.bot-icon.large {
  width: 48px;
  height: 48px;
}

.citation-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: -8px 0 22px 52px;
}

.citation-chips button {
  padding: 8px 12px;
  border: 1px solid var(--ka-border);
  border-radius: 4px;
  color: var(--ka-primary);
  background: #eef1ff;
  cursor: pointer;
}

.feedback-row {
  display: flex;
  gap: 10px;
  margin: -10px 0 18px 52px;
}

.feedback-button {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid var(--ka-border);
  border-radius: 4px;
  color: var(--ka-text-secondary);
  background: #fff;
  cursor: pointer;
}

.feedback-button.active {
  color: var(--ka-primary);
  border-color: #b9c9ff;
  background: #eef1ff;
}

.feedback-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.composer {
  min-height: 142px;
  padding: 18px 22px;
  border: 1px solid var(--ka-border);
  border-radius: 8px;
  background: #f4f5ff;
}

.composer textarea {
  width: 100%;
  min-height: 64px;
  border: 0;
  outline: 0;
  color: var(--ka-text);
  background: transparent;
  resize: none;
}

.composer-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.composer-tools {
  display: flex;
  gap: 20px;
  color: #344054;
  font-size: 22px;
}

.ai-note {
  margin: 12px 0 0;
  color: var(--ka-placeholder);
  text-align: center;
}

.citation-panel {
  border-right: 0;
  background: #fbfaff;
}

.citation-panel header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 72px;
  padding: 0 24px;
  border-bottom: 1px solid var(--ka-border);
}

.citation-panel h2 {
  margin: 0;
  font-size: 18px;
}

.reference-card {
  margin: 24px;
  padding-left: 14px;
  border-left: 2px solid var(--ka-primary);
}

.reference-title {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
}

.reference-title strong {
  overflow-wrap: anywhere;
}

.ref-index {
  display: grid;
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 2px;
  color: #fff;
  background: var(--ka-primary);
  font-weight: 700;
}

blockquote {
  margin: 0;
  padding: 16px;
  border-radius: 4px;
  color: var(--ka-text-secondary);
  background: #f4f5fb;
  line-height: 1.6;
}

.reference-card footer {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
  color: var(--ka-placeholder);
  font-size: 12px;
}

.reference-empty {
  display: grid;
  place-items: center;
  margin-top: 70px;
  color: var(--ka-placeholder);
  text-align: center;
}

.reference-empty span {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border: 4px solid #c7cad4;
  border-radius: 50%;
  font-weight: 800;
}

@media (max-width: 1280px) {
  .chat-page {
    grid-template-columns: 300px minmax(420px, 1fr);
  }

  .citation-panel {
    display: none;
  }
}

@media (max-width: 860px) {
  .chat-page {
    grid-template-columns: 1fr;
    height: auto;
    min-height: calc(100vh - var(--ka-header-height));
  }

  .conversation-panel {
    border-bottom: 1px solid var(--ka-border);
  }

  .message-panel {
    min-height: 680px;
  }
}
</style>
