# MetaMAVS 总体设计指南 (Guide Line)

> 本文档讲清楚三件事:
> 1. MetaMAVS 是什么、为什么这样设计;
> 2. 总共有 **4 个开发阶段 (Phase)**,每个阶段做什么、当前进度到哪;
> 3. 技术框架如何分层、各个文件/库各自扮演什么角色。
>
> 配合阅读:`README.md`(安装与使用)、`CLAUDE.md`(给 AI 协作者的规格说明)。

---

## 1. 项目一句话定位

**MetaMAVS = Metagenomic Multi-Agent Virus Surveillance System**
一个基于 **LangGraph** 的、有状态的**多智能体工作流系统**,用于从**废水 / 环境 / 临床宏基因组测序数据**中做病毒监测:质控 → 去宿主 → 病毒检测 → 分类 → 丰度趋势 → 新型病毒筛查 → 风险评估 → 人工审核 → 自动报告。

核心定位三个关键词:
- **研究级 (research-grade)**:科学审慎,不夸大弱信号。
- **多智能体 (multi-agent)**:不是一段顺序脚本,而是 LangGraph 状态机。
- **可演进 (LLM-ready)**:第一版纯确定性,未来可在节点内接入 LLM 推理。

---

## 2. 核心设计哲学 (为什么这么设计)

### 2.1 用 LangGraph 状态机,而不是顺序脚本
项目**强制要求**核心流程表达为 LangGraph `StateGraph`。原因:

- **条件路由**:高风险/新型候选/QC 失败时,流程要会"拐弯"去人工审核,而不是死板地直走。
- **错误分流**:任何节点出致命错误能转到 `error_handler`,而不是整体崩溃。
- **人在回路 (HITL)**:在关键决策点暂停,交给人拍板。
- **检查点 (checkpoint)**:可恢复、可追溯。
- **可测试性**:每个节点是独立纯函数,能单独测。

### 2.2 一个共享状态贯穿全程
所有数据放在一个 `MetaMAVSState`(TypedDict)里流动。每个节点接收完整 state、只返回**局部更新**(partial dict),由 LangGraph 合并。
其中 `warnings` / `errors` / `execution_log` 用 `Annotated[list, operator.add]` **累加器(reducer)**,所以每个节点只需返回"新增的几条",框架自动追加,不会互相覆盖。

### 2.3 框架依赖收口到一个文件
只有 `graph.py` 直接 import LangGraph。16 个 agent 和路由都是普通 Python 函数 → 不依赖框架即可测试,未来升级/替换框架代价最小。

### 2.4 关注点分层
- **编排层**(框架):LangGraph,决定"流程怎么走"。
- **节点层**(业务):16 个 agent,各做一件(分析或远程/IO)。
- **工具层**(基础设施):logging / 文件 / 命令构造 / 分类学 / 报告渲染。
- **数据校验层**(工具库):pydantic 只负责"配置和清单合不合法",**不是**编排框架。

### 2.5 科学审慎是硬约束
报告用"检测到的序列信号"而非"确诊感染";噬菌体与人类病原体分开报告;低读数、低复杂度、可能污染都要标注;高风险检测必须建议确认性检测。这条贯穿 `taxonomy` / `risk` / `report` 三个节点。

---

## 3. 总体有几个 Phase?—— 共 4 个阶段

MetaMAVS 采用**渐进式交付**:先跑通骨架,再逐步加真实能力。**总共 4 个 Phase**:

| Phase | 名称 | 目标 | 是否需要外部工具 | 是否需要 LLM API Key | 当前状态 |
|---|---|---|---|---|---|
| **Phase 1** | 最小可运行原型 | 确定性、本地、dry-run 跑通整条 LangGraph 流程,出报告+测试 | ❌ 不需要 | ❌ 不需要 | ✅ **已完成** |
| **Phase 2** | 真实命令执行 | 把 dry-run 生成的命令真正跑起来,加工具检查、校验、恢复、SLURM | ⚠️ 需要部分工具 | ❌ 不需要 | ✅ **已完成** |
| **Phase 3** | 生信工具扩展(混合 HPC) | 本地控制端提交 SLURM 作业到远程 HPC,下载结果,本地解析 | ✅ 需要(在 HPC 上) | ❌ 不需要 | ✅ **已完成(v1)** |
| **Phase 4** | 智能解释 | 可选 LLM(Claude)生成监测叙事;确定性风险评估仍为权威 | ✅ 需要 | ✅ 需要(可选) | ✅ **已完成** |

下面逐个展开。

### Phase 1 — 最小可运行原型 ✅(已完成)
**做了什么**
- 完整项目骨架 + YAML 配置加载 + 样本清单校验
- `MetaMAVSState` 状态定义 + LangGraph 图构建/编译
- 全部 12 个 Phase-1 节点的 dry-run 逻辑 + 命令生成
- 中间产物落盘(CSV/JSON)+ Markdown/HTML 报告
- CLI:`metamavs run --dry-run`、`metamavs graph`、`validate`、`slurm`
- 37 个 pytest 测试全绿

**关键特征**:不执行任何外部命令、不连网、不需要数据库、不需要 root、不需要 API key。dry-run 模式下用**确定性合成数据**让整条流程(含高风险升级、噬菌体标记、新型候选、人工审核分支)全部跑到。

**完成判定 (Definition of Done)** —— 全部满足:
- `metamavs run --config configs/example_config.yaml --dry-run` 成功运行
- LangGraph 图能编译;节点按序执行;条件审核路由生效
- 中间文件生成;最终 Markdown 报告生成
- config/state/graph/routing/manifest 测试通过;README 完整

### Phase 2 — 真实命令执行 ✅(已完成)
在 Phase 1 之上扩展,**未改动图的接线**:
- 基于 subprocess 的**真实命令执行** + 重试循环(`CommandRunner.run` + `utils/execution.py`)
- **工具可用性检查**(`shutil.which`)+ 新增 `metamavs tools` 命令
- **退出码校验** + **警告后继续**的恢复策略;可配置 `execution.retries`
- **输出文件校验**(执行后检查预期产物是否生成)
- **优雅回退**:所需工具缺失时,该步骤记警告并回退到合成数据,流水线仍能跑完
- 每步执行日志(`logs/exec_<step>.log`)+ `execution_reports` 状态累加器
- **SLURM 脚本生成**,由 config 的 `slurm:` 段驱动(`workflows/slurm_workflow.py`)
- 新增 13 个测试(共 50 个全绿);dry-run 行为完全保留

### Phase 3 — 生信工具扩展(混合 HPC)✅(v1 已完成)
采用**本地控制 + HPC 执行 + 结果回传**的混合架构(详见 `PHASE3_DESIGN.md`)。
MetaMAVS 主体留在本地;只有自包含的 SLURM 脚本 + 输入跨到集群;结果下载回本地解析。
- `metamavs/remote/`:`RemoteBackend` 抽象(`SSHBackend` 真实、`MockBackend` 本地测试)、
  `slurm.py`(脚本生成、`sacct` 解析、依赖 DAG、轮询)、`job_ledger.py`(可恢复 jobs.json)、`jobgen.py`。
- 新增 3 个 agent:`remote_execution`(暂存→sbatch DAG→监控)、`result_sync`(下载+完整性)、
  `tool_output_parser`(原始输出→标准化表)。
- `metamavs/parsers/`:FastQC、samtools flagstat、Kraken2、Bracken、DIAMOND、CheckV——
  防御式解析器,产出供现有 taxonomy/abundance/risk agent 使用的表。
- 新增 `execution.mode: hpc` + `hpc:` 配置;`input.remote_data`(数据已在集群);
  `mode_router` 选择本地 vs 远程,**不改动 Phase 1/2**。
- 新增 17 个测试,含用 `MockBackend` + fixtures 的完整 hpc 模式集成测试(无需真集群)。

**真集群加固(UGA GACRC Sapelo2):**
- SSH ControlMaster 连接复用,Duo 2FA 每次运行只需认证一次;`metamavs remote-check`
  在运行前诊断 ssh/调度器/路径/conda 环境。
- 用 conda 环境执行(`env_setup` + `conda activate`)而非 module;新增 GOTTCHA2 命令生成器与解析器,与 Kraken2/Bracken 并存。
- `configs/sapelo2_config.yaml`(host/user/分区 `bahl_p`/remote_base/conda 环境已填好;数据库路径标 TODO)。共 72 个测试全绿。
- 待办(需在集群上、由你来做):填好 DB/宿主参考/manifest 路径,确认 conda module 名,然后跑 `remote-check` 和一次小样本真实冒烟运行。

### Phase 4 — 智能解释(LLM)✅(已完成)
一个**可选的** LLM 解释层(Anthropic Claude),完全增量、不破坏既有流程:
- `metamavs/llm/`:防御式 client(读 `.env`,`override=True`;`claude-opus-4-8` + adaptive thinking;
  在静态、审慎的系统提示上放 cache_control 断点;任何失败 → 返回 `None`)+ 按运行构建 user prompt。
- 新增 `llm_interpretation` 节点,位于 风险/人审 与 报告 之间;写一段"AI 辅助解读"
  (执行摘要、风险解读、推荐行动、注意事项)。**确定性风险评估仍为权威**。
- `LLMConfig`(默认 `enabled: false`,可配 model/effort/max_tokens,以及 `overrides`
  分 agent 覆盖模型);`[llm]` 可选依赖;`.env` 已 gitignore。
- **优雅降级**:无 key / 未启用 / SDK 或 API 失败 → 干净 no-op;Phase 1–3 仍无需 key。新增 6 个测试(共 90 个)。
- 已用真实 key 实跑验证:Claude 生成了科学审慎的叙事(检测信号措辞、逐病原体 RT-qPCR 确认建议、噬菌体分列、明确注意事项)。

> 缓存说明:静态系统提示(~541 tokens)低于 Anthropic ~1024 token 的缓存下限,所以当前断点是 no-op——
> 位置放对了,等缓存前缀变大(如加入文献上下文)会自动生效。后续可做:分类学/假阳性解释、文献感知解读、公共卫生预警摘要。

**原则**:即便到 Phase 4,Phase 1–3 仍保持"无 API key 也能跑";LLM 是可选增强,不是硬依赖。

### Phase 演进示意
```
Phase 1 (✅ 确定性 dry-run)
   │  把 CommandRunner.run 接上 subprocess
   ▼
Phase 2 (真实执行 + SLURM + 恢复)
   │  把各工具 report 解析进统一数据结构
   ▼
Phase 3 (真实生信工具全接入)
   │  在节点内插入 LLM 推理(可选)
   ▼
Phase 4 (LLM 智能解释)
```
**关键点:每个 Phase 完成后系统都保持可运行,且后一个 Phase 不需要重写前一个。**

---

## 4. 技术框架与分层

### 4.1 框架分层图
```
┌────────────────────────────────────────────────────────┐
│  编排层 / 框架   LangGraph (StateGraph)                  │  graph.py 唯一接触
│  节点、条件边、checkpoint、HITL、错误路由                 │
└────────────────────────────────────────────────────────┘
        ▲ 装配并驱动 16 个节点
┌────────────────────────────────────────────────────────┐
│  节点层 / 业务   agents/*.py (16 个 agent)               │  纯函数 (state)->dict
└────────────────────────────────────────────────────────┘
        ▲ 调用
┌────────────────────────────────────────────────────────┐
│  工具层 / 基础设施  utils/*.py                            │  logging/文件/命令/分类/报告
│  数据校验  config.py + schemas.py (pydantic)             │  只校验数据合法性
└────────────────────────────────────────────────────────┘
```

### 4.2 各依赖库的角色(避免混淆)
| 库 | 类别 | 在项目里做什么 |
|---|---|---|
| **LangGraph** | **多智能体/工作流框架**(唯一核心框架) | StateGraph、节点、条件路由、checkpoint |
| pydantic | 数据校验库(工具) | 校验 config 与 manifest;**不是**编排框架 |
| pandas | 数据处理库 | 读写 CSV、聚合表格 |
| PyYAML | 解析库 | 读取 YAML 配置 |
| typer | CLI 库 | 命令行入口 |
| pytest | 测试框架 | 单元/端到端测试 |
| (LangChain) | 仅 Phase 4 可能引入 | LLM 消息/封装,当前**未使用** |

> 注意:只有 **LangGraph** 是"多智能体编程框架";pydantic 等都是被它驱动的普通工具库。二者是"框架 + 工具"的分层协作,不是"两种框架混合"。

---

## 5. 共享状态 `MetaMAVSState`

定义在 `state.py`,是一个 `TypedDict(total=False)`。设计要点:

- **大部分字段**:后写覆盖(last-write-wins,LangGraph 默认行为)。
- **三个累加器字段**`warnings` / `errors` / `execution_log`:用 `Annotated[list, operator.add]`,各节点只返回新增项,自动追加。
- `create_initial_state(...)` 负责把所有字段初始化为合理默认值。

字段分组:运行元数据 → 输入 → 各节点产物(qc/host/detection/taxonomy/abundance/novel/risk)→ 人工审核 → 报告路径 → 跨切面累加器 → 工作流状态。

---

## 6. 工作流结构(16 个节点)

图里共 **16 个节点**:最初的 12 个(Phase 1)+ 3 个远程 HPC 节点(Phase 3)+ 1 个 LLM 解读节点(Phase 4)。

### 6.1 主流程
```
START
  → input_manager            (1) 校验输入,产出干净 manifest
  → qc_agent                 (2) 质控命令/解析 + 通过/失败(LLM 评估数据是否足够)
  → host_removal_agent       (3) 去宿主命令 + 非宿主 reads
  → viral_detection_agent    (4) 病毒检测命令 + 命中表
  → [mode_router]
        ├─ hpc:  remote_execution_agent   (5)  上传 + 提交 sbatch DAG + 监控
        │        result_sync_agent        (6)  下载 + 完整性校验
        │        tool_output_parser_agent (7)  解析真实输出 → 标准化表
        │          → taxonomy_agent
        └─ local/dry-run:  → taxonomy_agent
  → taxonomy_agent           (8) 分类清洗 + 噬菌体/假阳性(LLM + NCBI 谱系)
  → abundance_agent          (9) RPM 归一化 + 趋势(LLM 趋势解读)
  → novel_virus_agent        (10) 组装/筛查 + 新型候选(LLM 评估)
  → risk_assessment_agent    (11) 四级风险评级 + 理由(LLM + NCBI)
  → [conditional_review_router]
        ├─ human_review       (12) 人在回路:auto / interactive / pause 暂停恢复
        │     └─ pause → END(之后用 `metamavs review` 恢复)
        └──────────────────────────────────────────────→ llm_interpretation
  → llm_interpretation       (13) 公共卫生监测叙事(LLM)
  → report_writer_agent      (14) Markdown + HTML 报告
  → final_summary            (15) 终末摘要 + state.json
  → END

任何节点出致命错误 → error_handler (16) → 可继续则补报告,否则收尾
```

### 6.2 节点职责速查(全部 16 个)
`🧠` 标记**LLM agent**(启用时用 Claude,否则退回确定性)。`(hpc)` 标记仅在
`execution.mode: hpc` 时走的远程节点。

| # | 节点 | LLM | 一句话职责 |
|---|---|---|---|
| 1 | input_manager | | 入口守门:校验清单/元数据,产出 `validated_manifest.csv` |
| 2 | qc_agent | 🧠 | QC 命令+通过/失败;LLM 评估数据是否足够检测 |
| 3 | host_removal_agent | | 生成 Bowtie2/BWA/minimap2 去宿主命令 |
| 4 | viral_detection_agent | | 生成 Kraken2/DIAMOND/GOTTCHA2 命令,产出原始命中+候选 taxon |
| 5 | remote_execution_agent `(hpc)` | | 上传脚本/输入 → 提交 SLURM 依赖 DAG → 轮询 `sacct` 至作业终止 |
| 6 | result_sync_agent `(hpc)` | | 从 HPC 下载结果文件 + 完整性校验,落到 `results/raw/` |
| 7 | tool_output_parser_agent `(hpc)` | | 解析真实工具输出(GOTTCHA2/Kraken2 等)→ 标准化表 |
| 8 | taxonomy_agent | 🧠 | 归一分类;LLM 判 噬菌体/病原/假阳性,**基于 NCBI 真实谱系 grounding** |
| 9 | abundance_agent | 🧠 | RPM 归一化+趋势;LLM 做流行病学趋势解读 |
| 10 | novel_virus_agent | 🧠 | 组装+筛查命令;LLM 评估新型/分歧候选 |
| 11 | risk_assessment_agent | 🧠 | 逐 taxon 评 Low/Medium/High/Critical;LLM 推理+NCBI 谱系,在安全护栏内 |
| 12 | human_review | | HITL 检查点(auto / interactive / **pause 暂停恢复**)|
| 13 | llm_interpretation | 🧠 | 为报告生成公共卫生监测叙事 |
| 14 | report_writer_agent | | 生成 Markdown + HTML 监测报告 |
| 15 | final_summary | | 终末摘要、报告路径、落盘 `state.json` |
| 16 | error_handler | | 错误分类、判定能否继续、防止静默失败 |

### 6.3 LLM agent("大脑")
**6 个节点是真正的 LLM agent**(Anthropic Claude,`claude-opus-4-8`):qc、taxonomy、
abundance、novel_virus、risk、llm_interpretation。其余节点是基础设施/IO/控制类,**有意保持确定性**——它们不需要"大脑"。

**四条设计原则(每个 LLM agent 都满足):**
1. **可选 + 无 key 降级**:默认关闭(`llm.enabled: false`);无 key/SDK/API 失败 → 干净退回确定性。Phase 1–3 永不需要 key。
2. **有据可查,不止凭记忆**:判断建立在 (a) 用 taxid 实时查的 **NCBI 真实谱系**(`ncbi.enabled`,本地控制端;Division `Phages` = 权威噬菌体);(b) 手写**文献参考**(`llm/reference.py`,同时作缓存前缀);(c) 逐病原片段。
3. **确定性安全护栏**:LLM 只能"加谨慎"不能"减"——噬菌体/假阳性钉 Low、已知高危病原体托底 High(`_clamp_llm_risk`);taxonomy 标记取并集(只加不减);PMMoV/crAssphage 当**归一化对照**而非威胁。
4. **成本优化**:共享文献参考作缓存的系统提示前缀(>1024 token → 同一运行内跨 agent 真正命中缓存)。

每次判断叠加的知识层:**NCBI(权威)+ 文献参考 + Claude 训练知识 → 在确定性安全护栏内**。

**分 agent 设模型**:6 个 agent 默认共用 `llm.model`/`effort`/`max_tokens`;在 `llm.overrides`
下按 agent 名(qc、taxonomy、abundance、novel_virus、risk_assessment、llm_interpretation)
可单独覆盖任意字段,未写的继承顶层默认——例如让 risk 用强模型/高 effort、qc 用便宜模型省成本。

### 6.4 人在回路审核(`human_review.mode`)
审核检查点能真正让人类参与。触发条件:总体风险 High/Critical、有新型候选、或样本 QC 失败。三种模式:
- **auto**(默认):模拟批准——不阻塞,适合自动化/CI。
- **interactive**:真实终端 y/N 提示(前台运行)。
- **pause**:运行到检查点**暂停退出**,存盘可恢复快照(`paused_state.json`)+ `review_request.json`。之后真人跑
  `metamavs review --run-dir <目录>` 查看风险上下文、批准/驳回(`--approve`/`--reject` 或交互)。批准→恢复 解读→报告→收尾;驳回→收尾不出报告。**与运行解耦**,适合**后台/长 HPC 作业 + 延迟人审**——决定和审核备注写进报告。

### 6.5 路由逻辑(`routing.py`)
- `make_step_router(next)`:主干每个节点后挂的"错误守卫"——有致命错误转 `error_handler`,否则去下一节点。
- `mode_router`:viral_detection 之后——`execution.mode == hpc` 则走远程(HPC)链,否则直达 taxonomy。
- `review_router`:risk 之后分流——需审核去 `human_review`,否则去 `llm_interpretation` → 报告。
- `review_pause_router`:`human_review` 之后——若暂停等人审则到 END(之后用 `metamavs review` 恢复),否则继续解读。
- `error_handler_router`:`error_handler` 之后——可继续去 `report_writer`,否则去 `final_summary`。
- `should_request_review`:判定是否触发人审(高/危风险、新型候选、QC 失败)。

---

## 7. 目录结构与文件职责

```text
MetaMAVS/
  GUIDE_LINE.md          # 本文档:总体设计指南
  README.md              # 安装与使用
  CLAUDE.md              # 给 AI 协作者的规格说明
  pyproject.toml         # 依赖与 CLI 入口
  configs/
    example_config.yaml  # 示例配置
  data/
    example_manifest.csv # 示例样本清单
  metamavs/
    __init__.py          # 版本号
    cli.py               # Typer CLI:run / graph / validate / slurm
    config.py            # pydantic 配置模型 + YAML 加载
    schemas.py           # 清单 schema + 校验规则
    state.py             # MetaMAVSState(TypedDict + reducer)
    routing.py           # 条件路由函数
    graph.py             # ★唯一接触 LangGraph:构建+编译 StateGraph
    agents/              # 16 个节点(含远程+LLM),每个一文件
    utils/               # logging / file / command_runner / taxonomy / report
    workflows/
      local_workflow.py  # 本地执行后端(已用)
      slurm_workflow.py  # SLURM 后端(Phase 2 占位)
  reports/               # 运行产物(示例报告已入库,大文件被 .gitignore 排除)
  tests/                 # config/state/graph/routing/manifest 测试
```

### 每次运行产生的目录
```text
reports/<run_name>/
  logs/          # metamavs.log, error_summary.json, final_summary.json
  intermediate/  # 校验后清单 + 各步骤 JSON 摘要
  commands/      # 生成的 *.sh 命令脚本
  tables/        # 各类 CSV 结果表
  report.md      # 最终 Markdown 报告
  report.html    # 最终 HTML 报告
  state.json     # 完整终态
```

---

## 8. 如何运行(快速回顾)

```bash
pip install -e ".[dev]"
metamavs graph    --config configs/example_config.yaml   # 看工作流结构
metamavs validate --config configs/example_config.yaml   # 校验配置+清单
metamavs tools    --config configs/example_config.yaml   # 检查工具可用性
metamavs run      --config configs/example_config.yaml --dry-run  # 跑全流程
# HPC(Phase 3):真实运行 + 人在回路审核
metamavs remote-check --config configs/sapelo2_config.yaml        # 诊断 SSH/SLURM
metamavs run          --config configs/sapelo2_config.yaml --execute  # 可能在人审点暂停
metamavs review --run-dir reports/<run_name> --approve --notes "…"   # 真人拍板
pytest                                                    # 跑测试
```
(未安装时用 `python -m metamavs.cli ...` 代替 `metamavs`。)

**可选 LLM + NCBI grounding**:把 `ANTHROPIC_API_KEY` 放进 `.env`,config 里设
`llm.enabled: true`、(可选)`ncbi.enabled: true`。不设这些就纯确定性、无需 key 运行。

---

## 9. 给后续开发者的建议(如何从 Phase 1 往后走)

1. **不要重写**:每个 Phase 都是在前一个之上增量扩展。
2. **Phase 2 切入点**:`utils/command_runner.py` 的 `CommandRunner.run` 已预留真实执行分支;先在这里接 subprocess,再扩 `error_handler` 做重试/跳过。
3. **Phase 3 切入点**:为每个工具写一个"report 解析器",把真实输出转成现有 `raw_viral_hits` / 分类表结构;**下游节点不用改**。
4. **Phase 4 切入点**:在 `taxonomy` / `risk` / `report` 等节点内部插入 LLM 调用;保持 LLM 为可选,不破坏无 key 运行。
5. **保持纪律**:节点维持纯函数 `(state)->dict`;框架依赖只留在 `graph.py`;科学语言保持审慎;改动后跑 `pytest`。

---

## 10. 一页纸总结

- **是什么**:基于 LangGraph 的多智能体病毒监测工作流。
- **几个 Phase**:**4 个**。Phase 1(确定性原型,✅已完成)→ Phase 2(真实执行+SLURM)→ Phase 3(真实生信工具)→ Phase 4(LLM 解释)。
- **核心框架**:仅 **LangGraph**;pydantic/pandas/typer 等是工具库,不是第二个框架。
- **架构精髓**:共享状态 + 12 节点纯函数 + 条件路由 + 错误分流 + 人在回路;框架依赖收口单文件;科学审慎贯穿始终;为 LLM 演进预留干净接缝。
