# 新加坡出口管制法规洞察平台 — 设计文档

> 版本 v0.1 · 2026-04-20

---

## 1. 项目概述

### 1.1 背景
新加坡作为亚太地区主要贸易枢纽，其出口管制制度（以《战略物资（管制）法》Strategic Goods (Control) Act, SGCA 为核心）对涉及战略物资、双用途物项、受制裁国家/实体业务的企业有直接合规影响。本平台旨在为企业合规、法务、贸易团队提供一个**主题化、可检索、可追踪**的出口管制法规洞察入口。

### 1.2 目标
- 将零散的法规、清单、许可、制裁信息按企业实际场景聚合
- 帮助企业快速判断"我这单业务是否受管制 / 需要什么许可"
- 跟踪法规更新，降低合规盲区

### 1.3 非目标（v1 不做）
- 不替代律师出具正式合规意见
- 不直接对接 TradeNet 申报
- 不做付费会员 / 账号体系（v1 公开访问）

---

## 2. 目标用户与典型场景

| 用户角色 | 关注点 | 典型动作 |
| --- | --- | --- |
| 企业合规官 (Compliance Officer) | 体系搭建、ICP、内部培训 | 浏览主题、下载清单、导出 PDF |
| 法务 (Legal Counsel) | 法条原文、判例、处罚 | 检索条款、对比修订历史 |
| 贸易/物流经理 | 单笔业务能否出货、需要什么许可 | 决策树、HS Code 关联、许可类型查询 |
| 高管/BD | 进入新市场前的合规风险摸底 | 概览页、风险热力图、订阅更新 |

---

## 3. 核心功能（v1）

### 3.1 主题化浏览（核心）
按企业场景维度组织，而非按法条号。一级主题建议如下：

1. **战略物资管制（SGCA / SGCR）**
   - 战略物资清单 (Strategic Goods Control List, SGCL)
   - 军品（Munitions List）/ 双用途（Dual-Use List）
   - 多边出口管制体系映射（Wassenaar、MTCR、NSG、AG）
2. **许可类型（Permits）**
   - Individual Permit / Bulk Permit / Special Permit
   - Tier 1 / Tier 2 / Tier 3 适用条件
   - 申请流程、所需材料、时效
3. **管控行为（Controlled Activities）**
   - 出口 (Export)
   - 转运 (Transhipment)
   - 过境 (Transit)
   - 中介/经纪 (Brokering)
   - 无形技术转让 (Intangible Technology Transfer)
4. **制裁与禁运（Sanctions）**
   - UN 安理会制裁
   - 新加坡自主制裁
   - 与 OFAC / EU 清单的对照提示
5. **Catch-All 管控**
   - WMD 终端用途 / 终端用户判定
   - Red Flag 指标
6. **合规体系（ICP）**
   - 内部合规计划要素
   - 审计与记录保存（5 年）
7. **违规与处罚**
   - 罚则（罚款 / 监禁 / 实体黑名单）
   - 典型案例
8. **更新动态（Updates）**
   - 法规修订时间线
   - 清单变更通知

### 3.2 检索
- 全文检索（按主题 / 关键词 / HS Code 关键字）
- 高亮 + 上下文片段
- v1 用本地索引（Fuse.js 或 FlexSearch），不依赖后端

### 3.3 决策树（Quick Check）
回答 4-6 个问题，给出"是否受管制 / 建议许可类型 / 需进一步咨询"的初判结果，并附**免责声明**。

### 3.4 法规更新订阅（轻量）
- 邮件订阅（v1 用第三方表单服务，如 Formspree）
- 站内"What's New"时间线

### 3.5 导出
- 主题页一键导出 PDF（用 `html2pdf.js` 或浏览器打印样式）

---

## 4. 信息架构（IA）

```
首页 (Landing)
├── 主题浏览 (Topics)
│   ├── 战略物资管制
│   ├── 许可类型
│   ├── 管控行为
│   ├── 制裁与禁运
│   ├── Catch-All
│   ├── 合规体系 (ICP)
│   └── 违规与处罚
├── 快速判断 (Quick Check) — 决策树
├── 法规库 (Library) — 原文链接 + 摘要
├── 更新动态 (Updates)
├── 资源下载 (Resources) — 清单 PDF / 模板
└── 关于 / 免责声明 (About)
```

每个主题页统一模板：
- 概述 (Overview)
- 关键定义 (Key Definitions)
- 适用情形 (Applicability)
- 企业实操要点 (Practical Points)
- 关联法条 (Linked Provisions)
- 常见问题 (FAQ)
- 相关主题 (Related Topics)
- 最近更新 (Recent Changes)

---

## 5. 页面结构与关键组件

### 5.1 页面清单

| 路由 | 页面 | 核心组件 |
| --- | --- | --- |
| `/` | 首页 | HeroBanner、TopicGrid、UpdatesPreview、QuickCheckEntry |
| `/topics` | 主题列表 | TopicCard × N、CategoryFilter |
| `/topics/:slug` | 主题详情 | TopicHeader、Toc、ContentBlocks、RelatedTopics、ChangeLog |
| `/quick-check` | 决策树 | StepWizard、ResultCard、Disclaimer |
| `/library` | 法规库 | LawList、SearchBar、SourceLinkBadge |
| `/updates` | 更新动态 | Timeline、UpdateCard |
| `/resources` | 资源下载 | DownloadCard |
| `/about` | 关于 | StaticContent |
| `/search?q=` | 搜索结果 | SearchInput、ResultList、HighlightSnippet |

### 5.2 关键组件设计
- **TopicCard**：图标 + 标题 + 一句话描述 + 标签（如「高频」「新规」）
- **StepWizard**：单选/多选 → 下一步分支 → 结果页（结果含建议+免责声明+联系律师 CTA）
- **Toc**：右侧锚点目录，sticky，滚动高亮
- **ChangeLog**：日期 + 变更摘要 + 来源链接
- **Disclaimer**：贯穿决策树和主题页底部，醒目但不突兀

---

## 6. 技术架构

### 6.1 技术栈
- **框架**：Vue 3 + `<script setup>` + TypeScript
- **构建**：Vite
- **路由**：Vue Router 4（History 模式）
- **状态**：Pinia（v1 状态轻，主要存当前主题筛选 / 决策树进度）
- **UI**：
  - 选项 A：Element Plus（企业风强、组件全）✅ 推荐
  - 选项 B：Naive UI（更轻、TS 友好）
- **样式**：UnoCSS 或 Tailwind CSS
- **Markdown 渲染**：`markdown-it` + `markdown-it-anchor` + `shiki`（代码高亮，本项目用得少）
- **检索**：FlexSearch（轻量、性能好）
- **PDF 导出**：`html2pdf.js`
- **图标**：`@iconify/vue`
- **部署**：静态部署（Vercel / Netlify / Cloudflare Pages 任一）

### 6.2 目录结构（建议）
```
src/
├── assets/              # 图片、字体
├── components/          # 通用组件（TopicCard, StepWizard, Toc...）
├── composables/         # useSearch, useToc, useExport
├── content/             # 法规内容（Markdown + frontmatter）
│   ├── topics/
│   │   ├── strategic-goods.md
│   │   ├── permits.md
│   │   └── ...
│   ├── updates/
│   └── library.json
├── layouts/             # DefaultLayout, TopicLayout
├── pages/               # 路由页面
├── router/
├── stores/              # Pinia
├── styles/
├── utils/               # markdown 解析、index 构建
└── main.ts
```

### 6.3 内容管理策略
- **v1**：内容存为 Markdown + frontmatter（在 `src/content/` 下），构建时由 Vite 插件（`vite-plugin-md` 或自定义）转为 JSON/组件
- **v2**：迁移到 Headless CMS（Strapi / Directus）或 Notion API，便于非技术同事编辑

### 6.4 数据模型（Topic frontmatter 示例）
```yaml
---
slug: strategic-goods
title: 战略物资管制
category: core
order: 1
tags: [SGCA, SGCL, dual-use]
summary: 介绍 SGCA 框架与战略物资清单结构
lastUpdated: 2026-03-15
sources:
  - title: Strategic Goods (Control) Act
    url: https://sso.agc.gov.sg/Act/SGCA2002
relatedTopics: [permits, sanctions]
---
```

---

## 7. UI/UX 设计原则

- **企业级稳重感**：主色建议深蓝 (#0F2C4C) + 中性灰 + 警示橙；无花哨动效
- **信息密度可控**：默认折叠次要信息，鼠标悬停/点击展开
- **可读性优先**：正文行高 1.7、最大宽度 720px、衬线字体用于法条引用
- **响应式**：桌面优先（企业用户主要在 PC 端）；移动端做基础适配
- **可访问性**：WCAG AA 对比度、键盘导航、ARIA 标签
- **语言**：中文单语版（简体中文为主）；不做英文版。所有引用的英文法规名第一次出现时附中文译名 + 英文原名（如「战略物资（管制）法 Strategic Goods (Control) Act」）

---

## 8. 内容来源策略

### 8.1 来源原则
内容**仅采集自新加坡政府官网与主流媒体公开报道**，不使用未经核实的二手解读，所有条目必须可溯源。

### 8.2 一手来源（政府官网）— 权威性最高

| 来源 | 用途 | 链接 |
| --- | --- | --- |
| Singapore Customs (新加坡海关) | SGCA 主管机关，许可申请、清单、指南 | customs.gov.sg |
| Singapore Statutes Online (SSO) | 法律原文（SGCA、SGCR 等） | sso.agc.gov.sg |
| Ministry of Trade and Industry (MTI) | 贸易政策、出口管制立场 | mti.gov.sg |
| Ministry of Foreign Affairs (MFA) | 制裁公告、UN 决议落地 | mfa.gov.sg |
| Ministry of Law (MinLaw) | 立法动态 | mlaw.gov.sg |
| Monetary Authority of Singapore (MAS) | 金融制裁、反洗钱关联指引 | mas.gov.sg |
| TradeNet / Networked Trade Platform | 申报操作说明 | ntp.gov.sg |

### 8.3 二手来源（主流媒体）— 用于动态、案例、解读

| 来源 | 语言 | 用途 |
| --- | --- | --- |
| 联合早报 (Lianhe Zaobao) | 中文 ✅ 优先 | 中文版直接引用；本地视角解读 |
| 海峡时报 (The Straits Times) | 英文 | 翻译后引用，用于政策动态 |
| 商业时报 (The Business Times) | 英文 | 企业合规、罚案报道 |
| Channel News Asia (CNA) | 英文 | 政府表态、突发监管动态 |

### 8.4 内容采集与审校流程
1. **采集**：编辑按主题定期巡检上述来源（建议每两周一次）
2. **核验**：媒体报道必须能在政府官网找到对应原始文件方可引用
3. **改写**：禁止整段照搬，做摘要 + 关键术语对照；引用原文不超过单条 200 字
4. **标注**：每条内容标记 `source`（机构名）+ `sourceUrl` + `retrievedAt`（采集日期）
5. **审校**：上线前由合规顾问/法务复核（参见 §10）

### 8.5 版权与免责
- 仅展示**摘要 + 关键要点**，不复刻全文；提供「查看原文」深链
- 媒体报道引用遵循合理使用边界（短摘 + 注明出处 + 链接回原站）
- 政府公开法规属于公共信息，可摘录但需标注 SSO 来源

### 8.6 数据模型补充（Topic frontmatter 新增字段）
```yaml
sources:
  - title: Strategic Goods (Control) Act
    publisher: Singapore Statutes Online
    url: https://sso.agc.gov.sg/Act/SGCA2002
    type: primary           # primary | secondary
    retrievedAt: 2026-04-15
  - title: 新加坡收紧战略物资出口管制
    publisher: 联合早报
    url: https://www.zaobao.com.sg/...
    type: secondary
    retrievedAt: 2026-04-10
```

---

## 9. 风险与合规

### 9.1 风险矩阵

| 风险 | 缓解措施 |
| --- | --- |
| 内容被误用为法律意见 | 全站显著免责声明；决策树结果页强提示「请咨询持牌律师」 |
| 法规更新滞后 | 每条主题展示 `lastUpdated`；建立月度审校流程 |
| 引用原文版权问题 | 仅摘要 + 链接到 SSO（Singapore Statutes Online）官方页 |
| 误导性建议 | 决策树仅给「方向性提示」，不给具体许可号建议 |

### 9.2 合规审核机制（采用「企业内部审核」模式）

不引入外部律师，由企业内部完成全部审核工作。为弥补缺少外部背书带来的风险，需配套**更强的免责声明**和**保守的决策树措辞**（详见下文）。

**角色分工**

| 角色 | 职责 | 频率 |
| --- | --- | --- |
| 内容编辑 | 撰写、改写、标注来源 | 持续 |
| 企业内部合规官 (Compliance Officer) | **一审**：内容准确性、来源核验、术语一致性 | 每篇必过 |
| 企业法务 / 资深合规负责人 | **二审**：决策树逻辑、高风险主题（制裁、Catch-All、处罚） | 每篇必过；高风险主题加倍复核 |
| 内容负责人（产品/编辑主管） | **终审 + 发布**：把关用词中立性、免责标注完整性 | 发布前 |

> 注：一审和二审不能由同一人担任，强制双人复核（four-eyes principle）。

**审核流程**

```
内容编辑撰写
   ↓
合规官一审 → 修订
   ↓
法务/合规负责人二审（高风险主题加倍复核）→ 修订
   ↓
内容负责人终审
   ↓
打 reviewStatus: approved 标记 → 发布
```

**周期性复审**
- 双周巡检：编辑 + 合规官扫描所有政府官网/媒体来源，更新有变化的主题
- 季度全审：每季由法务对**决策树**和**高风险主题**全量回看一次
- 重大变更触发：SGCA / SGCR 修订、UN 制裁名单更新时，相关主题 48 小时内重审

**风险补偿措施（因无外部律师背书）**
1. **决策树降级**：结果页只输出「可能受管制 / 建议进一步核查」三档方向性提示，**不给出具体许可类型建议**
2. **强免责声明**：每个主题页顶部 + 决策树结果页都强制展示「本平台内容由企业内部团队整理，不构成法律意见，请就具体业务咨询持牌律师或新加坡海关」
3. **来源透明**：每条结论可点击跳转到原始政府/媒体来源，让用户自行核验
4. **审计留痕**：审核记录（谁审、何时审、改了什么）必须可追溯，保存至少 5 年（与 SGCA 记录保存要求对齐）

**Frontmatter 审核字段**
```yaml
review:
  status: approved              # draft | first-reviewed | approved
  author: 编辑姓名
  firstReviewer: 合规官姓名
  firstReviewedAt: 2026-04-15
  secondReviewer: 法务/合规负责人姓名
  secondReviewedAt: 2026-04-16
  finalApprover: 内容负责人姓名
  publishedAt: 2026-04-17
```
站点上仅展示 `approved` 状态的主题；其它状态不可访问。

---

## 10. 开发里程碑（建议）

| 阶段 | 周期 | 交付 |
| --- | --- | --- |
| M1 — 脚手架 + 设计系统 | 1 周 | Vite + Vue3 + UI 组件库选型落地、配色规范、Layout |
| M2 — 主题模块 | 2 周 | 8 个主题页 + Markdown 渲染管线 + Toc |
| M3 — 检索 + 决策树 | 1.5 周 | FlexSearch 索引、StepWizard、结果页 |
| M4 — 更新/库/资源 | 1 周 | Updates Timeline、Library、Resources |
| M5 — 打磨 + 部署 | 1 周 | a11y、SEO、PDF 导出、上线 |

**总计 ≈ 6.5 周**（1 名前端 + 0.5 名内容编辑）

---

## 11. 待确认事项

> ✅ 已确认：
> - 内容来源（政府官网 + 主流媒体，详见 §8）
> - 语言（中文单语版）
> - 合规审核机制（企业内部双人复核 + 内容负责人终审，无外部律师，详见 §9.2）
> - 内部审核团队（合规官 / 法务 / 内容负责人）已就位

1. 部署域名 / 品牌归属
2. 是否需要埋点分析（如 Plausible / GA4）以了解用户行为？
3. 媒体报道引用是否需要先逐条获取版权许可（联合早报等可能有商用限制）？
4. 决策树「降级输出」的最终措辞由谁拍板（建议法务负责人确定模板文案）

---

*本设计文档为初稿，待与业务方对齐后细化各模块。*
