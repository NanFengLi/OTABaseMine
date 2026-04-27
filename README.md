# OTABaseMine

基于 [OTABase](https://github.com/OTABase/OTABase) 的 4G LTE / 5G NR RRC 协议模糊测试框架。本项目实现了 **合法 RRC 消息生成 → 比特流级字段变异 → OTA 空口注入** 的完整 fuzzing 流水线，支持 4G LTE（srsRAN 4G）和 5G NR（srsRAN Project）两套协议栈。

## 项目架构

```
OTABaseMine/
├── bishe/
│   ├── generate_new/          # 合法 RRC 消息生成器（4G / 5G）
│   │   ├── main.py            #   命令行入口
│   │   ├── rrc_generator.py   #   核心 ASN.1 递归生成器
│   │   ├── rrc_batch_generator.py  # 批量生成 + 消息精简
│   │   ├── path_trie.py       #   SQLite 持久化前缀树（断点续传）
│   │   ├── output_4g/         #   4G 合法 payload + coverage.db
│   │   └── output_5g/         #   5G 合法 payload + coverage.db
│   ├── mutated/               # 比特流级变异引擎
│   │   ├── tools/             #   四种字段类型变异工具（4G + 5G）
│   │   ├── langchain_agent_4g_mutator.py  # 4G 批量变异入口
│   │   ├── langchain_agent_5g_mutator.py  # 5G 批量变异入口
│   │   ├── mutate_output_4g/  #   4G 变异结果输出
│   │   └── mutate_output_5g/  #   5G 变异结果输出
│   └── pycrate_asn1obj/       # pycrate ASN.1 协议定义加载
├── artifact/
│   ├── srsRAN_Project/        # 5G gNB（基于 srsRAN Project 修改）
│   └── otabase/               # 4G eNB/EPC（基于 srsRAN 4G 修改）
└── pycrate/                   # pycrate 库（本地副本）
```

## 快速开始

### 环境准备

```bash
# 激活 conda 环境
conda activate bishe

# 进入项目根目录
cd /path/to/OTABaseMine
```

### Step 1：生成合法 RRC 消息

```bash
# 4G LTE：生成覆盖所有字段类型的合法 payload
python -m bishe.generate_new.main -f OCTET_STRING BIT_STRING INTEGER SEQOF

# 5G NR：生成覆盖所有字段类型的合法 payload
python -m bishe.generate_new.main --rat 5g -f OCTET_STRING BIT_STRING INTEGER SEQOF

# 中断后再次运行相同命令，自动从断点续传（基于 SQLite 前缀树持久化）
python -m bishe.generate_new.main -f OCTET_STRING BIT_STRING INTEGER SEQOF

# 强制从头开始（删除旧的前缀树数据库 coverage.db）
python -m bishe.generate_new.main -f OCTET_STRING BIT_STRING INTEGER SEQOF --clean

# 其他可选参数
#   --max-lines 2000    每个文件最多行数（默认 2000，超出自动分文件）
#   -s 42               随机种子
#   -c 2                递归循环深度
```

路径去重使用 SQLite 持久化前缀树（`coverage.db`），进程中断后重新运行相同命令会自动跳过已覆盖路径继续生成。

输出目录：
- 4G → `bishe/generate_new/output_4g/`
- 5G → `bishe/generate_new/output_5g/`

每个目录下生成：
- `rrc_legitimate_payloads_<timestamp>.txt`（按 2000 行自动分文件）
- `testFileIndex`（指向第一个 payload 文件，供 eNB/gNB 读取）
- `coverage.db`（SQLite 前缀树数据库，用于断点续传）

### Step 2：批量变异

```bash
# 4G 批量变异（读取 output_4g → 输出到 mutate_output_4g）
python -m bishe.mutated.langchain_agent_4g_mutator --batch

# 5G 批量变异（读取 output_5g → 输出到 mutate_output_5g）
python -m bishe.mutated.langchain_agent_5g_mutator --batch

# 可选参数
#   --limit N              每个文件最多处理 N 行
#   --max-strategies N     无约束 OCTET STRING / BIT STRING 每条消息随机挑选 N 种策略（默认全部）
#   --inspect-only         仅识别字段类型，不执行变异
```

变异流程：对每条合法 payload，自动识别字段类型（INTEGER / OCTET STRING / BIT STRING / SEQUENCE OF），调用对应的 BASE 策略变异工具，在 UPER 比特流层面直接替换字段值，绕过 pycrate 约束校验。

输出文件格式：
```
<总条数>
<序号>,<变异后hex>,<消息类型>,<字段路径>,<字段类型>,<变异策略编号>
```

### Step 3：OTA 空口注入

#### 5G 注入（srsRAN Project gNB）

```bash
# 构建 gNB
cd artifact/srsRAN_Project && mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$(nproc) gnb

# 配置 otabase_fuzzing.yml（关键参数）
#   otabase_enable_5g_rrc_fuzzing: true
#   otabase_test_index_file: ../../bishe/generate_new/output_5g/testFileIndex
#   otabase_inject_after_auth_only: false  # true=仅认证后注入，false=从 rrc_setup_complete 起注入（默认）

# 启动
sudo ./apps/gnb/gnb \
    -c ../configs/gnb_rf_b200_tdd_n78_20mhz.yml \
    -c ../configs/otabase_fuzzing.yml \
    cu_cp security --nea_pref_list=nea2,nea1,nea3,nea0
```

#### 4G 注入（srsRAN 4G eNB）

```bash
# 参考 artifact/otabase/ 下的构建和启动脚本
artifact/otabase/build_trial.sh
artifact/otabase/install.sh
```

### 其他运行模式

```bash
# 直接调用工具演示（无需 API Key）
python -m bishe.mutated.langchain_agent_4g_mutator
python -m bishe.mutated.langchain_agent_5g_mutator

# 通过 LangChain Agent 交互（需要 OPENAI_API_KEY）
python -m bishe.mutated.langchain_agent_4g_mutator --agent
python -m bishe.mutated.langchain_agent_5g_mutator --agent
```

## 变异策略

基于 OTABase 的 BASE 策略，在 UPER 比特流层面直接替换字段，共支持四种字段类型：

| 字段类型 | 变异数量 | 策略概要 |
|---------|---------|---------|
| INTEGER | 2 条 | 比特全1溢出、上界+1溢出 |
| OCTET STRING（受约束） | 4 条 | 长度/内容不匹配、边界溢出 |
| OCTET STRING（无约束） | 22 条 | 10 个 PER 长度编码边界 × 2 + 2 条非法编码 |
| BIT STRING（受约束） | 4 条 | 长度/内容不匹配（比特级） |
| BIT STRING（无约束） | 12 条 | 3 个边界长度 × 3 + 3 条非法编码 |
| SEQUENCE OF | 4 条 | 长度头：0、实际值、随机、最大编码 |

> 无约束 OCTET STRING / BIT STRING 策略数量较多，可通过 `--max-strategies N` 限制每条消息随机挑选 N 种策略，例如 `--max-strategies 4`。受约束字段不受此参数影响。
>
> **策略编号说明**：输出文件中的策略编号始终反映该策略在全部策略集合中的**原始编号**（1-based），而非采样后的重编号。例如无约束 OCTET STRING 共 22 种策略，若 `--max-strategies 4` 随机挑选了第 3、7、15、19 号策略，输出中仍记录为 `3,7,15,19`，而非重编号为 `1,2,3,4`。

详细策略说明见 [`bishe/mutated/tools/README.md`](bishe/mutated/tools/README.md)。

## OTA 注入与异常检测机制

变异后的 RRC 消息由 eNB/gNB 注入空口发送给 UE，整个过程包含 **发送 → Oracle 检测 → 黑名单 → Crash 记录** 四个环节。

### 发送链路对比

| 维度 | srsRAN_Project (5G NR) | otabase (4G LTE) |
|------|------------------------|------------------|
| **架构** | CU-CP 与 DU 分离 | 单体 eNB |
| **注入点** | CU-CP 侧 RRC UE | eNB 侧 RRC |
| **发送链路** | RRC → PDCP → F1AP → SCTP → DU → RLC/MAC/PHY → 空口 | RRC → PDCP → RLC → MAC → PHY → 空口 |
| **CU↔DU 传输** | F1AP over SCTP（跨网络） | 无（同一进程） |

两者都从 `testFileIndex` 索引文件定位 payload 文件和当前行号，逐条读取 hex 载荷，经 PDCP 安全封装（完整性保护 + 加密）后通过空口发送。

### Oracle 机制（UE 存活检测）

每发送一条变异消息后，基站紧接着发送一条 **UECapabilityEnquiry** 作为探测：

1. 若 UE 在 **1000ms** 内回复 `UECapabilityInformation` → UE 存活，继续下一条
2. 超时未回复 → 最多**重试 2 次**
3. 重试仍失败 → 进入 **Backtracking**（逐条回溯最近发送的消息，定位导致崩溃的具体消息）

otabase (4G) 额外支持 **RLC Max Retx 检测**：当 RLC 层最大重传次数耗尽（UE 未 ACK），直接判定 UE 可能崩溃并进入 Backtracking。

5G NR 同样具备 RLC 层，但由于 CU-DU 分离，RLC 运行在 **DU** 侧而非 CU-CP 侧：

| 维度 | 4G（otabase） | 5G（srsRAN_Project） |
|------|--------------|----------------------|
| RLC 所在位置 | eNB 同进程 | DU（独立进程/主机） |
| Max Retx 触发方式 | `max_retx_attempted()` 同进程直接回调 | DU → F1AP `UE Context Release Request`（原因码 `rl_failure`）→ SCTP → CU-CP |
| CU-CP 感知方式 | 直接（同线程） | 间接（跨网络 F1AP 消息） |
| 当前是否启用 | ✅ 已启用 | ✅ 已启用（F1AP 路径） |

**5G RLC Max Retx 实现原理**：当 DU 检测到 RLC Max Retx 时，通过 F1AP `UE Context Release Request`（原因码 `rl_fail_rlc` / `rl_fail_others`）通知 CU-CP；CU-CP 的 `du_processor_impl::handle_du_initiated_ue_context_release_request()` 收到后，调用 `rrc_ue_interface::handle_rlc_max_retx()`，将 oracle 重试计数器强制设为阈值以上并立即进入 Backtracking，与 4G 的 `max_retx_attempted()` 行为等价。F1AP/SCTP 传输延迟（< 20ms）远小于 Oracle 超时（1000ms），不影响检测实时性。

### 黑名单机制

两者都维护**永久黑名单 + 临时黑名单**（内存数据结构）：

| 类型 | 说明 |
|------|------|
| **永久黑名单** | Backtracking 确认 crash 候选后，在 payload 文件中永久跳过同一 `msgName+fieldName` 的所有行 |
| **临时黑名单** | 同一 `msgName+fieldName` 触发超时 **3 次**后临时屏蔽，累计跳过 **30 行**后自动移除 |

**临时黑名单开关**（与 4G 一致）：  
- **4G**：`--temp_blacklist`（默认 true），设为 false 可关闭临时黑名单，仅保留永久黑名单。  
- **5G**：`otabase_temp_blacklist`（YAML：`cu_cp.rrc.otabase_temp_blacklist`，CLI：`--otabase_temp_blacklist`，默认 true），设为 false 可关闭临时黑名单。

**注入时机开关**（5G 专有）：  
- **5G**：`otabase_inject_after_auth_only`（YAML：`cu_cp.rrc.otabase_inject_after_auth_only`，CLI：`--otabase_inject_after_auth_only`，默认 false）。`false` 时从 `rrc_setup_complete`（认证前）起开始注入；`true` 时跳过认证前，首次注入发生在 `security_mode_complete`（认证后）。

**`msgName` 与 `fieldName` 含义**（与 payload 文件列对应）：

- **msgName**：第 3 列，**消息类型**（如 `dlDedicatedMessageSegment-r16`）。
- **fieldName**：第 4 列到行末的整段字符串，与 msgName 一起唯一标识该行测试用例：
  - **生成器**输出格式为 `序号,hex,消息类型,消息路径` → fieldName = **消息路径**（path_csv）。
  - **变异器**输出格式为 `序号,hex,消息类型,消息路径,变异的字段类型,变异的策略序号` → fieldName = **消息路径,字段类型,策略序号**。

因此“fieldName”不是单指 ASN.1 字段名，而是“路径（及可选的其他列）”这一整段，用于黑名单键 `msgName+fieldName` 的匹配与跳过统计。

回放模式（`--replay` / `otabase_replay_mode`）下黑名单机制会被禁用，用于复现验证。

### Crash 记录与输出文件

| 文件 | 说明 |
|------|------|
| `testFileIndex` | 测试进度索引：`payloadFileName,curLineNum,totalLineNum`，每发送一条自动递增，支持断点续跑 |
| `crashes/crash_N/candidates.json` | 第 N 次 crash 的详细信息：最近发送的消息队列、Best Candidate（Payload hex / Message 类型 / Field 路径） |
| `crashes/crash_count.txt` | 累计 crash 次数 |
| `candidate_list.txt` | 所有 crash 候选的行号列表（`testFileName,candidate_line`），追加写入 |

> **5G (srsRAN_Project)**：与 4G 一致，通过可配置输出目录写入崩溃用例。命令行可用 **`-o`**（与 4G 相同），或 YAML：`cu_cp.rrc.otabase_output_directory`、长选项 `--otabase_output_directory`。未配置时默认使用 **`otabase_crashes/`**（相对进程当前工作目录）；配置后则写入该目录，即 `{otabase_output_directory}/crashes/crash_count.txt`、`{otabase_output_directory}/crashes/crash_N/candidates.json`、`{otabase_output_directory}/candidate_list.txt`。  
> **4G (otabase)**：输出目录由 `-o` 参数指定，上述文件写在该目录下。

## 注意事项

1. 5G gNB 必须使用 5G NR RRC payload，不能混用 4G LTE payload
2. `testFileIndex` 与 payload 文件路径需一致且可访问
3. 若从 `build/` 启动 gNB，路径解析基于配置中的 `otabase_test_index_file`
4. 输出目录 `output_4g/`、`output_5g/`、`mutate_output_4g/`、`mutate_output_5g/` 建议忽略 Git 管理

## 参考资料

- [OTABase](https://github.com/OTABase/OTABase) — 原始 4G RRC fuzzing 框架
- [srsRAN Project](https://github.com/srsran/srsRAN_Project) — 5G NR gNB 实现
- 3GPP TS 36.331 — LTE RRC 协议规范
- 3GPP TS 38.331 — NR RRC 协议规范

