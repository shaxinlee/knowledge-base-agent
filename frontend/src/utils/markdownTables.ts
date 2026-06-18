export type MarkdownDisplayBlock =
  | { type: 'paragraph'; key: string; text: string }
  | { type: 'heading'; key: string; level: number; text: string }
  | { type: 'list'; key: string; items: string[] }
  | { type: 'quote'; key: string; lines: string[] }
  | { type: 'code'; key: string; code: string; language: string }
  | { type: 'table'; key: string; headers: string[]; rows: string[][] }

interface TableRowCandidate {
  prefix: string
  row: string
}

export function parseMarkdownDisplayBlocks(
  lines: string[],
  normalizeText: (content: string) => string,
): MarkdownDisplayBlock[] {
  const blocks: MarkdownDisplayBlock[] = []
  let index = 0
  while (index < lines.length) {
    if (!lines[index].trim()) {
      index += 1
      continue
    }

    if (isFencedCodeStart(lines[index])) {
      const language = lines[index].trim().replace(/^```/, '').trim()
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !isFencedCodeStart(lines[index])) {
        codeLines.push(lines[index])
        index += 1
      }
      if (index < lines.length) {
        index += 1
      }
      blocks.push({
        type: 'code',
        key: `code-${index}-${blocks.length}`,
        code: codeLines.join('\n'),
        language,
      })
      continue
    }

    const current = extractTableRowCandidate(lines[index])
    const next = extractTableRowCandidate(lines[index + 1] ?? '')
    if (current && next && isMarkdownTableSeparator(next.row)) {
      if (current.prefix.trim()) {
        blocks.push({
          type: 'paragraph',
          key: `p-${index}-${blocks.length}`,
          text: current.prefix.trim(),
        })
      }

      const tableLines = [current.row, next.row]
      index += 2
      while (index < lines.length) {
        if (!lines[index].trim()) {
          const nextRowIndex = findNextNonEmptyLineIndex(lines, index + 1)
          const nextRow = nextRowIndex === -1 ? null : extractTableRowCandidate(lines[nextRowIndex])
          if (!nextRow || nextRow.prefix.trim()) {
            break
          }
          index = nextRowIndex
          continue
        }

        const row = extractTableRowCandidate(lines[index])
        if (!row || row.prefix.trim()) {
          break
        }
        tableLines.push(row.row)
        index += 1
      }

      const table = parseMarkdownTable(tableLines, normalizeText)
      if (table) {
        blocks.push({ ...table, key: `table-${index}-${blocks.length}` })
        continue
      }
    }

    const heading = parseHeading(lines[index], normalizeText)
    if (heading) {
      blocks.push({ ...heading, key: `heading-${index}-${blocks.length}` })
      index += 1
      continue
    }

    const listItem = parseListItem(lines[index], normalizeText)
    if (listItem) {
      const items = [listItem]
      index += 1
      while (index < lines.length) {
        const item = parseListItem(lines[index], normalizeText)
        if (!item) {
          break
        }
        items.push(item)
        index += 1
      }
      blocks.push({ type: 'list', key: `list-${index}-${blocks.length}`, items })
      continue
    }

    const quoteLine = parseQuoteLine(lines[index], normalizeText)
    if (quoteLine) {
      const quoteLines = [quoteLine]
      index += 1
      while (index < lines.length) {
        const line = parseQuoteLine(lines[index], normalizeText)
        if (!line) {
          break
        }
        quoteLines.push(line)
        index += 1
      }
      blocks.push({ type: 'quote', key: `quote-${index}-${blocks.length}`, lines: quoteLines })
      continue
    }

    if (lines[index].trim()) {
      blocks.push({
        type: 'paragraph',
        key: `p-${index}-${blocks.length}`,
        text: normalizeText(lines[index]),
      })
    }
    index += 1
  }
  return blocks
}

function isFencedCodeStart(line: string): boolean {
  return line.trim().startsWith('```')
}

function parseHeading(
  line: string,
  normalizeText: (content: string) => string,
): { type: 'heading'; level: number; text: string } | null {
  const match = /^(#{1,6})\s+(.+)$/.exec(line.trim())
  if (!match) {
    return null
  }
  return {
    type: 'heading',
    level: Math.min(match[1].length, 6),
    text: normalizeText(match[2]),
  }
}

function parseListItem(line: string, normalizeText: (content: string) => string): string | null {
  const match = /^\s*(?:[-*+]|\d+[.)])\s+(.+)$/.exec(line)
  if (!match) {
    return null
  }
  return normalizeText(match[1])
}

function parseQuoteLine(line: string, normalizeText: (content: string) => string): string | null {
  const match = /^\s*>\s?(.*)$/.exec(line)
  if (!match) {
    return null
  }
  return normalizeText(match[1])
}

function extractTableRowCandidate(line: string): TableRowCandidate | null {
  const firstPipeIndex = line.indexOf('|')
  const lastPipeIndex = line.lastIndexOf('|')
  if (firstPipeIndex === -1 || lastPipeIndex <= firstPipeIndex) {
    return null
  }
  const row = line.slice(firstPipeIndex, lastPipeIndex + 1).trim()
  if (!isMarkdownTableRow(row)) {
    return null
  }
  return {
    prefix: line.slice(0, firstPipeIndex),
    row,
  }
}

function isMarkdownTableRow(line: string): boolean {
  const trimmed = line.trim()
  return (
    trimmed.startsWith('|') && trimmed.endsWith('|') && splitMarkdownTableRow(trimmed).length > 1
  )
}

function isMarkdownTableSeparator(line: string): boolean {
  const cells = splitMarkdownTableRow(line)
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.trim().replace(/\s+/g, '')))
}

function parseMarkdownTable(
  lines: string[],
  normalizeText: (content: string) => string,
): { type: 'table'; headers: string[]; rows: string[][] } | null {
  if (lines.length < 2) {
    return null
  }
  const headers = splitMarkdownTableRow(lines[0]).map(normalizeText)
  const rows = lines
    .slice(2)
    .map((line) => normalizeRow(splitMarkdownTableRow(line), headers.length, normalizeText))
  if (headers.length === 0 || rows.length === 0) {
    return null
  }
  return { type: 'table', headers, rows }
}

function splitMarkdownTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  const cells: string[] = []
  let current = ''
  let escaped = false
  for (const char of trimmed) {
    if (escaped) {
      current += char
      escaped = false
      continue
    }
    if (char === '\\') {
      escaped = true
      continue
    }
    if (char === '|') {
      cells.push(current.trim())
      current = ''
      continue
    }
    current += char
  }
  if (escaped) {
    current += '\\'
  }
  cells.push(current.trim())
  return cells
}

function normalizeRow(
  cells: string[],
  expectedLength: number,
  normalizeText: (content: string) => string,
): string[] {
  const normalized = cells.map(normalizeText)
  while (normalized.length < expectedLength) {
    normalized.push('')
  }
  return normalized
}

function findNextNonEmptyLineIndex(lines: string[], startIndex: number): number {
  for (let index = startIndex; index < lines.length; index += 1) {
    if (lines[index].trim()) {
      return index
    }
  }
  return -1
}
