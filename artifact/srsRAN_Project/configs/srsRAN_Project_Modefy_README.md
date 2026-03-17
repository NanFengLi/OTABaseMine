# srsRAN_Project 修改记录

本文档记录对 srsRAN_Project 的所有 OTABase 相关修改，包括 5G RRC fuzzing 注入功能的实现、
与 4G OTABase 的对比分析，以及各次改动的详细说明。

---

## 修改一览（按时间倒序）

| 日期 | 改动 | 涉及文件数 | 简述 |
|------|------|-----------|------|
| 2026-03-16 | **真正的 RLC ACK 通知** | 20+ | DU RLC 收到 UE 上行 status PDU 时通知 CU-CP，触发下一条（与 4G 一致） |
| 2026-03-16 | Pacing Timer 快速注入 | 11 | 模仿 4G RLC ACK 驱动，发完一条自动触发下一条（备选方案） |
| 此前 | RLC Max Retx → 立即回溯 | 4 | DU 报 RLC 失败时绕过 oracle 重试直接进入 backtracking |
| 此前 | OTABase 5G RRC Fuzzing 基础功能 | 多个 | 注入/oracle/回溯/黑名单/落盘全链路 |

---

# Part A — 4G vs 5G 注入速度对比分析

## A.1 为什么 4G (eNB) 快、5G (gNB) 慢

### 4G OTABase eNB：由 RLC ACK（Layer 2）驱动

```
发送 fuzzed RRC → UE RLC 收到 → UE RLC 回 ACK → eNB RLC 收到 ACK → 立即发下一条
```

关键代码位于 `artifact/otabase/srsenb/src/stack/upper/rlc.cc`：

```cpp
// rlc::write_pdu()
if (((payload[0] >> 7) & 0x1) == 0) {   // RLC control PDU (ACK)
    rrc->send_next_test_msg(rnti);       // 直接触发下一条
}
```

特点：
- RLC ACK 是**传输层确认**，只要 UE 收到 PDU 就会回，不管 RRC 层是否理解/处理
- 即使 fuzzed 消息是完全畸形的、UE 在 RRC 层直接丢弃，RLC ACK **照样回来**
- 4G eNB 是**单体架构**（RLC 和 RRC 在同一个进程），所以 RLC ACK 可以直接调用 `rrc->send_next_test_msg()`
- 结果：每条消息间隔 **~5ms**（无线往返时间）

### 5G srsRAN_Project gNB（改动前）：由 UL RRC 消息（Layer 3）驱动

```
发送 fuzzed RRC → UE 收到 → UE RRC 层不认识 → 静默丢弃 → 没有 UL RRC 回来 → gNB 卡住
```

关键代码位于 `lib/rrc/ue/rrc_ue_message_handlers.cpp`：

```cpp
// handle_pdu() — 只有收到以下 UL RRC 消息时才触发下一条
case rrc_setup_complete:     maybe_send_next_otabase_rrc_message("rrc_setup_complete");
case security_mode_complete: maybe_send_next_otabase_rrc_message("security_mode_complete");
case ue_cap_info:            maybe_send_next_otabase_rrc_message("oracle_ok");
case rrc_recfg_complete:     maybe_send_next_otabase_rrc_message("rrc_recfg_complete");
case rrc_reest_complete:     maybe_send_next_otabase_rrc_message("rrc_reest_complete");
```

特点：
- 5G 采用 **CU/DU 分离架构**：RLC 在 DU，RRC 在 CU-CP，通过 F1AP 通信
- **RLC ACK 只到达 DU，CU-CP 根本看不到**
- 对于被 UE 丢弃的 fuzzed 消息，没有 UL RRC 回来 → CU-CP 卡住
- 只能等 oracle 超时（1 秒）才能继续
- 结果：每条消息间隔 **~秒级**

### 速度对比

| | 4G eNB | 5G gNB（改动前） | 5G gNB（Pacing Timer） | 5G gNB（**真正 RLC ACK**） |
|---|---|---|---|---|
| **触发层级** | Layer 2（RLC ACK） | Layer 3（UL RRC） | Timer（模拟 L2） | **Layer 2（RLC ACK）** |
| **每条消息间隔** | ~5ms | ~秒级 | ~5ms | **~5ms（真实无线往返）** |
| **UE 丢弃 fuzzed 消息时** | RLC ACK 照样回来 | 卡住，等 oracle | 5ms 后自动发下一条 | **RLC ACK 照样回来** |
| **架构限制** | 无（单体） | CU/DU 分离 | 用 timer 绕过 | **DU→CU 直接回调** |

## A.2 真正的 RLC ACK 通知（已实现）

5G gNB 现已支持与 4G 一致的**真正 RLC ACK 驱动**。DU 的 RLC 收到 UE 上行 status PDU 时，
通过进程内回调通知 CU-CP，触发 `handle_rlc_ack()` → `maybe_send_next_otabase_rrc_message("rlc_ack")`。

通知链路（monolithic gNB，DU 与 CU-CP 同进程）：

```
rlc_rx_am_entity::handle_control_pdu() (lib/rlc/)
  → rx_upper_cn->on_control_pdu_received()
  → rlc_ack_du_adapter (lib/du/du_high/du_manager/du_ue/)
  → du_ue_index → gnb_cu_ue_f1ap_id (f1ap_ue_id_translator)
  → rlc_ack_to_cu_notifier(cu_id)  // 进程内 std::function 回调
  → cu_cp.on_rlc_ack_received(cu_id)
  → rrc_ue->handle_rlc_ack()
  → maybe_send_next_otabase_rrc_message("rlc_ack")
```

**Pacing Timer** 仍保留为备选：当 `otabase_pacing_ms > 0` 时，RLC ACK 与 timer 均可触发；
若 RLC ACK 先到则取消 timer。建议 `otabase_pacing_ms: 0` 时完全依赖 RLC ACK。

---

# Part B — 真正的 RLC ACK 通知（2026-03-16）

## B.0 改动原理

DU 的 RLC AM 实体在收到 UE 上行 status PDU（ACK）时，通过新增的 `rlc_rx_upper_layer_control_notifier`
通知上层。`rlc_ack_du_adapter` 将 `du_ue_index` 映射为 `gnb_cu_ue_f1ap_id`，经进程内回调
`rlc_ack_to_cu_notifier` 通知 CU-CP。CU-CP 查找对应 `rrc_ue` 并调用 `handle_rlc_ack()`，
进而触发 `maybe_send_next_otabase_rrc_message("rlc_ack")` 发送下一条测试消息。

## B.0.1 修改的文件清单

| 层级 | 文件 | 改动 |
|------|------|------|
| RLC | `include/srsran/rlc/rlc_rx.h` | 新增 `rlc_rx_upper_layer_control_notifier` |
| RLC | `lib/rlc/rlc_rx_am_entity.{h,cpp}` | 构造/调用 `rx_upper_cn` |
| RLC | `lib/rlc/rlc_am_entity.h` | 传入 `rx_upper_cn` |
| RLC | `lib/rlc/rlc_factory.cpp` | `msg.rx_upper_cn` |
| DU | `lib/du/du_high/du_manager/du_ue/du_ue_adapters.{h,cpp}` | `rlc_ack_du_adapter` |
| DU | `lib/du/du_high/du_manager/du_ue/du_ue_controller_impl.{h,cpp}` | `get_rlc_ack_notifier()` |
| DU | `include/srsran/du/du_high/du_manager/du_manager_params.h` | `rlc_ack_ue_id_translator`, `rlc_ack_to_cu_notifier` |
| DU | `lib/du/du_high/du_manager/converters/rlc_config_helpers.{h,cpp}` | SRB 支持 `rx_upper_cn` |
| DU | `lib/du/du_high/du_manager/procedures/ue_creation_procedure.cpp` | SRB1 传入 `get_rlc_ack_notifier()` |
| DU | `lib/du/du_high/du_manager/procedures/ue_configuration_procedure.cpp` | SRB2 传入 `get_rlc_ack_notifier()` |
| DU | `include/srsran/du/du_high/du_high_configuration.h` | `rlc_ack_to_cu_notifier` |
| DU | `lib/du/du_high/du_high_impl.cpp` | 传入 f1ap 与 callback |
| DU | `apps/units/flexible_o_du/o_du_unit.h` | `rlc_ack_to_cu_notifier` |
| DU | `apps/units/flexible_o_du/split_helpers/flexible_o_du_factory.cpp` | 传递 callback |
| CU-CP | `include/srsran/rrc/rrc_ue.h` | `handle_rlc_ack()` |
| CU-CP | `lib/rrc/ue/rrc_ue_impl.h` | 声明 |
| CU-CP | `lib/rrc/ue/rrc_ue_message_senders.cpp` | 实现：`maybe_send_next_otabase_rrc_message("rlc_ack")` |
| CU-CP | `include/srsran/cu_cp/cu_cp.h` | `on_rlc_ack_received()` |
| CU-CP | `lib/cu_cp/cu_cp_impl.{h,cpp}` | 实现：查找 ue → `rrc_ue->handle_rlc_ack()` |
| F1AP | `include/srsran/f1ap/cu_cp/f1ap_cu.h` | `get_ue_index(gnb_cu_ue_f1ap_id_t)` |
| F1AP | `lib/f1ap/cu_cp/f1ap_cu_impl.{h,cpp}` | 实现 |
| App | `apps/gnb/gnb.cpp` | `odu_dependencies.rlc_ack_to_cu_notifier` 回调 CU-CP |

## B.0.2 配置说明

RLC ACK 通知在 monolithic gNB 下**默认启用**（gnb 创建 DU 时已绑定回调）。无需额外配置。

- `otabase_pacing_ms: 5`：RLC ACK 与 pacing timer 并存，谁先到谁触发
- `otabase_pacing_ms: 0`：完全依赖 RLC ACK，与 4G 行为一致

---

# Part C — Pacing Timer 快速注入（2026-03-16）

## C.1 改动原理

在 CU-CP 发完每条测试消息后，启动一个短定时器（默认 5ms）作为**备选触发**。当 `otabase_pacing_ms > 0` 时，
**RLC ACK** 与 **pacing timer** 均可触发下一条：谁先到谁触发，若 RLC ACK 先到则取消 timer。

流程：

```
发送 fuzzed RRC → 启动 5ms pacing timer（若 otabase_pacing_ms > 0）
                     ↓
    RLC ACK 先到 或  timer 到期 → 自动发下一条 → 再启动 timer → ...
    (若 UL RRC 先到 → 取消 timer → 用 RRC 响应触发)

每 check_period 条 → 发 oracle → 不启动 pacing timer → 等 UE 回应或 1s 超时
```

## C.2 修改的文件清单

### 配置定义（4 个文件，添加 `otabase_pacing_ms` 字段）

| 文件 | 改动 |
|------|------|
| `include/srsran/rrc/rrc_ue_config.h` | 添加 `unsigned otabase_pacing_ms = 5;` |
| `include/srsran/rrc/rrc_config.h` | 添加 `unsigned otabase_pacing_ms = 5;` |
| `include/srsran/cu_cp/cu_cp_configuration.h` | 添加 `unsigned otabase_pacing_ms = 5;` |
| `apps/units/o_cu_cp/cu_cp/cu_cp_unit_config.h` | 添加 `unsigned otabase_pacing_ms = 5;` |

### 配置解析与传递（4 个文件）

| 文件 | 改动 |
|------|------|
| `apps/units/o_cu_cp/cu_cp/cu_cp_unit_config_cli11_schema.cpp` | 添加 `--otabase_pacing_ms` CLI 选项 |
| `apps/units/o_cu_cp/cu_cp/cu_cp_unit_config_yaml_writer.cpp` | 添加 `node["otabase_pacing_ms"]` YAML 输出 |
| `apps/units/o_cu_cp/cu_cp/cu_cp_config_translators.cpp` | 添加 `out_cfg.rrc.otabase_pacing_ms = ...` |
| `lib/rrc/rrc_du_impl.cpp` | 添加 `ue_cfg.otabase_pacing_ms = cfg.otabase_pacing_ms;` |

### 核心逻辑（2 个文件）

| 文件 | 改动 |
|------|------|
| `lib/rrc/ue/rrc_ue_impl.h` | 添加 `unique_timer otabase_pacing_timer;` 和 `void start_otabase_pacing_timer();` |
| `lib/rrc/ue/rrc_ue_message_senders.cpp` | 主要逻辑改动（见下方详细 diff） |

### 配置/文档（1 个文件）

| 文件 | 改动 |
|------|------|
| `configs/otabase_fuzzing.yml` | 添加 `otabase_pacing_ms: 5` |

## C.3 核心代码改动详解

### rrc_ue_impl.h

```diff
   // OTABase oracle / backtracking / blacklisting helpers.
   void handle_rlc_max_retx() override;
   void send_ue_cap_enquiry_oracle();
   void set_otabase_oracle_timer();
   void otabase_oracle_timer_expired(timer_id_t tid);
+  void start_otabase_pacing_timer();
   void notify_rrc_oracle();
   void send_rrc_test_message_backtracking();

   // OTABase oracle / backtracking state.
+  unique_timer                           otabase_pacing_timer;
   unique_timer                           otabase_oracle_timer;
```

### rrc_ue_message_senders.cpp — maybe_send_next_otabase_rrc_message()

```diff
 void rrc_ue_impl::maybe_send_next_otabase_rrc_message(const char* trigger)
 {
   if (!context.cfg.otabase_enable_5g_rrc_fuzzing || context.state != rrc_state::connected) {
     return;
   }

+  // Cancel any running pacing timer so we don't double-fire.
+  if (otabase_pacing_timer.is_valid() && otabase_pacing_timer.is_running()) {
+    otabase_pacing_timer.stop();
+  }
+
   // ... (oracle / backtracking / normal dispatch 逻辑不变) ...

   logger.log_info("OTABase trigger={} send payload len={}B", trigger, payload_hex.size() / 2U);
   send_dl_dcch_bytes(srb_id_t::srb1, payload_hex);
+
+  // Start the pacing timer to trigger the next test message automatically.
+  start_otabase_pacing_timer();
 }
```

### rrc_ue_message_senders.cpp — 新增 start_otabase_pacing_timer()

```cpp
void rrc_ue_impl::start_otabase_pacing_timer()
{
  if (context.cfg.otabase_pacing_ms == 0) {
    return;      // 配置为 0 时禁用，回退到仅 UL RRC 触发（慢速模式）
  }

  if (!otabase_pacing_timer.is_valid()) {
    otabase_pacing_timer = cu_cp_ue_notifier.get_timer_factory().create_timer();
  }

  otabase_pacing_timer.set(std::chrono::milliseconds(context.cfg.otabase_pacing_ms),
                           [this](timer_id_t /*tid*/) {
                             maybe_send_next_otabase_rrc_message("pacing_timer");
                           });
  otabase_pacing_timer.run();
}
```

### rrc_ue_message_senders.cpp — send_rrc_test_message_backtracking()

```diff
   logger.log_info("OTABase: [Backtracking #{}] payload len={}B", ...);
   send_dl_dcch_bytes(srb_id_t::srb1, payload);
+
+  // Use pacing timer for backtracking payloads too (same as 4G).
+  start_otabase_pacing_timer();
 }
```

### rrc_ue_message_senders.cpp — handle_rlc_max_retx()

```diff
   // RLC failure supersedes any pending pacing / oracle wait; cancel timers.
+  if (otabase_pacing_timer.is_valid() && otabase_pacing_timer.is_running()) {
+    otabase_pacing_timer.stop();
+  }
   if (otabase_oracle_timer.is_running()) {
     otabase_oracle_timer.stop();
   }
```

## C.4 Timer、RLC ACK 与 Oracle 的交互关系

```
                    ┌──────────────────────────────────────────────────┐
                    │          maybe_send_next_otabase_rrc_message()    │
                    │                                                  │
                    │  1. 取消 pacing timer（防重复）                    │
                    │  2. 检查 oracle 等待中？ → 是 → return            │
                    │  3. 回溯模式？ → 是 → send_backtracking()        │
                    │  4. oracle 周期到？ → 是 → send_oracle()         │
                    │     （不启动 pacing timer，等 UE 回应）           │
                    │  5. 否则 → send_test_msg() + start_pacing_timer │
                    └──────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
  RLC ACK 到达              pacing timer 到期          UE 回了 UL RRC
  ("rlc_ack")               ("pacing_timer")           (取消 pacing timer)
          │                         │                         │
          └─────────────────────────┴─────────────────────────┘
                                    │
                                    ▼
                          再次调用 maybe_send()
                                    │
          oracle 超时 1s ────────────┼─────────────► 重试 oracle / 进入回溯
```

## C.5 配置方式

YAML（推荐）：

```yaml
cu_cp:
  rrc:
    otabase_pacing_ms: 5      # 5=RLC ACK 与 timer 并存；0=纯 RLC ACK（与 4G 一致）
```

CLI：

```bash
--otabase_pacing_ms=5
```

设为 `0` 则完全依赖 RLC ACK 触发（与 4G 一致）；设为 `5` 时 RLC ACK 与 pacing timer 并存。

---

# Part D — RLC Max Retx 立即回溯

## D.1 改动原理

4G OTABase 中，当 RLC 达到最大重传次数时会直接进入 backtracking。5G 中这个路径
原本缺失，导致需要等 oracle 超时。改动后 DU 报告 RLC Max Retx 时，CU-CP 立即
取消 oracle 等待并直接进入 backtracking。

## D.2 修改的文件

| 文件 | 改动 |
|------|------|
| `include/srsran/rrc/rrc_ue.h` | 添加 `virtual void handle_rlc_max_retx() {}` |
| `lib/cu_cp/du_processor/du_processor_impl.cpp` | 检测 `rl_fail_rlc` / `rl_fail_others` 并调用 `rrc_ue->handle_rlc_max_retx()` |
| `lib/rrc/ue/rrc_ue_impl.h` | 声明 `void handle_rlc_max_retx() override;` |
| `lib/rrc/ue/rrc_ue_message_senders.cpp` | 实现：取消 oracle timer → 设 oracle cnt 超限 → 调 notify_rrc_oracle() |

## D.3 通知链路

```
RLC AM (rlc_tx_am_entity::check_sn_reached_max_retx)
  → upper_cn.on_max_retx()
  → rlc_rlf_du_adapter::on_max_retx()
  → du_ue::handle_rlf_detection()
  → rlf_state_machine::trigger_ue_release()
  → F1AP UE Context Release Request (cause: rl_fail_rlc)
  → f1c_local_connector → CU-CP F1AP
  → du_processor_impl::handle_du_initiated_ue_context_release_request()
  → [OTABase] rrc_ue->handle_rlc_max_retx()
  → 取消 pacing/oracle timer → 直接进入 backtracking
```

---

# Part E — OTABase 5G RRC Fuzzing 基础功能说明

## 1. 功能开关位置

OTABase 的 5G RRC fuzzing 开关仍然位于：

```yaml
cu_cp:
  rrc:
    otabase_enable_5g_rrc_fuzzing: true
    otabase_test_index_file: testFileIndex
    otabase_check_period: 10
    otabase_replay_mode: false
```

对应 CLI 参数为：

```bash
--otabase_enable_5g_rrc_fuzzing
--otabase_test_index_file
--otabase_check_period
--otabase_replay_mode
```

## 2. 启用前准备（testFileIndex 与 payload 文件）

当前代码已经恢复成和原版 OTABase 一样的逻辑：固定读取文件名 `testFileIndex`。

```text
testFileIndex
```

所以现在最关键的是：

1. `gnb` 当前工作目录下必须存在一个叫 `testFileIndex` 的文件。
2. 这个文件里写的 payload 文件名，必须也能被程序正确打开。

### 2.1 编译 gNB

```bash
cd artifact/srsRAN_Project
mkdir -p build
cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j8 gnb
```

### 2.2 准备测试用例文件

先用 OTABase 的 test-case-generator 生成 RRC payload 文件，例如：

```text
rrcPayloads1
rrcPayloads2
rrcPayloads3
```

每个 payload 文件格式如下：

```text
<total_line_count>
<numbering>,<hex_payload>,<msgName>,<fieldName>
...
```

例如：

```text
100
1,0123456789ABCDEF,RRCReconfiguration,radioBearerConfig
2,AA55CC33,UECapabilityEnquiry,lateNonCriticalExtension
```

### 2.3 准备索引文件

当前固定索引文件名是：

```text
testFileIndex
```

最简单写法：

```bash
echo "rrcTest1" > testFileIndex
```

如果你想指定从某一行开始，也可以写成：

```bash
echo "rrcTest1,1,0" > testFileIndex
```

含义是：

- 第 1 个字段：当前使用的 payload 文件名
- 第 2 个字段：当前读取到的行号
- 第 3 个字段：总行数占位，当前实现里即使写 0 也可以正常工作

重要说明：

- `testFileIndex` 现在和原版 OTABase 一样，是固定文件名，不是固定绝对路径。
- 也就是说，程序会在 `gnb` 当前工作目录里查找 `testFileIndex`。
- `testFileIndex` 里面第一列如果写的是相对文件名，例如 `rrcTest1`，那么这个 payload 文件也同样按 `gnb` 当前工作目录解析。

例如你在 `artifact/srsRAN_Project/build` 目录下执行：

```bash
cd artifact/srsRAN_Project/build
sudo ./gnb ...
```

那么：

- 程序会读取 `artifact/srsRAN_Project/build/testFileIndex`
- 如果 `testFileIndex` 里写的是 `rrcTest1`，程序会继续读取 `artifact/srsRAN_Project/build/rrcTest1`

如果你的 payload 文件不在启动目录里，最稳妥的做法是让 `testFileIndex` 第一列写 payload 的绝对路径。

例如：

```text
/Users/nanfeng/Project/PythonProjects/OTABaseMine/artifact/srsRAN_Project/example-test-case/rrc/rrcTest1,1,0
```

## 3. 启用方式

支持两种方式：

### 方式 A：通过 YAML 配置启用

项目里已经提供了一个最小 OTABase 叠加配置：

`configs/otabase_fuzzing.yml`

它的内容是：

```yaml
cu_cp:
  rrc:
    otabase_enable_5g_rrc_fuzzing: true
    otabase_test_index_file: testFileIndex
    otabase_check_period: 10
    otabase_replay_mode: false
    otabase_pacing_ms: 5      # 0=纯 RLC ACK，5=RLC ACK 与 timer 并存
```

启动时叠加到原有 gNB 配置即可：

```bash
cd artifact/srsRAN_Project/build
sudo ./gnb -c ../configs/gnb_rf_b200_tdd_n78_20mhz.yml \
           -c ../configs/otabase_fuzzing.yml
```

如果你已经有自己的 gNB 配置文件，也可以直接把上面的 `cu_cp.rrc` 段合并进你的现有 YAML，而不一定非要使用叠加文件。

### 方式 B：通过命令行参数启用

如果你不想改 YAML，也可以直接在启动命令里加参数。注意这里的 `otabase_test_index_file` 现在只是兼容保留；为了和原版 OTABase 一样，当前代码实际使用的是固定文件名 `testFileIndex`：

```bash
cd artifact/srsRAN_Project/build
sudo ./gnb -c ../configs/gnb_rf_b200_tdd_n78_20mhz.yml \
    --otabase_enable_5g_rrc_fuzzing=true \
    --otabase_test_index_file=testFileIndex \
    --otabase_check_period=10 \
    --otabase_replay_mode=false
```

## 4. 全部参数说明

| YAML Key | CLI Flag | 默认值 | 说明 |
|---|---|---|---|
| `cu_cp.rrc.otabase_enable_5g_rrc_fuzzing` | `--otabase_enable_5g_rrc_fuzzing` | `false` | 总开关，必须为 true 才会启用注入 |
| `cu_cp.rrc.otabase_test_index_file` | `--otabase_test_index_file` | `testFileIndex` | 索引文件路径（支持绝对路径和相对路径） |
| `cu_cp.rrc.otabase_check_period` | `--otabase_check_period` | `10` | 每发送 N 条测试消息插入一次 oracle 检查 |
| `cu_cp.rrc.otabase_replay_mode` | `--otabase_replay_mode` | `false` | 回放模式，启用后会更频繁做 oracle 检查，并关闭 blacklist |
| `cu_cp.rrc.otabase_output_directory` | **`-o`** / `--otabase_output_directory` | 空（默认用 `otabase_crashes`） | 崩溃候选输出目录，与 4G 的 `-o` 一致；未设置时写当前目录下的 `otabase_crashes/` |
| `cu_cp.rrc.otabase_temp_blacklist` | `--otabase_temp_blacklist` | `true` | 是否启用临时黑名单（与 4G `temp_blacklist` 一致）；为 false 时仅保留永久黑名单 |
| `cu_cp.rrc.otabase_pacing_ms` | `--otabase_pacing_ms` | `5` | 注入节奏定时器（ms）。与 RLC ACK 并存时，谁先到谁触发。设为 0 则完全依赖 RLC ACK（与 4G 一致） |

建议：

- 正常 fuzzing：`otabase_check_period: 10`，`otabase_pacing_ms: 0`（纯 RLC ACK）或 `5`（RLC ACK + timer 兜底）
- 复现崩溃：`otabase_replay_mode: true`

## 5. 如何确认已经启用

启用成功后，gNB 在 UE 进入 `RRC connected` 并出现对应 UL DCCH 交互后，会开始读取当前工作目录下的 `testFileIndex`，再打开其中指定的 payload 文件，并向 UE 发送原始 DL-DCCH PDU。

你可以从以下现象确认它已经生效：

1. gNB 不再只发送标准流程消息，而会额外发送来自 payload 文件的原始 RRC 消息。
2. 每隔 `otabase_check_period` 条消息，会插入一次 `UECapabilityEnquiry` 作为 liveness oracle。
3. 如果 UE 不响应 oracle，系统会进入 backtracking 模式。
4. 当识别到候选崩溃消息后，会在 `otabase_output_directory`（未配置时为 `otabase_crashes`）下生成：

```text
{otabase_output_directory}/crashes/crash_N/candidates.json
{otabase_output_directory}/crashes/crash_count.txt
{otabase_output_directory}/candidate_list.txt
```

## 6. 典型启动流程

下面是一套最小可执行流程：

```bash
cd /Users/nanfeng/Project/PythonProjects/OTABaseMine/artifact/srsRAN_Project

# 1. 进入构建目录
cd build

# 2. 在当前目录准备 testFileIndex
echo "/Users/nanfeng/Project/PythonProjects/OTABaseMine/artifact/srsRAN_Project/example-test-case/rrc/rrcTest1,1,0" > testFileIndex

# 3. 启动 gNB，并叠加 OTABase fuzzing 配置
sudo ./gnb -c ../configs/gnb_rf_b200_tdd_n78_20mhz.yml \
           -c ../configs/otabase_fuzzing.yml
```

为了和原版 OTABase 一样，建议你在 `gnb` 启动目录下放 `testFileIndex`，并且把 `testFileIndex` 第一列写成 payload 的绝对路径，这样最稳。

## 7. 运行机制简述

1. **注入阶段**：首次由 UL RRC 事件（如 `rrc_setup_complete`）触发，之后由 **RLC ACK**（DU 收到 UE status PDU 时通知 CU-CP）或 pacing timer（默认 5ms）自动连续发送测试 payload。RLC ACK 与 4G 行为一致。
2. **Oracle 阶段**：每隔 `check_period` 条测试消息，gNB 发送一次 `UECapabilityEnquiry` 作为活性检查，并启动 1 秒定时器。此时暂停 pacing timer，等待 UE 回应。
3. **Backtracking 阶段**：若 UE 连续不响应 oracle（或 DU 报告 RLC Max Retx），则回放最近 10 条消息，按"消息 / oracle / 消息 / oracle"方式缩小触发范围。
4. **落盘阶段**：命中候选消息后，会把最近消息和候选项保存到配置的 `otabase_output_directory` 目录（未配置时为当前目录下的 `otabase_crashes`）。
