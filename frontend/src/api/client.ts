import type {
  AuditLog,
  AuditLogListQuery,
  AssistantProfile,
  Chunk,
  ConsumerSessionRequest,
  ConsumerUserOptionsResponse,
  Conversation,
  ConversationCreateRequest,
  ConversationDetail,
  DocumentSummary,
  FileItem,
  FileListQuery,
  FileStatusResponse,
  FileUploadResponse,
  Feedback,
  FeedbackCreateRequest,
  KnowledgeBaseCreateRequest,
  KnowledgeBaseListQuery,
  LoginRequest,
  LoginResponse,
  MessageCreateRequest,
  MessageCreateResponse,
  ModelSettings,
  PaginatedResponse,
  KnowledgeBase,
  KnowledgeBasePublicSummary,
  KnowledgeBaseUpdateRequest,
  KnowledgeGraph,
  LogoutRequest,
  ParseJob,
  ResetPasswordRequest,
  ResetPasswordResponse,
  SseDoneEvent,
  SseMessageCreatedEvent,
  SseRetrievalEvent,
  SseThinkingEvent,
  SseTokenEvent,
  User,
  UserCreateRequest,
  UserListQuery,
  UserUpdateRequest,
} from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
const ACCESS_TOKEN_KEY = 'kb_agent_access_token'
const REFRESH_TOKEN_KEY = 'kb_agent_refresh_token'
let cachedCurrentUser: User | null = null
let currentUserRequest: Promise<User> | null = null

export class ApiClientError extends Error {
  code?: string
  details: Record<string, unknown>

  constructor(message: string, code?: string, details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiClientError'
    this.code = code
    this.details = details
  }
}

export function getAccessToken(): string | null {
  return window.localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  return window.localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function saveAuthTokens(response: LoginResponse): void {
  window.localStorage.setItem(ACCESS_TOKEN_KEY, response.access_token)
  window.localStorage.setItem(REFRESH_TOKEN_KEY, response.refresh_token)
  cachedCurrentUser = response.user
  currentUserRequest = null
}

export function clearAuthTokens(): void {
  window.localStorage.removeItem(ACCESS_TOKEN_KEY)
  window.localStorage.removeItem(REFRESH_TOKEN_KEY)
  cachedCurrentUser = null
  currentUserRequest = null
}

export async function login(payload: LoginRequest): Promise<LoginResponse> {
  return apiRequest<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
    skipAuth: true,
  })
}

export async function listConsumerUsers(): Promise<ConsumerUserOptionsResponse> {
  return apiRequest<ConsumerUserOptionsResponse>('/auth/consumer-users', {
    skipAuth: true,
  })
}

export async function createConsumerSession(
  payload: ConsumerSessionRequest,
): Promise<LoginResponse> {
  return apiRequest<LoginResponse>('/auth/consumer-session', {
    method: 'POST',
    body: JSON.stringify(payload),
    skipAuth: true,
  })
}

export function getCachedCurrentUser(): User | null {
  return cachedCurrentUser
}

export async function getCurrentUser(forceRefresh = false): Promise<User> {
  if (!forceRefresh && cachedCurrentUser) {
    return cachedCurrentUser
  }
  if (!forceRefresh && currentUserRequest) {
    return currentUserRequest
  }

  const request = apiRequest<User>('/auth/me')
    .then((user) => {
      cachedCurrentUser = user
      return user
    })
    .finally(() => {
      if (currentUserRequest === request) {
        currentUserRequest = null
      }
    })
  currentUserRequest = request
  return request
}

export async function logout(payload: LogoutRequest): Promise<void> {
  return apiRequest<void>('/auth/logout', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function listUsers(query: UserListQuery = {}): Promise<PaginatedResponse<User>> {
  const params = new URLSearchParams()
  params.set('page', String(query.page ?? 1))
  params.set('page_size', String(query.page_size ?? 50))
  if (query.keyword) {
    params.set('keyword', query.keyword)
  }
  if (query.role) {
    params.set('role', query.role)
  }
  if (query.is_active !== undefined) {
    params.set('is_active', String(query.is_active))
  }
  return apiRequest<PaginatedResponse<User>>(`/users?${params.toString()}`)
}

export async function createUser(payload: UserCreateRequest): Promise<User> {
  return apiRequest<User>('/users', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateUser(userId: string, payload: UserUpdateRequest): Promise<User> {
  return apiRequest<User>(`/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function disableUser(userId: string): Promise<User> {
  return apiRequest<User>(`/users/${userId}/disable`, {
    method: 'POST',
  })
}

export async function enableUser(userId: string): Promise<User> {
  return apiRequest<User>(`/users/${userId}/enable`, {
    method: 'POST',
  })
}

export async function resetUserPassword(
  userId: string,
  payload: ResetPasswordRequest,
): Promise<ResetPasswordResponse> {
  return apiRequest<ResetPasswordResponse>(`/users/${userId}/reset-password`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getAssistantProfile(): Promise<AssistantProfile> {
  return apiRequest<AssistantProfile>('/assistant-profile')
}

export async function updateAssistantProfile(
  payload: AssistantProfile,
): Promise<AssistantProfile> {
  return apiRequest<AssistantProfile>('/assistant-profile', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function getModelSettings(): Promise<ModelSettings> {
  return apiRequest<ModelSettings>('/model-settings')
}

export async function updateModelSettings(payload: ModelSettings): Promise<ModelSettings> {
  return apiRequest<ModelSettings>('/model-settings', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function listKnowledgeBases(
  query: KnowledgeBaseListQuery = {},
): Promise<PaginatedResponse<KnowledgeBase>> {
  const params = new URLSearchParams()
  params.set('page', String(query.page ?? 1))
  params.set('page_size', String(query.page_size ?? 50))
  if (query.keyword) {
    params.set('keyword', query.keyword)
  }
  if (query.status) {
    params.set('status', query.status)
  }
  return apiRequest<PaginatedResponse<KnowledgeBase>>(`/knowledge-bases?${params.toString()}`)
}

export async function getKnowledgeBasePublicSummary(): Promise<KnowledgeBasePublicSummary> {
  return apiRequest<KnowledgeBasePublicSummary>('/knowledge-bases/public-summary', {
    skipAuth: true,
  })
}

export async function getKnowledgeGraph(query: {
  knowledge_base_id?: string
  include_cross_knowledge_base?: boolean
  min_similarity?: number
} = {}): Promise<KnowledgeGraph> {
  const params = new URLSearchParams()
  if (query.knowledge_base_id) {
    params.set('knowledge_base_id', query.knowledge_base_id)
  }
  params.set(
    'include_cross_knowledge_base',
    String(query.include_cross_knowledge_base ?? true),
  )
  params.set('min_similarity', String(query.min_similarity ?? 0.45))
  return apiRequest<KnowledgeGraph>(`/knowledge-graph?${params.toString()}`)
}

export async function refreshKnowledgeGraph(forceEmbeddings = false): Promise<KnowledgeGraph> {
  return apiRequest<KnowledgeGraph>('/knowledge-graph/refresh', {
    method: 'POST',
    body: JSON.stringify({ force_embeddings: forceEmbeddings }),
  })
}

export async function createKnowledgeBase(
  payload: KnowledgeBaseCreateRequest,
): Promise<KnowledgeBase> {
  return apiRequest<KnowledgeBase>('/knowledge-bases', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateKnowledgeBase(
  knowledgeBaseId: string,
  payload: KnowledgeBaseUpdateRequest,
): Promise<KnowledgeBase> {
  return apiRequest<KnowledgeBase>(`/knowledge-bases/${knowledgeBaseId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteKnowledgeBase(knowledgeBaseId: string): Promise<void> {
  return apiRequest<void>(`/knowledge-bases/${knowledgeBaseId}`, {
    method: 'DELETE',
  })
}

export async function listFiles(
  knowledgeBaseId: string,
  query: FileListQuery = {},
): Promise<PaginatedResponse<FileItem>> {
  const params = new URLSearchParams()
  params.set('page', String(query.page ?? 1))
  params.set('page_size', String(query.page_size ?? 50))
  if (query.keyword) {
    params.set('keyword', query.keyword)
  }
  if (query.status) {
    params.set('status', query.status)
  }
  return apiRequest<PaginatedResponse<FileItem>>(
    `/knowledge-bases/${knowledgeBaseId}/files?${params.toString()}`,
  )
}

export async function uploadFiles(
  knowledgeBaseId: string,
  files: File[],
  force = false,
): Promise<FileUploadResponse> {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  formData.append('force', String(force))
  return apiRequest<FileUploadResponse>(`/knowledge-bases/${knowledgeBaseId}/files/upload`, {
    method: 'POST',
    body: formData,
  })
}

export async function getFileStatus(fileId: string): Promise<FileStatusResponse> {
  return apiRequest<FileStatusResponse>(`/files/${fileId}/status`)
}

export async function getFile(fileId: string): Promise<FileItem> {
  return apiRequest<FileItem>(`/files/${fileId}`)
}

export async function getFileSummary(fileId: string): Promise<DocumentSummary> {
  return apiRequest<DocumentSummary>(`/files/${fileId}/summary`)
}

export async function retryFileSummary(
  fileId: string,
  force = false,
): Promise<DocumentSummary> {
  return apiRequest<DocumentSummary>(`/files/${fileId}/summary/retry`, {
    method: 'POST',
    body: JSON.stringify({ force }),
  })
}

export async function retryParseFile(fileId: string): Promise<ParseJob> {
  return apiRequest<ParseJob>(`/files/${fileId}/retry-parse`, {
    method: 'POST',
  })
}

export async function deleteFile(fileId: string): Promise<void> {
  return apiRequest<void>(`/files/${fileId}`, {
    method: 'DELETE',
  })
}

export async function listFileChunks(
  fileId: string,
  page = 1,
  pageSize = 50,
): Promise<PaginatedResponse<Chunk>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  return apiRequest<PaginatedResponse<Chunk>>(`/files/${fileId}/chunks?${params.toString()}`)
}

export async function listConversations(
  knowledgeBaseId: string,
): Promise<PaginatedResponse<Conversation>> {
  return apiRequest<PaginatedResponse<Conversation>>(
    `/conversations?knowledge_base_id=${encodeURIComponent(knowledgeBaseId)}&page=1&page_size=50`,
  )
}

export async function createConversation(
  payload: ConversationCreateRequest,
): Promise<Conversation> {
  return apiRequest<Conversation>('/conversations', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getConversation(conversationId: string): Promise<ConversationDetail> {
  return apiRequest<ConversationDetail>(`/conversations/${conversationId}`)
}

export async function deleteConversation(conversationId: string): Promise<void> {
  return apiRequest<void>(`/conversations/${conversationId}`, {
    method: 'DELETE',
  })
}

export async function sendConversationMessage(
  conversationId: string,
  payload: MessageCreateRequest,
): Promise<MessageCreateResponse> {
  return apiRequest<MessageCreateResponse>(`/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export interface ConversationMessageStreamHandlers {
  onMessageCreated?: (event: SseMessageCreatedEvent) => void
  onRetrieval?: (event: SseRetrievalEvent) => void
  onThinking?: (event: SseThinkingEvent) => void
  onToken?: (event: SseTokenEvent) => void
  onDone?: (event: SseDoneEvent) => void
}

export async function streamConversationMessage(
  conversationId: string,
  payload: MessageCreateRequest,
  handlers: ConversationMessageStreamHandlers,
): Promise<void> {
  const headers = new Headers()
  headers.set('Content-Type', 'application/json')
  const token = getAccessToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ ...payload, stream: true }),
  })
  if (!response.ok) {
    throw await readError(response)
  }
  if (!response.body) {
    throw new ApiClientError('Streaming response body is empty.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) {
      break
    }
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    parts.forEach((part) => dispatchSseEvent(part, handlers))
  }
  buffer += decoder.decode()
  if (buffer.trim()) {
    dispatchSseEvent(buffer, handlers)
  }
}

function dispatchSseEvent(rawEvent: string, handlers: ConversationMessageStreamHandlers): void {
  const lines = rawEvent.split('\n')
  const event = lines
    .find((line) => line.startsWith('event:'))
    ?.slice('event:'.length)
    .trim()
  const data = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice('data:'.length).trim())
    .join('\n')
  if (!event || !data) {
    return
  }
  const payload = JSON.parse(data) as unknown
  if (event === 'message_created') {
    handlers.onMessageCreated?.(payload as SseMessageCreatedEvent)
  } else if (event === 'retrieval') {
    handlers.onRetrieval?.(payload as SseRetrievalEvent)
  } else if (event === 'thinking') {
    handlers.onThinking?.(payload as SseThinkingEvent)
  } else if (event === 'token') {
    handlers.onToken?.(payload as SseTokenEvent)
  } else if (event === 'done') {
    handlers.onDone?.(payload as SseDoneEvent)
  }
}

export async function submitMessageFeedback(
  messageId: string,
  payload: FeedbackCreateRequest,
): Promise<Feedback> {
  return apiRequest<Feedback>(`/messages/${messageId}/feedback`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function loadAuthorizedAssetObjectUrl(assetUrl: string): Promise<string> {
  if (assetUrl.startsWith('data:image/')) {
    return assetUrl
  }
  if (assetUrl.startsWith('http://') || assetUrl.startsWith('https://')) {
    return assetUrl
  }

  const requestUrl = buildAssetRequestUrl(assetUrl)
  const headers = new Headers()
  const token = getAccessToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const response = await fetch(requestUrl, { headers })
  if (!response.ok) {
    throw await readError(response)
  }
  return URL.createObjectURL(await response.blob())
}

function buildAssetRequestUrl(assetUrl: string): string {
  if (assetUrl.startsWith(API_BASE_URL)) {
    return assetUrl
  }
  if (assetUrl.startsWith('/api/v1')) {
    return `${API_BASE_URL}${assetUrl.slice('/api/v1'.length)}`
  }
  if (assetUrl.startsWith('/')) {
    return `${API_BASE_URL}${assetUrl}`
  }
  return assetUrl
}

export async function listAuditLogs(
  query: AuditLogListQuery = {},
): Promise<PaginatedResponse<AuditLog>> {
  const params = new URLSearchParams()
  params.set('page', String(query.page ?? 1))
  params.set('page_size', String(query.page_size ?? 50))
  if (query.actor_id) {
    params.set('actor_id', query.actor_id)
  }
  if (query.action) {
    params.set('action', query.action)
  }
  if (query.resource_type) {
    params.set('resource_type', query.resource_type)
  }
  return apiRequest<PaginatedResponse<AuditLog>>(`/audit-logs?${params.toString()}`)
}

interface ApiRequestInit extends RequestInit {
  skipAuth?: boolean
}

async function apiRequest<T>(path: string, init: ApiRequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (!(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!init.skipAuth) {
    const token = getAccessToken()
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  })

  if (!response.ok) {
    const error = await readError(response)
    throw error
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

async function readError(response: Response): Promise<ApiClientError> {
  try {
    const payload = (await response.json()) as {
      error?: { code?: string; message?: string; details?: Record<string, unknown> }
    }
    const code = payload.error?.code
    const message = payload.error?.message
    const details = payload.error?.details ?? {}
    return new ApiClientError(
      [code, message].filter(Boolean).join(': ') || response.statusText,
      code,
      details,
    )
  } catch {
    return new ApiClientError(response.statusText)
  }
}
