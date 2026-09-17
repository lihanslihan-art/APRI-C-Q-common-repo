# patent-corpus-web

无线标准语料全文检索服务。方案 B，已上线。

对两套语料提供毫秒级全文检索：**IEEE 802 标准**（55 份，17,837 页）与
**Wi-Fi 8 / IEEE P802.11bn（TGbn）工作组文档**（2,767 份，29,240 页）。
合计 2,822 份文档、47,077 可检索页。

为什么值得单独做成服务：标准组织的提案属于**公开披露但专利数据库不收录**。
一份 2023 年提交到 Mentor 的提案不会出现在任何专利检索结果里，这套语料是它唯一可检索的地方。
因此本服务的定位是**先行技术检索**，每条结果返回的是**首次公开日期**（r0 版本），
而不是最新修订日期 —— 后者不是先行技术的正确判定基准。

设计与选型依据见 [`initial_proposal.md`](./initial_proposal.md)。

---

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

python build_db.py                    # 建库，约 7 秒，产出 173 MB 的 corpus.db
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 3014

./smoke_test.sh                       # 21 项检查
```

浏览器打开 <http://127.0.0.1:3014/>，交互式 API 文档在 `/docs`。

`corpus.db` 不入 git，随时可由 `build_db.py` 重建。

---

## 为什么是 SQLite FTS5

上游语料自带一套 JSON 倒排索引，检索脚本每次调用都要 `json.loads` 整个 30 MB 索引文件。
在目标部署机上实测对比：

| | JSON 倒排索引 | SQLite FTS5 |
|---|---|---|
| 常驻内存 | 607 MB | **110 MB**（含 Web 服务，压测后稳定值；冷启 32 MB） |
| 单词检索 | ~900 ms | 5 ms（SQL 层） |
| 端到端 HTTP 中位延迟 | — | **21 ms**（p95 52 ms；连续压测下 25 / 110 ms） |
| 短语 / 布尔 / 前缀 | 仅短语，需全表扫 | 全部原生支持 |
| 命中总数统计 | 需全表扫 | 0 ms |
| 建库 | — | 7 秒全量 |

部署机总内存 3,499 MB，可用仅 1,209 MB，且已有一个 346 MB 的常驻服务。
把 607 MB 索引常驻内存会占掉一半可用内存，**所以 FTS5 不是优化项而是必选项**。

110 MB 这个数字是 180 次请求压测后的稳定值，涨幅来自 SQLite 的页缓存，
不是泄漏：它会在缓存上限处停住，不随请求数继续增长。冷启动是 32 MB。

---

## API

所有接口返回 JSON。OpenAPI 规范在 `/openapi.json`，便于被 Agent 自动发现。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/search` | 主检索 |
| GET | `/api/doc/{doc_id}` | 文档元数据 + 主题 + 目录 + 有文本页清单 |
| GET | `/api/doc/{doc_id}/page/{page}` | 单页全文 |
| GET | `/api/facets` | 可用筛选取值与计数 |
| GET | `/api/stats` | 语料规模与建库时间 |
| GET | `/healthz` | 健康检查 |

### `/api/search`

| 参数 | 默认 | 说明 |
|---|---|---|
| `q` | 必填 | 查询串，1–500 字符 |
| `mode` | `token` | `token` 分词后 AND；`phrase` 精确短语；`boolean` 支持 `AND OR NOT ( )`；`prefix` 前缀匹配 |
| `corpus` | 全部 | `ieee_standards` / `wifi8_tgbn` |
| `kind` | 全部 | `sfd` `pdt` `cr` `proposal` `minutes` `agenda` `base` … |
| `topic` | 全部 | 内容推导的主题标签，如 `npca` `mapc` `mlo` |
| `ballot` | 全部 | `CC50` `LB291` `LB292` `LB296` |
| `year` | 全部 | 年份 |
| `limit` / `offset` | 20 / 0 | 分页，`limit` 上限 200 |
| `snippet_tokens` | 16 | 摘要长度 |

```bash
curl 'localhost:3014/api/search?q=npca&kind=cr&ballot=LB291&limit=5'

curl -G localhost:3014/api/search \
  --data-urlencode 'q=non-primary channel access' --data-urlencode 'mode=phrase'

curl -G localhost:3014/api/search \
  --data-urlencode 'q=co-tdma AND rtwt' --data-urlencode 'mode=boolean'
```

每条结果包含 `doc_id` `title` `kind` `ballot` `year` `author` `page`
`first_disclosed` `url` `score`，以及 `snippet`（纯文本）和 `snippet_html`
（已转义、仅含 `<mark>` 高亮标签，可直接注入 DOM）。

---

## 两个实现细节，都是踩过的坑

**一，FTS5 里带连字符的词必须加引号。** `co-tdma` 会被 FTS5 解析成列引用，
报 `no such column: tdma`。所以 `build_match()` 对每个用户输入的词项一律加引号后
再交给 `MATCH`，布尔模式下只保留 `AND OR NOT ( )` 不转义。

**二，FTS5 的 `snippet()` 不转义 HTML。** 语料里真实存在
`click "UHR <MAC/PHY/Joint> conference call"` 这样的页面，直接输出会把标签注入消费方。
因此高亮用私有区哨兵字符 `U+E000` / `U+E001` 标记，服务端先 `html.escape()`
再换回 `<mark>`，保证只有 `<mark>` 能存活。烟雾测试里有一项专门扫描这个泄漏。

---

## 认证

全部接口走 HTTP Basic 认证，**唯一例外是 `/healthz`**，它只返回一个布尔值，
留开给探活用。认证做在 middleware 而不是路由依赖上，这样将来新增路径不会漏掉，
`/docs`、`/openapi.json` 和静态页面也一并覆盖。

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # 填进 AUTH_PASS
chmod 600 .env
```

`.env` 不入 git。**凭据为空时服务拒绝启动**，缺文件会是一次响亮的失败而不是一个默默敞开的端口。
只在可信内网裸跑时才设 `ALLOW_NO_AUTH=1`。

两个实现细节：用户名和密码都用 `hmac.compare_digest` 做**定长时间比较**，
且无论用户名是否匹配都比较两段，避免时序泄漏用户名是否存在；失败尝试按来源 IP 节流，
5 分钟内 10 次失败后返回 429 并带 `Retry-After`。节流触发后正确凭据也会被拒，
这是有意的锁定行为，5 分钟自动解除。

---

## 部署

| 项 | 值 |
|---|---|
| 端口 | 3014 |
| 绑定 | 0.0.0.0，经阿里云安全组对外 |
| 认证 | HTTP Basic，见上 |
| 传输 | **明文 HTTP，无 TLS** |
| 进程管理 | systemd user unit，见 `deploy/` |
| 常驻内存 | 冷启 32 MB，180 次请求后稳定在 110 MB |

```bash
cp deploy/patent-corpus-web.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now patent-corpus-web
loginctl enable-linger admin     # 让 unit 在登出后继续运行
```

unit 里所有路径都写绝对路径：本机 nvm 下的 node 是 v24 而 `/usr/bin/node` 是 v20，
systemd 的默认 PATH 找不到 nvm 的东西。同时 unit 用
`ProtectSystem=strict` + `ProtectHome=read-only`，服务对语料只有读权限。

语料路径通过 `CORPUS_ROOT` 环境变量配置，数据库位置通过 `CORPUS_DB` 配置。
**服务以只读方式打开数据库，且从不写入语料目录**，因此无法影响它所读取的上游工作区。

### 关于 TLS

当前是明文 HTTP，所以 **Basic 认证的凭据在链路上是可嗅探的**（base64 不是加密）。
这是「最省事地放到公网」的直接代价。要上 TLS 需要装 caddy 或 nginx 做反代，
但本机 443 端口被 xray 占用，反代要么换端口，要么配 xray 回落把非 VLESS 流量转给反代。

### 内容暴露提示

`/api/doc/{id}/page/{n}` 会返回 IEEE 标准的全文页面，那是受版权保护的商业出版物。
认证是这批内容与公网之间唯一的一层，**不要把凭据外发，也不要关掉认证**。

---

## 与方案 D 的关系

方案 D 是 Agent 驱动的起草工作台。它的第一道强制闸门就是先行技术检索，
现在这一步会直接调用本服务的 `/api/search`，单次从约 900 ms 降到 21 ms，
且能一次批量查多个词而不必反复付进程启动代价。`/openapi.json` 让 Agent 可以自动发现接口。

**本服务全程只读，天然可并发**，这一点和方案 D 形成对比 —— 后者的所有流程都假设
单会话独占文件系统，做多用户必须做会话隔离。详见提案第 4.4 节。

---

## 重建语料库

上游语料更新后：

```bash
python build_db.py                        # 两套语料全量重建
python build_db.py --corpus wifi8_tgbn    # 只重建一套
systemctl --user restart patent-corpus-web
```

`build_db.py` 先写 `corpus.db.tmp` 再原子替换，中途失败不会留下半成品数据库。
