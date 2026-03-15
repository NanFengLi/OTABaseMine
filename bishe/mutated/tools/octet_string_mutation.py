"""
OCTET_STRING 字段变异工具

接口：
  输入  uper_hex      — 合法 RRC 消息的 UPER 十六进制字符串
       message_type  — 消息类型名（如 "dlInformationTransfer"）
       target_path   — 目标 OCTET STRING 字段在消息树中的路径列表
  输出  变异后的 (uper_hex, message_type, target_path) 三元组列表

完全移植自 OTABase rrc_fuzzer.py::mutate_rrc_octet_field()
核心思路：直接在 UPER 比特流层面定位并替换目标字段的比特，
         绕过 pycrate 的约束校验，从而生成不合法的模糊测试数据。
"""

# ── 标准库导入 ────────────────────────────────────────────────────────────────
import math                          # 数学运算（log2 等）
import random                        # 随机数生成
from typing import List, Tuple, Optional  # 类型提示

# ── pycrate ASN.1 运行时配置 ──────────────────────────────────────────────────
from pycrate.pycrate_asn1rt.asnobj import ASN1Obj  # ASN.1 对象基类
ASN1Obj._SAFE_BND = False  # 关闭安全边界检查，允许设置超出约束范围的值
ASN1Obj._SILENT  = True    # 静默模式，抑制 pycrate 的告警输出

# ── pycrate LTE RRC 协议定义 ─────────────────────────────────────────────────
from bishe.pycrate_asn1obj.eutran_4g import RRCLTE  # 导入 LTE RRC ASN.1 模块（含所有消息定义）

# ── 自定义变异辅助工具 ───────────────────────────────────────────────────────
from .mutation_utils import (
    bytes_to_bit_str,                 # bytes → "01001..." 比特字符串
    bit_str_to_bytes,                 # "01001..." 比特字符串 → bytes（自动补齐到 8 的倍数）
    generate_random_bytes,            # 生成指定长度的随机字节
    encode_unbound_length,            # PER 无界长度决定子编码（输入整数 → 输出编码字节列表）
    generate_invalid_length_encoding, # 生成不合法的 PER 长度编码字节（用于模糊测试）
    n_random_bits,                    # 生成指定长度的随机比特串（未在本文件使用，但统一导入）
    normalize_field_path_for_get_val_at,
    get_field_type_at_value_path,
)

# ── 全局常量 ──────────────────────────────────────────────────────────────────
MAX_OTA      = 2048   # OTA（Over-The-Air）单包最大字节数限制，防止生成过大的变异包
OVERFLOW_LEN = 100    # 受约束模式下溢出变异使用的固定内容长度（100 字节）

# ══════════════════════════════════════════════════════════════════════════════
# 共享比特工具函数
# ══════════════════════════════════════════════════════════════════════════════

def _field_bits(field) -> str:
    """
    提取字段的有效 UPER 比特串（去除 pycrate to_uper() 添加的字节对齐填充位）。

    对于受约束字段，pycrate 的 to_uper() 会将输出补齐到字节边界（8 的倍数），
    但在数据包比特流中，字段之间是紧密排列的，所以要去掉末尾的填充位。

    去除规则：
      - 有 SIZE 约束时，长度头占 lbs = floor(log2(ub-lb)) + 1 位
      - 如果 lbs 不是 8 的倍数，说明 to_uper() 末尾填充了 (8 - lbs%8) 位
      - 去掉这些填充位后得到的才是数据包中字段的真实比特
    """
    # 将字段单独编码为 UPER 字节，再转为比特串
    bits = bytes_to_bit_str(field.to_uper())

    # 只有受约束的字段才需要去填充（无约束字段的 to_uper 已是精确比特）
    if field._const_sz is not None:
        # 计算约束范围的跨度
        max_len = field._const_sz.ub - field._const_sz.lb
        # 计算长度头所需的比特数
        lbs     = math.floor(math.log2(max_len)) + 1
        # 如果长度头比特数不是 8 的整数倍，则 to_uper() 末尾有填充
        if lbs % 8 != 0:
            # 去掉末尾的 (8 - lbs%8) 个填充比特
            bits = bits[:-(8 - lbs % 8)]
    return bits


def _find_all(pkt_bits: str, tgt: str) -> set:
    """
    在数据包比特串中查找目标比特串 tgt 的所有出现位置。

    参数：
        pkt_bits: 完整数据包的比特串（如 "0010110..."）
        tgt:      要查找的目标比特串

    返回：
        所有匹配起始位置的集合（可能有多个，如字段值恰好在其他位置也出现）
    """
    s, idx_set = 0, set()  # s: 当前搜索起始位置；idx_set: 存放所有匹配位置
    while True:
        i = pkt_bits.find(tgt, s)  # 从位置 s 开始查找 tgt
        if i == -1:                # 找不到了，搜索结束
            break
        idx_set.add(i)             # 记录找到的位置
        s = i + 1                  # 下一次从 i+1 开始查找（允许重叠匹配）
    return idx_set


def _find_index(pkt_bits: str, fld_bits: str, val_path: list, packet, fld, old_val) -> int:
    """
    在数据包比特串中精确定位目标字段的起始比特位置。
    old_val 由调用方在 to_uper() 之前获取并传入，避免 to_uper() 修改内部状态后 get_val_at 失败。
    """
    idxs = _find_all(pkt_bits, fld_bits)
    if not idxs:
        raise ValueError("字段未在数据包比特流中找到")
    if len(idxs) == 1:
        return idxs.pop()

    original_idxs = set(idxs)
    new = old_val
    while new == old_val:
        new = random.randbytes(len(old_val))

    packet.set_val_at(val_path, new)
    fld._val = new

    new_bits = _field_bits(fld)
    new_pkt  = bytes_to_bit_str(packet.to_uper())
    idxs     = _find_all(new_pkt, new_bits) & original_idxs

    if not idxs:
        return min(original_idxs)
    return min(idxs)


def _replace(pkt_bits: str, fld_bits: str, idx: int, mut: str) -> str:
    """
    在数据包比特串中，将从 idx 开始、长度为 len(fld_bits) 的原始字段比特
    替换为变异后的比特串 mut。

    变异比特串 mut 的长度可以与原始字段不同，从而产生长度变化的畸形数据包。

    参数：
        pkt_bits: 完整数据包的比特串
        fld_bits: 原始字段的比特串（用于确定替换范围）
        idx:      字段在数据包中的起始比特位置
        mut:      用于替换的变异比特串

    返回：
        替换后的新数据包比特串
    """
    # 保留 idx 之前的部分 + 变异比特 + idx+原始字段长度 之后的部分
    return pkt_bits[:idx] + mut + pkt_bits[idx + len(fld_bits):]

# ══════════════════════════════════════════════════════════════════════════════
# 变异比特生成（核心逻辑）
# ══════════════════════════════════════════════════════════════════════════════

def _constrained_octet_muts(field) -> List[Tuple[str, int]]:
    """
    受约束 OCTET STRING 变异（字段有 SIZE(lb..ub) 约束），共 4 条。
    移植自 OTABase mutate_rrc_octet_field()。

    UPER 编码格式：[长度头: lbs 位][内容: N 字节]
      - 长度头编码的是 (实际长度 - lb) 的偏移量，范围 0..(ub-lb)
      - lbs = floor(log2(ub - lb)) + 1，即表示最大范围所需的最少比特数
      - 最大可编码长度值 maxe = 2^lbs - 1（可能超出 ub-lb，属于非法值）

    返回：
        [(变异比特串, 字节大小变化量), ...] 的列表，共 4 条
    """
    # 获取字段的原始 UPER 编码（包含长度头 + 内容）
    fb    = field.to_uper()          # 字段完整 UPER 编码的字节（bytes）
    # 获取字段的纯内容值（不含长度编码头）
    fval  = field.get_val_at([])     # 字段的原始值（bytes），即纯 OCTET STRING 内容
    # 记录原始编码的字节数，用于计算变异后的大小变化
    fsz   = len(fb)                  # 原始编码的总字节数
    # 从 SIZE 约束中计算可编码的最大长度范围
    maxl  = field._const_sz.ub - field._const_sz.lb   # 约束范围跨度 = ub - lb
    # 长度头需要的比特数：能表示 0..maxl 所需的最少比特
    lbs   = math.floor(math.log2(maxl)) + 1           # 长度头比特数
    # 长度头能表示的最大数值（若 lbs=5 则 maxe=31，可能超过实际约束上界）
    maxe  = 2**lbs - 1               # 长度头可编码的最大值

    def gen(length: int, clen: int):
        """
        构造一条变异的字段比特串。

        参数：
            length: 写入长度头的值（编码为 lbs 个比特）
            clen:   实际填充的内容字节数

        返回：
            (比特串, 字节大小变化量 × 8) 的元组

        内容构造逻辑：
          - 如果要求的内容长度 clen > 原始值长度，则在原始值后面追加随机字节补足
          - 如果 clen ≤ 原始值长度，则截取原始值的前 clen 个字节
        """
        # 构造内容字节：不够则追加随机字节，多余则截取原始值
        content = (fval + generate_random_bytes(clen - len(fval))
                   if clen > len(fval) else fval[:clen])
        # 将长度值编码为 lbs 位的二进制字符串，拼接内容的比特串
        bits  = format(length, f"0{lbs}b") + bytes_to_bit_str(content)
        # 计算变异后字节数与原始字节数的差异（× 8 转为比特数）
        delta = len(bit_str_to_bytes(bits)) - fsz
        return (bits, delta * 8)

    # 生成一个随机的合法长度偏移值，范围 [0, maxl-1]
    r = random.randint(0, max(0, maxl - 1))

    return [
        # 变异 1：长度头声明为随机合法值 r，但内容为空（0 字节）
        # 效果：解码器读到长度后期望读 r+lb 字节内容，但实际没有 → 缓冲区下溢
        gen(r, 0),

        # 变异 2：长度头声明为 0（即实际长度 = lb），但塞入 100 字节内容
        # 效果：解码器只读 lb 字节，剩余字节被当作下一个字段解析 → 解析错乱
        gen(0, OVERFLOW_LEN),

        # 变异 3：随机合法长度，但内容字节数 = 随机合法长度 + lb + 1（比声明多 1 字节）
        # 效果：多出的 1 字节干扰后续字段的解析
        gen(random.randint(0, max(0, maxl - 1)),
            random.randint(0, max(0, maxl - 1)) + field._const_sz.lb + 1),

        # 变异 4：长度头设为 maxe（长度头能表示的最大值，通常 > maxl，属于非法值）
        #         内容填满 ub 字节
        # 效果：长度值超出约束范围，测试解码器的越界处理
        gen(maxe, field._const_sz.ub),
    ]


def _unconstrained_octet_muts(field) -> List[Tuple[str, int]]:
    """
    无约束 OCTET STRING 变异（字段无 SIZE 约束），共 22 条。
    移植自 OTABase mutate_rrc_octet_field()。

    无约束 OCTET STRING 在 UPER 中的编码格式：
      [长度决定子（变长）][内容字节]

    长度决定子的编码规则（PER 规范的无界长度编码）：
      - 长度 0~127     → 1 字节: 首位=0，后 7 位为长度值（如 0x00~0x7F）
      - 长度 128~16383  → 2 字节: 首两位=10，后 14 位为长度值（如 0x8080~0xBFFF）
      - 长度 ≥16384     → 分片编码: 首字节高 2 位=11，低 6 位×16384 为本片长度

    变异策略：10 个边界长度值 × 每个 2 条 + 2 条非法长度 = 22 条

    返回：
        [(变异比特串, 字节大小变化量 × 8), ...] 的列表，共 22 条
    """
    # 获取字段的原始 UPER 编码（长度决定子 + 内容），用于计算大小差异
    fb   = field.to_uper()       # 字段完整 UPER 编码（bytes），包含长度头 + 内容
    # 获取字段的纯内容值；CONTAINING 等类型可能返回非 bytes，统一转为 bytes
    fval = field.get_val_at([])
    if not isinstance(fval, (bytes, bytearray)):
        fval = b""
    # 原始编码的总字节数
    fsz  = len(fb)               # 原始编码字节数，用于计算 delta
    # 初始化变异结果列表
    muts = []                    # 存放所有 (变异比特串, delta) 元组

    def gen(enc: list, clen: int):
        """
        构造一条无约束 OCTET STRING 的变异字段。

        参数：
            enc:  encode_unbound_length() 的返回值，列表格式 [长度编码字节(bytes)]
            clen: 实际填充的内容字节数

        返回：
            (变异比特串, 字节大小变化量 × 8)

        构造方式：
          - 将 enc[0]（长度决定子的编码字节）与 content（内容字节）拼接
          - 再将拼接后的字节转为比特串，作为替换原始字段的变异比特
        """
        # 构造内容字节：不够则追加随机字节，多余则截取原始值
        content       = (fval + generate_random_bytes(clen - len(fval))
                         if clen > len(fval) else fval[:clen])
        # 拼接：长度编码字节（enc 可能多段，如分片编码）+ 内容字节
        length_enc    = enc[0] if len(enc) == 1 else b"".join(enc)
        mutated_bytes = length_enc + content
        # 计算变异后字节数与原始字节数的差异（× 8 转为比特数）
        delta         = len(mutated_bytes) - fsz
        # 将变异字段字节逐字节转为 8 位二进制字符串，拼接成完整比特串
        return ("".join(format(b, "08b") for b in mutated_bytes), delta * 8)

    # ── 10 个边界长度值，覆盖 PER 无界长度编码的所有格式切换点 ────────────────
    #
    #  值              含义                              编码格式
    #  ─────────────   ────────────────────────────────  ──────────
    #  0               空字符串                          1 字节 (0x00)
    #  127             单字节编码的最大值                  1 字节 (0x7F)
    #  128             双字节编码的最小值                  2 字节 (0x8080)
    #  2^14 - 1        双字节编码的最大值 (16383)          2 字节 (0xBFFF)
    #  2^14            分片编码的最小值 (16384 = 1×16384) 2 字节 (0xC001)
    #  2×(2^14)        2 片分片 (32768 = 2×16384)        2 字节 (0xC002)
    #  2×(2^14) + 1    2 片 + 余数 1                     分片 + 递归编码
    #  3×(2^14)        3 片分片 (49152 = 3×16384)        2 字节 (0xC003)
    #  3×(2^14) + 1    3 片 + 余数 1                     分片 + 递归编码
    #  2^16 - 1        测试的最大值 (65535)               分片 + 递归编码
    #
    for l in [0, 127, 128, 2**14 - 1, 2**14, 2*(2**14),
              2*(2**14) + 1, 3*(2**14), 3*(2**14) + 1, 2**16 - 1]:
        # 将边界长度值 l 编码为 PER 无界长度字节
        enc  = encode_unbound_length(l)
        # 计算安全的内容上限：不超过 MAX_OTA(2048)，且不超过 l-1（确保内容不足声明长度）
        safe = max(1, min(MAX_OTA, l - 1 if l > 0 else 1))

        # 子变异 A：声明长度为 l，但内容为空（0 字节）
        # 效果：解码器按长度 l 读取内容，但无内容可读 → 缓冲区下溢
        muts.append(gen(enc, 0))

        # 子变异 B：声明长度为 l，但只填充 1~(l-1) 个随机字节
        # 效果：内容长度不足声明长度 → 解码器读到未初始化的内存或越界
        muts.append(gen(enc, random.randint(1, safe)))

    # ── 非法长度编码变异（2 条） ─────────────────────────────────────────────
    # generate_invalid_length_encoding() 返回一个 2 字节的非法 PER 长度编码
    # 其值在 0xC005~0xFFFE 之间，高 2 位为 11（分片模式标志），
    # 但低位的值不符合 PER 规范（合法分片只允许 counter=1/2/3/4）
    inv   = [generate_invalid_length_encoding()]  # 包装成列表，匹配 gen() 的 enc 参数格式
    inv_l = int.from_bytes(inv[0], "big")         # 将非法编码解释为整数，用于计算内容长度

    # 变异 21：非法长度编码 + 空内容
    # 效果：解码器尝试解析不合法的分片长度 → 可能崩溃或进入异常分支
    muts.append(gen(inv, 0))

    # 变异 22：非法长度编码 + 随机 1~inv_l-1 字节的内容
    # 效果：同上，但附带一些内容字节，测试更丰富的错误路径
    muts.append(gen(inv, random.randint(1, min(MAX_OTA, max(1, inv_l - 1)))))

    return muts

# ══════════════════════════════════════════════════════════════════════════════
# 公开接口
# ══════════════════════════════════════════════════════════════════════════════

def mutate_octet_string(
    uper_hex: str,
    message_type: str,
    target_path: List[str],
    seed: Optional[int] = None,
    max_strategies: Optional[int] = None,
) -> List[Tuple[str, str, List[str], int]]:
    """
    对合法 RRC 消息中的 OCTET STRING 字段执行比特流级变异。

    参数：
        uper_hex:        合法消息的 UPER 十六进制编码字符串
        message_type:    消息类型名称
        target_path:     目标字段在消息树中的路径列表
        seed:            随机数种子（可选）
        max_strategies:  无约束字段时，从全部策略中随机挑选的最大数量（None 表示全部使用）

    返回：
        [(mutated_uper_hex, message_type, target_path, strategy_idx), ...] 列表
        strategy_idx 为原始 1-based 编号（从全部策略中采样时保留原始编号）
    """
    # 如果指定了种子，设置随机数种子以确保结果可复现
    if seed is not None:
        random.seed(seed)

    # ── 步骤 1：解码 UPER hex 为 pycrate 消息对象 ───────────────────────────
    # 获取 DL-DCCH-Message 的 ASN.1 类型定义对象（pycrate 全局单例）
    pkt = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
    # 将 UPER 十六进制字符串解码填充到消息对象中
    pkt.from_uper(bytes.fromhex(uper_hex))

    # ── 步骤 2：获取并初始化目标字段 ────────────────────────────────────────
    val_path = normalize_field_path_for_get_val_at(target_path)

    fld = get_field_type_at_value_path(pkt, val_path)
    old_val = pkt.get_val_at(val_path)
    fld._val = old_val

    # ── 步骤 3：类型检查 ────────────────────────────────────────────────────
    if fld.TYPE != "OCTET STRING":
        raise TypeError(f"字段类型为 {fld.TYPE}，不是 OCTET STRING")

    # ── 步骤 4：根据约束类型生成变异比特串，并记录原始 1-based 策略编号 ────────
    if fld._const_sz is not None:
        bit_muts = _constrained_octet_muts(fld)
        strategy_indices = list(range(1, len(bit_muts) + 1))
    else:
        bit_muts = _unconstrained_octet_muts(fld)
        if max_strategies is not None and max_strategies < len(bit_muts):
            # 随机采样时保留原始编号（如从 22 中取 4 个，编号仍为 1-22 中的对应值）
            sampled = sorted(random.sample(range(len(bit_muts)), max_strategies))
            bit_muts = [bit_muts[i] for i in sampled]
            strategy_indices = [i + 1 for i in sampled]
        else:
            strategy_indices = list(range(1, len(bit_muts) + 1))

    # ── 步骤 5：在数据包比特流中定位字段的精确位置 ──────────────────────────
    pkt_bits  = bytes_to_bit_str(pkt.to_uper())
    fld_bits  = _field_bits(fld)

    # to_uper() 可能修改 pycrate 内部状态，需重新加载确保 _find_index 中 set_val_at 可用
    pkt.from_uper(bytes.fromhex(uper_hex))
    fld_idx   = _find_index(pkt_bits, fld_bits, val_path, pkt, fld, old_val)

    pkt.from_uper(bytes.fromhex(uper_hex))
    pkt_bits = bytes_to_bit_str(pkt.to_uper())

    # ── 步骤 6：逐条替换字段比特，生成变异数据包 ────────────────────────────
    results = []  # 存放最终结果的列表
    for strategy_idx, (mut_bits, _delta) in zip(strategy_indices, bit_muts):
        mutated = bit_str_to_bytes(_replace(pkt_bits, fld_bits, fld_idx, mut_bits))
        results.append((mutated.hex(), message_type, target_path, strategy_idx))

    return results
