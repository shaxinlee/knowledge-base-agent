<script setup lang="ts">
import {
  Connection,
  Refresh,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import {
  getCurrentUser,
  getKnowledgeGraph,
  listKnowledgeBases,
  refreshKnowledgeGraph,
} from '@/api/client'
import type {
  CommunitySummary,
  KnowledgeBase,
  KnowledgeGraph,
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
  User,
} from '@/api/types'
import AppLayout from '@/components/AppLayout.vue'
import PageHeader from '@/components/PageHeader.vue'

interface PositionedNode extends KnowledgeGraphNode {
  x: number
  y: number
  radius: number
  color: string
}

interface CommunityBoundary {
  id: string
  name: string
  color: string
  x: number
  y: number
  width: number
  height: number
}

const GRAPH_WIDTH = 1120
const GRAPH_HEIGHT = 700
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5))
const GRAPH_COLORS = [
  '#315c49',
  '#a85f2d',
  '#3e668f',
  '#8a536f',
  '#85712e',
  '#4e7c7a',
  '#745c9a',
  '#9a4f45',
]

const currentUser = ref<User | null>(null)
const knowledgeBases = ref<KnowledgeBase[]>([])
const graph = ref<KnowledgeGraph | null>(null)
const positionedNodes = ref<PositionedNode[]>([])
const loading = ref(false)
const refreshLoading = ref(false)
const selectedKnowledgeBaseId = ref('')
const includeCrossKnowledgeBase = ref(true)
const minSimilarity = ref(0.45)
const selectedNodeId = ref('')
const hoveredNodeId = ref('')
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const svgRef = ref<SVGSVGElement | null>(null)
const draggingNodeId = ref('')
const isPanning = ref(false)
const activePointerId = ref<number | null>(null)
let graphPollTimer: number | null = null

const isAdmin = computed(() => currentUser.value?.role === 'admin')
const selectedNode = computed(
  () => graph.value?.nodes.find((node) => node.id === selectedNodeId.value) ?? null,
)
const positionedNodeMap = computed(
  () => new Map(positionedNodes.value.map((node) => [node.id, node])),
)
const visibleEdges = computed(() =>
  (graph.value?.edges ?? []).filter(
    (edge) =>
      positionedNodeMap.value.has(edge.source) && positionedNodeMap.value.has(edge.target),
  ),
)
const selectedCommunity = computed(() => {
  if (selectedNode.value) {
    return graph.value?.communities.find(
      (community) => community.knowledge_base_id === selectedNode.value?.knowledge_base_id,
    )
  }
  if (selectedKnowledgeBaseId.value) {
    return graph.value?.communities.find(
      (community) => community.knowledge_base_id === selectedKnowledgeBaseId.value,
    )
  }
  return graph.value?.communities[0] ?? null
})
const relatedDocuments = computed(() => {
  if (!selectedNode.value || !graph.value) return []
  return graph.value.edges
    .filter(
      (edge) =>
        edge.source === selectedNode.value?.id || edge.target === selectedNode.value?.id,
    )
    .map((edge) => {
      const relatedId =
        edge.source === selectedNode.value?.id ? edge.target : edge.source
      const node = graph.value?.nodes.find((item) => item.id === relatedId)
      return node ? { node, edge } : null
    })
    .filter(
      (item): item is { node: KnowledgeGraphNode; edge: KnowledgeGraphEdge } =>
        item !== null,
    )
    .sort((left, right) => right.edge.similarity - left.edge.similarity)
})
const graphStatusLabel = computed(() => {
  if (
    graph.value &&
    graph.value.summarized_document_count < graph.value.total_document_count
  ) {
    return `摘要处理中 ${graph.value.summarized_document_count}/${graph.value.total_document_count}`
  }
  const labels: Record<string, string> = {
    pending: '等待构建',
    running: '关系计算中',
    completed: '关系图已更新',
    failed: '构建失败',
  }
  return labels[graph.value?.status ?? 'pending']
})
const knowledgeBaseLegend = computed(() => {
  const seen = new Set<string>()
  return positionedNodes.value
    .filter((node) => {
      if (seen.has(node.knowledge_base_id)) return false
      seen.add(node.knowledge_base_id)
      return true
    })
    .map((node) => ({
      id: node.knowledge_base_id,
      name: node.knowledge_base_name,
      color: node.color,
    }))
})
const communityBoundaries = computed<CommunityBoundary[]>(() => {
  const groupedNodes = new Map<string, PositionedNode[]>()
  positionedNodes.value.forEach((node) => {
    const group = groupedNodes.get(node.knowledge_base_id) ?? []
    group.push(node)
    groupedNodes.set(node.knowledge_base_id, group)
  })

  return Array.from(groupedNodes.entries()).map(([knowledgeBaseId, nodes]) => {
    const firstNode = nodes[0]
    const left = Math.min(...nodes.map((node) => node.x - node.radius))
    const right = Math.max(...nodes.map((node) => node.x + node.radius))
    const top = Math.min(...nodes.map((node) => node.y - node.radius))
    const bottom = Math.max(...nodes.map((node) => node.y + node.radius))
    const horizontalPadding = 54
    const verticalPadding = 48
    const minimumWidth = 150
    const minimumHeight = 120
    const rawWidth = Math.max(right - left + horizontalPadding * 2, minimumWidth)
    const rawHeight = Math.max(bottom - top + verticalPadding * 2, minimumHeight)
    const centerX = (left + right) / 2
    const centerY = (top + bottom) / 2
    const x = Math.max(14, Math.min(centerX - rawWidth / 2, GRAPH_WIDTH - rawWidth - 14))
    const y = Math.max(14, Math.min(centerY - rawHeight / 2, GRAPH_HEIGHT - rawHeight - 14))

    return {
      id: knowledgeBaseId,
      name: firstNode?.knowledge_base_name ?? '未命名社区',
      color: firstNode?.color ?? GRAPH_COLORS[0],
      x,
      y,
      width: Math.min(rawWidth, GRAPH_WIDTH - 28),
      height: Math.min(rawHeight, GRAPH_HEIGHT - 28),
    }
  })
})

onMounted(async () => {
  await loadInitialData()
})

onUnmounted(() => {
  stopGraphPolling()
})

async function loadInitialData(): Promise<void> {
  loading.value = true
  try {
    const [user, kbResponse] = await Promise.all([
      getCurrentUser(),
      listKnowledgeBases({ page: 1, page_size: 100 }),
    ])
    currentUser.value = user
    knowledgeBases.value = kbResponse.items
    await loadGraph()
  } catch (error) {
    handleError(error)
  } finally {
    loading.value = false
  }
}

async function loadGraph(showMessage = false): Promise<void> {
  loading.value = true
  try {
    graph.value = await getKnowledgeGraph({
      knowledge_base_id: selectedKnowledgeBaseId.value || undefined,
      include_cross_knowledge_base: includeCrossKnowledgeBase.value,
      min_similarity: minSimilarity.value,
    })
    buildGraphLayout()
    if (
      selectedNodeId.value &&
      !graph.value.nodes.some((node) => node.id === selectedNodeId.value)
    ) {
      selectedNodeId.value = ''
    }
    updateGraphPolling()
    if (showMessage) ElMessage.success('知识地图已刷新')
  } catch (error) {
    stopGraphPolling()
    handleError(error)
  } finally {
    loading.value = false
  }
}

async function requestGraphRefresh(forceEmbeddings = false): Promise<void> {
  if (forceEmbeddings) {
    try {
      await ElMessageBox.confirm(
        '这会重新生成全部文档摘要向量并重建关系图。确认继续？',
        '重建知识地图',
        {
          confirmButtonText: '重新计算',
          cancelButtonText: '取消',
          type: 'warning',
        },
      )
    } catch (error) {
      if (error === 'cancel') return
      throw error
    }
  }
  refreshLoading.value = true
  try {
    graph.value = await refreshKnowledgeGraph(forceEmbeddings)
    ElMessage.success(forceEmbeddings ? '已提交全量重建' : '已提交关系刷新')
    updateGraphPolling()
  } catch (error) {
    handleError(error)
  } finally {
    refreshLoading.value = false
  }
}

function buildGraphLayout(): void {
  if (!graph.value) {
    positionedNodes.value = []
    return
  }
  const nodesByKb = new Map<string, KnowledgeGraphNode[]>()
  graph.value.nodes.forEach((node) => {
    const group = nodesByKb.get(node.knowledge_base_id) ?? []
    group.push(node)
    nodesByKb.set(node.knowledge_base_id, group)
  })
  const groups = Array.from(nodesByKb.entries())
  const centers = new Map<string, { x: number; y: number }>()
  groups.forEach(([knowledgeBaseId], index) => {
    if (groups.length === 1) {
      centers.set(knowledgeBaseId, { x: GRAPH_WIDTH / 2, y: GRAPH_HEIGHT / 2 })
      return
    }
    const angle = (index / groups.length) * Math.PI * 2 - Math.PI / 2
    const radius = Math.min(250, 130 + groups.length * 18)
    centers.set(knowledgeBaseId, {
      x: GRAPH_WIDTH / 2 + Math.cos(angle) * radius,
      y: GRAPH_HEIGHT / 2 + Math.sin(angle) * radius,
    })
  })

  const positioned: PositionedNode[] = []
  groups.forEach(([knowledgeBaseId, nodes], groupIndex) => {
    const center = centers.get(knowledgeBaseId) ?? {
      x: GRAPH_WIDTH / 2,
      y: GRAPH_HEIGHT / 2,
    }
    nodes
      .slice()
      .sort(
        (left, right) =>
          right.relation_count - left.relation_count ||
          left.file_name.localeCompare(right.file_name),
      )
      .forEach((node, index) => {
        const orbit = index === 0 ? 0 : 42 + Math.sqrt(index) * 42
        const angle = index * GOLDEN_ANGLE + groupIndex * 0.8
        positioned.push({
          ...node,
          x: center.x + Math.cos(angle) * orbit,
          y: center.y + Math.sin(angle) * orbit,
          radius: Math.min(23, 10 + Math.sqrt(node.relation_count + 1) * 3.2),
          color: GRAPH_COLORS[groupIndex % GRAPH_COLORS.length],
        })
      })
  })

  relaxGraph(positioned, graph.value.edges, centers)
  positionedNodes.value = positioned
}

function relaxGraph(
  nodes: PositionedNode[],
  edges: KnowledgeGraphEdge[],
  centers: Map<string, { x: number; y: number }>,
): void {
  const nodeMap = new Map(nodes.map((node) => [node.id, node]))
  const iterations = nodes.length <= 120 ? 55 : 18
  for (let iteration = 0; iteration < iterations; iteration += 1) {
    edges.forEach((edge) => {
      const source = nodeMap.get(edge.source)
      const target = nodeMap.get(edge.target)
      if (!source || !target) return
      const dx = target.x - source.x
      const dy = target.y - source.y
      const distance = Math.max(Math.hypot(dx, dy), 1)
      const desired = edge.cross_knowledge_base ? 245 : 120 + (1 - edge.similarity) * 90
      const force = (distance - desired) * 0.012
      const moveX = (dx / distance) * force
      const moveY = (dy / distance) * force
      source.x += moveX
      source.y += moveY
      target.x -= moveX
      target.y -= moveY
    })
    nodes.forEach((node) => {
      const center = centers.get(node.knowledge_base_id)
      if (!center) return
      node.x += (center.x - node.x) * 0.007
      node.y += (center.y - node.y) * 0.007
    })
    if (nodes.length <= 120) {
      for (let leftIndex = 0; leftIndex < nodes.length; leftIndex += 1) {
        for (let rightIndex = leftIndex + 1; rightIndex < nodes.length; rightIndex += 1) {
          const left = nodes[leftIndex]
          const right = nodes[rightIndex]
          const dx = right.x - left.x
          const dy = right.y - left.y
          const distance = Math.max(Math.hypot(dx, dy), 1)
          const minimum = left.radius + right.radius + 18
          if (distance >= minimum) continue
          const push = (minimum - distance) * 0.12
          const pushX = (dx / distance) * push
          const pushY = (dy / distance) * push
          left.x -= pushX
          left.y -= pushY
          right.x += pushX
          right.y += pushY
        }
      }
    }
    nodes.forEach((node) => {
      node.x = Math.min(GRAPH_WIDTH - 50, Math.max(50, node.x))
      node.y = Math.min(GRAPH_HEIGHT - 50, Math.max(50, node.y))
    })
  }
}

function edgeCoordinates(edge: KnowledgeGraphEdge): {
  x1: number
  y1: number
  x2: number
  y2: number
} {
  const source = positionedNodeMap.value.get(edge.source)
  const target = positionedNodeMap.value.get(edge.target)
  return {
    x1: source?.x ?? 0,
    y1: source?.y ?? 0,
    x2: target?.x ?? 0,
    y2: target?.y ?? 0,
  }
}

function edgeOpacity(edge: KnowledgeGraphEdge): number {
  if (!selectedNodeId.value) return 0.2 + edge.similarity * 0.45
  return edge.source === selectedNodeId.value || edge.target === selectedNodeId.value
    ? 0.9
    : 0.08
}

function edgeWidth(edge: KnowledgeGraphEdge): number {
  return 0.8 + Math.max(0, edge.similarity - minSimilarity.value) * 5
}

function nodeOpacity(node: PositionedNode): number {
  if (!selectedNodeId.value) return 1
  if (node.id === selectedNodeId.value) return 1
  return relatedDocuments.value.some((item) => item.node.id === node.id) ? 0.95 : 0.28
}

function selectNode(node: KnowledgeGraphNode): void {
  selectedNodeId.value = selectedNodeId.value === node.id ? '' : node.id
}

function selectRelatedNode(node: KnowledgeGraphNode): void {
  selectedNodeId.value = node.id
}

function startNodeDrag(event: PointerEvent, node: PositionedNode): void {
  event.preventDefault()
  event.stopPropagation()
  draggingNodeId.value = node.id
  activePointerId.value = event.pointerId
  svgRef.value?.setPointerCapture(event.pointerId)
}

function startCanvasPan(event: PointerEvent): void {
  if (event.button !== 0 || draggingNodeId.value) return
  event.preventDefault()
  isPanning.value = true
  activePointerId.value = event.pointerId
  svgRef.value?.setPointerCapture(event.pointerId)
}

function handlePointerMove(event: PointerEvent): void {
  if (!svgRef.value || activePointerId.value !== event.pointerId) return
  const bounds = svgRef.value.getBoundingClientRect()
  const movementX = (event.movementX / bounds.width) * GRAPH_WIDTH
  const movementY = (event.movementY / bounds.height) * GRAPH_HEIGHT

  if (draggingNodeId.value) {
    const node = positionedNodes.value.find((item) => item.id === draggingNodeId.value)
    if (!node) return
    node.x += movementX / zoom.value
    node.y += movementY / zoom.value
    node.x = Math.min(GRAPH_WIDTH - 30, Math.max(30, node.x))
    node.y = Math.min(GRAPH_HEIGHT - 30, Math.max(30, node.y))
    return
  }

  if (isPanning.value) {
    panX.value += movementX
    panY.value += movementY
  }
}

function stopPointerInteraction(event?: PointerEvent): void {
  if (
    event &&
    activePointerId.value !== null &&
    activePointerId.value !== event.pointerId
  ) {
    return
  }
  if (
    event &&
    svgRef.value?.hasPointerCapture(event.pointerId)
  ) {
    svgRef.value.releasePointerCapture(event.pointerId)
  }
  draggingNodeId.value = ''
  isPanning.value = false
  activePointerId.value = null
}

function adjustZoom(delta: number): void {
  zoom.value = Math.min(1.8, Math.max(0.55, zoom.value + delta))
}

function handleWheel(event: WheelEvent): void {
  event.preventDefault()
  adjustZoom(event.deltaY > 0 ? -0.08 : 0.08)
}

function updateGraphPolling(): void {
  stopGraphPolling()
  if (
    graph.value &&
    (
      ['pending', 'running'].includes(graph.value.status) ||
      graph.value.summarized_document_count < graph.value.total_document_count
    )
  ) {
    graphPollTimer = window.setTimeout(() => {
      void loadGraph()
    }, 5000)
  }
}

function stopGraphPolling(): void {
  if (graphPollTimer !== null) {
    window.clearTimeout(graphPollTimer)
    graphPollTimer = null
  }
}

function communityStatusLabel(status: CommunitySummary['status']): string {
  const labels: Record<CommunitySummary['status'], string> = {
    pending: '等待生成',
    running: '生成中',
    completed: '已更新',
    failed: '生成失败',
    not_ready: '等待文档摘要',
  }
  return labels[status]
}

function formatSimilarity(value: number): string {
  return `${Math.round(value * 100)}%`
}

function truncateFileName(value: string, length = 22): string {
  return value.length > length ? `${value.slice(0, length)}…` : value
}

function formatTime(value: string | null | undefined): string {
  if (!value) return '-'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function handleError(error: unknown): void {
  ElMessage.error(error instanceof Error ? error.message : '知识地图加载失败')
}
</script>

<template>
  <AppLayout>
    <section class="map-page">
      <PageHeader
        title="知识地图"
        subtitle="通过文档摘要相似度连接知识库中的相关文件，并持续维护知识社区概览。"
      >
        <template #actions>
          <el-button :loading="loading" @click="loadGraph(true)">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
          <el-button
            v-if="isAdmin"
            type="primary"
            :loading="refreshLoading"
            @click="requestGraphRefresh(false)"
          >
            <el-icon><Connection /></el-icon>
            更新关系
          </el-button>
        </template>
      </PageHeader>

      <section class="map-toolbar">
        <div class="toolbar-field kb-filter">
          <label>知识库范围</label>
          <el-select
            v-model="selectedKnowledgeBaseId"
            placeholder="全部知识库"
            clearable
            @change="loadGraph()"
          >
            <el-option
              v-for="knowledgeBase in knowledgeBases"
              :key="knowledgeBase.id"
              :label="knowledgeBase.name"
              :value="knowledgeBase.id"
            />
          </el-select>
        </div>
        <div class="toolbar-field similarity-field">
          <label>
            最低相似度
            <strong>{{ formatSimilarity(minSimilarity) }}</strong>
          </label>
          <el-slider
            v-model="minSimilarity"
            :min="graph?.similarity_threshold ?? 0.45"
            :max="0.95"
            :step="0.05"
            :show-tooltip="false"
            @change="loadGraph()"
          />
        </div>
        <div class="toolbar-field cross-field">
          <label>跨知识库连线</label>
          <el-switch
            v-model="includeCrossKnowledgeBase"
            active-text="显示"
            inactive-text="隐藏"
            @change="loadGraph()"
          />
        </div>
        <div class="toolbar-status">
          <span :class="['status-beacon', graph?.status ?? 'pending']"></span>
          <div>
            <strong>{{ graphStatusLabel }}</strong>
            <small>{{ formatTime(graph?.updated_at) }}</small>
          </div>
        </div>
      </section>

      <section class="map-stats">
        <div>
          <span>摘要覆盖</span>
          <strong>
            {{ graph?.summarized_document_count ?? 0 }}
            <small>/ {{ graph?.total_document_count ?? 0 }}</small>
          </strong>
        </div>
        <div>
          <span>关联关系</span>
          <strong>{{ graph?.relation_count ?? 0 }}</strong>
        </div>
        <div>
          <span>知识社区</span>
          <strong>{{ graph?.communities.length ?? 0 }}</strong>
        </div>
        <div>
          <span>向量模型</span>
          <strong class="model-name">{{ graph?.embedding_model || '等待构建' }}</strong>
        </div>
      </section>

      <div class="map-workspace">
        <section class="graph-stage">
          <header class="graph-stage-header">
            <div class="graph-legend">
              <span
                v-for="item in knowledgeBaseLegend"
                :key="item.id"
                class="legend-item"
              >
                <i :style="{ background: item.color }"></i>
                {{ item.name }}
              </span>
            </div>
            <div class="viewport-actions">
              <button
                class="zoom-symbol"
                type="button"
                aria-label="缩小"
                title="缩小"
                @click="adjustZoom(-0.12)"
              >
                −
              </button>
              <span>{{ Math.round(zoom * 100) }}%</span>
              <button
                class="zoom-symbol"
                type="button"
                aria-label="放大"
                title="放大"
                @click="adjustZoom(0.12)"
              >
                +
              </button>
            </div>
          </header>

          <div v-if="loading && !graph" class="graph-empty">
            <span class="map-spinner"></span>
            <strong>正在读取文档关系</strong>
          </div>
          <div v-else-if="!positionedNodes.length" class="graph-empty">
            <el-icon><Connection /></el-icon>
            <strong>暂无可展示的文档关系</strong>
            <p v-if="graph?.pending_summary_count">
              还有 {{ graph.pending_summary_count }} 篇文档正在生成摘要，完成后会自动加入关系图。
            </p>
            <p v-else-if="graph?.failed_summary_count">
              有 {{ graph.failed_summary_count }} 篇文档摘要失败，请在文件管理中重试。
            </p>
            <p v-else>文档摘要完成后，后台会自动计算关联并更新社区摘要。</p>
          </div>
          <svg
            v-else
            ref="svgRef"
            :class="['knowledge-graph', { panning: isPanning }]"
            :viewBox="`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`"
            role="img"
            aria-label="文档摘要关联图"
            @pointerdown="startCanvasPan"
            @pointermove="handlePointerMove"
            @pointerup="stopPointerInteraction"
            @pointercancel="stopPointerInteraction"
            @wheel="handleWheel"
          >
            <defs>
              <pattern id="grid-pattern" width="32" height="32" patternUnits="userSpaceOnUse">
                <path d="M 32 0 L 0 0 0 32" fill="none" stroke="#d8d9d2" stroke-width="0.6" />
              </pattern>
              <filter id="node-shadow" x="-50%" y="-50%" width="200%" height="200%">
                <feDropShadow dx="0" dy="4" stdDeviation="5" flood-color="#1d2821" flood-opacity="0.18" />
              </filter>
            </defs>
            <rect width="100%" height="100%" fill="url(#grid-pattern)" />
            <g :transform="`translate(${panX} ${panY}) scale(${zoom})`">
              <g
                v-for="community in communityBoundaries"
                :key="community.id"
                class="community-boundary"
              >
                <rect
                  :x="community.x"
                  :y="community.y"
                  :width="community.width"
                  :height="community.height"
                  rx="28"
                  :fill="community.color"
                  :stroke="community.color"
                />
                <text
                  :x="community.x + 18"
                  :y="community.y + 23"
                  :fill="community.color"
                >
                  {{ community.name }}
                </text>
              </g>
              <line
                v-for="edge in visibleEdges"
                :key="edge.id"
                v-bind="edgeCoordinates(edge)"
                :class="['graph-edge', { cross: edge.cross_knowledge_base }]"
                :stroke-width="edgeWidth(edge)"
                :stroke-opacity="edgeOpacity(edge)"
              />
              <g
                v-for="node in positionedNodes"
                :key="node.id"
                :transform="`translate(${node.x} ${node.y})`"
                :class="[
                  'graph-node',
                  {
                    selected: selectedNodeId === node.id,
                    hovered: hoveredNodeId === node.id,
                  },
                ]"
                :opacity="nodeOpacity(node)"
                role="button"
                tabindex="0"
                @mouseenter="hoveredNodeId = node.id"
                @mouseleave="hoveredNodeId = ''"
                @pointerdown.stop="startNodeDrag($event, node)"
                @click="selectNode(node)"
                @keydown.enter="selectNode(node)"
              >
                <circle
                  class="node-halo"
                  :r="node.radius + 9"
                  :fill="node.color"
                />
                <circle
                  class="node-core"
                  :r="node.radius"
                  :fill="node.color"
                  filter="url(#node-shadow)"
                />
                <text
                  v-if="
                    positionedNodes.length <= 60 ||
                      selectedNodeId === node.id ||
                      hoveredNodeId === node.id
                  "
                  class="node-label"
                  :y="node.radius + 22"
                  text-anchor="middle"
                >
                  {{ truncateFileName(node.file_name) }}
                </text>
                <title>{{ node.file_name }} · {{ node.knowledge_base_name }}</title>
              </g>
            </g>
          </svg>

          <footer class="graph-stage-footer">
            <span>节点大小表示关联数量</span>
            <span>虚线边界表示知识社区</span>
            <span>实线为同库关系</span>
            <span>虚线连线为跨库关系</span>
            <span>可滚轮缩放、拖动节点</span>
          </footer>
        </section>

        <aside class="map-inspector">
          <section v-if="selectedNode" class="inspector-document">
            <div class="inspector-kicker">
              <span
                class="inspector-dot"
                :style="{
                  background:
                    positionedNodeMap.get(selectedNode.id)?.color ?? GRAPH_COLORS[0],
                }"
              ></span>
              {{ selectedNode.knowledge_base_name }}
            </div>
            <h2>{{ selectedNode.file_name }}</h2>
            <div class="document-meta">
              <span>{{ selectedNode.file_ext }}</span>
              <span>{{ selectedNode.relation_count }} 条关联</span>
            </div>
            <article>{{ selectedNode.summary }}</article>

            <div class="related-heading">
              <strong>相关文件</strong>
              <span>{{ relatedDocuments.length }}</span>
            </div>
            <div v-if="relatedDocuments.length" class="related-list">
              <button
                v-for="item in relatedDocuments"
                :key="item.edge.id"
                type="button"
                @click="selectRelatedNode(item.node)"
              >
                <span>
                  <strong>{{ item.node.file_name }}</strong>
                  <small>
                    {{ item.node.knowledge_base_name }}
                    <em v-if="item.edge.cross_knowledge_base">跨库</em>
                  </small>
                </span>
                <b>{{ formatSimilarity(item.edge.similarity) }}</b>
              </button>
            </div>
            <p v-else class="inspector-empty">当前阈值下没有其他关联文件。</p>
          </section>

          <section v-else class="inspector-intro">
            <span class="inspector-index">MAP / 01</span>
            <h2>选择一个文档节点</h2>
            <p>查看文档摘要、相似度最高的相关文件，以及它所在知识库的社区概览。</p>
          </section>

          <section v-if="selectedCommunity" class="community-panel">
            <header>
              <div>
                <span>社区摘要</span>
                <h3>{{ selectedCommunity.knowledge_base_name }}</h3>
              </div>
              <b :class="selectedCommunity.status">
                {{ communityStatusLabel(selectedCommunity.status) }}
              </b>
            </header>
            <article v-if="selectedCommunity.summary">
              {{ selectedCommunity.summary }}
            </article>
            <p v-else-if="selectedCommunity.status === 'failed'" class="community-error">
              {{ selectedCommunity.error_message || '社区摘要生成失败' }}
            </p>
            <p v-else class="community-placeholder">
              后台正在根据已完成的文档摘要维护该知识社区。
            </p>
            <footer>
              <span>{{ selectedCommunity.document_count }} 篇文档</span>
              <span>{{ formatTime(selectedCommunity.updated_at) }}</span>
            </footer>
          </section>

          <section v-if="!selectedNode && graph?.communities.length" class="community-list">
            <button
              v-for="community in graph.communities"
              :key="community.knowledge_base_id"
              type="button"
              @click="
                selectedKnowledgeBaseId = community.knowledge_base_id;
                loadGraph()
              "
            >
              <span>{{ community.knowledge_base_name }}</span>
              <strong>{{ community.document_count }}</strong>
            </button>
          </section>

          <button
            v-if="isAdmin"
            class="force-rebuild"
            type="button"
            :disabled="refreshLoading"
            @click="requestGraphRefresh(true)"
          >
            重新计算全部摘要向量
          </button>
        </aside>
      </div>
    </section>
  </AppLayout>
</template>

<style scoped>
.map-page {
  min-height: calc(100vh - var(--ka-header-height));
  padding: 22px 24px 32px;
  background:
    linear-gradient(90deg, rgba(43, 65, 52, 0.025) 1px, transparent 1px),
    linear-gradient(rgba(43, 65, 52, 0.025) 1px, transparent 1px),
    #f1f2ed;
  background-size: 28px 28px;
}

.map-toolbar {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(240px, 1.2fr) 180px minmax(180px, auto);
  gap: 22px;
  align-items: end;
  padding: 17px 20px;
  border: 1px solid #d3d6ce;
  background: rgba(252, 252, 248, 0.92);
}

.toolbar-field {
  display: grid;
  gap: 8px;
}

.toolbar-field label {
  color: #5e655e;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.03em;
}

.similarity-field label {
  display: flex;
  justify-content: space-between;
}

.similarity-field label strong {
  color: #244c38;
  font-family: 'Courier New', monospace;
}

.toolbar-status {
  display: flex;
  gap: 11px;
  align-items: center;
  justify-content: flex-end;
  min-height: 42px;
  padding-left: 18px;
  border-left: 1px solid #d9dbd4;
}

.toolbar-status div {
  display: grid;
  gap: 2px;
}

.toolbar-status strong {
  color: #29332d;
  font-size: 13px;
}

.toolbar-status small {
  color: #868b84;
  font-family: 'Courier New', monospace;
}

.status-beacon {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #8f958e;
  box-shadow: 0 0 0 5px rgba(143, 149, 142, 0.12);
}

.status-beacon.running {
  background: #2f75a8;
  animation: map-pulse 1.5s ease-in-out infinite;
}

.status-beacon.completed {
  background: #2f8059;
}

.status-beacon.failed {
  background: #b64a3d;
}

.map-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(120px, 0.65fr)) minmax(240px, 1.4fr);
  margin-top: 14px;
  border-top: 1px solid #d5d8d0;
  border-left: 1px solid #d5d8d0;
  background: rgba(255, 255, 252, 0.72);
}

.map-stats div {
  display: grid;
  gap: 6px;
  min-height: 76px;
  padding: 14px 18px;
  border-right: 1px solid #d5d8d0;
  border-bottom: 1px solid #d5d8d0;
}

.map-stats span {
  color: #737970;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.map-stats strong {
  color: #253129;
  font-family: 'Courier New', monospace;
  font-size: 24px;
}

.map-stats .model-name {
  align-self: end;
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.map-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 370px;
  min-height: 690px;
  margin-top: 14px;
  border: 1px solid #cfd3ca;
  background: #f8f9f4;
  box-shadow: 0 18px 50px rgba(48, 59, 51, 0.08);
}

.graph-stage {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-width: 0;
  border-right: 1px solid #cfd3ca;
}

.graph-stage-header {
  display: flex;
  min-height: 54px;
  justify-content: space-between;
  gap: 18px;
  align-items: center;
  padding: 10px 14px 10px 18px;
  border-bottom: 1px solid #d8dbd3;
  background: #fbfcf7;
}

.graph-legend {
  display: flex;
  gap: 13px;
  align-items: center;
  overflow-x: auto;
}

.legend-item {
  display: inline-flex;
  flex: 0 0 auto;
  gap: 6px;
  align-items: center;
  color: #5e655e;
  font-size: 11px;
}

.legend-item i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.viewport-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  border: 1px solid #d2d5cd;
  background: #fff;
}

.viewport-actions button {
  display: grid;
  width: 34px;
  height: 32px;
  place-items: center;
  border: 0;
  border-right: 1px solid #e0e2dc;
  color: #505951;
  background: transparent;
  cursor: pointer;
}

.viewport-actions button:hover {
  color: #fff;
  background: #315c49;
}

.viewport-actions .zoom-symbol {
  padding: 0 0 2px;
  font-family: 'Courier New', monospace;
  font-size: 20px;
  font-weight: 700;
  line-height: 1;
}

.viewport-actions span {
  min-width: 48px;
  color: #60675f;
  font-family: 'Courier New', monospace;
  font-size: 11px;
  text-align: center;
}

.knowledge-graph {
  display: block;
  width: 100%;
  min-height: 580px;
  background:
    radial-gradient(circle at 50% 45%, rgba(55, 85, 67, 0.06), transparent 46%),
    #f5f6f1;
  cursor: grab;
  touch-action: none;
}

.knowledge-graph:active {
  cursor: grabbing;
}

.knowledge-graph.panning {
  cursor: grabbing;
}

.graph-edge {
  stroke: #718379;
  transition: opacity 160ms ease;
}

.graph-edge.cross {
  stroke: #9a6a43;
  stroke-dasharray: 7 7;
}

.community-boundary {
  pointer-events: none;
}

.community-boundary rect {
  fill-opacity: 0.035;
  stroke-width: 1.6;
  stroke-dasharray: 10 8;
  vector-effect: non-scaling-stroke;
}

.community-boundary text {
  paint-order: stroke;
  stroke: #f5f6f1;
  stroke-width: 4px;
  stroke-linejoin: round;
  font-family: 'Noto Sans SC', sans-serif;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.graph-node {
  cursor: pointer;
  outline: none;
  transition: opacity 160ms ease;
}

.node-halo {
  opacity: 0.08;
  transition: opacity 160ms ease, transform 160ms ease;
}

.node-core {
  stroke: #fff;
  stroke-width: 2.5;
  transition: stroke-width 160ms ease, transform 160ms ease;
}

.graph-node:hover .node-halo,
.graph-node.hovered .node-halo {
  opacity: 0.18;
  transform: scale(1.18);
}

.graph-node.selected .node-halo {
  opacity: 0.24;
  transform: scale(1.32);
}

.graph-node.selected .node-core {
  stroke-width: 4;
}

.node-label {
  fill: #2d352f;
  paint-order: stroke;
  stroke: #f5f6f1;
  stroke-width: 5px;
  stroke-linejoin: round;
  font-family: 'Noto Sans SC', sans-serif;
  font-size: 11px;
  font-weight: 700;
  pointer-events: none;
}

.graph-stage-footer {
  display: flex;
  gap: 18px;
  align-items: center;
  min-height: 38px;
  padding: 8px 18px;
  border-top: 1px solid #d8dbd3;
  color: #7a8078;
  background: #fbfcf7;
  font-size: 10px;
  letter-spacing: 0.04em;
}

.map-inspector {
  display: flex;
  min-width: 0;
  flex-direction: column;
  background:
    linear-gradient(rgba(50, 69, 57, 0.035) 1px, transparent 1px),
    #f2f2ec;
  background-size: 100% 27px;
}

.inspector-document,
.inspector-intro {
  padding: 26px 25px;
  border-bottom: 1px solid #d2d5cd;
  background: rgba(250, 250, 245, 0.92);
}

.inspector-kicker {
  display: flex;
  gap: 8px;
  align-items: center;
  color: #6c736b;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.inspector-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.inspector-document h2,
.inspector-intro h2 {
  margin: 10px 0 8px;
  color: #222c26;
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 21px;
  line-height: 1.45;
}

.document-meta {
  display: flex;
  gap: 9px;
  margin-bottom: 18px;
}

.document-meta span {
  padding: 3px 7px;
  border: 1px solid #d2d6ce;
  color: #70766f;
  background: #fff;
  font-family: 'Courier New', monospace;
  font-size: 10px;
}

.inspector-document article {
  max-height: 240px;
  overflow-y: auto;
  color: #414a43;
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 13px;
  line-height: 1.85;
  white-space: pre-wrap;
}

.related-heading {
  display: flex;
  justify-content: space-between;
  margin-top: 22px;
  padding-top: 16px;
  border-top: 1px solid #dcddd6;
  color: #3c463f;
  font-size: 12px;
}

.related-heading span {
  font-family: 'Courier New', monospace;
}

.related-list {
  display: grid;
  gap: 7px;
  margin-top: 10px;
}

.related-list button {
  display: flex;
  width: 100%;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 10px 11px;
  border: 1px solid #d9dcd4;
  color: #303a33;
  background: rgba(255, 255, 252, 0.82);
  text-align: left;
  cursor: pointer;
}

.related-list button:hover {
  border-color: #6f8878;
  background: #fff;
}

.related-list button > span {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.related-list strong {
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.related-list small {
  color: #7e847d;
  font-size: 10px;
}

.related-list em {
  margin-left: 5px;
  color: #a85f2d;
  font-style: normal;
}

.related-list b {
  flex: 0 0 auto;
  color: #315c49;
  font-family: 'Courier New', monospace;
  font-size: 11px;
}

.inspector-index {
  color: #315c49;
  font-family: 'Courier New', monospace;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.inspector-intro p,
.inspector-empty {
  margin: 0;
  color: #737a72;
  font-size: 12px;
  line-height: 1.7;
}

.community-panel {
  margin: 18px;
  padding: 19px;
  border: 1px solid #cfd3ca;
  border-left: 4px solid #315c49;
  background: rgba(255, 255, 252, 0.9);
}

.community-panel header {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.community-panel header span {
  color: #7b8179;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.community-panel h3 {
  margin: 4px 0 0;
  color: #29342d;
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 16px;
}

.community-panel header b {
  flex: 0 0 auto;
  padding: 3px 6px;
  border: 1px solid #d7dad2;
  color: #777d76;
  font-size: 9px;
}

.community-panel header b.completed {
  border-color: #afd0bc;
  color: #2d7652;
  background: #eff8f2;
}

.community-panel header b.running {
  border-color: #b8cbe0;
  color: #2f6694;
  background: #eff5fb;
}

.community-panel article {
  max-height: 250px;
  margin-top: 15px;
  overflow-y: auto;
  color: #465048;
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 12px;
  line-height: 1.85;
  white-space: pre-wrap;
}

.community-placeholder,
.community-error {
  color: #7b817a;
  font-size: 11px;
  line-height: 1.65;
}

.community-error {
  color: #a1463a;
}

.community-panel footer {
  display: flex;
  justify-content: space-between;
  margin-top: 15px;
  padding-top: 11px;
  border-top: 1px solid #e1e2dc;
  color: #858a84;
  font-family: 'Courier New', monospace;
  font-size: 9px;
}

.community-list {
  display: grid;
  gap: 6px;
  margin: 0 18px 18px;
}

.community-list button {
  display: flex;
  justify-content: space-between;
  padding: 10px 12px;
  border: 1px solid #d7dad3;
  color: #525b54;
  background: rgba(255, 255, 252, 0.72);
  cursor: pointer;
}

.community-list button:hover {
  border-color: #7a9182;
}

.community-list strong {
  font-family: 'Courier New', monospace;
}

.force-rebuild {
  margin: auto 18px 18px;
  padding: 9px 12px;
  border: 1px solid #c9a99f;
  color: #93463b;
  background: rgba(255, 248, 245, 0.75);
  font-size: 11px;
  cursor: pointer;
}

.force-rebuild:hover {
  border-color: #93463b;
  background: #fff7f4;
}

.force-rebuild:disabled {
  opacity: 0.5;
  cursor: wait;
}

.graph-empty {
  display: grid;
  min-height: 580px;
  place-items: center;
  align-content: center;
  gap: 10px;
  color: #667069;
  background: #f5f6f1;
  text-align: center;
}

.graph-empty .el-icon {
  color: #819087;
  font-size: 34px;
}

.graph-empty p {
  max-width: 420px;
  margin: 0;
  color: #858b84;
  font-size: 12px;
}

.map-spinner {
  width: 26px;
  height: 26px;
  border: 2px solid #c8cdc6;
  border-top-color: #315c49;
  border-radius: 50%;
  animation: map-spin 900ms linear infinite;
}

@keyframes map-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes map-pulse {
  50% {
    box-shadow: 0 0 0 9px rgba(47, 117, 168, 0.04);
  }
}

@media (max-width: 1180px) {
  .map-toolbar {
    grid-template-columns: 1fr 1fr;
  }

  .toolbar-status {
    justify-content: flex-start;
    padding-left: 0;
    border-left: 0;
  }

  .map-workspace {
    grid-template-columns: minmax(0, 1fr) 330px;
  }
}

@media (max-width: 900px) {
  .map-page {
    padding: 16px;
  }

  .map-stats {
    grid-template-columns: repeat(2, 1fr);
  }

  .map-workspace {
    grid-template-columns: 1fr;
  }

  .graph-stage {
    border-right: 0;
    border-bottom: 1px solid #cfd3ca;
  }

  .knowledge-graph,
  .graph-empty {
    min-height: 500px;
  }

  .map-inspector {
    min-height: 420px;
  }
}

@media (max-width: 620px) {
  .map-toolbar {
    grid-template-columns: 1fr;
  }

  .map-stats {
    grid-template-columns: 1fr 1fr;
  }

  .graph-stage-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .graph-stage-footer {
    flex-wrap: wrap;
    gap: 8px 14px;
  }

  .knowledge-graph,
  .graph-empty {
    min-height: 430px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .status-beacon.running,
  .map-spinner {
    animation: none;
  }

  .graph-edge,
  .graph-node,
  .node-core,
  .node-halo {
    transition: none;
  }
}
</style>
