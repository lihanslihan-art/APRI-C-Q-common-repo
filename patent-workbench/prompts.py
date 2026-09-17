#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The two phase prompts that drive the upstream drafting skill.

This module deliberately holds no drafting knowledge. The skill under
.claude/skills/ is 801 lines of it, and duplicating any of that here would
create a second copy to keep in sync. These prompts only:

  - point the agent at the skill and tell it to follow the skill's own steps,
  - redirect the skill's hardcoded output paths into this run's output/ dir,
  - redirect the skill's prior-art corpus search onto corpus.py, the CLI
    wrapper around the plan B search service, and spell out the two traps
    the first integration run fell into (wrong corpus filter, token-mode AND),
  - state the sandbox rules, and
  - enforce the stop at the skill's own human gate.

Everything about what a good draft looks like stays in the skill.
"""
from __future__ import annotations

# The skill's frontmatter name, used to invoke it.
SKILL_NAME = "wifi-patent-idea-slides"

_SANDBOX = """
## 运行环境规则（必须遵守）

1. **只能写入 `output/`**（相对当前工作目录）。这是本次任务的唯一输出位置。
   技能文档里提到的 `patent_pipeline/patent_drafts/<idea>/` 和
   `/mnt/user-data/outputs/` 在这里都不存在，**一律改写为 `output/`**。
2. **`.claude/skills/` 是只读参考**。不要修改任何 SKILL.md、state.json 或脚本。
   本次运行的技能副本是一次性的，改了也不会留存，只会让你的产物和技能不一致。
3. **不要执行 git 操作**，不要 commit、不要 push、不要改任何仓库状态。
4. `python3` 已指向一个装好 `python-pptx`、`python-docx`、`matplotlib`、`PyMuPDF`
   的虚拟环境，直接用即可，不要尝试 pip install。
5. **硬件在环（HIL）设备不可用**。技能把 HIL 定为「建议但非硬性闸门」，
   所以跳过它，并在产物里注明未做硬件验证。不要编造测量数据。
6. 无人值守运行，没有人能回答你的追问。遇到技能要求澄清的地方，
   **按最合理的假设继续，并把该假设明确写进产物**，不要停下来等回答。
"""

_CORPUS_API = """
## 先行技术语料检索（只用 `corpus.py`，不要自己拼 curl）

技能 Step 1 让你跑 `references/*/scripts/search.py`。**这里改用当前目录下的
`corpus.py`**，背后是同一批语料的检索服务：IEEE 802 标准 55 份加
Wi-Fi 8 / TGbn 工作组文档 2767 份，共 47077 页，单次查询约 20 毫秒。

**第一步必须是自检。** 先跑这条，确认语料真的在答话：

```bash
python3 corpus.py check
```

`USABLE: True` 才能继续。用法：

```bash
python3 corpus.py search npca --limit 10
python3 corpus.py search "non-primary channel access" --mode phrase
python3 corpus.py search npca --kind cr --ballot LB291
python3 corpus.py doc 11-24-0209-19          # 元数据 + 主题 + 目录
python3 corpus.py page 11-24-0209-19 12      # 单页全文
python3 corpus.py facets                     # 可用的 kind / topic / ballot / year
```

### 三个容易踩的坑，先看清楚再查

**一，两套语料覆盖范围不同，选错就是 0 命中。**

| 语料 | 内容 |
|---|---|
| `ieee_standards` | 已发布的 IEEE 802 标准，Wi-Fi 7 及更早 |
| `wifi8_tgbn` | Wi-Fi 8 / 802.11bn 工作组的公开记录 |

**NPCA、MAPC、Co-TDMA、Co-SR、Co-BF、DSO、DBE、ELR、DRU、UEQM 这些 Wi-Fi 8 术语
只存在于 `wifi8_tgbn`**，因为对应标准还没发布。`--corpus` 不填就同时搜两套，
**默认就不要填**，除非你明确只想查已发布标准。

**二，`token` 模式把每个词 AND 起来。** 所以 `search "load level priority beacon"`
是找同时含这四个词的页面，很容易 0 命中。查一个词组要用 `--mode phrase`。
中英混排的查询串几乎一定是 0 命中，分开查。

**三,`first_disclosed` 是首次公开日期(r0 版本),不是最新修订日期。**
判定先行技术只能用前者。引用时写工作组文档号,`corpus.py` 会连原文链接一起给你。

### 一条硬规则

**如果语料不可用,或者某个方向确实检索不到东西,就如实说检索不到,
绝对不要用你自己记忆里的标准知识去补位。** 记忆里的东西无法核对、日期常错、
条款号常错,冒充检索结果写进先行技术报告比不写更糟——它看起来像证据,其实不是。
这套语料存在的唯一理由就是:标准组织的提案属于公开披露但专利数据库不收录,
你记不住它们,只能查。

技能要求「任何 802.11bn 时代的主张都必须先查 SFD、再查 CR 文档」,这条继续遵守,
只是换成用 `corpus.py` 查。
"""


def screen_prompt(title: str, idea: str, track: str) -> str:
    """Phase 1: the skill's mandatory prior-art gate plus pre-drafting analysis.

    Stops before drafting, which is the skill's own rule.
    """
    track_note = {
        "std": "**WiFi 标准演进型**：走 MAC 路线，关注 IE、帧、字段、关联前/时/后生命周期。",
        "product": "**WiFi 产品体验型**：走交互路线，关注实体、流程、UI 状态。",
        "generic": "**非 WiFi 产品型**：走产品/UX 路线，底层技术不是 WiFi。"
                   "注意这超出技能声明的 WiFi-only 范围，在产物里说明这一点。",
    }.get(track, "")

    return f"""你要处理一个专利 IDEA 的**筛查阶段**。

先读技能 `.claude/skills/wifi_patent_skill/SKILL.md`（frontmatter 名称
`{SKILL_NAME}`），按它自己的流程做事。技能怎么说就怎么做，本提示只负责
交代环境和边界。

## 输入

**工作标题**：{title}

**专利类型**：{track_note}

**想法描述**：

{idea}

{_SANDBOX}
{_CORPUS_API}

## 本阶段要做什么

只做技能的 **Step 0（先行技术闸门，强制）** 和 **Step 3（起草前分析）**，
外加 Step 1 需要的参考阅读。**做完就停，不要起草。**

技能里明确写了「等用户明确说 draft 才起草」，那个闸门在这里是真实的暂停：
筛查结果会交给人看，人点同意之后你才会被唤醒继续。

具体产出两个文件：

1. **`output/prior_art.md`** — 先行技术筛查报告。用 `corpus.py` 检索，
   报告开头写明 `corpus.py check` 的结果和你实际跑过的查询，
   按技能 Step 0 的要求给出结论：`file-as-is` / `narrow-claims` /
   `major-reframe` / `abandon` 之一。每条命中要有工作组文档号、
   首次公开日期、以及技能要求的那行 `Action:`（说明独立权利要求必须加入
   哪些要素才能绕开该引证）。
2. **`output/analysis.md`** — 技能 Step 3 的起草前分析，七个小节都要有：
   场景复述、真实技术痛点（换算成客观的 MAC 层代价）、层次分析（应用/传输/
   网络/LLC/MAC/PHY 各自为什么不行）、为什么必须在 MAC 层、一句话核心发明、
   逐条列出引入的协议变更、以及实施例二的交互阶段规划。

最后用**一段不超过 200 字的中文**收尾，直接说三件事：筛查结论是什么、
最大的新颖性风险在哪、以及建议起草还是放弃。这段话会原样显示给决策的人看，
所以要能独立读懂。

如果筛查结论是 `abandon`，明确说出来并给出理由，不要为了推进而软化结论。
"""


def draft_prompt(decision_note: str) -> str:
    """Phase 2: resume the same session after a human approved the gate."""
    note = f"\n\n审批人附带的说明：{decision_note}\n" if decision_note.strip() else "\n"

    return f"""人已经看过你的筛查报告，**批准继续起草**。{note}
现在按技能 `.claude/skills/wifi_patent_skill/SKILL.md` 的 **Step 4 到 Step 11**
走完整流程。你上一阶段的先行技术报告和起草前分析都还在上下文里，直接用，不要重做。

沙箱规则不变：**只写 `output/`**，不改 `.claude/skills/`，不执行 git 操作，
HIL 硬件不可用所以跳过并注明，遇到需要澄清的地方按最合理假设继续并写明假设。

## 必须交付

按技能 Step 4 的目录结构，在 `output/` 下产出：

- **`output/idea.md`** — 技能 Step 5 的真相来源，一节对一页幻灯片。
- **`output/build_pptx.py`** + **`output/IDEA - <English title>.pptx`** —
  英文 IDEA 演示文稿。按技能 Step 8 和 `references/pptx_conventions.md` 来，
  图形必须是原生 PowerPoint 形状，不要 SVG 或 PNG。
  记得把 `scripts/pptx_helpers.py` 复制到 `output/` 再 import。
- **`output/build_jiaodishu.py`** + **`output/交底书_<slug>.docx`** —
  中文交底书，按技能 Step 10，含图、术语解释和结尾的缩略语对照表。
- **`output/fig/`** — 交底书用到的图。

产出后**必须跑技能自带的校验**：

```bash
python3 .claude/skills/wifi_patent_skill/scripts/verify_pptx.py "output/IDEA - <title>.pptx"
```

校验不通过就修到通过，把最终结果写进下面的报告。

## Step 11 是强制的

技能规定每次重大起草改动后都要做**对抗性批判加应答循环**。这一步不能跳。
把批判和应答写进 **`output/critique.md`**：至少五条针对独立权利要求和
实施例的实质攻击，每条给出你的应答，以及应答导致的具体修改。
如果某条攻击你答不上来，如实写「未解决」并说明影响，不要编造应答。

最后写 **`output/REPORT.md`**：产物清单、每个文件一句话说明、
`verify_pptx.py` 的结果、跳过 HIL 的说明、你做过的全部假设、
以及 `critique.md` 里未解决的问题。这份报告是交付物的入口。

收尾再用一段不超过 200 字的中文说明交付了什么、哪里还弱。
"""
