# OTABase 5G RRC Fuzzing 启用说明

本文档说明如何在 srsRAN_Project 的 gNB CU-CP 中启用 OTABase 5G RRC fuzzing。

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

## 2. 启用前准备

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

[configs/otabase_fuzzing.yml](/Users/nanfeng/Project/PythonProjects/OTABaseMine/artifact/srsRAN_Project/configs/otabase_fuzzing.yml)

它的内容是：

```yaml
cu_cp:
  rrc:
    otabase_enable_5g_rrc_fuzzing: true
    otabase_test_index_file: testFileIndex
    otabase_check_period: 10
    otabase_replay_mode: false
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

## 4. 参数说明

| YAML Key | CLI Flag | 默认值 | 说明 |
|---|---|---|---|
| `cu_cp.rrc.otabase_enable_5g_rrc_fuzzing` | `--otabase_enable_5g_rrc_fuzzing` | `false` | 总开关，必须为 true 才会启用注入 |
| `cu_cp.rrc.otabase_test_index_file` | `--otabase_test_index_file` | 固定文件名 `testFileIndex` | 当前保留为兼容字段 |
| `cu_cp.rrc.otabase_check_period` | `--otabase_check_period` | `10` | 每发送 N 条测试消息插入一次 oracle 检查 |
| `cu_cp.rrc.otabase_replay_mode` | `--otabase_replay_mode` | `false` | 回放模式，启用后会更频繁做 oracle 检查，并关闭 blacklist |
| `cu_cp.rrc.otabase_output_directory` | **`-o`** / `--otabase_output_directory` | 空（默认用 `otabase_crashes`） | 崩溃候选输出目录，与 4G 的 `-o` 一致；未设置时写当前目录下的 `otabase_crashes/` |
| `cu_cp.rrc.otabase_temp_blacklist` | `--otabase_temp_blacklist` | `true` | 是否启用临时黑名单（与 4G `temp_blacklist` 一致）；为 false 时仅保留永久黑名单 |

建议：

- 正常 fuzzing：`otabase_check_period: 10`
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

1. 注入阶段：在若干个 UL DCCH 完成消息之后，gNB 会读取下一条 payload，并以原始 DL-DCCH PDU 形式从 SRB1 发给 UE。
2. Oracle 阶段：每隔 `check_period` 条测试消息，gNB 发送一次 `UECapabilityEnquiry` 作为活性检查，并启动 1 秒定时器。
3. Backtracking 阶段：若 UE 连续不响应 oracle，则回放最近 10 条消息，按“消息 / oracle / 消息 / oracle”方式缩小触发范围。
4. 落盘阶段：命中候选消息后，会把最近消息和候选项保存到配置的 `otabase_output_directory` 目录（未配置时为当前目录下的 `otabase_crashes`）。
