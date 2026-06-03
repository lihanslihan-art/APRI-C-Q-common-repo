# SG Compliance Hub

新加坡合规信息聚合 POC —— 出口管制、商业秘密保护、合法用工 + 新闻聚合 + AI 助手。

> 仅作信息聚合与学习用途，不构成法律意见。

## Phases

- **Phase 1 ✅** — 3 个静态合规模块、首页布局、中英双语路由、顶部导航与语言切换。
- **Phase 2** — 新闻聚合：RSS 订阅 + 必要的 HTML 抓取，定时任务，列表/详情页。来源候选：MAS、MOM、Singapore Customs、Singapore Law Watch。
- **Phase 3** — AI 助手：DeepSeek API + 对已有合规内容做 RAG，自然语言问答。
- **Phase 4** — 搜索、收藏、全站多语言切换打磨、部署。

## Stack

- Next.js 16 (App Router, Turbopack)
- React 19, TypeScript, Tailwind CSS v4
- i18n: 手动 `[locale]` 子路径 + `proxy.ts` 做 `accept-language` 检测和默认重定向（Next.js 16 用 `proxy` 替代 `middleware`）
- 词典：`dictionaries/{en,zh}.json` + 服务端 `getDictionary()` 加载

## Project structure

```
app/
  [locale]/
    layout.tsx              # 根 layout（html/body/Nav/Footer）
    page.tsx                # 首页（hero + 模块卡 + News/Chat 占位）
    export-control/page.tsx
    trade-secrets/page.tsx
    employment/page.tsx
  globals.css
components/
  Nav.tsx                   # 顶部导航 + 语言切换
  LanguageSwitcher.tsx      # 客户端组件：保持当前路径切换语言
  Footer.tsx
  ModuleCard.tsx
  ModulePage.tsx            # 模块详情页通用模板
dictionaries/
  en.json
  zh.json
lib/
  i18n-config.ts            # locale 配置
  dictionary.ts             # server-only 字典加载
proxy.ts                    # locale 检测 + 重定向（原 middleware）
content/                    # Phase 2 抓取内容存放
```

## Run

```bash
npm install
npm run dev          # http://localhost:3000 → 重定向到 /en 或 /zh
npm run build        # 生成 8 个静态页面（4 路由 × 2 语言）
npm start
```

## Conventions / 注意事项

- 本项目使用 Next.js 16，部分 API 与训练数据不同：
  - `middleware.ts` → `proxy.ts`，导出函数名 `proxy`
  - `layout` / `page` 的 `params` 是 `Promise<...>`，需 `await`
- 修改字典 JSON 时注意：中文内容中如出现 ASCII `"`，需用 `\"` 转义。

## 内容免责

本仓库的合规条文摘要基于公开法规整理（截至 2026 年 6 月初），可能存在滞后或错漏。具体合规事项请以新加坡法定机构发布的最新文本为准，并咨询合资格的本地执业律师。
