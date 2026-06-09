export type MarkdownDisplayBlock =
  | { type: 'paragraph'; key: string; text: string }
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

    if (lines[index].trim()) {
      blocks.push({
        type: 'paragraph',
        key: `p-${index}-${blocks.length}`,
        text: lines[index],
      })
    }
    index += 1
  }
  return blocks
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
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.trim()))
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
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim())
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
