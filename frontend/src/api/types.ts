export type UserRole = 'admin' | 'user'

export type KnowledgeBaseStatus = 'active' | 'deleting' | 'deleted'

export type FileStatus =
  | 'uploaded'
  | 'queued'
  | 'processing'
  | 'indexed'
  | 'partially_indexed'
  | 'failed'
  | 'deleting'
  | 'deleted'

export type ParseJobStatus =
  | 'queued'
  | 'parsing'
  | 'normalizing'
  | 'chunking'
  | 'embedding'
  | 'indexing'
  | 'indexed'
  | 'partially_indexed'
  | 'failed'
  | 'cancelled'

export type MessageRole = 'user' | 'assistant' | 'system'

export type FeedbackRating = 'helpful' | 'unhelpful'

export interface ApiErrorEnvelope {
  code: string
  message: string
  details: Record<string, unknown>
  request_id: string
}

export interface ApiErrorResponse {
  error: ApiErrorEnvelope
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface HealthResponse {
  status: 'ok'
  service: string
  version: string
}

export interface User {
  id: string
  username: string
  display_name: string
  role: UserRole
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

export interface LoginRequest {
  username: string
  password: string
}

export interface ConsumerSessionRequest {
  session_id: string
  display_name?: string
}

export interface ConsumerUserOption {
  username: string
  display_name: string
}

export interface ConsumerUserOptionsResponse {
  items: ConsumerUserOption[]
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  expires_in: number
}

export interface LoginResponse extends TokenResponse {
  user: User
}

export interface RefreshTokenRequest {
  refresh_token: string
}

export interface LogoutRequest {
  refresh_token: string
}

export interface UserCreateRequest {
  email: string
  username: string
  display_name: string
  password: string
  role: UserRole
}

export interface UserUpdateRequest {
  display_name?: string
  role?: UserRole
}

export interface ResetPasswordRequest {
  new_password: string
}

export interface ResetPasswordResponse {
  user_id: string
  reset_at: string
}

export interface AssistantProfile {
  name: string
  identity_answer: string
  capability_answer: string
  greeting_answer: string
  thanks_answer: string
  usage_answer: string
  handoff_answer: string
  fallback_casual_answer: string
}

export interface ModelEndpointSettings {
  base_url: string
  api_key: string
  model: string
}

export interface ModelSettings {
  mineru: ModelEndpointSettings
  llm: ModelEndpointSettings
  document_summary: ModelEndpointSettings
  text_embedding: ModelEndpointSettings
  reranker: ModelEndpointSettings
  intent_recognition: ModelEndpointSettings
  knowledge_search_classifier: ModelEndpointSettings
  image_description: ModelEndpointSettings
  multimodal_embedding: ModelEndpointSettings
}

export interface KnowledgeBase {
  id: string
  name: string
  description: string
  status: KnowledgeBaseStatus
  file_count: number
  chunk_count: number
  created_by: string
  created_at: string
  updated_at: string
}

export interface KnowledgeBasePublicSummary {
  active_count: number
  deployment_day: number
}

export interface KnowledgeBaseCreateRequest {
  name: string
  description?: string
}

export interface KnowledgeBaseUpdateRequest {
  name?: string
  description?: string
  status?: KnowledgeBaseStatus
}

export interface FileItem {
  id: string
  knowledge_base_id: string
  file_name: string
  file_ext: string
  mime_type: string
  size_bytes: number
  file_hash: string
  status: FileStatus
  latest_parse_job_id: string | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface ParseJob {
  id: string
  file_id: string
  status: ParseJobStatus
  progress?: number
  error_code: string | null
  error_message: string | null
  logs: Record<string, unknown> | null
  started_at?: string | null
  finished_at?: string | null
  created_at: string
  updated_at: string
}

export interface FileUploadItem {
  file: FileItem
  parse_job: ParseJob
}

export interface FileUploadWarning {
  code: string
  message: string
  details: Record<string, unknown>
}

export interface FileUploadResponse {
  uploaded: FileUploadItem[]
  warnings: FileUploadWarning[]
}

export interface DuplicateFileHashDetails {
  duplicates: Array<{
    incoming_file_name: string
    existing_file_id: string
    existing_file_name: string
    file_hash: string
  }>
  can_force_upload: boolean
}

export interface FileStatusResponse {
  file_id: string
  file_status: FileStatus
  latest_parse_job: ParseJob | null
}

export type DocumentSummaryStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'partially_completed'
  | 'failed'
  | 'not_ready'

export interface ExtractedEntity {
  name: string
  normalized_name: string | null
  type: string
}

export interface ExtractedAssertion {
  statement: string
  statement_type: string
  subject: string | null
  predicate: string | null
  object: string | null
  conditions: string[]
  time_scope: string | null
  polarity: string
  certainty: string
  evidence_text: string
}

export interface ChunkKnowledgeExtractionPayload {
  chunk_id: string
  semantic_role: string
  short_summary: string
  topics: string[]
  keywords: string[]
  entities: ExtractedEntity[]
  assertions: ExtractedAssertion[]
  importance: number
  quality_flags: string[]
}

export interface ChunkKnowledgeExtraction {
  status: 'pending' | 'running' | 'completed' | 'failed'
  extraction: ChunkKnowledgeExtractionPayload | null
  model_name: string | null
  prompt_version: string
  attempt_count: number
  error_code: string | null
  error_message: string | null
}

export interface DocumentSummary {
  file_id: string
  parse_job_id: string | null
  status: DocumentSummaryStatus
  summary: string | null
  chunk_total: number
  chunk_completed: number
  chunk_succeeded: number
  chunk_failed: number
  failed_chunk_ids: string[]
  model_name: string | null
  chunk_prompt_version: string
  document_prompt_version: string
  reduction_level: number
  error_code: string | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  updated_at: string | null
}

export type KnowledgeGraphStatus = 'pending' | 'running' | 'completed' | 'failed'
export type CommunitySummaryStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'not_ready'

export interface KnowledgeGraphNode {
  id: string
  file_id: string
  document_summary_id: string
  file_name: string
  file_ext: string
  knowledge_base_id: string
  knowledge_base_name: string
  summary: string
  summary_status: string
  relation_count: number
}

export interface KnowledgeGraphEdge {
  id: string
  source: string
  target: string
  similarity: number
  cross_knowledge_base: boolean
}

export interface CommunitySummary {
  knowledge_base_id: string
  knowledge_base_name: string
  status: CommunitySummaryStatus
  summary: string | null
  document_count: number
  model_name: string | null
  prompt_version: string
  reduction_level: number
  error_code: string | null
  error_message: string | null
  updated_at: string | null
}

export interface KnowledgeGraph {
  status: KnowledgeGraphStatus
  source_fingerprint: string | null
  document_count: number
  total_document_count: number
  summarized_document_count: number
  pending_summary_count: number
  failed_summary_count: number
  not_ready_document_count: number
  relation_count: number
  embedding_model: string | null
  similarity_threshold: number
  max_relations_per_document: number
  nodes: KnowledgeGraphNode[]
  edges: KnowledgeGraphEdge[]
  communities: CommunitySummary[]
  updated_at: string | null
}

export interface Chunk {
  id: string
  file_id: string
  knowledge_base_id: string
  content: string
  description: string | null
  modality: 'text' | 'table' | 'image' | string
  image_url: string | null
  image_urls: string[]
  image_alt: string | null
  asset_paths: string[]
  document_block_types: string[]
  metadata: Record<string, unknown>
  source_locator: string
  token_count: number
  is_active: boolean
  created_at: string
  knowledge_extraction: ChunkKnowledgeExtraction | null
}

export interface RetrievalSearchRequest {
  query: string
  vector_top_k?: number
  full_text_top_k?: number
  top_k?: number
}

export interface RetrievalResultItem {
  chunk_id: string
  file_id: string
  file_name: string
  source_locator: string
  excerpt: string
  score: number
  source: 'vector' | 'full_text' | 'hybrid'
  modality: string
  image_url: string | null
  image_urls: string[]
  image_alt: string | null
}

export interface RetrievalSearchResponse {
  knowledge_base_id: string
  query: string
  items: RetrievalResultItem[]
  total: number
}

export interface Conversation {
  id: string
  knowledge_base_id: string
  title: string | null
  created_at: string
  updated_at: string
}

export interface ConversationCreateRequest {
  knowledge_base_id: string
  title?: string
}

export interface Citation {
  id?: string
  index: number
  file_name: string
  source_locator: string
  excerpt: string
  chunk_id: string
  modality: string
  image_url: string | null
  image_urls: string[]
  image_alt: string | null
}

export interface MessageAttachmentInput {
  type: 'image'
  file_name: string
  media_type: string
  data_url: string
}

export interface MessageAttachment {
  id: string
  type: 'image' | string
  file_name: string
  media_type: string
  size_bytes: number
  url: string
}

export interface Message {
  id: string
  conversation_id: string
  role: MessageRole
  content: string
  thinking_content?: string | null
  created_at: string
  citations: Citation[]
  attachments: MessageAttachment[]
  feedback_rating: FeedbackRating | null
  visual_result_mode: 'none' | 'single' | 'gallery' | null
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

export interface MessageCreateRequest {
  content: string
  stream?: boolean
  enable_thinking?: boolean
  attachments?: MessageAttachmentInput[]
}

export interface MessageCreateResponse {
  user_message: Message
  assistant_message: Message
}

export interface SseMessageCreatedEvent {
  user_message: Message
  assistant_message: Message
}

export interface SseRetrievalEvent {
  retrieved_count: number
  reranked_count: number
  final_context_count: number
}

export interface SseTokenEvent {
  text: string
}

export interface SseThinkingEvent {
  text: string
}

export interface SseStageEvent {
  name: string
}

export interface SseDoneEvent {
  message_id: string
  answer: string
  citations: Citation[]
  visual_result_mode?: 'none' | 'single' | 'gallery' | null
}

export interface SseErrorEvent {
  code: string
  message: string
  request_id: string
}

export interface FeedbackCreateRequest {
  rating: FeedbackRating
  comment?: string
}

export interface Feedback {
  id: string
  message_id: string
  user_id: string
  knowledge_base_id: string
  rating: FeedbackRating
  comment: string | null
  query_text: string | null
  retrieved_chunk_ids: string[] | null
  final_cited_chunk_ids: string[] | null
  model_name: string | null
  prompt_version: string | null
  embedding_model: string | null
  reranker_model: string | null
  latency_ms: number | null
  token_input: number | null
  token_output: number | null
  created_at: string
  updated_at: string
}

export interface AuditLog {
  id: string
  actor_id: string
  action: string
  resource_type: string
  resource_id: string | null
  details: Record<string, unknown>
  created_at: string
}

export interface ListQuery {
  page?: number
  page_size?: number
  keyword?: string
}

export interface UserListQuery extends ListQuery {
  role?: UserRole
  is_active?: boolean
}

export interface KnowledgeBaseListQuery extends ListQuery {
  status?: KnowledgeBaseStatus
}

export interface FileListQuery extends ListQuery {
  status?: FileStatus
}

export interface ConversationListQuery {
  knowledge_base_id: string
  page?: number
  page_size?: number
}

export interface AuditLogListQuery {
  page?: number
  page_size?: number
  actor_id?: string
  action?: string
  resource_type?: string
}
