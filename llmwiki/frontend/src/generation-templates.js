/**
 * 生成模块的内置 Skill 模板系统。
 * 为每种产物类型提供子类型模板:预设指令/示例输出/配置。
 * 用户选择模板后自动填入指令,也可自行编辑。
 */
export const SKILL_TEMPLATES = {
  // ========== 报告 ==========
  report: {
    label: "报告",
    glyph: "📄",
    defaultTemplate: "research",
    subTypes: [
      {
        id: "research",
        label: "研究报告",
        desc: "深度分析,含摘要/背景/方法/结论",
        instruction: "基于知识库中的文档,撰写一份结构化研究报告。包含:1) 摘要;2) 背景与上下文;3) 核心发现(逐条展开,每条标注证据引用);4) 对比分析;5) 结论与建议。全文用中文,markdown格式。",
        icon: "🔬",
      },
      {
        id: "summary",
        label: "总结摘要",
        desc: "快速提炼核心内容",
        instruction: "基于知识库中的文档,撰写一份总结摘要。包含:1) 核心结论(3-5条);2) 关键数据;3) 下一步行动。控制在500字以内,markdown格式。",
        icon: "📋",
      },
      {
        id: "analysis",
        label: "分析报告",
        desc: "问题分析+数据洞察+建议",
        instruction: "基于知识库中的文档,撰写一份分析报告。包含:1) 问题陈述;2) 数据分析(引用具体数字);3) 根因分析;4) 多个方案对比;5) 推荐方案与理由。markdown格式,关键结论后标注证据引用。",
        icon: "📊",
      },
      {
        id: "comparison",
        label: "对比报告",
        desc: "多实体/方案对比分析",
        instruction: "基于知识库中的文档,撰写一份对比分析报告。以表格形式对比不同方案/实体/时期的异同,每个指标后标注证据引用。包含:1) 对比维度概述;2) 对比表格;3) 各维度详细说明;4) 综合建议。markdown格式。",
        icon: "⚖️",
      },
      {
        id: "timeline",
        label: "时间线",
        desc: "事件/里程碑时序梳理",
        instruction: "基于知识库中的文档,梳理事件/里程碑的时间线。按时间顺序列出关键事件,每个事件包含:时间、事件描述、涉及实体、证据引用。用markdown表格或列表格式。",
        icon: "📅",
      },
      {
        id: "custom",
        label: "自定义",
        desc: "自由编写指令",
        icon: "✏️",
      },
    ],
  },

  // ========== 图表 ==========
  chart: {
    label: "图表",
    glyph: "📊",
    defaultTemplate: "bar",
    subTypes: [
      {
        id: "bar",
        label: "柱状图",
        desc: "分类数据对比",
        instruction: "基于证据中的数据,生成柱状图规范。请从证据中提取数字数据,比较不同类别的数值差异。输出Vega-Lite JSON规范。",
        icon: "📊",
        chartHint: "比较不同类别的数值",
      },
      {
        id: "line",
        label: "折线图",
        desc: "趋势变化展示",
        instruction: "基于证据中的数据,生成折线图规范。请从证据中提取时间序列数据,展示随时间变化的趋势。输出Vega-Lite JSON规范。",
        icon: "📈",
        chartHint: "展示随时间变化的趋势",
      },
      {
        id: "pie",
        label: "饼图",
        desc: "占比/分布展示",
        instruction: "基于证据中的数据,生成饼图规范。请从证据中提取各部分占总体的比例数据。输出Vega-Lite JSON规范。",
        icon: "🥧",
        chartHint: "展示各部分占比",
      },
      {
        id: "scatter",
        label: "散点图",
        desc: "相关性分析",
        instruction: "基于证据中的数据,生成散点图规范。请从证据中提取两变量的对应数据,展示其相关性。输出Vega-Lite JSON规范。",
        icon: "🔹",
        chartHint: "展示两个变量之间的关系",
      },
      {
        id: "table_chart",
        label: "数据表格",
        desc: "结构化数据展示",
        instruction: "基于证据中的数据,生成表格JSON规范。整理为行列清晰的数据表,包含列标题和数据行。输出JSON格式。",
        icon: "▦",
        chartHint: "结构化数据展示",
      },
      {
        id: "custom",
        label: "自定义",
        desc: "自由编写指令",
        icon: "✏️",
      },
    ],
  },

  // ========== 表格 ==========
  table: {
    label: "表格",
    glyph: "▦",
    defaultTemplate: "structured",
    subTypes: [
      {
        id: "structured",
        label: "结构化表格",
        desc: "标准行列数据表",
        instruction: "基于知识库中的证据,整理为结构化表格。要求:1) 列名清晰;2) 每行一个数据项;3) 数值精确,来自证据;4) 标注每行/每列的证据来源span_id。输出columns+rows格式JSON。",
        icon: "📋",
      },
      {
        id: "comparison_table",
        label: "对比表格",
        desc: "横向对比多维数据",
        instruction: "基于知识库中的证据,生成对比表格。行=对比项,列=对比维度。例如:行可以是不同项目/方案/实体,列可以是预算/进度/质量等。输出columns+rows格式JSON。",
        icon: "⚖️",
      },
      {
        id: "summary_table",
        label: "汇总表",
        desc: "统计汇总数据",
        instruction: "基于知识库中的证据,生成统计汇总表。包含合计、均值、最大值、最小值等聚合行。输出columns+rows格式JSON。",
        icon: "📊",
      },
      {
        id: "custom",
        label: "自定义",
        desc: "自由编写指令",
        icon: "✏️",
      },
    ],
  },

  // ========== 幻灯片 ==========
  slides: {
    label: "幻灯片",
    glyph: "▭",
    defaultTemplate: "presentation",
    subTypes: [
      {
        id: "presentation",
        label: "演示文稿",
        desc: "标准汇报演示(5-8页)",
        instruction: "基于知识库中的证据,生成PPT演示大纲。包含:封面→目录→背景→核心发现→数据分析→结论→建议→附录。每页标题+3-5条要点,要点标注证据引用。输出slides JSON格式。",
        icon: "📑",
      },
      {
        id: "briefing",
        label: "简报",
        desc: "快速汇报(3-5页)",
        instruction: "基于知识库中的证据,生成简报式PPT大纲。包含:封面→核心发现(2-3页)→建议→附录。每页标题+3条要点,要点标注证据引用。输出slides JSON格式。",
        icon: "📌",
      },
      {
        id: "deep_dive",
        label: "深度报告",
        desc: "详细技术/分析报告(10-15页)",
        instruction: "基于知识库中的证据,生成深度PPT大纲。包含:封面→目录→执行摘要→背景→方法论→详细发现(4-6页)→对比分析→结论→建议→附录。每页标题+要点,详细标注证据引用。输出slides JSON格式。",
        icon: "🔍",
      },
      {
        id: "status",
        label: "进度汇报",
        desc: "项目状态快报",
        instruction: "基于知识库中的证据,生成项目进度PPT大纲。包含:封面→整体进度→已完成里程碑→待办事项→风险和问题→下一步计划。用进度条/百分比展示完成度,标注证据引用。输出slides JSON格式。",
        icon: "✅",
      },
      {
        id: "custom",
        label: "自定义",
        desc: "自由编写指令",
        icon: "✏️",
      },
    ],
  },
};

/**
 * 根据类型和子类型 ID 获取预设指令。
 */
export function getTemplateInstruction(type, subTypeId) {
  const t = SKILL_TEMPLATES[type];
  if (!t) return "";
  const st = t.subTypes.find((s) => s.id === subTypeId);
  if (!st) return "";
  // "自定义"类型没有预设指令
  if (st.id === "custom") return "";
  return st.instruction;
}

/**
 * 获取默认子类型 ID
 */
export function getDefaultSubType(type) {
  const t = SKILL_TEMPLATES[type];
  if (!t) return "custom";
  return t.defaultTemplate;
}
