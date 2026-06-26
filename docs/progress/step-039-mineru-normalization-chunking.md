# Step 039：真实 MinerU 产物标准化与 chunking 优化

## 1. 本步骤目标

本步骤目标是在 Step 038 已完成 MinerU API 解析状态、失败隔离和 parsed-results 保存的基础上，增强 MinerU zip 产物到 `document_blocks` 与 `chunks_metadata` 的转换质量。

本步骤聚焦真实解析产物的标准化与 chunking，不接入 embedding / reranker / LLM API，不新增数据库表，不改变文件上传接口，不做完整 RAG 端到端验收。

## 2. 对应 SDD 条目

- SDD v0.1 1.3：文档解析 -> 文本标准化 -> Chunking -> Embedding -> 检索 -> Reranker -> LLM -> 引用溯源。
- SDD v0.1 1.4：解析结果持久化；文档标准化为 blocks；文档切片生成 chunks；引用必须包含文件名、定位信息和原文片段。
- SDD v0.1 2.1.4：失败 job 不能污染线上检索；只有最新成功的 parse_job 产物允许进入 active 检索集合。
- SDD v0.1 2.1.5：`save MinerU markdown/json/assets -> normalize document blocks -> chunking -> save chunks metadata`。
- SDD v0.1 2.1.6：每个 chunk 必须生成 `source_locator`，示例包含 `pdf:p12-p13`、`pptx:slide-8`、`xlsx:Sheet1!A20:F35`、`md:Chapter 2 > Method`、`image:ocr-region-3`、`txt:chunk-12`。
- SDD v0.1 4.7 / 4.8：`document_blocks` 与 `chunks_metadata` 保存标准化 block、chunk 原文、hash、token_count、定位字段、source_locator、metadata、is_active。
- 用户确认方向：MinerU 使用 API 调用方式；后续 embedding/reranker/LLM 继续按 API 化方向推进。

## 3. 本步骤完成内容

- 增强 Markdown 标准化：
  - 识别 `#` 到 `######` heading。
  - 维护 heading 层级路径，写入 block metadata。
  - 识别 Markdown table block。
  - 保留段落、表格和 heading 的自然边界。
- 增强 JSON 标准化：
  - 递归提取 `blocks`、`document_blocks`、`pages`、`content`、`children`、`items`、`layout_dets`、`para_blocks`、`tables`、`images` 等结构。
  - 父级 page/sheet/row/bbox/heading_path 上下文会传递给子 block。
  - 支持 `content/text/md/markdown/html/table_body/lines` 等文本字段。
  - 将 `table`、`image/figure/ocr`、`heading/title` 等类型标准化为 `table`、`image_ocr`、`heading` 等稳定 block_type。
  - 保留 `source_locator`、`asset_path`、`heading_path`、raw keys 等 metadata，支持图片 OCR 区域定位。
- 升级 chunking 策略：
  - 从 `one_block_one_chunk` 升级为 `heading_aware_recursive`。
  - 小段会按同一 heading_path 合并，避免过碎 chunks。
  - 表格和图片 OCR 保持边界，除非超长才切分。
  - 长文本按段落、换行、中文句号、英文句号和空格递归切分。
  - 默认目标长度约 1000 字符，上限 1200 字符，overlap 120 字符。
  - 每个 chunk 继续保存 `content_hash`、`token_count`、`heading_path`、`source_locator`、block ids/indexes/types 等 metadata。
  - 重新解析时仍会将同一文件旧 active chunks 置为 inactive，避免旧产物污染检索。
- 优化 source_locator：
  - 优先使用 MinerU/标准化元数据中的 `source_locator`。
  - PDF/分页内容生成 `source:pN` 或 `source:pN-pM`。
  - PPT 生成 `source:slide-N`。
  - 表格 sheet/row 生成 `source:Sheet!row-start-row-end`。
  - Markdown/DOCX 优先使用标题路径，如 `md:Chapter > Section`。
  - 图片 OCR 支持 `image:ocr-region-N`。
  - 超长切分的多 part 会追加 `#part-N`。
- 更新后端测试：
  - 新增真实结构 zip fixture，覆盖 Markdown heading/table、JSON pages/table/image OCR。
  - 更新索引链路测试以适配 heading-aware chunking 后的 chunk 数量和 embedding 请求。

## 4. 修改文件清单

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| `backend/app/services/document_blocks.py` | 修改 | 增强 MinerU zip 中 Markdown/JSON 的 block 标准化、heading_path、table、image OCR、父级上下文和 source_locator metadata |
| `backend/app/services/chunks.py` | 修改 | 将 chunking 从 one-block-one-chunk 升级为 heading-aware recursive chunking，并增强 source_locator 生成 |
| `backend/tests/test_files_api.py` | 修改 | 新增真实结构 MinerU zip fixture 与标准化/chunking 覆盖测试，更新索引/删除测试断言 |
| `docs/progress/step-039-mineru-normalization-chunking.md` | 新增 | 记录 Step 039 的目标、实现、验证、风险和下一步建议 |
| `docs/progress/README.md` | 修改 | 同步 Step 039 状态、已完成内容和下一步建议 |

## 5. 关键实现说明

- `parse_markdown_blocks()`：
  - 使用 `parse_markdown_heading()` 识别 heading level 和 title。
  - 使用 `update_heading_path()` 维护层级路径。
  - 使用 `is_markdown_table()` 判断表格 block。
- `find_json_block_candidates()`：
  - 递归扫描 MinerU JSON 常见容器字段。
  - 使用 `merge_json_context()` 将父级 page/sheet/row/bbox/heading_path 传给子 block。
- `normalize_json_block_type()`：
  - 将真实产物中可能变化的 `type/category/kind/block_type` 映射到稳定 block type。
- `build_chunk_drafts()`：
  - 同一 heading_path 下的小文本块会合并。
  - heading 会开启新的 buffer，避免不同章节内容混入同一 chunk。
  - table/image_ocr 会先 flush 当前文本 buffer，再作为边界 chunk 处理。
- `split_text_recursively()`：
  - 优先按段落、换行和句子边界切分。
  - 找不到合适边界时使用滑窗，并保留 overlap。
- `build_chunk_source_locator()`：
  - 按 metadata locator、页码范围、slide、sheet/row、heading_path、image OCR region 的优先级生成定位。

## 6. 验证与测试结果

| 验证项 | 命令或方式 | 结果 | 说明 |
|---|---|---|---|
| 后端目标测试 | `backend/.venv/bin/python -m pytest backend/tests/test_files_api.py -q` | 通过 | 13 passed，覆盖真实结构 zip 标准化、chunking、索引、失败路径 |
| 后端格式检查 | `backend/.venv/bin/black --check backend/app backend/tests backend/migrations` | 通过 | 84 files unchanged |
| 后端 lint | `backend/.venv/bin/ruff check backend/app backend/tests backend/migrations` | 通过 | All checks passed |
| 后端类型检查 | `backend/.venv/bin/mypy backend/app backend/tests` | 通过 | 74 source files 无类型错误 |
| 后端完整测试 | `backend/.venv/bin/python -m pytest backend/tests -q` | 通过 | 46 passed，存在既有 Starlette/JWT secret warning |
| 前端类型检查 | `npm run typecheck` | 通过 | 前端未改业务代码，类型检查通过 |
| 前端构建测试 | `npm run build` | 通过 | 构建成功；仍有既有 `@vueuse/core` pure annotation warning，不阻塞 |
| Docker 构建与启动 | `docker compose up -d --build backend-api frontend` | 通过 | 后端镜像使用阿里云 PyPI 镜像构建，服务已重启 |
| Migration | `docker compose exec -T backend-api alembic upgrade head` | 通过 | 无新增 migration，当前 schema 可用 |
| 服务健康检查 | `curl -fsS http://localhost:5173/api/v1/health` | 通过 | 返回 `status=ok` |
| Docker Compose 服务状态 | `docker compose ps` | 通过 | frontend、backend-api、postgres、redis、qdrant、minio 均 Up |
| 容器内后端完整测试 | `docker compose exec -T backend-api pytest -q` | 通过 | 46 passed，存在既有 Starlette/JWT secret warning |
| 真实 MinerU 在线 zip 标准化 | 配置 `MINERU_API_TOKEN` 后上传真实文件并解析 | 未执行 | 当前 `.env` 中 `MINERU_API_TOKEN=` 为空，无法获取真实 MinerU 线上产物 |

## 7. 当前未完成事项

- 当前仍未配置 `MINERU_API_TOKEN`，真实 MinerU 在线产物未执行样本验证。
- 当前没有把 assets 图片文件单独保存到 MinIO `assets` bucket；本步骤只保留 asset path/source metadata。
- 当前 `token_count` 是基础正则统计，不是 embedding 模型 tokenizer 的真实 token 数。
- 当前 Excel 单元格范围如 `A20:F35` 仍依赖 MinerU JSON 是否提供明确字段；本步骤保留 sheet/row 范围基础定位。
- Step 040 的 API 化 embedding / reranker / LLM 未在本步骤处理。

## 8. 风险与注意事项

- MinerU 真实 JSON 字段可能与当前 fixture 不完全一致，后续拿到真实 token 和真实样本文档后需要继续补齐映射。
- heading-aware chunking 会改变旧 demo/fake 样本的 chunk 数量。例如旧 `one_block_one_chunk` 下的 4 个 chunks，现在会合并为 2 个更合理的 chunks；测试已同步该行为。
- 如果后续真实表格特别长，当前会按文本边界切分，仍可能需要更细的表格结构化策略。
- 当前 source_locator 生成不改变数据库结构；如果后续需要更精确定位，如 PDF bbox 或 Excel cell range，可继续扩展 metadata 映射。

## 9. 下一步建议

建议进入 Step 040：API 化 embedding / reranker / LLM 接入。

原因：Step 039 已将解析产物到 blocks/chunks 的质量向真实链路推进。下一步应按用户确认的 API 化方向，将 embedding、reranker 和 LLM 从本地/模板/fake 能力升级为可配置 API client，并保留 fake/demo client 仅用于测试和演示。
