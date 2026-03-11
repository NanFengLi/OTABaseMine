# OTABaseMine 使用说明（整合版）

本仓库可以分成 4 个核心部分：

1. `bishe/generate_new`：生成合法 RRC 消息（4G / 5G）
2. `bishe/mutated`：对合法 RRC 消息进行大模型/手动变异
3. `artifact/srsRAN_Project`：发送 5G 变异消息（gNB 侧）
4. `artifact/otabase`：发送 4G 变异消息（eNB/MME 侧）

---

## 一、目录职责

### 1) 合法消息生成（4G/5G）

- 目录：`bishe/generate_new`
- 作用：生成 ASN.1 合法 RRC UPER payload，作为后续变异输入
- 输出目录：
	- 4G：`bishe/generate_new/output_4g`
	- 5G：`bishe/generate_new/output_5g`

### 2) 变异（LLM 或直接工具）

- 目录：`bishe/mutated`
- 作用：对指定字段进行 INTEGER / OCTET STRING / BIT STRING / SEQUENCE OF 变异
- 支持：
	- 4G mutator
	- 5G mutator
	- 直接工具模式（无需 LLM）

### 3) 5G 发送（srsRAN gNB）

- 目录：`artifact/srsRAN_Project`
- 作用：CU-CP RRC 层读取 `testFileIndex` 和 payload 文件，向 UE 注入变异 RRC 消息

### 4) 4G 发送（原版 OTABase）

- 目录：`artifact/otabase`
- 作用：在 4G 栈中执行 OTABase 风格变异注入

---

## 二、环境准备

建议先激活 Python 环境：

```bash
source /home/lab221/miniconda3/bin/activate bishe
```

在仓库根目录执行命令：

```bash
cd /home/lab221/Projects/OTABaseMine
```

---

## 三、如何生成合法 RRC 消息（generate_new）

### 1) 生成 4G 合法消息

```bash
python -m bishe.generate_new.main -f OCTET_STRING BIT_STRING INTEGER SEQOF
```

### 2) 生成 5G 合法消息

```bash
python -m bishe.generate_new.main --rat 5g -f OCTET_STRING BIT_STRING INTEGER SEQOF
```

### 3) 文件切分规则（已支持）

- 每个 payload 文件最多 `2000` 条（可通过 `--max-lines` 调整）
- 超过后自动写入下一个文件
- 文件名按时间戳递增，例如：
	- `rrc_legitimate_payloads_1710000000.txt`
	- `rrc_legitimate_payloads_1710000001.txt`
	- `rrc_legitimate_payloads_1710000002.txt`
- 同时生成 `testFileIndex`，指向第一个文件

示例：

```bash
python -m bishe.generate_new.main --rat 5g -f OCTET_STRING --max-lines 2000
```

---

## 四、如何做变异（mutated）

### 1) 5G 变异（推荐先用直接工具模式）

```bash
python -m bishe.mutated.langchain_agent_5g_mutator
```

- 不带参数：直接工具演示模式（无需 API Key）
- Agent 模式（需要配置 `OPENAI_API_KEY`）：

```bash
python -m bishe.mutated.langchain_agent_5g_mutator --agent
```

### 2) 4G 变异

```bash
python -m bishe.mutated.langchain_agent_4g_mutator
```

---

## 五、如何发送 5G 变异消息（srsRAN_Project）

### 1) 构建 gNB

```bash
cd artifact/srsRAN_Project
mkdir -p build
cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc) gnb
```

### 2) 配置 `testFileIndex` 路径

编辑：`artifact/srsRAN_Project/configs/otabase_fuzzing.yml`

关键项：

```yaml
cu_cp:
	rrc:
		otabase_enable_5g_rrc_fuzzing: true
		otabase_test_index_file: <你的 testFileIndex 路径>
		otabase_check_period: 10
		otabase_replay_mode: false
```

如果你用 `bishe/generate_new/output_5g` 的结果，通常填：

```yaml
otabase_test_index_file: ../../bishe/generate_new/output_5g/testFileIndex
```

（相对路径基于 gNB 运行目录 `artifact/srsRAN_Project/build`）

### 3) 启动 gNB

```bash
cd artifact/srsRAN_Project/build
sudo ./apps/gnb/gnb \
	-c ../configs/gnb_rf_b200_tdd_n78_20mhz.yml \
	-c ../configs/otabase_fuzzing.yml
```

### 4) 生效判定

- UE 进入 `RRC Connected` 后才会触发注入
- 日志中出现 `OTABase trigger=... send payload len=...` 表示正在发送变异消息

---

## 六、如何发送 4G 变异消息（artifact/otabase）

`artifact/otabase` 是原版 OTABase 4G 路径，典型流程：

1. 在 4G test-case-generator 侧准备 `testFileIndex` + payload 文件
2. 启动 `srsenb/srsepc`（或你的 4G OTABase 运行脚本）
3. eNB RRC 侧读取 `testFileIndex` 并按序注入变异消息

可参考目录内脚本：

- `artifact/otabase/build_trial.sh`
- `artifact/otabase/install.sh`
- `artifact/otabase/srsenb/`
- `artifact/otabase/srsepc/`

---

## 七、推荐端到端流程

1. 用 `generate_new` 生成 5G 合法消息（`output_5g`）
2. 用 `mutated` 对目标字段做 5G 变异，得到变异后的 payload 集
3. 组织为 OTABase 格式文件并更新 `testFileIndex`
4. 在 `srsRAN_Project` 启动 gNB 注入
5. 观察 UE 行为、崩溃/恢复、网络侧日志（含 oracle/backtracking）

---

## 八、注意事项

1. 5G gNB 必须喂 5G NR RRC payload，不能混用 4G LTE payload
2. `testFileIndex` 与 payload 文件路径需一致且可访问
3. 若从 `build/` 启动 gNB，路径解析基于配置中的 `otabase_test_index_file`
4. 输出目录 `output_4g/`、`output_5g/` 已建议忽略 Git 管理

