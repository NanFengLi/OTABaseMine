# OTABaseMine

本仓库围绕 RRC fuzzing 做了三件事：

1. 生成 4G LTE / 5G NR 的合法 RRC DL-DCCH payload。
2. 对合法 payload 做 UPER 比特流级字段变异。
3. 将 payload 注入到两个空口执行框架中：
   - `artifact/otabase`：4G LTE，基于 OTABase / srsRAN 4G。
   - `artifact/srsRAN_Project`：5G NR，基于 srsRAN Project 修改。

本文档只关注 RRC 相关内容。NAS、IP、PDCP 等方向不在这里展开。

## 与上游 OTABase 的关系

上游 [OTABase/OTABase](https://github.com/OTABase/OTABase) 将 OTABase 描述为一个 over-the-air LTE baseband testing framework，核心包括三类能力：

- network-side state control；
- specification-guided test case generation；
- crash detection oracle。

上游项目目标是 LTE commercial baseband 的 RRC/NAS memory crash 检测，并把 `artifact/otabase/` 作为执行框架，把 `artifact/test-case-generator/` 作为测试用例生成器。

本仓库和上游的主要不同点：

- 保留并使用 `artifact/otabase` 作为 4G RRC 空口执行参考。
- 另引入 `artifact/srsRAN_Project`，尝试把 OTABase 风格的 RRC fuzzing 移植到 5G NR gNB。
- 将生成器整理到 `bishe/generate_new`，支持 4G LTE 和 5G NR 合法 RRC payload 生成。
- 将字段变异整理到 `bishe/mutated`，目前主要复现 BASE 类字段变异策略。

因此，本仓库不是上游 OTABase 的简单镜像；它的研究重点是：**以 4G OTABase 的 RRC fuzzing 行为为基准，让 5G srsRAN Project 尽量实现同等能力。**

## 目录结构

```text
OTABaseMine/
├── bishe/
│   ├── generate_new/      # 4G/5G RRC 合法 payload 生成
│   └── mutated/           # RRC payload 字段变异
├── artifact/
│   ├── otabase/           # 4G OTABase / srsRAN 4G 执行框架
│   └── srsRAN_Project/    # 5G srsRAN Project 执行框架
└── pycrate/               # 本地 pycrate 副本
```

## Payload 生成与变异

### 生成合法 RRC payload

```bash
# 4G LTE
python -m bishe.generate_new.main -f OCTET_STRING BIT_STRING INTEGER SEQOF

# 5G NR
python -m bishe.generate_new.main --rat 5g -f OCTET_STRING BIT_STRING INTEGER SEQOF
```

生成器输出：

- 4G：`bishe/generate_new/output_4g/`
- 5G：`bishe/generate_new/output_5g/`

典型文件：

- `rrc_legitimate_payloads_<timestamp>.txt`
- `testFileIndex`
- `coverage.db`

payload 文件格式：

```text
<total_count>
<id>,<hex_payload>,<message_type>,<field_path>
```

### 批量变异

```bash
# 4G
python -m bishe.mutated.langchain_agent_4g_mutator --batch

# 5G
python -m bishe.mutated.langchain_agent_5g_mutator --batch
```

变异输出格式：

```text
<total_count>
<id>,<mutated_hex>,<message_type>,<field_path>,<field_type>,<strategy_id>
```

当前变异工具覆盖：

| 字段类型 | 当前实现 |
|---|---|
| INTEGER | 比特冗余/边界溢出类变异 |
| OCTET STRING | 受约束/无约束长度与内容不一致变异 |
| BIT STRING | 受约束/无约束比特长度与内容变异 |
| SEQUENCE OF | 长度头变异 |

注意：当前变异侧主要实现 BASE 类策略；上游 OTABase README 中提到的 TRUNCATE、ADD 等策略不应默认认为已经完整移植到本仓库变异工具。

## 4G RRC 执行框架：artifact/otabase

4G 侧是当前最完整的参考实现。RRC fuzzing 相关源码集中在：

- `artifact/otabase/srsenb/src/stack/rrc/rrc.cc`
- `artifact/otabase/srsenb/src/stack/rrc/rrc_ue.cc`
- `artifact/otabase/srsenb/hdr/stack/rrc/rrc.h`
- `artifact/otabase/srsenb/src/stack/upper/rlc.cc`

### 4G 的发送驱动

4G 通过 RLC ACK 触发下一条测试消息：

```text
fuzzed RRC DL-DCCH
  -> PDCP/RLC/MAC/PHY
  -> UE 收到 RLC PDU
  -> eNB RLC 收到 ACK
  -> rrc::send_next_test_msg()
  -> send_rrc_test_message() 或 send_rrc_test_message_backtracking()
```

关键函数：

- `rrc::send_next_test_msg()`：收到 ACK 后决定发送普通测试消息或 backtracking 消息。
- `rrc::ue::send_rrc_test_message()`：正常读取并发送下一条 RRC payload。
- `rrc::ue::send_rrc_test_message_backtracking()`：从最近消息队列倒序回放候选。

### 4G 的 payload 读取和断点续跑

4G 固定读取当前工作目录下的 `testFileIndex`。

`testFileIndex` 支持两种形态：

```text
rrcTest1
rrcTest1,curLineNum,totalLineNum
```

`rrc::get_test_msg_from_file()` 会：

- 打开 `testFileIndex` 指定的 payload 文件；
- 读取第一行总数；
- 逐行读取 `<id>,<hex>,<message>,<field>`；
- 每发送一条后回写 `testFileIndex`；
- 文件结束后通过文件名数字递增切到下一个文件。

4G 每次读取到 payload 后会把：

```text
payload,msgName,fieldName
```

放入 `test_message_queue`，用于后续 backtracking。

### 4G 的 RRC oracle

4G 每隔 `check_period` 条消息发送 `UECapabilityEnquiry` 作为 RRC 存活探测。

```text
UE 回复 UECapabilityInformation -> 认为 UE 存活，继续发送
UE 未回复，oracle timer 超时 -> 重试
超过重试次数 -> 进入 backtracking
```

关键函数：

- `rrc::ue::send_ue_cap_enquiry()`
- `rrc::set_rrc_oracle_timer()`
- `rrc::rrc_oracle_timer_expired()`
- `rrc::ue::notify_rrc_oracle()`

### 4G 的 RLC Max Retx crash 信号

4G RLC Max Retx 通过同进程回调直接进入 RRC：

```text
RLC max retx
  -> rrc::max_retx_attempted(rnti)
  -> ue->notify_ack_timeout()
  -> ue->max_rlc_retx_reached()
```

如果此时处于 backtracking，4G 会将当前 backtracking payload 记录为 crash candidate。

### 4G 的 crash 记录

4G crash 记录在 `rrc::save_recent_messages()` 中完成，输出目录来自 `-o` 参数。

输出文件：

```text
<output_dir>/candidate_list.txt
<output_dir>/crashes/crash_count.txt
<output_dir>/crashes/crash_N/candidates.json
```

`candidate_list.txt` 格式：

```text
testFileName,candidate_line
```

其中 `candidate_line` 由：

```cpp
curLineNum - backtracking_num
```

计算得到。

### 4G 的关键特点

4G 的 OTABase RRC 状态主要保存在父级 `rrc` 对象中，包括：

- `is_backtracking`
- `backtracking_num`
- `backtracking_msg`
- `test_message_queue`
- `blacklistMsgField`
- `crashCounter`
- payload 文件读取状态

这很重要：UE 掉线或重连时，父级 `rrc` 对象仍然存在，因此 backtracking 状态和最近消息队列不容易丢失。

## 5G RRC 执行框架：artifact/srsRAN_Project

5G 侧在 srsRAN Project 的 CU-CP/RRC 位置加入了 OTABase 风格逻辑。主要源码：

- `artifact/srsRAN_Project/lib/rrc/ue/rrc_ue_message_senders.cpp`
- `artifact/srsRAN_Project/lib/rrc/ue/rrc_ue_message_handlers.cpp`
- `artifact/srsRAN_Project/lib/rrc/ue/rrc_ue_impl.h`
- `artifact/srsRAN_Project/lib/cu_cp/du_processor/du_processor_impl.cpp`
- `artifact/srsRAN_Project/lib/cu_cp/cu_cp_impl.cpp`
- `artifact/srsRAN_Project/lib/du/du_high/du_manager/du_ue/du_ue_adapters.cpp`

### 5G 配置入口

5G 使用 `cu_cp.rrc` 下的 OTABase 配置：

```yaml
cu_cp:
  rrc:
    otabase_enable_5g_rrc_fuzzing: true
    otabase_test_index_file: /absolute/path/to/testFileIndex
    otabase_check_period: 10
    otabase_replay_mode: false
    otabase_output_directory: /absolute/path/to/otabase_crashes
    otabase_temp_blacklist: true
    otabase_pacing_ms: 5
    otabase_inject_after_auth_only: false
```

配置链路：

```text
YAML / CLI
  -> cu_cp_unit_config
  -> cu_cp_config_translators.cpp
  -> cu_cp_configuration.rrc
  -> du_processor_impl.cpp create_rrc_config()
  -> rrc_du_impl.cpp
  -> rrc_ue_cfg_t
  -> rrc_ue_impl
```

### 5G 的注入触发点

5G 在 UL DCCH handler 里触发下一条测试消息：

- `rrc_setup_complete`
- `security_mode_complete`
- `ue_cap_info`
- `rrc_recfg_complete`
- `rrc_reest_complete`

如果 `otabase_inject_after_auth_only=false`，从 `rrc_setup_complete` 后开始注入；如果为 `true`，跳过认证前阶段，从 `security_mode_complete` 后开始注入。

5G 发送前有硬条件：

```cpp
context.cfg.otabase_enable_5g_rrc_fuzzing == true
context.state == rrc_state::connected
```

也就是说，当前实现只在 RRC CONNECTED 状态发送 DL-DCCH fuzz payload。

### 5G 的 RRC 状态

5G RRC 状态枚举为：

```cpp
enum class rrc_state { idle = 0, connected, connected_inactive };
```

当前 fuzzing 只支持 `connected`。这不是 bug，而是因为当前 payload 是 DL-DCCH，需要 SRB1/PDCP 发送路径。`idle` 或 `connected_inactive` 不应按同一方式直接发送 DL-DCCH fuzz payload。

### 5G 的发送驱动

5G 当前有两类驱动：

1. UL RRC 消息触发：例如 `security_mode_complete`、`ue_cap_info`。
2. RLC ACK / pacing timer 触发：
   - DU 侧 RLC 收到 status/control PDU 后通过 `rlc_ack_du_adapter` 回调；
   - `gnb.cpp` 将 DU 的 `rlc_ack_to_cu_notifier` 接到 CU-CP；
   - `cu_cp_impl::on_rlc_ack_received()` 找到 UE 后调用 `rrc_ue->handle_rlc_ack()`；
   - `rrc_ue_impl::handle_rlc_ack()` 调用 `maybe_send_next_otabase_rrc_message("rlc_ack")`；
   - 同时，`otabase_pacing_ms` 提供定时器兜底。

因此，当前 5G 代码已经尝试补齐 4G 的 ACK 驱动节奏；这部分不能简单说“5G 只能靠 timer”。

### 5G 的 payload 读取

5G 从 `context.cfg.otabase_test_index_file` 读取 `testFileIndex`，支持绝对路径和相对路径。相对 payload 文件会按 `testFileIndex` 所在目录解析。

每发送一条后，5G 会回写：

```text
payload_file,curLineNum,totalLineNum
```

并将：

```text
payload,msgName,fieldName
```

放入 `otabase_test_msg_queue`。

### 5G 的 oracle 和 backtracking

5G 同样使用 `UECapabilityEnquiry` 作为 RRC liveness oracle：

- `send_ue_cap_enquiry_oracle()`
- `set_otabase_oracle_timer()`
- `otabase_oracle_timer_expired()`
- `notify_rrc_oracle()`

超过重试次数后进入 backtracking：

- `otabase_is_backtracking = true`
- `send_rrc_test_message_backtracking()`
- 最近消息队列倒序回放
- backtracking 中再次 oracle failure 时保存 refined candidate

当前 5G 还做了一个 preliminary save：第一次进入 backtracking 时就把最近一条消息作为 best guess 写盘，避免 UE context 很快销毁导致完全没有记录。

### 5G 的 RLC Max Retx 路径

5G RLC 在 DU 侧，RRC UE 在 CU-CP 侧。因此 RLC Max Retx 不能像 4G 一样同进程直接调 eNB RRC。

当前代码通过 DU initiated UE context release 的 F1AP cause 处理：

```text
DU reports UE Context Release Request
  -> du_processor_impl::handle_du_initiated_ue_context_release_request()
  -> cause == rl_fail_rlc 或 rl_fail_others
  -> rrc_ue->handle_rlc_max_retx()
  -> notify_rrc_oracle()
```

注意：只有 cause 是 `rl_fail_rlc` 或 `rl_fail_others` 时，当前代码才会走这条 RLC Max Retx 兜底路径。

### 5G 的 crash 记录

5G 保存函数是 `rrc_ue_impl::save_otabase_recent_messages()`。

输出目录：

- 如果配置了 `otabase_output_directory`，写入该目录。
- 如果未配置，写入进程当前工作目录下的 `otabase_crashes/`。

输出文件：

```text
<output_dir>/candidate_list.txt
<output_dir>/crashes/crash_count.txt
<output_dir>/crashes/crash_N/candidates.json
```

`candidate_list.txt` 格式同样是：

```text
payload_file,candidate_line
```

## 4G 与 5G 当前差异

| 维度 | 4G `artifact/otabase` | 5G `artifact/srsRAN_Project` | 当前判断 |
|---|---|---|---|
| 协议栈架构 | eNB 单体进程 | CU-CP / DU 分层 | 5G 状态和回调链更复杂 |
| 注入点 | eNB RRC UE | CU-CP RRC UE | 都是 RRC 层注入 DL-DCCH |
| 发送链路 | RRC -> PDCP -> RLC -> MAC -> PHY | RRC -> PDCP -> F1AP -> DU -> RLC/MAC/PHY | 5G 多一层 F1AP/CU-DU 边界 |
| 下一条消息触发 | RLC ACK 触发 `send_next_test_msg()` | UL RRC / RLC ACK 回调 / pacing timer | 5G 已有 ACK 回调和 timer |
| oracle | UECapabilityEnquiry | UECapabilityEnquiry | 机制相同 |
| RLC Max Retx | RLC 同进程直接通知 RRC | DU release cause 间接通知 CU-CP RRC | 5G 只匹配 `rl_fail_rlc` / `rl_fail_others` |
| crash 记录 | `rrc::save_recent_messages()` | `rrc_ue_impl::save_otabase_recent_messages()` | 文件结构大体对齐 |
| backtracking 状态位置 | 父级 `rrc` 对象 | per-UE `rrc_ue_impl` | 这是 5G 最大差异 |
| UE 重连后的状态保留 | 更容易保留 | 容易随 `rrc_ue_impl` 销毁丢失 | 5G 尚未完全等价 |
| RRC 状态 | LTE eNB UE 状态机 | `idle / connected / connected_inactive` | 5G 只应在 connected 发送 DL-DCCH |

## 当前 5G 尚未完全等价 4G 的点

当前 5G 已经实现了很多 4G 行为：

- payload 文件读取；
- `testFileIndex` 进度回写；
- RRC oracle；
- backtracking；
- crash 文件落盘；
- blacklist / temp blacklist；
- RLC ACK 回调；
- RLC Max Retx cause 处理；
- preliminary crash save。

但仍有一个结构性差异：**5G 的 OTABase 状态仍放在每个 `rrc_ue_impl` 中，而不是放在更持久的 RRC/CU-CP session 中。**

这会导致：

- UE context 被释放后，backtracking 状态可能丢失；
- UE 重连后，新 `rrc_ue_impl` 不自然继承旧队列；
- preliminary save 能避免“完全没有记录”，但不等于 4G 那种跨重连继续精确 backtracking；
- 如果 DU initiated release 的 cause 不是 `rl_fail_rlc` / `rl_fail_others`，当前 RLC Max Retx 兜底不一定触发。

## 后续修改 5G 的推荐方向

目标：让 5G RRC fuzzing 行为更接近 4G OTABase。

推荐修改顺序：

1. 新增一个长生命周期的 OTABase RRC fuzzing session/state。

   不要继续把所有状态都放在 `rrc_ue_impl`。应将下面这些状态上移：

   - payload 文件名、当前行号、总行数；
   - 最近消息队列；
   - backtracking 开关、编号、当前 candidate；
   - crash counter；
   - blacklist / temp blacklist；
   - crash 保存逻辑。

2. 让新的 `rrc_ue_impl` 复用同一个 session。

   UE 崩溃并重连后，新 RRC UE 对象应能继续旧 session 的 backtracking，而不是从空状态开始。

3. 对 DU initiated UE context release 增加兜底记录。

   当前只处理 `rl_fail_rlc` / `rl_fail_others`。建议在 OTABase 开启且最近消息队列非空时，对更多 UE release 场景至少做 preliminary save，并记录 cause，避免 crash 后没有编号。

4. 保留 `rrc_state::connected` 限制。

   不建议在 `idle` 或 `connected_inactive` 中直接发送 DL-DCCH fuzz payload。若需要“保持手机处于 CONNECTED”，应通过配置或状态控制减少 inactivity/release，而不是绕过 RRC 状态机。

5. 明确单 UE 测试假设或实现多 UE 隔离。

   4G OTABase 通常按单目标 UE OTA 测试理解。5G 若要支持多 UE，需要按 UE/session 隔离 recent queue、candidate、blacklist，否则 crash 归因可能串号。

## 建议运行配置

### 4G RRC

上游 OTABase 的 RRC 执行方式是：

```bash
cd artifact/otabase/build/srsenb/src
cp ../../../example-test-case/rrc/* .
echo rrcTest1 > testFileIndex
sudo ./srsenb ../../../conf/enb/enb.conf --target_protocol=rrc --o=<outdir> --rf.dl_earfcn=<earfcn>
```

实际参数以本地构建和 RF 环境为准。

### 5G RRC

建议使用绝对路径，避免工作目录造成误判：

```yaml
cu_cp:
  rrc:
    otabase_enable_5g_rrc_fuzzing: true
    otabase_test_index_file: /home/nanfeng/projects/OTABaseMine/bishe/generate_new/output_5g/testFileIndex
    otabase_output_directory: /home/nanfeng/projects/OTABaseMine/artifact/srsRAN_Project/otabase_crashes
    otabase_check_period: 10
    otabase_replay_mode: false
    otabase_temp_blacklist: true
    otabase_pacing_ms: 5
    otabase_inject_after_auth_only: true
```

`otabase_inject_after_auth_only=true` 更适合先验证稳定的 CONNECTED 后注入；如果需要测试认证前路径，再改为 `false`。

## 文档维护原则

本 README 是本仓库 RRC 相关的主文档。后续如果继续修改 `artifact/otabase` 或 `artifact/srsRAN_Project` 的 RRC fuzzing 行为，应优先更新这里，避免多个 Markdown 互相矛盾。

保留第三方/上游项目自身 README 的原因是它们属于 vendored 项目的原始说明；本仓库对 4G/5G RRC fuzzing 的判断以本 README 和源码为准。

## 参考

- OTABase: https://github.com/OTABase/OTABase
- srsRAN Project: https://github.com/srsran/srsRAN_Project
- 3GPP TS 36.331: LTE RRC
- 3GPP TS 38.331: NR RRC
