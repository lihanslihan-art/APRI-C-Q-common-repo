# patent-workbench

专利起草工作台。**方案 D,已部署并端到端跑通,公网可访问**。
浏览器直接输 `47.250.10.235`,入口页上点解锁链接即可,**不需要密码**。
应用本身只绑 127.0.0.1:3015,经 Caddy 做 TLS 反向代理。见「公网访问」一节。

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

### 真正起作用的那一层:内核级文件系统限制

工具白名单挡不住 `python3 -c`,所以真正的边界是**内核拒绝写入**。
本服务是**系统级 systemd unit**(`User=admin`),整个文件系统只读,
只挖三个可写洞:

```
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=<本服务目录>          run 目录、作业库、缓存
ReadWritePaths=/home/admin/.claude   claude CLI 的会话状态
ReadWritePaths=/home/admin/.claude.json
```

**实测结果**(10 项探针):`~/.ssh`、`~/.bashrc`、`ai_patent_experiments`、
`patent-corpus-web`、`sg-compliance`、`/etc`、`/usr/local/bin` 全部只读;
本服务目录和 `~/.claude` 可写;上游语料仍可读。
被攻陷的 Agent 仍能读这个用户的文件、仍能访问网络,但**改不了自己运行目录以外的任何东西**。

### 为什么必须是系统级 unit——这一点差点漏掉

本机其他服务都是用户级 unit,这个服务最初也是。**但用户级 unit 里上面那套沙箱静默失效。**
这台机器是 Ubuntu 24.04,`kernel.apparmor_restrict_unprivileged_userns=1`,
用户级 service manager 建不出这些指令需要的挂载命名空间。

诡异的是它只是部分失效:`ProtectSystem=strict` 看起来生效了(挡住了 `/etc` 和 `/usr`),
而 `ProtectHome`、`ReadOnlyPaths`、`InaccessiblePaths` 全是空操作——
`~/.ssh`、`~/.bashrc` 和每个同级项目都照样可写。**只看有没有报错会以为配好了。**
改成系统级 unit 加 `User=admin`,同样的指令由内核强制执行。

如果你要加新的沙箱指令,**用探针实测,不要假设**:

```bash
sudo systemd-run --quiet --wait --pipe -p User=admin \
  -p ProtectSystem=strict -p ProtectHome=read-only \
  -p ReadWritePaths=<本目录> /bin/bash -c 'echo x > /home/admin/.bashrc && echo 可写 || echo 只读'
```

### 缓存目录必须重定向

matplotlib 默认往 `~/.config/matplotlib` 写字体缓存,`~/.cache` 同理,
沙箱下这两处只读,交底书插图会在最不该失败的时候失败。unit 里把
`MPLCONFIGDIR`、`XDG_CACHE_HOME`、`XDG_CONFIG_HOME` 全部指到本服务目录下的
`.cache/`,并已实测沙箱内 matplotlib 能正常出图。

### 仍未做到的

**Agent 能读这个用户的全部文件,也能自由访问网络。** 写入被限死了,读取和外联没有。
要把这两样也管住得上容器或网络命名空间,那是下一步。

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

## 公网访问

**不需要输用户名密码。** 浏览器打开一次解锁链接,之后永久免登录:

```
https://47.250.10.235:5000/unlock/<ACCESS_TOKEN>
```

完整链接由 `deploy/render_caddyfile.sh` 在结尾打印,`ACCESS_TOKEN` 在 `.env` 里。
`http://47.250.10.235/` 的入口页上也有这个链接,从那里点最省事。
自签证书会提示一次,点「继续前往」。

解锁之后直接访问 `https://47.250.10.235:5000/` 就进去了。
换浏览器、换设备或清了 Cookie,再点一次解锁链接即可。

| 服务 | 访问方式 |
|---|---|
| 起草工作台 | 解锁链接,之后免密码 |
| 语料检索 | `https://47.250.10.235:8080/`,仍用 Basic 认证,凭据在 `patent-corpus-web/.env` |

### 为什么是解锁链接,不是直接关掉认证

浏览器的 Basic 认证弹框实际上挡住了人:访问日志显示某天**所有请求都没带认证头、全部 401**,
UI 根本进不去。所以密码这一关确实该去掉。

但这个端点不能敞开。它会启动能运行解释器、能写文件、能访问网络的 Agent 会话,
而这台机器同时跑着 VPN 和另外十个服务。同一个端口三天内记录了
**66 个不同来源 IP 探测 259 种路径**——`/.git/config`、`/client/.env`、`/backup/.env`、
`/.env.dev`、`/metrics`、`/mcp`、`/sse`,全是在找这类暴露。无认证的话,
它们任何一个都能 POST `/api/jobs` 起一个 Agent。

所以:**不用打字,但仍然关着。**

1. 打开解锁链接一次,Caddy 设一个一年期 Cookie 并把你送进应用。
2. 之后每次访问都带着这个 Cookie,Caddy 认出来后**自己注入 Basic 凭据**给上游,
   应用照常逐请求认证,而浏览器永远不弹框。
3. 没有 Cookie 的请求返回 **404 而不是 401**,扫描器连「这里有东西」都探不出来。

应用自己的认证**故意保留**:万一这套 Cookie 逻辑哪天破了,应用仍然要求凭据,
不会直接敞开。

想换成别的方式也容易。**IP 白名单**是更强的一道,Caddy 里加
`@allowed remote_ip <你的IP>` 即可,前提是出口 IP 固定。
**真的要完全敞开**就在 `.env` 里设 `ALLOW_NO_AUTH=1` 并把模板里的
`@unlocked` 判断去掉——看过上面那份扫描日志再决定。

### 配置是渲染出来的,不是直接编辑

渲染后的配置里有解锁 token 和上游凭据两个秘密,所以**只有模板入 git**:

```bash
sudo ./deploy/render_caddyfile.sh
```

它读 `.env`,填好 `deploy/Caddyfile.template` 和 `deploy/landing.html` 里的占位符,
写到 `/etc/caddy/Caddyfile`(权限 640 root:caddy)和 `/etc/caddy/landing/index.html`,
校验后重启 caddy,最后把完整解锁链接打印出来。

**是 restart 不是 reload。** `admin off` 关掉了 Caddy 在 localhost:2019 的管理接口,
而 `systemctl reload caddy` 正是往那个接口 POST 新配置,所以 reload 会以
"connection refused" 失败而 `caddy validate` 却通过。

**轮换 token**:改 `.env` 里的 `ACCESS_TOKEN`,重跑渲染脚本。旧链接和旧 Cookie 立即失效。

### 端口布局

443 用不了,被 xray(VPN)占着。安全组逐个端口探过,只放行 **80、5000、8080**
(3001、3016、3020、7000、8000、8081、8082、8090、8443、8888、9090、10000 全部超时)。

| 端口 | 协议 | 内容 |
|---|---|---|
| 80 | 明文 HTTP | 入口页(只有链接,不涉及凭据) |
| 5000 | HTTPS | 起草工作台 |
| 8080 | HTTPS | 语料检索 |
| 8443 | HTTPS | 工作台备用,安全组放行后可用 |

协议错配有两个对称的报错,都踩过:用 `http://` 打 TLS 端口得到
`Client sent an HTTP request to an HTTPS server`;用 `https://` 打明文端口
Chrome 显示 `This site can't provide a secure connection`。
一个端口只能二选一,所以**从入口页点链接,不要手输端口**。

**两个应用都只绑回环**,Caddy 是唯一的公网入口。

### 证书有个必须守的上限

**Chrome 拒绝有效期超过 398 天的证书**,报 `ERR_CERT_VALIDITY_TOO_LONG`,
而且这条**不能点「继续前往」绕过**——地址输对了也进不去,而 curl 完全正常,极易误判。
重新签发务必 `-days 397` 或更短:

```bash
sudo openssl req -x509 -newkey rsa:2048 -nodes -days 397 \
  -keyout /etc/caddy/certs/workbench.key -out /etc/caddy/certs/workbench.crt \
  -subj "/CN=47.250.10.235" \
  -addext "subjectAltName=IP:47.250.10.235,DNS:localhost,IP:127.0.0.1" \
  -addext "basicConstraints=CA:FALSE" -addext "keyUsage=digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth"
sudo systemctl restart caddy
```

配置里**故意没有 HSTS**:自签证书下 HSTS 会让浏览器不再允许点过证书警告,把所有人锁在外面。

**指任意域名到这个 IP 就能换真证书**,也免掉 398 天这个手工负担。
80 端口已放行且在服务入口页,ACME HTTP-01 可用。

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
# SYSTEM unit, not --user: the sandbox is a no-op in a user unit on this
# host (see the isolation section).
sudo cp deploy/patent-workbench.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now patent-workbench

# TLS reverse proxy for public access
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

日志用 `sudo journalctl -u patent-workbench -f`(系统级,不是 `--user`)。

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

**Bash 白名单不是沙箱**,见「隔离」一节。真正的边界是内核级写入限制,
但 Agent 的**读取和外联仍不受限**。

**自签证书不认证服务器身份。** 通道是加密的,凭据不会被嗅探,
但链路上的攻击者理论上仍可 MITM。指一个域名过来就能换真证书。

**无人值守意味着没人能回答 Agent 的追问。** 提示词要求它遇到技能中需要澄清的地方
按最合理假设继续,并把假设写进产物。所以产出的 `REPORT.md` 里那份假设清单要认真读。
