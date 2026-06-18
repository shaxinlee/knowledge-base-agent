<script setup lang="ts">
import {
  Bot,
  BookOpen,
  CircleCheck,
  CircleX,
  Image,
  MessageCircle,
  Plus,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  Trash2,
  TriangleAlert,
  UserCircle,
} from '@lucide/vue'
import {
  ElButton,
  ElDialog,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElOption,
  ElSelect,
} from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  createConversation,
  deleteConversation,
  getAccessToken,
  getCurrentUser,
  getConversation,
  loadAuthorizedAssetObjectUrl,
  listConversations,
  listKnowledgeBases,
  streamConversationMessage,
  submitMessageFeedback,
} from '@/api/client'
import type {
  Citation,
  Conversation,
  FeedbackRating,
  KnowledgeBase,
  Message,
  MessageAttachment,
  MessageAttachmentInput,
  UserRole,
} from '@/api/types'
import AppLayout from '@/components/AppLayout.vue'
import MarkdownContent from '@/components/MarkdownContent.vue'

interface CitationImageItem {
  key: string
  citation: Citation
  sourceUrl: string
  alt: string
}

interface SelectedCitationImage {
  src: string
  alt: string
}

interface PendingImageAttachment {
  file_name: string
  media_type: string
  data_url: string
}

const VISIBLE_CITATION_LIMIT = 3
const IMAGE_GALLERY_LIMIT = 12
const MAX_MESSAGE_IMAGE_SIZE_BYTES = 8 * 1024 * 1024
const APP_SIDEBAR_WIDTH_KEY = 'kb_agent_chat_app_sidebar_width'
const CONVERSATION_PANEL_WIDTH_KEY = 'kb_agent_chat_conversation_panel_width'
const CITATION_PANEL_WIDTH_KEY = 'kb_agent_chat_citation_panel_width'
const CITATION_PANEL_OPEN_KEY = 'kb_agent_chat_citation_panel_open'
const APP_SIDEBAR_MIN_WIDTH = 76
const APP_SIDEBAR_MAX_WIDTH = 360
const CONVERSATION_PANEL_MIN_WIDTH = 280
const CONVERSATION_PANEL_MAX_WIDTH = 560
const CITATION_PANEL_MIN_WIDTH = 300
const CITATION_PANEL_MAX_WIDTH = 560
const MESSAGE_PANEL_MIN_WIDTH = 420
const CHAT_SIDEBAR_BREAKPOINT = 960

type ResizeTarget = 'app-sidebar' | 'conversation-panel' | 'citation-panel'

interface ResizeState {
  target: ResizeTarget
  startX: number
  startWidth: number
}

const router = useRouter()
const route = useRoute()
const knowledgeBases = ref<KnowledgeBase[]>([])
const conversations = ref<Conversation[]>([])
const currentUserRole = ref<UserRole | null>(null)
const activeKnowledgeBaseId = ref('')
const activeConversationId = ref('')
const conversationSearchQuery = ref('')
const messages = ref<Message[]>([])
const composerText = ref('')
const loading = ref(false)
const sending = ref(false)
const errorMessage = ref('')
const selectedCitation = ref<Citation | null>(null)
const selectedCitationImageUrl = ref('')
const selectedCitationImageLoading = ref(false)
const selectedCitationImageError = ref('')
const selectedImage = ref<SelectedCitationImage | null>(null)
const streamingAssistantMessageId = ref('')
const citationImageUrls = ref<Record<string, string>>({})
const citationImageLoading = ref<Record<string, boolean>>({})
const attachmentImageUrls = ref<Record<string, string>>({})
const attachmentImageLoading = ref<Record<string, boolean>>({})
const pendingImageAttachment = ref<PendingImageAttachment | null>(null)
const imageInputRef = ref<HTMLInputElement | null>(null)
const messagesRef = ref<HTMLElement | null>(null)
const feedbackByMessageId = ref<Record<string, FeedbackRating>>({})
const feedbackSubmitting = ref<Record<string, boolean>>({})
const deletingConversationById = ref<Record<string, boolean>>({})
const appSidebarWidth = ref(220)
const conversationPanelWidth = ref(360)
const citationPanelWidth = ref(380)
const citationPanelOpen = ref(true)
const activeResize = ref<ResizeState | null>(null)
const viewportWidth = ref(typeof window === 'undefined' ? 1440 : window.innerWidth)

const isConsumerUser = computed(() => currentUserRole.value === 'user')
const conversationPanelInlineVisible = computed(
  () => !isConsumerUser.value || viewportWidth.value <= CHAT_SIDEBAR_BREAKPOINT,
)
const citationPanelVisible = computed(() => citationPanelOpen.value && viewportWidth.value > 1280)
const citationPanelCollapsedVisible = computed(
  () => !citationPanelOpen.value && viewportWidth.value > 1280,
)

const chatGridTemplateColumns = computed(() => {
  if (viewportWidth.value <= 860) {
    return '1fr'
  }
  const messageColumn = `minmax(${MESSAGE_PANEL_MIN_WIDTH}px, 1fr)`
  if (!conversationPanelInlineVisible.value) {
    if (citationPanelCollapsedVisible.value) {
      return `${messageColumn} 64px`
    }
    if (!citationPanelVisible.value) {
      return messageColumn
    }
    return `${messageColumn} ${citationPanelWidth.value}px`
  }
  if (citationPanelCollapsedVisible.value) {
    return `${conversationPanelWidth.value}px minmax(${MESSAGE_PANEL_MIN_WIDTH}px, 1fr) 64px`
  }
  if (!citationPanelVisible.value) {
    return `${conversationPanelWidth.value}px minmax(${MESSAGE_PANEL_MIN_WIDTH}px, 1fr)`
  }
  return (
    `${conversationPanelWidth.value}px minmax(${MESSAGE_PANEL_MIN_WIDTH}px, 1fr) ` +
    `${citationPanelWidth.value}px`
  )
})

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
  return latestAssistant ? visibleMessageCitations(latestAssistant) : []
})

const canSend = computed(
  () =>
    Boolean(activeKnowledgeBaseId.value) &&
    (composerText.value.trim().length > 0 || Boolean(pendingImageAttachment.value)) &&
    !sending.value,
)

const welcomePrompts = [
  '请概括当前知识库中的核心内容。',
  '这份资料里有哪些关键步骤和注意事项？',
  '请列出与我的问题最相关的引用来源。',
  '根据当前知识库，帮我对比相关方案差异。',
]

onMounted(async () => {
  initializeResizableLayout()
  window.addEventListener('resize', handleViewportResize)
  if (!getAccessToken()) {
    await router.push('/login')
    return
  }
  try {
    currentUserRole.value = (await getCurrentUser()).role
  } catch {
    currentUserRole.value = null
  }
  await loadKnowledgeBases()
})

watch(selectedCitation, (citation) => {
  void loadSelectedCitationImage(citation)
})

watch(
  messages,
  () => {
    void preloadCitationImages()
    void preloadAttachmentImages()
  },
  { deep: true },
)

onBeforeUnmount(() => {
  revokeSelectedCitationImageUrl()
  revokeCitationImageUrls()
  revokeAttachmentImageUrls()
  stopColumnResize()
  window.removeEventListener('resize', handleViewportResize)
})

function initializeResizableLayout(): void {
  appSidebarWidth.value = readStoredNumber(
    APP_SIDEBAR_WIDTH_KEY,
    appSidebarWidth.value,
    APP_SIDEBAR_MIN_WIDTH,
    APP_SIDEBAR_MAX_WIDTH,
  )
  conversationPanelWidth.value = readStoredNumber(
    CONVERSATION_PANEL_WIDTH_KEY,
    conversationPanelWidth.value,
    CONVERSATION_PANEL_MIN_WIDTH,
    CONVERSATION_PANEL_MAX_WIDTH,
  )
  citationPanelWidth.value = readStoredNumber(
    CITATION_PANEL_WIDTH_KEY,
    citationPanelWidth.value,
    CITATION_PANEL_MIN_WIDTH,
    CITATION_PANEL_MAX_WIDTH,
  )
  citationPanelOpen.value = window.localStorage.getItem(CITATION_PANEL_OPEN_KEY) !== 'false'
  handleViewportResize()
  applyAppSidebarWidth()
}

function readStoredNumber(
  key: string,
  fallback: number,
  min: number,
  max: number,
): number {
  const value = Number(window.localStorage.getItem(key))
  if (!Number.isFinite(value)) {
    return fallback
  }
  return clamp(value, min, max)
}

function applyAppSidebarWidth(): void {
  document.documentElement.style.setProperty('--ka-sidebar-width', `${appSidebarWidth.value}px`)
}

function startColumnResize(target: ResizeTarget, event: PointerEvent): void {
  if (viewportWidth.value <= 860 || (target === 'app-sidebar' && viewportWidth.value <= 960)) {
    return
  }
  event.preventDefault()
  activeResize.value = {
    target,
    startX: event.clientX,
    startWidth: resizeTargetWidth(target),
  }
  document.body.classList.add('ka-column-resizing')
  window.addEventListener('pointermove', handleColumnResize)
  window.addEventListener('pointerup', stopColumnResize)
}

function handleColumnResize(event: PointerEvent): void {
  const resize = activeResize.value
  if (!resize) {
    return
  }
  const deltaX = event.clientX - resize.startX
  if (resize.target === 'app-sidebar') {
    appSidebarWidth.value = clamp(
      resize.startWidth + deltaX,
      APP_SIDEBAR_MIN_WIDTH,
      APP_SIDEBAR_MAX_WIDTH,
    )
    applyAppSidebarWidth()
    return
  }
  if (resize.target === 'conversation-panel') {
    conversationPanelWidth.value = clamp(
      resize.startWidth + deltaX,
      CONVERSATION_PANEL_MIN_WIDTH,
      CONVERSATION_PANEL_MAX_WIDTH,
    )
    return
  }
  citationPanelWidth.value = clamp(
    resize.startWidth - deltaX,
    CITATION_PANEL_MIN_WIDTH,
    CITATION_PANEL_MAX_WIDTH,
  )
}

function stopColumnResize(): void {
  if (activeResize.value) {
    persistResizableLayout()
  }
  activeResize.value = null
  document.body.classList.remove('ka-column-resizing')
  window.removeEventListener('pointermove', handleColumnResize)
  window.removeEventListener('pointerup', stopColumnResize)
}

function resizeTargetWidth(target: ResizeTarget): number {
  if (target === 'app-sidebar') {
    return appSidebarWidth.value
  }
  if (target === 'conversation-panel') {
    return conversationPanelWidth.value
  }
  return citationPanelWidth.value
}

function persistResizableLayout(): void {
  window.localStorage.setItem(APP_SIDEBAR_WIDTH_KEY, String(appSidebarWidth.value))
  window.localStorage.setItem(CONVERSATION_PANEL_WIDTH_KEY, String(conversationPanelWidth.value))
  window.localStorage.setItem(CITATION_PANEL_WIDTH_KEY, String(citationPanelWidth.value))
}

function toggleCitationPanel(): void {
  citationPanelOpen.value = !citationPanelOpen.value
  window.localStorage.setItem(CITATION_PANEL_OPEN_KEY, String(citationPanelOpen.value))
}

function handleViewportResize(): void {
  viewportWidth.value = window.innerWidth
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

async function loadKnowledgeBases(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await listKnowledgeBases()
    knowledgeBases.value = response.items.filter((item) => item.status === 'active')
    activeKnowledgeBaseId.value = resolveInitialKnowledgeBaseId()
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
    errorMessage.value = '暂无可用知识库，请联系管理员维护知识库。'
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
    selectedImage.value = null
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
  const imageAttachment = pendingImageAttachment.value
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
        attachments: imageAttachment ? [buildMessageAttachmentInput(imageAttachment)] : [],
      },
      {
        onMessageCreated(event) {
          streamStarted = true
          assistantMessageId = event.assistant_message.id
          streamingAssistantMessageId.value = assistantMessageId
          pendingImageAttachment.value = null
          messages.value = [...messages.value, event.user_message, event.assistant_message]
          void preloadAttachmentImages()
          void scrollToBottom()
        },
        onToken(event) {
          messages.value = messages.value.map((message) =>
            message.id === assistantMessageId
              ? { ...message, content: `${message.content}${event.text}` }
              : message,
          )
          void scrollToBottom()
        },
        onDone(event) {
          messages.value = messages.value.map((message) =>
            message.id === event.message_id
              ? {
                  ...message,
                  content: event.answer,
                  citations: event.citations,
                  visual_result_mode: event.visual_result_mode ?? null,
                }
              : message,
          )
          streamingAssistantMessageId.value = ''
          const assistantMessage = messages.value.find((message) => message.id === event.message_id)
          selectedCitation.value = assistantMessage
            ? visibleMessageCitations(assistantMessage)[0] ?? null
            : null
          void preloadCitationImages()
          void scrollToBottom()
        },
      },
    )
    await refreshConversationList()
    await scrollToBottom()
  } catch (error) {
    if (!streamStarted) {
      composerText.value = content
      pendingImageAttachment.value = imageAttachment
    }
    handleError(error)
  } finally {
    sending.value = false
    streamingAssistantMessageId.value = ''
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

function buildMessageAttachmentInput(attachment: PendingImageAttachment): MessageAttachmentInput {
  return {
    type: 'image',
    file_name: attachment.file_name,
    media_type: attachment.media_type,
    data_url: attachment.data_url,
  }
}

function openImagePicker(): void {
  imageInputRef.value?.click()
}

async function handleImageFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  if (!file.type.startsWith('image/')) {
    ElMessage.warning('请选择图片文件')
    return
  }
  if (file.size > MAX_MESSAGE_IMAGE_SIZE_BYTES) {
    ElMessage.warning('图片不能超过 8MB')
    return
  }
  pendingImageAttachment.value = {
    file_name: file.name,
    media_type: file.type,
    data_url: await readFileAsDataUrl(file),
  }
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

function removePendingImageAttachment(): void {
  pendingImageAttachment.value = null
}

function messageAttachmentKey(attachment: MessageAttachment): string {
  return `${attachment.id}:${attachment.url}`
}

function messageAttachmentObjectUrl(attachment: MessageAttachment): string {
  return attachmentImageUrls.value[messageAttachmentKey(attachment)] ?? ''
}

async function preloadAttachmentImages(): Promise<void> {
  const attachments = messages.value.flatMap((message) =>
    message.attachments.filter((attachment) => attachment.type === 'image'),
  )
  await Promise.all(
    attachments.map(async (attachment) => {
      const key = messageAttachmentKey(attachment)
      if (attachmentImageUrls.value[key] || attachmentImageLoading.value[key]) {
        return
      }
      attachmentImageLoading.value = { ...attachmentImageLoading.value, [key]: true }
      try {
        const objectUrl = await loadAuthorizedAssetObjectUrl(attachment.url)
        attachmentImageUrls.value = { ...attachmentImageUrls.value, [key]: objectUrl }
      } catch {
        attachmentImageUrls.value = { ...attachmentImageUrls.value, [key]: '' }
      } finally {
        attachmentImageLoading.value = { ...attachmentImageLoading.value, [key]: false }
      }
    }),
  )
}

function revokeAttachmentImageUrls(): void {
  Object.values(attachmentImageUrls.value).forEach((url) => {
    if (url.startsWith('blob:')) {
      URL.revokeObjectURL(url)
    }
  })
}

function openAttachmentImagePreview(attachment: MessageAttachment): void {
  const objectUrl = messageAttachmentObjectUrl(attachment)
  if (objectUrl) {
    openImagePreview(objectUrl, attachment.file_name)
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

function resolveInitialKnowledgeBaseId(): string {
  const queryKnowledgeBaseId =
    typeof route.query.knowledge_base_id === 'string' ? route.query.knowledge_base_id : ''
  if (queryKnowledgeBaseId && knowledgeBases.value.some((item) => item.id === queryKnowledgeBaseId)) {
    return queryKnowledgeBaseId
  }
  return knowledgeBases.value[0]?.id ?? ''
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

function isWaitingMessage(message: Message): boolean {
  return (
    message.role === 'assistant' &&
    message.id === streamingAssistantMessageId.value &&
    message.content.length === 0
  )
}

function displayMessageLines(message: Message): string[] {
  if (message.role !== 'assistant') {
    return normalizeSpecialDisplayText(message.content).split('\n')
  }
  return stripMarkdownImageLines(normalizeSpecialDisplayText(message.content))
}

function displayMessageContent(message: Message): string {
  return displayMessageLines(message).join('\n')
}

function stripMarkdownImageLines(content: string): string[] {
  const lines = content.split('\n')
  const visibleLines: string[] = []
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index].trim()
    const nextLine = lines[index + 1]?.trim() ?? ''
    if (isInlineMarkdownImageLine(line)) {
      continue
    }
    if (isStandaloneMarkdownImageMarker(line) && isStandaloneImagePathLine(nextLine)) {
      index += 1
      continue
    }
    if (isStandaloneImagePathLine(line)) {
      continue
    }
    visibleLines.push(lines[index])
  }
  return visibleLines
}

function isInlineMarkdownImageLine(line: string): boolean {
  return /^!\[[^\]]*]\([^)]+\)$/.test(line)
}

function isStandaloneMarkdownImageMarker(line: string): boolean {
  return /^!\[[^\]]*]$/.test(line)
}

function isStandaloneImagePathLine(line: string): boolean {
  const normalized = line.replace(/^\(/, '').replace(/\)$/, '').trim().toLocaleLowerCase()
  return /^images\/.+\.(jpg|jpeg|png|webp|gif|bmp)(\?.*)?$/.test(normalized)
}

function normalizeSpecialDisplayText(content: string): string {
  return normalizeLatexText(stripHtmlTags(decodeHtmlEntities(content)))
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
    .replace(/<\s*li\b[^>]*>/gi, '- ')
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, '')
}

function normalizeLatexText(content: string): string {
  const replacements: Record<string, string> = {
    '\\times': '×',
    '\\cdot': '·',
    '\\div': '÷',
    '\\leq': '≤',
    '\\le': '≤',
    '\\geq': '≥',
    '\\ge': '≥',
    '\\neq': '≠',
    '\\ne': '≠',
    '\\approx': '≈',
    '\\pm': '±',
    '\\rightarrow': '→',
    '\\to': '→',
    '\\infty': '∞',
    '\\sum': 'Σ',
    '\\int': '∫',
    '\\alpha': 'α',
    '\\beta': 'β',
    '\\gamma': 'γ',
    '\\delta': 'δ',
    '\\theta': 'θ',
    '\\lambda': 'λ',
    '\\pi': 'π',
  }
  let normalized = content
    .replace(/\\\[(.*?)\\\]/gs, '$1')
    .replace(/\\\((.*?)\\\)/gs, '$1')
    .replace(/\$\$(.*?)\$\$/gs, '$1')
    .replace(/(?<!\$)\$([^$\n]+)\$(?!\$)/g, '$1')
    .replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, '($1)/($2)')
    .replace(/\\sqrt\{([^{}]+)\}/g, '√($1)')
    .replace(/\\(?:text|mathrm|mathbf|operatorname)\{([^{}]+)\}/g, '$1')
    .replace(/\\begin\{[^}]+}|\s*\\end\{[^}]+}/g, '')
    .replace(/\\\\/g, '\n')
    .replace(/&/g, ' ')
    .replace(/\^\{([^}]+)}/g, '^$1')
    .replace(/_\{([^}]+)}/g, '_$1')
  Object.entries(replacements).forEach(([source, replacement]) => {
    normalized = normalized.split(source).join(replacement)
  })
  return normalized
    .replace(/\\[a-zA-Z]+/g, '')
    .replace(/[{}]/g, '')
    .trim()
}

function visibleMessageCitations(message: Message): Citation[] {
  return message.citations.slice(0, VISIBLE_CITATION_LIMIT)
}

function extractReferencedCitationIndexes(content: string): number[] {
  const indexes: number[] = []
  const seen = new Set<number>()
  const regex = /\[(\d+)\]/g
  let match: RegExpExecArray | null
  while ((match = regex.exec(content)) !== null) {
    const index = Number(match[1])
    if (Number.isInteger(index) && index > 0 && !seen.has(index)) {
      indexes.push(index)
      seen.add(index)
    }
  }
  return indexes
}

function messageImageItems(message: Message): CitationImageItem[] {
  if (message.role !== 'assistant') {
    return []
  }
  if (message.visual_result_mode === 'gallery') {
    return message.citations
      .filter((citation) => citation.modality === 'image' && citationPrimaryImageSourceUrl(citation))
      .slice(0, IMAGE_GALLERY_LIMIT)
      .map((citation) => {
        const sourceUrl = citationPrimaryImageSourceUrl(citation)
        return {
          key: citationImageKey(citation, sourceUrl, 0),
          citation,
          sourceUrl,
          alt: citation.image_alt || citation.file_name,
        }
      })
  }
  const referencedIndexes = extractReferencedCitationIndexes(message.content)
  for (const referencedIndex of referencedIndexes) {
    const citation = message.citations.find(
      (item) => item.index === referencedIndex && item.modality === 'image',
    )
    const sourceUrl = citation ? citationPrimaryImageSourceUrl(citation) : ''
    if (citation && sourceUrl) {
      return [
        {
          key: citationImageKey(citation, sourceUrl, 0),
          citation,
          sourceUrl,
          alt: citation.image_alt || citation.file_name,
        },
      ]
    }
  }
  return []
}

function citationPrimaryImageSourceUrl(citation: Citation): string {
  return citation.image_url || citation.image_urls[0] || ''
}

function citationImageSourceUrls(citation: Citation): string[] {
  const sourceUrl = citationPrimaryImageSourceUrl(citation)
  return sourceUrl ? [sourceUrl] : []
}

function citationImageKey(citation: Citation, sourceUrl: string, index: number): string {
  const citationKey =
    citation.id ?? `${citation.chunk_id}:${citation.source_locator}:${citation.index}`
  return `${citationKey}:${index}:${sourceUrl}`
}

function citationImageObjectUrl(item: CitationImageItem): string {
  return citationImageUrls.value[item.key] ?? ''
}

function openMessageImagePreview(item: CitationImageItem): void {
  const objectUrl = citationImageObjectUrl(item)
  selectedCitation.value = item.citation
  if (objectUrl) {
    openImagePreview(objectUrl, item.alt)
  }
}

function openSelectedCitationImagePreview(): void {
  if (!selectedCitation.value || !selectedCitationImageUrl.value) {
    return
  }
  openImagePreview(
    selectedCitationImageUrl.value,
    selectedCitation.value.image_alt || selectedCitation.value.file_name,
  )
}

function openImagePreview(src: string, alt: string): void {
  selectedImage.value = { src, alt }
}

function handleImageDialogOpenChange(open: boolean): void {
  if (!open) {
    selectedImage.value = null
  }
}

async function preloadCitationImages(): Promise<void> {
  const imageItems = messages.value.flatMap((message) => messageImageItems(message))
  await Promise.all(
    imageItems.map(async (item) => {
      if (citationImageUrls.value[item.key] || citationImageLoading.value[item.key]) {
        return
      }
      citationImageLoading.value = { ...citationImageLoading.value, [item.key]: true }
      try {
        const objectUrl = await loadAuthorizedAssetObjectUrl(item.sourceUrl)
        citationImageUrls.value = { ...citationImageUrls.value, [item.key]: objectUrl }
      } catch {
        citationImageUrls.value = { ...citationImageUrls.value, [item.key]: '' }
      } finally {
        citationImageLoading.value = { ...citationImageLoading.value, [item.key]: false }
      }
    }),
  )
}

async function loadSelectedCitationImage(citation: Citation | null): Promise<void> {
  revokeSelectedCitationImageUrl()
  selectedCitationImageUrl.value = ''
  selectedCitationImageError.value = ''
  const imageUrl = citation ? citationPrimaryImageSourceUrl(citation) : ''
  if (!imageUrl) {
    selectedCitationImageLoading.value = false
    return
  }
  selectedCitationImageLoading.value = true
  try {
    selectedCitationImageUrl.value = await loadAuthorizedAssetObjectUrl(imageUrl)
  } catch {
    selectedCitationImageError.value = '图片无法加载'
  } finally {
    selectedCitationImageLoading.value = false
  }
}

function revokeSelectedCitationImageUrl(): void {
  if (selectedCitationImageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(selectedCitationImageUrl.value)
  }
}

function revokeCitationImageUrls(): void {
  Object.values(citationImageUrls.value).forEach((url) => {
    if (url.startsWith('blob:')) {
      URL.revokeObjectURL(url)
    }
  })
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
  <AppLayout :consumer-sidebar-active="isConsumerUser && viewportWidth > CHAT_SIDEBAR_BREAKPOINT">
    <template
      v-if="isConsumerUser && viewportWidth > CHAT_SIDEBAR_BREAKPOINT"
      #consumer-sidebar-main
    >
      <div class="chat-sidebar-main">
        <div class="chat-sidebar-kb">
          <BookOpen class="lucide-icon" />
          <el-select
            v-model="activeKnowledgeBaseId"
            data-testid="knowledge-base-select"
            placeholder="选择知识库"
            class="kb-select"
            :disabled="loading || knowledgeBases.length === 0"
            @change="handleKnowledgeBaseChange"
          >
            <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
          </el-select>
        </div>

        <div class="chat-sidebar-actions">
          <el-button
            type="primary"
            class="new-chat"
            size="large"
            data-testid="new-conversation-button"
            :loading="loading"
            @click="startConversation"
          >
            <Plus class="lucide-icon" />
            新建对话
          </el-button>
          <el-button
            class="refresh-button"
            size="large"
            data-testid="refresh-knowledge-bases-button"
            :loading="loading"
            @click="loadKnowledgeBases"
          >
            <RefreshCw class="lucide-icon" />
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
              <Search class="input-icon" />
            </template>
          </el-input>
        </div>

        <div class="sidebar-conversations ka-scrollbar">
          <div v-if="knowledgeBases.length === 0" class="panel-empty">
            <TriangleAlert class="lucide-icon" />
            <span>暂无可用知识库，请联系管理员维护知识库。</span>
          </div>
          <div v-else-if="conversations.length === 0" class="panel-empty">
            <MessageCircle class="lucide-icon" />
            <span>暂无历史会话</span>
          </div>
          <div v-else-if="filteredConversations.length === 0" class="panel-empty">
            <Search class="lucide-icon" />
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
              <Trash2 class="lucide-icon" />
            </button>
          </div>
        </div>

        <nav class="chat-sidebar-nav" aria-label="用户导航">
          <RouterLink class="chat-sidebar-nav-item" to="/chat">
            <MessageCircle class="lucide-icon" />
            <span>对话问答</span>
          </RouterLink>
          <RouterLink class="chat-sidebar-nav-item" to="/knowledge">
            <BookOpen class="lucide-icon" />
            <span>知识库</span>
          </RouterLink>
          <RouterLink class="chat-sidebar-nav-item" to="/profile">
            <UserCircle class="lucide-icon" />
            <span>个人资料</span>
          </RouterLink>
        </nav>
      </div>
    </template>

    <template #top-left>
      <div v-if="!isConsumerUser || viewportWidth <= CHAT_SIDEBAR_BREAKPOINT" class="kb-switcher">
        <BookOpen class="lucide-icon" />
        <el-select
          v-model="activeKnowledgeBaseId"
          data-testid="knowledge-base-select"
          placeholder="选择知识库"
          class="kb-select"
          :disabled="loading || knowledgeBases.length === 0"
          @change="handleKnowledgeBaseChange"
        >
          <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
        </el-select>
      </div>
      <div v-else class="kb-switcher chat-top-title">
        <MessageCircle class="lucide-icon" />
        <span>知识库问答</span>
      </div>
    </template>

    <section
      :class="[
        'chat-page',
        {
          'citation-collapsed': !citationPanelVisible,
          'has-inline-conversations': conversationPanelInlineVisible,
        },
      ]"
      :style="{ gridTemplateColumns: chatGridTemplateColumns }"
      data-testid="chat-demo-page"
    >
      <div
        v-if="!isConsumerUser"
        class="app-sidebar-resizer"
        role="separator"
        aria-label="调整主导航宽度"
        aria-orientation="vertical"
        @pointerdown="startColumnResize('app-sidebar', $event)"
      ></div>
      <aside
        v-if="conversationPanelInlineVisible"
        class="conversation-panel"
        data-testid="conversation-panel"
      >
        <el-button
          type="primary"
          class="new-chat"
          size="large"
          data-testid="new-conversation-button"
          :loading="loading"
          @click="startConversation"
        >
          <Plus class="lucide-icon" />
          新建对话
        </el-button>
        <el-button
          class="refresh-button"
          size="large"
          data-testid="refresh-knowledge-bases-button"
          :loading="loading"
          @click="loadKnowledgeBases"
        >
          <RefreshCw class="lucide-icon" />
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
            <Search class="input-icon" />
          </template>
        </el-input>

        <div v-if="knowledgeBases.length === 0" class="panel-empty">
          <TriangleAlert class="lucide-icon" />
          <span>暂无可用知识库，请联系管理员维护知识库。</span>
        </div>
        <div v-else-if="conversations.length === 0" class="panel-empty">
          <MessageCircle class="lucide-icon" />
          <span>暂无历史会话</span>
        </div>
        <div v-else-if="filteredConversations.length === 0" class="panel-empty">
          <Search class="lucide-icon" />
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
            <Trash2 class="lucide-icon" />
          </button>
        </div>
      </aside>

      <div
        v-if="conversationPanelInlineVisible && viewportWidth > 860"
        class="column-resizer conversation-column-resizer"
        :style="{ left: `${conversationPanelWidth}px` }"
        role="separator"
        aria-label="调整会话列表宽度"
        aria-orientation="vertical"
        @pointerdown="startColumnResize('conversation-panel', $event)"
      ></div>

      <section class="message-panel" data-testid="message-panel">
        <div ref="messagesRef" class="messages ka-scrollbar" data-testid="message-list">
          <div v-if="errorMessage" class="error-banner" data-testid="chat-error-banner">
            {{ errorMessage }}
          </div>

          <div v-if="messages.length === 0" class="welcome-state" data-testid="chat-welcome-state">
            <div class="welcome-icon">
              <Bot class="lucide-icon" />
            </div>
            <h2>向当前知识库提问</h2>
            <p>回答会基于已索引的知识片段，并在右侧展示引用来源。</p>
            <div class="welcome-prompts">
              <button
                v-for="prompt in welcomePrompts"
                :key="prompt"
                type="button"
                @click="composerText = prompt"
              >
                <Sparkles class="lucide-icon" />
                <span>{{ prompt }}</span>
              </button>
            </div>
          </div>

          <template v-for="message in messages" :key="message.id">
            <div :class="['bubble-row', message.role === 'user' ? 'user' : 'ai']">
              <div v-if="message.role !== 'user'" class="bot-icon">
                <Bot class="lucide-icon" />
              </div>
              <article
                :class="['chat-bubble', message.role === 'user' ? 'user-bubble' : 'ai-bubble']"
                :data-testid="`message-bubble-${message.role}`"
              >
                <p v-if="isWaitingMessage(message)" class="waiting-text">思考中</p>
                <template v-else>
                  <MarkdownContent
                    :content="displayMessageContent(message)"
                    :normalize-text="normalizeSpecialDisplayText"
                  />
                </template>
              </article>
            </div>

            <div
              v-if="message.role === 'user' && message.attachments.length"
              class="message-attachments"
              data-testid="message-attachment-list"
            >
              <button
                v-for="attachment in message.attachments"
                :key="attachment.id"
                type="button"
                class="message-attachment-preview"
                data-testid="message-attachment-preview"
                @click="openAttachmentImagePreview(attachment)"
              >
                <img
                  v-if="messageAttachmentObjectUrl(attachment)"
                  :src="messageAttachmentObjectUrl(attachment)"
                  :alt="attachment.file_name"
                />
                <span v-else>图片加载中</span>
              </button>
            </div>

            <div
              v-if="messageImageItems(message).length"
              :class="['message-images', { gallery: message.visual_result_mode === 'gallery' }]"
              data-testid="message-image-list"
            >
              <button
                v-for="item in messageImageItems(message)"
                :key="item.key"
                type="button"
                class="message-image-preview"
                data-testid="message-image-preview"
                @click="openMessageImagePreview(item)"
              >
                <img
                  v-if="citationImageObjectUrl(item)"
                  :src="citationImageObjectUrl(item)"
                  :alt="item.alt"
                />
                <span v-else>图片加载中</span>
                <small v-if="message.visual_result_mode === 'gallery'">
                  [{{ item.citation.index }}] {{ item.citation.file_name }}
                </small>
              </button>
            </div>

            <div
              v-if="message.role === 'assistant' && visibleMessageCitations(message).length"
              class="citation-chips"
              data-testid="citation-chip-list"
            >
              <button
                v-for="citation in visibleMessageCitations(message)"
                :key="citation.chunk_id"
                type="button"
                data-testid="citation-chip"
                :data-citation-index="citation.index"
                @click="selectedCitation = citation"
              >
                <Image v-if="citation.modality === 'image'" class="lucide-icon" />
                [{{ citation.index }}] {{ citation.file_name }}
              </button>
            </div>
            <div v-if="message.role === 'assistant'" class="feedback-row">
              <button
                :class="[
                  'feedback-button',
                  feedbackByMessageId[message.id] === 'helpful' ? 'active' : '',
                ]"
                type="button"
                data-testid="feedback-helpful-button"
                :disabled="feedbackSubmitting[message.id]"
                @click="submitFeedback(message, 'helpful')"
              >
                <CircleCheck class="lucide-icon" />
                有帮助
              </button>
              <button
                :class="[
                  'feedback-button',
                  feedbackByMessageId[message.id] === 'unhelpful' ? 'active' : '',
                ]"
                type="button"
                data-testid="feedback-unhelpful-button"
                :disabled="feedbackSubmitting[message.id]"
                @click="submitFeedback(message, 'unhelpful')"
              >
                <CircleX class="lucide-icon" />
                没帮助
              </button>
            </div>
          </template>
        </div>

        <div class="composer">
          <div v-if="pendingImageAttachment" class="pending-attachment">
            <img :src="pendingImageAttachment.data_url" :alt="pendingImageAttachment.file_name" />
            <span>{{ pendingImageAttachment.file_name }}</span>
            <button type="button" aria-label="移除图片" @click="removePendingImageAttachment">
              ×
            </button>
          </div>
          <textarea
            v-model="composerText"
            data-testid="message-composer"
            placeholder="请输入关于当前知识库的问题..."
            @keydown.enter.exact.prevent="sendMessage"
          />
          <div class="composer-footer">
            <div class="composer-tools">
              <input
                ref="imageInputRef"
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                class="image-input"
                @change="handleImageFileChange"
              />
              <button type="button" class="composer-tool-button" @click="openImagePicker">
                <Image class="lucide-icon" />
                <span>图片</span>
              </button>
            </div>
            <el-button
              type="primary"
              data-testid="send-message-button"
              :disabled="!canSend"
              :loading="sending"
              @click="sendMessage"
            >
              发送
              <Send class="lucide-icon" />
            </el-button>
          </div>
        </div>
        <p class="ai-note">回答基于当前知识库检索结果，请核实重要信息。</p>
      </section>

      <div
        v-if="citationPanelVisible"
        class="column-resizer citation-column-resizer"
        :style="{ right: `${citationPanelWidth}px` }"
        role="separator"
        aria-label="调整引用详情宽度"
        aria-orientation="vertical"
        @pointerdown="startColumnResize('citation-panel', $event)"
      ></div>

      <button
        v-if="!citationPanelOpen && viewportWidth > 1280"
        class="citation-open-button"
        type="button"
        data-testid="citation-panel-open-button"
        aria-label="打开引用详情"
        @click="toggleCitationPanel"
      >
        <span></span>
        <span></span>
        <span></span>
      </button>

      <aside v-if="citationPanelVisible" class="citation-panel" data-testid="citation-panel">
        <header>
          <button
            class="citation-collapse-button"
            type="button"
            data-testid="citation-panel-close-button"
            aria-label="折叠引用详情"
            @click="toggleCitationPanel"
          >
            ‹
          </button>
          <h2>引用详情</h2>
          <div class="citation-header-actions">
            <span>{{ activeCitations.length }}</span>
          </div>
        </header>

        <div class="citation-panel-body ka-scrollbar">
          <article v-if="selectedCitation" class="reference-card" data-testid="citation-detail">
            <div class="reference-title">
              <span class="ref-index">{{ selectedCitation.index }}</span>
              <strong data-testid="citation-detail-file-name">{{
                selectedCitation.file_name
              }}</strong>
            </div>
            <div
              v-if="citationImageSourceUrls(selectedCitation).length"
              class="reference-image"
              data-testid="citation-detail-image"
            >
              <div v-if="selectedCitationImageLoading" class="reference-image-state">
                图片加载中
              </div>
              <button
                v-else-if="selectedCitationImageUrl"
                type="button"
                class="reference-image-preview"
                @click="openSelectedCitationImagePreview"
              >
                <img
                  :src="selectedCitationImageUrl"
                  :alt="selectedCitation.image_alt || selectedCitation.file_name"
                />
              </button>
              <div v-else class="reference-image-state error">
                {{ selectedCitationImageError || '图片无法加载' }}
              </div>
            </div>
            <blockquote data-testid="citation-detail-excerpt">
              {{ selectedCitation.excerpt }}
            </blockquote>
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
        </div>
      </aside>

      <el-dialog
        :model-value="Boolean(selectedImage)"
        title="图片预览"
        width="min(900px, 92vw)"
        class="chat-image-dialog"
        @update:model-value="handleImageDialogOpenChange"
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
.kb-switcher {
  display: inline-flex;
  gap: 10px;
  align-items: center;
  min-height: 44px;
  padding: 0 14px;
  border: 1px solid var(--ka-border);
  border-radius: 8px;
  color: var(--ka-text);
  background: rgb(255 255 255 / 78%);
  box-shadow: 0 8px 18px rgb(23 32 29 / 4%);
  font-weight: 700;
}

.chat-sidebar-main {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  gap: 16px;
  flex: 1 1 auto;
  min-height: 0;
}

.chat-sidebar-kb {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  min-height: 78px;
  padding: 0 16px;
  border: 1px solid var(--ka-border);
  border-radius: 18px;
  color: var(--ka-text);
  background: #fff;
  box-shadow: 0 10px 28px rgb(24 24 27 / 4%);
}

.chat-sidebar-kb .lucide-icon {
  width: 24px;
  height: 24px;
  color: var(--ka-text);
}

.chat-sidebar-kb .kb-select {
  width: 100%;
}

.chat-sidebar-kb .kb-select :deep(.el-select__wrapper) {
  min-height: 52px;
  padding: 0;
  border: 0;
  background: transparent;
  box-shadow: none;
}

.chat-sidebar-kb .kb-select :deep(.el-select__selection) {
  font-size: 20px;
  font-weight: 750;
}

.chat-sidebar-kb .kb-select :deep(.el-select__placeholder) {
  color: var(--ka-text-secondary);
  font-size: 16px;
  font-weight: 650;
}

.chat-sidebar-actions {
  display: grid;
  gap: 12px;
  padding-top: 4px;
}

.chat-sidebar-actions .new-chat,
.chat-sidebar-actions .refresh-button {
  height: 54px;
  margin-left: 0;
  border-radius: 16px;
  font-size: 17px;
}

.chat-sidebar-actions .search-input :deep(.el-input__wrapper) {
  min-height: 54px;
  padding-inline: 14px;
  border-radius: 16px;
}

.chat-sidebar-actions .input-icon {
  width: 20px;
  height: 20px;
  color: #a1a1aa;
}

.sidebar-conversations {
  display: grid;
  align-content: start;
  gap: 10px;
  min-height: 0;
  padding-right: 2px;
  overflow: auto;
}

.chat-sidebar-nav {
  display: grid;
  gap: 6px;
  padding-top: 12px;
  border-top: 1px solid var(--ka-border);
}

.chat-sidebar-nav-item {
  display: flex;
  gap: 10px;
  align-items: center;
  min-height: 38px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 12px;
  color: var(--ka-text-secondary);
  font-size: 13px;
  font-weight: 650;
  transition:
    color 0.16s ease,
    background 0.16s ease,
    border-color 0.16s ease;
}

.chat-sidebar-nav-item:hover,
.chat-sidebar-nav-item.router-link-active {
  color: var(--ka-text);
  border-color: var(--ka-border);
  background: #f4f4f5;
}

.chat-top-title {
  font-weight: 700;
}

.kb-select {
  width: 260px;
}

.kb-select :deep(.el-select__wrapper) {
  border-radius: 6px;
  background: rgb(255 255 255 / 86%);
  box-shadow: 0 0 0 1px var(--ka-border) inset;
}

.chat-page {
  position: relative;
  display: grid;
  height: calc(100vh - var(--ka-header-height));
  background:
    linear-gradient(90deg, rgb(15 118 110 / 4%) 0 1px, transparent 1px 100%),
    linear-gradient(180deg, #f7f8f6 0%, #eef1ef 100%);
  background-size:
    28px 100%,
    auto;
}

.app-sidebar-resizer {
  position: fixed;
  z-index: 35;
  top: 0;
  bottom: 0;
  left: calc(var(--ka-sidebar-width) - 4px);
  width: 8px;
  cursor: col-resize;
}

.app-sidebar-resizer::after,
.column-resizer::after {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 3px;
  width: 2px;
  background: transparent;
  content: '';
  transition: background 0.15s ease;
}

.app-sidebar-resizer:hover::after,
.column-resizer:hover::after {
  background: var(--ka-primary);
}

.column-resizer {
  position: absolute;
  z-index: 8;
  top: 0;
  bottom: 0;
  width: 8px;
  transform: translateX(-4px);
  cursor: col-resize;
}

.conversation-column-resizer {
  left: 360px;
}

.citation-column-resizer {
  right: 380px;
}

:global(body.ka-column-resizing) {
  cursor: col-resize;
  user-select: none;
}

:global(body.ka-column-resizing *) {
  cursor: col-resize !important;
}

.conversation-panel,
.citation-panel {
  border-right: 1px solid var(--ka-border);
  background: rgb(246 248 246 / 88%);
  backdrop-filter: blur(10px);
}

.citation-panel {
  display: grid;
  grid-template-rows: 72px minmax(0, 1fr);
  height: calc(100vh - var(--ka-header-height));
  min-height: 0;
  overflow: hidden;
}

.conversation-panel {
  display: grid;
  align-content: start;
  gap: 14px;
  padding: 22px 20px;
}

.new-chat,
.refresh-button {
  width: 100%;
  height: 48px;
  border-radius: 8px;
}

.new-chat {
  --el-button-bg-color: var(--ka-primary);
  --el-button-border-color: var(--ka-primary);
  --el-button-hover-bg-color: var(--ka-primary-deep);
  --el-button-hover-border-color: var(--ka-primary-deep);
  box-shadow: 0 12px 22px rgb(15 118 110 / 16%);
  font-size: 15px;
  font-weight: 800;
}

.refresh-button {
  border-color: var(--ka-border);
  background: rgb(255 255 255 / 76%);
  color: var(--ka-primary);
}

.search-input :deep(.el-input__wrapper) {
  min-height: 48px;
  border-radius: 8px;
  background: rgb(255 255 255 / 84%);
  box-shadow: 0 0 0 1px var(--ka-border) inset;
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
  min-height: 64px;
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
  border-radius: 6px;
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
  border-color: var(--ka-primary);
  color: #fff;
  background: var(--ka-primary);
  box-shadow: 0 10px 20px rgb(15 118 110 / 16%);
}

.conversation.active span {
  color: rgb(255 255 255 / 76%);
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

.chat-sidebar-main .conversation {
  grid-template-columns: minmax(0, 1fr) 44px;
  border-color: var(--ka-border);
  border-radius: 18px;
  background: #fff;
}

.chat-sidebar-main .conversation:hover,
.chat-sidebar-main .conversation.active {
  border-color: var(--ka-border-strong);
  background: #f4f4f5;
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 70%);
}

.chat-sidebar-main .conversation-main {
  min-height: 82px;
  padding: 17px 0 17px 18px;
}

.chat-sidebar-main .conversation strong {
  font-size: 17px;
  line-height: 1.35;
}

.chat-sidebar-main .conversation span {
  font-size: 14px;
}

.chat-sidebar-main .conversation-delete {
  width: 34px;
  height: 34px;
  margin-right: 10px;
  border-radius: 10px;
}

.chat-sidebar-main .panel-empty {
  min-height: 72px;
  border-radius: 16px;
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
  background: rgb(255 255 255 / 72%);
}

.message-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  padding: 34px 32px 16px;
  overflow: hidden;
  border-right: 1px solid var(--ka-border);
  background: #fbfcfb;
}

.messages {
  flex: 0 1 auto;
  min-height: 0;
  max-height: calc(100vh - var(--ka-header-height) - 240px);
  overflow: auto;
  padding: 14px 18px 28px;
}

.error-banner {
  padding: 12px 14px;
  margin-bottom: 16px;
  color: var(--ka-error);
  background: #fff0ed;
}

.welcome-state {
  display: grid;
  width: min(100%, 900px);
  min-height: 220px;
  margin: 12px auto 0;
  justify-items: center;
  gap: 14px;
  padding: 34px 36px;
  color: var(--ka-text-secondary);
  background: rgb(255 255 255 / 84%);
  box-shadow: 0 14px 34px rgb(23 32 29 / 6%);
  backdrop-filter: blur(10px);
  text-align: center;
}

.welcome-icon {
  display: grid;
  width: 54px;
  height: 54px;
  place-items: center;
  border-radius: 8px;
  color: #fff;
  background: var(--ka-primary);
  box-shadow: 0 12px 24px rgb(15 118 110 / 16%);
  font-size: 26px;
}

.welcome-state h2,
.welcome-state p {
  margin: 0;
}

.welcome-state h2 {
  color: var(--ka-text);
  font-size: 24px;
  line-height: 1.2;
}

.welcome-state p {
  max-width: 680px;
  font-size: 15px;
  line-height: 1.5;
}

.welcome-prompts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  width: 100%;
  margin-top: 12px;
}

.welcome-prompts button {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
  min-height: 76px;
  padding: 16px;
  border: 1px solid var(--ka-border);
  border-radius: 8px;
  color: var(--ka-text);
  background: rgb(255 255 255 / 78%);
  font-weight: 700;
  text-align: left;
  cursor: pointer;
  box-shadow: 0 8px 20px rgb(23 32 29 / 4%);
}

.welcome-prompts button:hover {
  border-color: var(--ka-primary);
  background: #fff;
  transform: translateY(-1px);
}

.welcome-prompts .el-icon {
  color: var(--ka-primary);
  font-size: 22px;
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
  padding: 18px 22px;
  font-size: 15px;
  line-height: 1.7;
  box-shadow: 0 10px 26px rgb(23 32 29 / 5%);
}

.chat-bubble p {
  margin: 0 0 8px;
}

.chat-bubble p:last-child {
  margin-bottom: 0;
}

.waiting-text {
  color: var(--ka-text-secondary);
  font-style: italic;
}

.waiting-text::after {
  display: inline-block;
  width: 18px;
  content: '...';
  animation: waiting-pulse 1.2s infinite;
}

@keyframes waiting-pulse {
  0%,
  100% {
    opacity: 0.35;
  }

  50% {
    opacity: 1;
  }
}

.user-bubble {
  border-radius: 8px 8px 2px;
  color: #fff;
  background: var(--ka-primary);
  box-shadow: 0 12px 26px rgb(15 118 110 / 18%);
}

.ai-bubble {
  border: 1px solid var(--ka-border);
  border-radius: 2px 8px 8px;
  background: #fff;
}

.bot-icon {
  display: grid;
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 8px;
  color: var(--ka-primary);
  background: var(--ka-primary-soft);
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

.message-images {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 260px));
  gap: 12px;
  margin: -8px 0 18px 52px;
}

.message-images.gallery {
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  max-width: 900px;
}

.message-attachments {
  display: flex;
  justify-content: flex-end;
  margin: -8px 0 18px;
}

.message-attachment-preview {
  display: grid;
  width: min(260px, 42vw);
  min-height: 132px;
  overflow: hidden;
  place-items: center;
  border: 1px solid var(--ka-border);
  border-radius: 8px;
  color: var(--ka-text-secondary);
  background: #fff;
  cursor: pointer;
}

.message-attachment-preview img {
  display: block;
  width: 100%;
  height: 160px;
  object-fit: contain;
}

.message-image-preview {
  display: grid;
  min-height: 132px;
  overflow: hidden;
  place-items: center;
  border: 1px solid var(--ka-border);
  border-radius: 8px;
  color: var(--ka-text-secondary);
  background: #fff;
  cursor: pointer;
}

.message-images.gallery .message-image-preview {
  grid-template-rows: 140px auto;
}

.message-image-preview img {
  display: block;
  width: 100%;
  height: 160px;
  object-fit: contain;
}

.message-images.gallery .message-image-preview img {
  height: 140px;
}

.message-image-preview span {
  font-size: 13px;
}

.message-image-preview small {
  width: 100%;
  padding: 8px 10px;
  overflow: hidden;
  border-top: 1px solid var(--ka-border);
  color: var(--ka-text-secondary);
  font-size: 12px;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.citation-chips button {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 8px 12px;
  border: 1px solid var(--ka-border);
  border-radius: 6px;
  color: var(--ka-primary);
  background: var(--ka-primary-soft);
  cursor: pointer;
}

.citation-chips button:hover {
  border-color: var(--ka-primary);
  background: #ecfaf6;
}

.citation-chips .el-icon {
  font-size: 14px;
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
  border-radius: 6px;
  color: var(--ka-text-secondary);
  background: rgb(255 255 255 / 78%);
  cursor: pointer;
}

.feedback-button.active {
  color: var(--ka-primary);
  border-color: var(--ka-primary);
  background: var(--ka-primary-soft);
}

.feedback-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.composer {
  width: min(100%, 960px);
  min-height: 146px;
  margin: 0 auto;
  padding: 18px 20px;
  border: 1px solid var(--ka-border-strong);
  border-radius: 8px;
  background: rgb(255 255 255 / 92%);
  box-shadow: 0 16px 38px rgb(23 32 29 / 10%);
  backdrop-filter: blur(10px);
}

.composer textarea {
  width: 100%;
  min-height: 76px;
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
  gap: 12px;
  color: #344054;
  font-size: 22px;
}

.image-input {
  display: none;
}

.composer-tool-button {
  display: grid;
  width: 36px;
  height: 36px;
  padding: 0;
  place-items: center;
  border: 0;
  border-radius: 6px;
  color: #344054;
  background: transparent;
  cursor: pointer;
  font-size: 22px;
}

.composer-tool-button:hover {
  color: var(--ka-primary);
  background: var(--ka-primary-soft);
}

.pending-attachment {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr) 28px;
  gap: 10px;
  align-items: center;
  max-width: 340px;
  padding: 8px;
  margin-bottom: 10px;
  border: 1px solid var(--ka-border);
  border-radius: 6px;
  background: #fff;
}

.pending-attachment img {
  width: 52px;
  height: 42px;
  object-fit: cover;
  border-radius: 4px;
}

.pending-attachment span {
  overflow: hidden;
  color: var(--ka-text-secondary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pending-attachment button {
  display: grid;
  width: 26px;
  height: 26px;
  padding: 0;
  place-items: center;
  border: 0;
  color: var(--ka-text-secondary);
  background: transparent;
  cursor: pointer;
  font-size: 20px;
}

.ai-note {
  margin: 12px 0 0;
  color: var(--ka-placeholder);
  text-align: center;
}

.citation-panel {
  border-right: 0;
  background: rgb(246 248 246 / 88%);
}

.citation-panel header {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  height: 72px;
  gap: 14px;
  padding: 0 22px;
  border-bottom: 1px solid var(--ka-border);
}

.citation-panel h2 {
  margin: 0;
  font-size: 18px;
  text-align: center;
}

.citation-panel-body {
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.citation-header-actions {
  display: inline-flex;
  gap: 12px;
  align-items: center;
}

.citation-open-button {
  border: 1px solid var(--ka-border);
  color: var(--ka-text-secondary);
  background: #fff;
  cursor: pointer;
}

.citation-collapse-button {
  display: grid;
  width: 34px;
  height: 34px;
  padding: 0;
  place-items: center;
  border: 0;
  border-radius: 6px;
  color: var(--ka-text);
  background: transparent;
  cursor: pointer;
  font-size: 28px;
  line-height: 1;
}

.citation-collapse-button:hover {
  color: var(--ka-primary);
  background: var(--ka-primary-soft);
}

.citation-open-button:hover {
  color: var(--ka-primary);
  border-color: var(--ka-primary);
  background: var(--ka-primary-soft);
}

.citation-open-button {
  position: relative;
  display: flex;
  align-self: stretch;
  justify-self: stretch;
  gap: 4px;
  align-items: center;
  justify-content: center;
  place-items: center;
  width: 100%;
  min-width: 0;
  padding: 0;
  border-width: 0 0 0 1px;
  border-radius: 0;
  background: rgb(246 248 246 / 88%);
}

.citation-open-button::before {
  position: absolute;
  display: block;
  width: 38px;
  height: 38px;
  border: 1px solid var(--ka-border);
  border-radius: 50%;
  background: #fff;
  content: '';
}

.citation-open-button span {
  position: relative;
  display: grid;
  width: 4px;
  height: 4px;
  border-radius: 999px;
  background: var(--ka-text-secondary);
  z-index: 1;
}

.citation-open-button span:nth-child(1) {
  transform: none;
}

.reference-card {
  margin: 24px;
  padding: 18px;
  border: 1px solid var(--ka-border);
  border-radius: 8px;
  background: rgb(255 255 255 / 86%);
  box-shadow: 0 12px 28px rgb(23 32 29 / 5%);
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

.reference-image {
  display: grid;
  min-height: 180px;
  margin-bottom: 14px;
  overflow: hidden;
  place-items: center;
  border: 1px solid var(--ka-border);
  border-radius: 8px;
  background: #fff;
}

.reference-image img {
  display: block;
  width: 100%;
  max-height: 320px;
  object-fit: contain;
}

.reference-image-preview {
  display: grid;
  width: 100%;
  min-height: 180px;
  padding: 0;
  border: 0;
  place-items: center;
  background: transparent;
  cursor: pointer;
}

.reference-image-preview img {
  max-height: 320px;
}

.reference-image-state {
  padding: 20px;
  color: var(--ka-text-secondary);
  font-size: 14px;
}

.reference-image-state.error {
  color: var(--ka-error);
}

.ref-index {
  display: grid;
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 6px;
  color: #fff;
  background: var(--ka-accent);
  font-weight: 700;
}

blockquote {
  margin: 0;
  padding: 16px;
  border-left: 3px solid var(--ka-accent);
  border-radius: 6px;
  color: var(--ka-text-secondary);
  background: var(--ka-accent-soft);
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

.dialog-image {
  display: block;
  max-width: 100%;
  max-height: 72vh;
  margin: 0 auto;
  object-fit: contain;
}

@media (max-width: 1280px) {
  .chat-page.has-inline-conversations {
    grid-template-columns: 300px minmax(420px, 1fr);
  }

  .citation-panel {
    display: none;
  }

  .citation-column-resizer,
  .citation-open-button {
    display: none;
  }
}

@media (max-width: 960px) {
  .app-sidebar-resizer {
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

  .app-sidebar-resizer,
  .column-resizer {
    display: none;
  }
}

/* User-facing v0/shadcn visual layer. Kept local to this page so admin pages are untouched. */
.lucide-icon,
.input-icon {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  stroke-width: 2;
}

.kb-switcher {
  min-height: 40px;
  padding: 0 12px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 8px 20px rgb(24 24 27 / 4%);
  font-weight: 600;
}

.kb-select :deep(.el-select__wrapper) {
  min-height: 34px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 0 0 1px transparent inset;
}

.chat-page {
  color: #18181b;
  background: #fafafa;
}

.app-sidebar-resizer:hover::after,
.column-resizer:hover::after {
  background: #a1a1aa;
}

.conversation-panel,
.citation-panel {
  border-right: 1px solid var(--ka-border);
  background: #fff;
  backdrop-filter: none;
}

.conversation-panel {
  gap: 12px;
  padding: 18px 16px;
}

.new-chat,
.refresh-button {
  height: 42px;
  border-radius: 12px;
  transition:
    background 0.16s ease,
    border-color 0.16s ease,
    color 0.16s ease;
}

.new-chat {
  --el-button-bg-color: #18181b;
  --el-button-border-color: #18181b;
  --el-button-hover-bg-color: #27272a;
  --el-button-hover-border-color: #27272a;
  box-shadow: 0 12px 28px rgb(24 24 27 / 10%);
  font-size: 14px;
  font-weight: 700;
}

.refresh-button {
  border-color: var(--ka-border);
  color: var(--ka-text-secondary);
  background: #fff;
}

.refresh-button:hover {
  border-color: var(--ka-border-strong);
  color: var(--ka-text);
  background: #f4f4f5;
}

.search-input :deep(.el-input__wrapper) {
  min-height: 42px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 0 0 1px var(--ka-border) inset;
}

.conversation {
  border-radius: 12px;
  transition:
    background 0.16s ease,
    border-color 0.16s ease;
}

.conversation:hover {
  border-color: #eeeeef;
  background: #f4f4f5;
}

.conversation-main {
  min-height: 60px;
}

.conversation-delete {
  border-radius: 10px;
}

.conversation.active {
  border-color: var(--ka-border);
  color: var(--ka-text);
  background: #f4f4f5;
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 68%);
}

.conversation.active span {
  color: var(--ka-text-secondary);
}

.conversation strong {
  font-weight: 650;
}

.panel-empty,
.welcome-state,
.error-banner {
  border-radius: 12px;
}

.panel-empty {
  background: #fafafa;
}

.message-panel {
  padding: 28px 28px 16px;
  background: #fafafa;
}

.messages {
  padding: 14px 18px 24px;
}

.error-banner {
  background: #fef2f2;
}

.welcome-state {
  min-height: 230px;
  gap: 16px;
  padding: 32px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(24 24 27 / 4%);
  backdrop-filter: none;
}

.welcome-icon {
  width: 52px;
  height: 52px;
  border: 1px solid var(--ka-border);
  border-radius: 14px;
  color: #fff;
  background: #18181b;
  box-shadow: 0 14px 32px rgb(24 24 27 / 12%);
}

.welcome-icon .lucide-icon {
  width: 24px;
  height: 24px;
}

.welcome-state h2 {
  font-weight: 750;
}

.welcome-prompts {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

.welcome-prompts button {
  display: inline-flex;
  grid-template-columns: none;
  gap: 8px;
  align-items: center;
  max-width: min(100%, 420px);
  min-height: 40px;
  padding: 9px 12px;
  border-radius: 999px;
  background: #fff;
  box-shadow: none;
  font-size: 13px;
  font-weight: 600;
  transition:
    background 0.16s ease,
    border-color 0.16s ease,
    color 0.16s ease,
    transform 0.16s ease;
}

.welcome-prompts button:hover {
  border-color: var(--ka-border-strong);
  background: #f4f4f5;
}

.welcome-prompts .lucide-icon {
  width: 16px;
  height: 16px;
  color: var(--ka-text-secondary);
}

.chat-bubble {
  padding: 16px 18px;
  box-shadow: none;
}

.message-table th {
  background: #f4f4f5;
}

.user-bubble {
  border-radius: 16px 16px 4px;
  background: #18181b;
  box-shadow: 0 12px 28px rgb(24 24 27 / 10%);
}

.ai-bubble {
  border-radius: 4px 16px 16px;
  background: #fff;
  box-shadow: 0 10px 26px rgb(24 24 27 / 4%);
}

.bot-icon {
  border: 1px solid var(--ka-border);
  border-radius: 12px;
  color: var(--ka-text);
  background: #fff;
}

.message-attachment-preview,
.message-image-preview {
  border-radius: 12px;
}

.citation-chips button {
  border-radius: 999px;
  color: var(--ka-text);
  background: #fff;
  font-size: 12px;
  transition:
    background 0.16s ease,
    border-color 0.16s ease;
}

.citation-chips button:hover {
  border-color: var(--ka-border-strong);
  background: #f4f4f5;
}

.citation-chips .lucide-icon {
  width: 14px;
  height: 14px;
}

.feedback-button {
  border-radius: 999px;
  background: #fff;
  transition:
    color 0.16s ease,
    background 0.16s ease,
    border-color 0.16s ease;
}

.feedback-button:hover:not(:disabled),
.feedback-button.active {
  color: var(--ka-text);
  border-color: var(--ka-border-strong);
  background: #f4f4f5;
}

.composer {
  width: min(100%, 900px);
  min-height: 142px;
  padding: 14px;
  border-color: #27272a;
  border-radius: 18px;
  color: #fff;
  background: #18181b;
  box-shadow: 0 18px 44px rgb(24 24 27 / 18%);
  backdrop-filter: none;
}

.composer textarea {
  color: #fff;
  background: #18181b;
  font-size: 15px;
  line-height: 1.6;
}

.composer textarea::placeholder {
  color: #71717a;
}

.composer-footer {
  padding-top: 12px;
  border-top: 1px solid #27272a;
}

.composer-tool-button {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  width: auto;
  min-height: 34px;
  padding: 0 10px;
  border: 1px solid #27272a;
  border-radius: 10px;
  color: #a1a1aa;
  background: #18181b;
  font-size: 13px;
  transition:
    color 0.16s ease,
    background 0.16s ease,
    border-color 0.16s ease;
}

.composer-tool-button:hover {
  color: #fff;
  border-color: #3f3f46;
  background: #27272a;
}

.composer :deep(.el-button--primary) {
  --el-button-bg-color: #fff;
  --el-button-border-color: #fff;
  --el-button-text-color: #18181b;
  --el-button-hover-bg-color: #e4e4e7;
  --el-button-hover-border-color: #e4e4e7;
  --el-button-hover-text-color: #18181b;
  min-height: 36px;
  border-radius: 999px;
}

.composer :deep(.el-button.is-disabled) {
  opacity: 0.5;
}

.pending-attachment {
  border-color: #27272a;
  border-radius: 12px;
  background: #27272a;
}

.pending-attachment span {
  color: #e4e4e7;
}

.pending-attachment button {
  color: #a1a1aa;
}

.citation-panel {
  border-left: 1px solid var(--ka-border);
  background: #fff;
}

.citation-panel-body {
  background: #fff;
}

.citation-collapse-button,
.citation-open-button {
  border-radius: 10px;
}

.citation-collapse-button:hover,
.citation-open-button:hover {
  color: var(--ka-text);
  border-color: var(--ka-border-strong);
  background: #f4f4f5;
}

.reference-card {
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(24 24 27 / 4%);
}

.reference-image,
.reference-image-preview,
.reference-image-state {
  border-radius: 12px;
}

.ref-index {
  border-radius: 10px;
  background: #18181b;
}

blockquote {
  border-left-color: var(--ka-border);
  border-radius: 12px;
  background: #f4f4f5;
}

.reference-empty {
  padding: 24px;
  border: 1px dashed var(--ka-border);
  border-radius: 16px;
  margin: 70px 24px 0;
  background: #fff;
}

@media (max-width: 860px) {
  .message-panel {
    padding: 18px 12px;
  }

  .messages {
    padding: 8px 4px 20px;
  }

  .welcome-prompts {
    justify-content: flex-start;
    overflow-x: auto;
    flex-wrap: nowrap;
    padding-bottom: 2px;
  }

  .welcome-prompts button {
    flex: 0 0 260px;
    max-width: 260px;
  }

  .composer {
    border-radius: 16px;
  }
}
</style>
