export const knowledgeBases = [
  {
    name: '2024 年度员工手册',
    description: '包含企业文化、福利制度、考勤规范及员工行为准则等核心规章制度。',
    status: '已发布',
    statusClass: 'success',
    files: 42,
    indexed: 40,
    updated: '2 小时前',
    icon: '文',
  },
  {
    name: '技术架构白皮书',
    description: '详细描述公司核心业务系统的架构设计、微服务治理及数据流向图。',
    status: '处理中',
    statusClass: 'processing',
    files: 156,
    indexed: 118,
    updated: '昨天',
    icon: '架',
  },
  {
    name: '客服常见问题 QA',
    description: '整理自过去三年的客户服务工单，包含高频问题及其标准解决方案。',
    status: '解析失败',
    statusClass: 'danger',
    files: 512,
    indexed: 486,
    updated: '3 天前',
    icon: '问',
  },
  {
    name: '合规与隐私协议',
    description: '法务部门审核通过的所有对外协议模板及数据处理合规指南。',
    status: '已发布',
    statusClass: 'success',
    files: 18,
    indexed: 18,
    updated: '上周',
    icon: '规',
  },
  {
    name: '品牌营销素材库',
    description: '2024 视觉识别系统设计规范及各渠道广告文案策略。',
    status: '已发布',
    statusClass: 'success',
    files: 89,
    indexed: 89,
    updated: '5 分钟前',
    icon: '品',
  },
]

export const files = [
  {
    name: '2024年度Q3财务详细报表.pdf',
    type: 'PDF',
    size: '18.4 MB',
    owner: '张经理',
    fileStatus: 'indexed',
    jobStatus: 'indexed',
    updated: '10 分钟前',
    error: '-',
  },
  {
    name: '研发中心人力资源报告.docx',
    type: 'DOCX',
    size: '4.2 MB',
    owner: '李工',
    fileStatus: 'indexed',
    jobStatus: 'indexed',
    updated: '35 分钟前',
    error: '-',
  },
  {
    name: '客户服务工单汇总.csv',
    type: 'CSV',
    size: '9.8 MB',
    owner: '王运营',
    fileStatus: 'partially_indexed',
    jobStatus: 'partially_indexed',
    updated: '1 小时前',
    error: '部分行 OCR 片段缺失',
  },
  {
    name: '品牌视觉规范.pptx',
    type: 'PPTX',
    size: '26.1 MB',
    owner: '赵设计',
    fileStatus: 'indexing',
    jobStatus: 'embedding',
    updated: '刚刚',
    error: '-',
  },
  {
    name: '旧版采购协议.xlsx',
    type: 'XLSX',
    size: '2.1 MB',
    owner: 'Admin',
    fileStatus: 'failed',
    jobStatus: 'failed',
    updated: '昨天',
    error: 'UNSUPPORTED_FILE_TYPE',
  },
]

export const chunks = [
  {
    id: 'chunk_8f32a9',
    locator: 'pdf:p42',
    section: 'PAGE 42 / LINE 12-18',
    chars: 482,
    content:
      '在第三季度，集团加大了对基础设施层的资金投入。其中，算力资源租赁协议涉及金额达 1,240 万元，较上一季度环比增长 32%。此项支出主要归属于研发中心的基础模型训练项目。',
  },
  {
    id: 'chunk_92c4d1',
    locator: 'docx:Talent Acquisition',
    section: 'SECTION: TALENT ACQUISITION',
    chars: 356,
    content:
      '截至 2024 年 9 月 30 日，研发中心累计入职专家级以上工程师 15 人。人才获取成本合计支出 450 万元，新增人员均位于 P8 及以上职级。',
  },
  {
    id: 'chunk_a72ef0',
    locator: 'xlsx:Sheet1!A20:F35',
    section: 'SHEET: BUDGET PLAN',
    chars: 218,
    content:
      '基础模型训练相关预算在 Q3 调整为重点投入项，云原生组件授权费用与推理资源租赁费用进入研发成本归集。',
  },
]

export const users = [
  { username: 'admin', display: '张经理', role: 'admin', active: true, updated: '刚刚' },
  { username: 'li-engineer', display: '李工', role: 'user', active: true, updated: '2 小时前' },
  { username: 'ops-wang', display: '王运营', role: 'user', active: true, updated: '昨天' },
  { username: 'old-account', display: '旧账号', role: 'user', active: false, updated: '上周' },
]

export const auditLogs = [
  {
    time: '2026-06-06 10:42',
    actor: '张经理',
    action: 'file.retry_parse',
    resource: 'file',
    request: 'req_8f32a9',
    result: '成功',
  },
  {
    time: '2026-06-06 10:18',
    actor: '张经理',
    action: 'knowledge_base.update',
    resource: 'knowledge_base',
    request: 'req_194bd2',
    result: '成功',
  },
  {
    time: '2026-06-05 18:03',
    actor: 'Admin User',
    action: 'user.reset_password',
    resource: 'user',
    request: 'req_76fd31',
    result: '成功',
  },
]
