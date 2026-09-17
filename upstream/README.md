# upstream/

外部代码的挂载点。这里的东西**不是本仓库自己的项目**，是通过 git submodule 指向别处的镜像。

## `ai_patent_experiments`

上游是一个 Claude Code Agent 工作区，做无线通信研究到专利起草的流水线。
`patent-corpus-web/` 的检索服务读的就是它里面的两套标准语料。

指向 → `lihanslihan-art/ai_patent_experiments_mirror`（**private**）

### 为什么是私有 submodule 而不是直接放在本仓库里

| 项 | 值 |
|---|---|
| 本仓库 | PUBLIC |
| 上游原仓库 | PRIVATE，属 ntutangyun，我方为 collaborator |
| 上游 LICENSE | 无 |
| 含 IEEE 标准抽取全文 | 48 MB，55 份标准 |

上游没有 LICENSE，我方没有再分发的权利；而且里面 48 MB 是 IEEE 标准的抽取全文，
那是 IEEE 在售的商业出版物。把它放进一个公开仓库等于代替原作者公开发布他的私有仓库，
并且构成版权暴露。所以内容只进一个私有镜像仓库，公开仓库这边只留一个指针。

**镜像必须保持 private。** 把它翻成公开会直接产生上面那两个问题，
建仓时的 description 里也写了这条约束。

上游作者在 2026-07-20 和 2026-09-14 做过两次 git 历史清洗，专门清掉与具体专利想法
相关的内容。公私分离是他明确在守的线，镜像沿用同一条线。

### 取出内容

本仓库是公开的，但这个 submodule 指向私有仓库，所以**匿名 clone 会在这一步失败（403）**，
这是预期行为。有权限的人这样取：

```bash
git submodule update --init upstream/ai_patent_experiments
```

默认**不检出**。这台部署机上另有一份工作用的 clone 在 `~/ai_patent_experiments`，
带着 `origin` 指向上游原仓库以便拉取更新，检索服务通过 `CORPUS_ROOT` 读那一份。
在同一台机器上再检出一份 223 MB 的相同内容没有意义，所以仓库里只登记指针。

### 同步镜像

镜像不会自动跟随上游。在那份工作 clone 里：

```bash
cd ~/ai_patent_experiments
git pull origin main                      # 取上游更新
git push mirror main                      # 推到私有镜像
```

然后回本仓库更新指针：

```bash
cd ~/APRI-C-Q-common-repo
git update-index --add --cacheinfo 160000,$(git -C ~/ai_patent_experiments rev-parse main),upstream/ai_patent_experiments
git commit -m "upstream: advance the mirror pointer"
```

上游语料变了之后记得重建检索库：

```bash
python patent-corpus-web/build_db.py
systemctl --user restart patent-corpus-web
```

### 嵌套 submodule

上游自己还有一个 submodule：`.claude/skills/harmonyos-app-dev` →
`ntutangyun/harmony_next_dev_skill`。镜像只带了那个 gitlink（`4c11528`），没有内容，
取它同样需要对那个仓库的访问权。
