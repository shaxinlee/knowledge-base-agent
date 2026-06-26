<script setup lang="ts">
import { computed } from 'vue'

import { parseMarkdownDisplayBlocks } from '@/utils/markdownTables'

const props = defineProps<{
  content: string
  normalizeText: (content: string) => string
}>()

const blocks = computed(() =>
  parseMarkdownDisplayBlocks(
    normalizeMarkdownBlockBreaks(props.content).split(/\r?\n/),
    props.normalizeText,
  ),
)

type InlineSegmentType = 'text' | 'strong' | 'emphasis' | 'code'

interface InlineSegment {
  key: string
  type: InlineSegmentType
  text: string
}

function normalizeMarkdownBlockBreaks(content: string): string {
  return content
    .replace(/\|\s*\|\s*(?=(?::?-{3,}:?\s*\|)|(?:\d+\s*\|))/g, '|\n| ')
    .replace(/([^\n])[\t ]+(?=#{1,6}\s+\S)/g, '$1\n\n')
}

function inlineSegments(text: string): InlineSegment[] {
  const segments: InlineSegment[] = []
  const pattern = /(`[^`\n]+`|\*\*[^*\n]+?\*\*|__[^_\n]+?__|\*[^*\s][^*\n]+?\*|_[^_\s][^_\n]+?_)/g
  let cursor = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      segments.push(createInlineSegment('text', text.slice(cursor, match.index), segments.length))
    }
    segments.push(parseInlineToken(match[0], segments.length))
    cursor = match.index + match[0].length
  }

  if (cursor < text.length) {
    segments.push(createInlineSegment('text', text.slice(cursor), segments.length))
  }
  return segments.length ? segments : [createInlineSegment('text', text, 0)]
}

function parseInlineToken(token: string, index: number): InlineSegment {
  if (token.startsWith('`') && token.endsWith('`')) {
    return createInlineSegment('code', token.slice(1, -1), index)
  }
  if (
    (token.startsWith('**') && token.endsWith('**')) ||
    (token.startsWith('__') && token.endsWith('__'))
  ) {
    return createInlineSegment('strong', token.slice(2, -2), index)
  }
  return createInlineSegment('emphasis', token.slice(1, -1), index)
}

function createInlineSegment(type: InlineSegmentType, text: string, index: number): InlineSegment {
  return {
    key: `${type}-${index}-${text}`,
    type,
    text,
  }
}
</script>

<template>
  <div class="markdown-content">
    <template v-for="block in blocks" :key="block.key">
      <component :is="`h${block.level}`" v-if="block.type === 'heading'" class="markdown-heading">
        <template v-for="segment in inlineSegments(block.text)" :key="segment.key">
          <strong v-if="segment.type === 'strong'">{{ segment.text }}</strong>
          <em v-else-if="segment.type === 'emphasis'">{{ segment.text }}</em>
          <code v-else-if="segment.type === 'code'" class="markdown-inline-code">{{
            segment.text
          }}</code>
          <template v-else>{{ segment.text }}</template>
        </template>
      </component>

      <p v-else-if="block.type === 'paragraph'" class="markdown-paragraph">
        <template v-for="segment in inlineSegments(block.text)" :key="segment.key">
          <strong v-if="segment.type === 'strong'">{{ segment.text }}</strong>
          <em v-else-if="segment.type === 'emphasis'">{{ segment.text }}</em>
          <code v-else-if="segment.type === 'code'" class="markdown-inline-code">{{
            segment.text
          }}</code>
          <template v-else>{{ segment.text }}</template>
        </template>
      </p>

      <component
        :is="block.ordered ? 'ol' : 'ul'"
        v-else-if="block.type === 'list'"
        class="markdown-list"
      >
        <li v-for="(item, index) in block.items" :key="index">
          <template v-for="segment in inlineSegments(item)" :key="segment.key">
            <strong v-if="segment.type === 'strong'">{{ segment.text }}</strong>
            <em v-else-if="segment.type === 'emphasis'">{{ segment.text }}</em>
            <code v-else-if="segment.type === 'code'" class="markdown-inline-code">{{
              segment.text
            }}</code>
            <template v-else>{{ segment.text }}</template>
          </template>
        </li>
      </component>

      <blockquote v-else-if="block.type === 'quote'" class="markdown-quote">
        <p v-for="(line, index) in block.lines" :key="index">
          <template v-for="segment in inlineSegments(line)" :key="segment.key">
            <strong v-if="segment.type === 'strong'">{{ segment.text }}</strong>
            <em v-else-if="segment.type === 'emphasis'">{{ segment.text }}</em>
            <code v-else-if="segment.type === 'code'" class="markdown-inline-code">{{
              segment.text
            }}</code>
            <template v-else>{{ segment.text }}</template>
          </template>
        </p>
      </blockquote>

      <pre
        v-else-if="block.type === 'code'"
        class="markdown-code"
      ><code>{{ block.code }}</code></pre>

      <div v-else class="markdown-table-wrap">
        <table class="markdown-table">
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
                <template v-for="segment in inlineSegments(cell)" :key="segment.key">
                  <strong v-if="segment.type === 'strong'">{{ segment.text }}</strong>
                  <em v-else-if="segment.type === 'emphasis'">{{ segment.text }}</em>
                  <code v-else-if="segment.type === 'code'" class="markdown-inline-code">{{
                    segment.text
                  }}</code>
                  <template v-else>{{ segment.text }}</template>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.markdown-content {
  display: grid;
  gap: 8px;
  color: inherit;
}

.markdown-heading {
  margin: 10px 0 2px;
  color: var(--ka-text);
  font-weight: 800;
  line-height: 1.35;
}

h1.markdown-heading {
  font-size: 19px;
}

h2.markdown-heading {
  font-size: 17px;
}

h3.markdown-heading,
h4.markdown-heading,
h5.markdown-heading,
h6.markdown-heading {
  font-size: 15px;
}

.markdown-paragraph {
  margin: 0;
  white-space: pre-wrap;
}

.markdown-list {
  display: grid;
  gap: 5px;
  margin: 0;
  padding-left: 20px;
}

.markdown-list li {
  padding-left: 2px;
}

.markdown-inline-code {
  padding: 1px 5px;
  border: 1px solid var(--ka-border);
  border-radius: 4px;
  color: var(--ka-text);
  background: #f5f7f6;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 0.92em;
}

.markdown-quote {
  margin: 2px 0;
  padding: 8px 12px;
  border-left: 3px solid var(--ka-primary);
  color: var(--ka-text-secondary);
  background: #f6faf8;
}

.markdown-quote p {
  margin: 0 0 4px;
}

.markdown-quote p:last-child {
  margin-bottom: 0;
}

.markdown-code {
  max-width: 100%;
  margin: 2px 0;
  padding: 10px 12px;
  overflow-x: auto;
  border: 1px solid var(--ka-border);
  border-radius: 6px;
  color: #28342f;
  background: #f5f7f6;
  font-size: 13px;
  line-height: 1.55;
}

.markdown-code code {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  white-space: pre;
}

.markdown-table-wrap {
  max-width: 100%;
  margin: 2px 0;
  overflow-x: auto;
}

.markdown-table {
  width: 100%;
  min-width: 420px;
  border-collapse: collapse;
  font-size: 14px;
  line-height: 1.5;
  background: #fff;
}

.markdown-table th,
.markdown-table td {
  padding: 8px 10px;
  border: 1px solid var(--ka-border);
  text-align: left;
  vertical-align: top;
}

.markdown-table th {
  color: var(--ka-text);
  font-weight: 700;
  background: #f0f5f2;
}

.markdown-table td {
  color: var(--ka-text-secondary);
}
</style>
