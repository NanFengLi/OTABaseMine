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
│   │   ├── output_4g/         #   4G 合法 payload 输出
│   │   └── output_5g/         #   5G 合法 payload 输出
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

# 可选参数
#   --max-lines 2000    每个文件最多行数（默认 2000，超出自动分文件）
#   -s 42               随机种子
#   -c 2                递归循环深度
```

输出目录：
- 4G → `bishe/generate_new/output_4g/`
- 5G → `bishe/generate_new/output_5g/`

每个目录下生成：
- `rrc_legitimate_payloads_<timestamp>.txt`（按 2000 行自动分文件）
- `testFileIndex`（指向第一个 payload 文件，供 eNB/gNB 读取）

### Step 2：批量变异

```bash
# 4G 批量变异（读取 output_4g → 输出到 mutate_output_4g）
python -m bishe.mutated.langchain_agent_4g_mutator --batch

# 5G 批量变异（读取 output_5g → 输出到 mutate_output_5g）
python -m bishe.mutated.langchain_agent_5g_mutator --batch

# 可选参数
#   --limit N           每个文件最多处理 N 行
#   --inspect-only      仅识别字段类型，不执行变异
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

# 配置 otabase_fuzzing.yml
#   otabase_enable_5g_rrc_fuzzing: true
#   otabase_test_index_file: ../../bishe/generate_new/output_5g/testFileIndex

# 启动
sudo ./apps/gnb/gnb \
    -c ../configs/gnb_rf_b200_tdd_n78_20mhz.yml \
    -c ../configs/otabase_fuzzing.yml
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
| INTEGER | 3 条 | 随机值、比特全1溢出、上界+1溢出 |
| OCTET STRING（受约束） | 4 条 | 长度/内容不匹配、边界溢出 |
| OCTET STRING（无约束） | 22 条 | 10 个 PER 长度编码边界 × 2 + 2 条非法编码 |
| BIT STRING（受约束） | 4 条 | 长度/内容不匹配（比特级） |
| BIT STRING（无约束） | 12 条 | 3 个边界长度 × 3 + 3 条非法编码 |
| SEQUENCE OF | 4 条 | 长度头：0、实际值、随机、最大编码 |

详细策略说明见 [`bishe/mutated/tools/README.md`](bishe/mutated/tools/README.md)。

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

