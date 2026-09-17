# patent-workbench

专利起草工作台。**方案 D,代码完成,默认未启用**,原因见下面「未验证的部分」和「隔离」两节。

这是提案四个方案里的 D:**不重写提示词,而是用 headless Claude Code 原样驱动上游那套技能**。
上游 `wifi_patent_skill/SKILL.md` 有 801 行起草知识,本服务一行都没有复制——
`prompts.py` 只负责交代环境、重定向输出路径、把语料检索换成
[patent-corpus-web](../patent-corpus-web/) 的 HTTP API,以及在技能自己的人工闸门处停下来。

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

## 未验证的部分

**Agent 实际启动那条路径没有跑通过端到端测试。** 这是本服务当前最大的未知。

已验证(`smoke_test.sh` 加针对性单元检查):

| 项 | 结果 |
|---|---|
| 运行目录准备 | 技能副本 43 文件 2.2 MB,语料符号链接可解析,SKILL.md 和 catalog.json 均可读 |
| stream-json 解析 | 用真实录制的事件流验证,5 条原始事件正确蒸馏出 init/thinking/text/result |
| `--resume` 会话连续性 | 实测通过,恢复后上下文保留,session id 不变 |
| 产物下载的路径穿越防护 | 9 个探针,`../`、绝对路径、`%2f` 编码全部拦住,HTTP 层一律 404 |
| 作业状态机 | 状态流转、成本累加、时间戳、产物列举 |
| 认证 | 除 `/healthz` 外全部 401,错误密码拒绝,失败节流 |
| 仅回环绑定 | 无 0.0.0.0 监听 |
| 起草依赖 | python-pptx / python-docx / matplotlib / PyMuPDF 均就位 |

**未验证**:提交一个真实想法、Agent 完整跑完筛查、命中闸门、批准后恢复会话并产出
PPTX 和交底书。开发过程中试图做这次联调时,本机的自动策略连续三次拒绝了
「创建不安全的 Agent」这类操作——包括写 unit、提交任务、以及重启服务跑烟雾测试。
**这个拒绝是对的**,不是误判:当时的配置确实是一个可远程触发、带 shell 的自主 Agent。
收窄工具面和改成回环绑定就是这几次拒绝的直接结果。

要做这次联调,需要人明确授权。建议顺序:

1. 先读完上面「隔离」一节,决定是否先上容器。
2. `systemctl --user enable --now patent-workbench`
3. `./smoke_test.sh` 应当全绿。
4. 用便宜模型和低预算先打通一遍:把 `.env` 里 `AGENT_MODEL` 临时改成
   `claude-haiku-4-5-20251001`、`BUDGET_SCREEN_USD=1`,提交一个简短想法,
   在 UI 里看事件流是否正常推进到 `awaiting_approval`。
5. 通了之后再换回 `claude-opus-5` 跑真实起草。

---

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
`CORPUS_AUTH`(格式 `user:password`,会作为环境变量传给 Agent,让它用 curl 查语料)。

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
