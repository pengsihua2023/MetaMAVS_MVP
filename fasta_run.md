# MetaMAVS 运行指南（脱离 Claude Code，在终端直接运行）

MetaMAVS 是一个标准的 Python 包。装好之后，用 `metamavs` 命令在终端里驱动整个
16 节点的 LangGraph 工作流，**不需要 Claude Code**。

> 命令没装成功也没关系，把 `metamavs` 换成 `python -m metamavs.cli` 即可。

---

## 1. 进入项目并激活环境

```bash
cd /mnt/d/claude-code-project/MetaMAVS
source .venv/bin/activate          # 之前建过虚拟环境就直接激活
```

如果还没安装过（或换了机器）：

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .                   # 核心：确定性、无需任何 API key
# 可选附加：
pip install -e ".[dev]"            # + pytest、rich（开发/测试）
pip install -e ".[llm]"            # + anthropic、python-dotenv（启用 LLM agents 时）
```

要求 Python **3.11+**。

---

## 2. 本地运行（无需 key，最常用）

```bash
metamavs graph    --config configs/example_config.yaml   # 查看 16 节点工作流结构
metamavs validate --config configs/example_config.yaml   # 校验 config + manifest
metamavs tools    --config configs/example_config.yaml   # 检查生信工具是否可用
metamavs run      --config configs/example_config.yaml --dry-run   # 完整 dry-run
```

> ⚠️ **`metamavs tools` 只查本机 PATH。** 本机显示 `0/9` 是正常的——生信工具装在
> HPC 集群上（见 sapelo2 配置的 `step_env`），不在本机。要确认集群上的工具/路径/SSH，
> 请改用 **`metamavs remote-check --config configs/sapelo2_config.yaml`**。

运行产物位于 `reports/<run_name>/`：

```text
reports/<run_name>/
  report.md / report.html   # 最终监测报告
  state.json                # 完整最终图状态
  tables/                   # 命中、分类、丰度、趋势、风险、新病毒候选（CSV）
  intermediate/ commands/ logs/   # 汇总、生成的 *.sh、日志
  remote/ results/raw/      # （HPC 模式）作业账本、脚本、下载的输出
```

---

## 3. 跑测试

```bash
pytest        # 119 个测试
```

---

## 4. 启用 LLM agents（Phase 4，可选）

6 个节点（qc / taxonomy / abundance / novel_virus / risk_assessment /
llm_interpretation）在开启后会变成由 Claude 驱动、并以 NCBI 分类学接地的 agent；
**未提供 key 时自动退回确定性逻辑**。

```bash
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env       # .env 已被 gitignore
```

在 config 中：

```yaml
llm:  { enabled: true, model: claude-opus-4-8, effort: medium }
ncbi: { enabled: true, email: you@example.com }   # 用真实 NCBI lineage 接地
```

然后照常 `metamavs run` 即可。

---

## 5. 真集群运行（Phase 3，UGA GACRC Sapelo2）

本地做编排/解析/报告，把生信步骤提交到远程 SLURM 集群执行。

```bash
metamavs remote-check --config configs/sapelo2_config.yaml   # 诊断 ssh / sbatch / 路径
metamavs run          --config configs/sapelo2_config.yaml --execute
```

- 需要先用 Duo 建好 SSH ControlMaster 通道（一次认证，整轮复用）。
- 运行到人审节点会**暂停并退出**，写出可恢复快照。

人工审核后恢复：

```bash
# 交互式（在真实终端按 y/N）：
metamavs review --run-dir reports/<run_name>

# 或非交互式：
metamavs review --run-dir reports/<run_name> --approve --notes "..."
```

批准后继续 解读 → 报告 → 汇总；拒绝则收尾、不出报告。

---

## 最小记忆版

```bash
cd /mnt/d/claude-code-project/MetaMAVS
source .venv/bin/activate
metamavs run --config configs/example_config.yaml --dry-run
```

---

## 配置与 manifest 速查

- **Config** — `configs/example_config.yaml`：`project / input / execution / tools /
  risk / report`，外加可选 `hpc / llm / ncbi / human_review`。
  Config = “怎么跑”；manifest = “跑什么”。
- **Manifest** — `data/example_manifest.csv`：列为
  `sample_id, read1, read2, collection_date, location, sample_type`。
  `sample_id` 唯一；`read1` 必填；双端模式需要 `read2`；日期格式 `YYYY-MM-DD`。
  `input.remote_data: true` 表示 read1/read2 是已在 HPC 上的路径。

> ⚠️ 科学审慎：MetaMAVS 报告的是“检测到的序列信号”，而非“确诊感染”；
> 高风险检测一律需要确证性检测。
