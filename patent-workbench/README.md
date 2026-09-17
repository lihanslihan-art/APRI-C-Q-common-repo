# patent-workbench

专利起草工作台。**方案 D,已部署并端到端跑通**(端口 3015,仅回环)。
上线前请先读「隔离」一节:容器化仍是待办,在那之前不要把端口放到回环之外。

这是提案四个方案里的 D:**不重写提示词,而是用 headless Claude Code 原样驱动上游那套技能**。
上游 `wifi_patent_skill/SKILL.md` 有 801 行起草知识,本服务一行都没有复制——
`prompts.py` 只负责交代环境、重定向输出路径、把语料检索换成 `corpus.py`
(对 [patent-corpus-web](../patent-corpus-web/) 检索服务的 CLI 封装),
以及在技能自己的人工闸门处停下来。

设计依据见 [initial_proposal.md](../patent-corpus-web/initial_proposal.md) 第 4、7 节。

---

## 两阶段加人工闸门

上游技能明确写着「等用户明确说 draft 才起草」。这个闸门在这里是真实的暂停,不是形式:

```
提交想法
   │
   ▼  阶段一(screening)
先行技术闸门(Step 0)+ 起草前分析(Step 3)
   │
   ▼
awaiting_approval ──否决──► rejected
   │
   │ 批准(可附带说明,会传给 Agent)
   ▼  阶段二(drafting)
恢复同一个 Agent 会话 → Step 4..11 → idea.md / PPTX / 交底书 / critique.md / REPORT.md
   │
   ▼
done
```

**阶段二恢复的是同一个会话 id**,不是新起一个。所以先行技术结论和起草前分析仍在上下文里,
不会被重新推导一遍——既省钱,也避免两个阶段对同一个想法给出不一致的判断。
`--resume` 的行为我实测验证过:恢复后模型能准确回忆上一阶段的内容,session id 保持不变。

状态机在 `jobs.py`,阶段执行在 `runner.py`,提示词在 `prompts.py`。

---

## 隔离

这是本服务最需要谨慎的地方,如实写清楚。

**每个任务一个运行目录**,`runs/<job_id>/`,里面:

- `.claude/skills/` — 技能的**私有副本**,43 个文件 2.2 MB。副本是关键:Agent 改不到共享的技能。
- `.claude/skills/wifi_patent_skill/references` — **符号链接**指向上游那 179 MB 只读语料。
  每个任务复制一份语料比整个服务还大,没有意义。
- `output/` — Agent 唯一被允许写入的位置,产物都在这里。
- `events.jsonl` — 原始 stream-json,完整留档。
- `idea_brief.md` — 提交的想法,所以一个运行目录能独立复现,不必查数据库。

- `corpus.py` — 先行技术检索 CLI,Agent 查语料的唯一入口(见「联调结果」一节)。

**Agent 的工具面**在 `runner.py` 的 `TOOLS_ALLOWED`:Bash 按命令收窄到
`python3`、`curl`、`mkdir`、`cp`、`mv`、`ls`、`cat`,而不是整个 Bash;文件操作走
Read/Write/Edit/Glob/Grep。`TOOLS_DENIED` 另外挡掉 git、gh、sudo、systemctl、ssh、scp、rm、chmod、pip。

**但要说清楚这个白名单值多少:它是减速带,不是沙箱。**
`python3 -c "import os; os.system(...)"` 直接穿过去,任何允许 Agent 运行解释器的白名单
都有同一个洞。真正起作用的边界只有三条:

1. **服务只绑 127.0.0.1**,没有任何远程触发的入口;
2. `--permission-prompts none`,白名单之外的一切直接拒绝,而不是挂在那里等一个没人会给的回答;
3. `--max-budget-usd`,每个阶段的硬性成本上限。

**真正的隔离是把 Agent 放进容器**,只挂载运行目录可写、语料只读、无宿主网络。
这台机器上 Docker 可用,这是本服务的下一步,在那之前**不要把端口放到回环之外**。

### 为什么不像 patent-corpus-web 那样开到公网

语料服务是只读检索,泄露凭据的后果是内容暴露。这个服务会启动能运行解释器、能写文件的
Agent 会话。一个能做到这件事的 HTTP 端点如果暴露在公网,凭据一旦泄露就等于这台机器上的
远程代码执行——而这台机器同时跑着 VPN 和另外六个服务,而且凭据走的是明文 HTTP。

所以 systemd unit 写死 `--host 127.0.0.1`。要用就开隧道:

```bash
ssh -L 3015:127.0.0.1:3015 admin@<host>
```

---

## 联调结果（已跑通）

**端到端跑通过两次**，用 `claude-haiku-4-5-20251001` 加低预算做的,`AGENT_MODEL`
换回 `claude-opus-5` 才是正式配置。

| 阶段 | 结果 |
|---|---|
| 筛查 | 20 轮,$0.2272,产出 `prior_art.md` + `analysis.md` |
| 人工闸门 | 正确停在 `awaiting_approval`,等人决策 |
| 会话恢复 | 批准后两个 init 事件的 session id **完全相同**,确认恢复而非新起 |
| 起草 | 恢复后继续产出,`output/` 下文件数递增 |

第一次联调暴露了一个严重问题,现在修好了,值得记下来。

**症状**:筛查跑完了,产物齐全,结论写得像样,但 `prior_art.md` 第 5 行自己声明
「语料库 API 不可用；基于公开文献的专业判断」——**先行技术闸门实质上空转了**,
一条语料引证都没有,还把 NPCA 误归给 802.11be(它是 802.11bn 的特性)。
Agent 是诚实的,没有伪造文档号,但这种报告看起来像证据其实不是,比不写更糟。

**四个根因**:

1. `Bash(curl *)` 只匹配**以 curl 开头**的命令。Agent 第一条是
   `echo "CORPUS_API=$CORPUS_API" && curl ...` 这种组合命令,被直接拒绝,
   它于是改用 `python3 << EOF` 包一层 —— 顺手证明了工具白名单确实是减速带不是沙箱。
2. 提示词让它自己拼 curl,依赖 shell 变量展开,和第 1 点直接冲突。
3. 两套语料覆盖范围不同,它把 `--corpus` 限定到了 `ieee_standards`,
   而 NPCA 只存在于 `wifi8_tgbn`,所以真的是 0 命中。
4. `token` 模式把每个词 AND 起来,`"load level priority beacon"` 这种查询自然 0 命中,
   提示词里没说清楚。

**修法**:加了 `corpus.py`,一个标准库写的检索 CLI,复制进每个运行目录。
它用 `python3 corpus.py ...` 调用,干净匹配白名单,把正确默认值写进代码而不是散文:
不填 `--corpus` 就搜两套、多词 token 查询主动警告并建议改 phrase、
限定错语料时提示 Wi-Fi 8 术语只在 `wifi8_tgbn`、`check` 子命令用一条已知必中的查询
自证语料可用。另外 `runner.py` 在**启动会话之前**先探一次语料,
探不通就直接让作业失败,不让它跑成一份空转的报告。

**修完的第二次联调**:Agent 先跑 `check`,然后用对了语料和 phrase 模式,
找到真实提案后还钻进去读具体页面。报告里四个引证的文档号全部在语料中真实存在:

| 文档号 | 类型 | 标题 |
|---|---|---|
| `11-24-1838-01` | proposal | Considerations on Coordinated NPCA |
| `11-24-2093-00` | proposal | NPCA Triggered by Intra-BSS TXOP |
| `11-24-0653-15` | agenda | TGbn May 2024 meeting agenda |
| `11-24-0976-13` | agenda | TGbn July 2024 meeting agenda |

这两份 NPCA 提案在任何专利数据库里都搜不到,这就是方案 B 存在的理由。

## 自动化检查

`./smoke_test.sh` 24 项,覆盖不启动 Agent 的全部路径:接口状态码、输入校验、
除 `/healthz` 外全部 401、仅回环绑定、语料服务连通性、并发上限、起草依赖是否齐全。

另外这些是单独验证过的:运行目录准备(技能副本 43 文件 2.2 MB,语料走符号链接)、
stream-json 解析(用真实录制的事件流)、产物下载的路径穿越防护(9 个探针全拦,
HTTP 层一律 404)、作业状态机。

**提交作业不在烟雾测试里**,因为那会真的启动 Agent、花钱、耗时几分钟。
要手动跑一次就把 `.env` 的 `AGENT_MODEL` 临时换成
`claude-haiku-4-5-20251001`、`BUDGET_SCREEN_USD=1`,提交一个简短想法。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/jobs` | 提交想法,`{title, idea, track}`,`track` 取 `std`/`product`/`generic` |
| GET | `/api/jobs` | 任务列表(不含想法正文) |
| GET | `/api/jobs/{id}` | 任务详情 + 产物清单 |
| GET | `/api/jobs/{id}/events` | 蒸馏后的事件,支持 `since` |
| GET | `/api/jobs/{id}/stream` | SSE 实时事件流,连接时先重放历史 |
| POST | `/api/jobs/{id}/approve` | 在闸门处批准,`{note}` 会传给 Agent |
| POST | `/api/jobs/{id}/reject` | 否决 |
| POST | `/api/jobs/{id}/cancel` | 取消,会终止 Agent 进程 |
| GET | `/api/jobs/{id}/artifacts` | 产物清单 |
| GET | `/api/jobs/{id}/artifacts/{path}` | 下载单个产物 |
| GET | `/api/slots` | 并发额度、模型、预算、语料服务连通性 |
| GET | `/healthz` | 健康检查,唯一不需要认证的路径 |

SSE 连接时会**先重放全部历史事件再跟进实时**,所以浏览器断线重连不会丢内容。
实时队列满时丢的只是实时推送,历史始终在 `events.jsonl` 里。

---

## 并发与成本

并发上限硬编码为 **2**。一个 headless 会话实测常驻 283 MB,这台机器可用内存约 1.2 GB,
第三个并发有很大概率让 OOM killer 顺手杀掉同机的其他服务。超出的任务排队,
由 `asyncio.Semaphore` 自然节流。

每阶段成本上限由 CLI 自己的 `--max-budget-usd` 强制,默认筛查 $5、起草 $20,在 `.env` 里调。
每个任务的实际花费和轮数记在作业库里,列表和详情都能看到。

服务重启时会**回收孤儿任务**:正在起草的标记失败;正在筛查且已拿到 session id 的
转入等待批准并附注说明,因为那个会话还能恢复。

---

## 部署

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt            # 服务本身
.venv/bin/pip install -r requirements-agent.txt      # Agent 要用的产物构建库

cp .env.example .env && chmod 600 .env               # 填两套凭据
cp deploy/patent-workbench.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now patent-workbench
```

`.env` 要填两套凭据:本服务自己的 Basic 认证,以及它调用语料服务所用的
`CORPUS_AUTH`(格式 `user:password`,作为环境变量传给 Agent,由 `corpus.py` 读取)。

unit 里 PATH 写死绝对路径:Agent 子进程需要 nvm 的 node 才能跑 claude CLI,
需要本服务 venv 的 python3 才能跑产物构建库,systemd 的默认 PATH 两个都没有。

`runs/` 和 `.env` 都不入 git。`runs/` 里是想法相关的内容,
上游的公私分离规则要求这类内容不进仓库。

---

## 已知限制

**硬件在环不可用。** 上游把 HIL 定为「建议但非硬性闸门」,本服务让 Agent 跳过并在产物里注明。
提示词明确禁止编造测量数据。真要做硬件验证,得接上那 2 块 Banana Pi 和 2 台鸿蒙设备。

**上游配套的公开知识库仓库未随镜像分发**,所以侦察类技能在这里跑不了。
本服务只驱动起草链路,不驱动情报侦察链路。

**Bash 白名单不是沙箱**,见「隔离」一节。

**无人值守意味着没人能回答 Agent 的追问。** 提示词要求它遇到技能中需要澄清的地方
按最合理假设继续,并把假设写进产物。所以产出的 `REPORT.md` 里那份假设清单要认真读。
