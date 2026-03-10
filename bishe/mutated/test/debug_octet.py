"""调试 OCTET STRING 变异的比特偏移问题"""
import math
import sys, os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pycrate.pycrate_asn1rt.asnobj import ASN1Obj
ASN1Obj._SAFE_BND = False
ASN1Obj._SILENT = True
from bishe.pycrate_asn1obj.eutran_4g import RRCLTE
from bishe.mutated.tools.mutation_utils import bytes_to_bit_str, encode_unbound_length

UPER_HEX = (
    "0220a61a1e100f3f6139bc5330e49a8c3e03f26ab1b74de1e2005939225c669d4bf88d73288380"
)
path = [
    "message", "c1", "csfbParametersResponseCDMA2000",
    "criticalExtensions", "csfbParametersResponseCDMA2000-r8",
    "mobilityParameters",
]

pkt = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
pkt.from_uper(bytes.fromhex(UPER_HEX))

#貌似是获取对应的字段变量
fld = pkt.get_at(path)
print(fld)
#貌似是设置对应字段变量值
fld.set_val(pkt.get_val_at(path))

#获取比特值对应的uper，目前来看没什么问题，包含长度+内容字段：201e7ec27378a661c935187c07e4d5636e9bc3c400b27244b8cd3a97f11ae65107
fb = fld.to_uper()
#获取内容字段，去除长度，验证没问题 1e7ec27378a661c935187c07e4d5636e9bc3c400b27244b8cd3a97f11ae65107
fval = fld.get_val_at([])

print(f"fld.TYPE     = {fld.TYPE}")
print(f"fld._const_sz= {fld._const_sz}")
print(f"fb (to_uper) = {len(fb)} bytes = {fb.hex()}")
print(f"fval (value) = {len(fval)} bytes = {fval.hex()}")


fb_bits = bytes_to_bit_str(fb)
fval_bits = bytes_to_bit_str(fval)
pkt_bits = bytes_to_bit_str(pkt.to_uper())

# 长度+内容的比特长度
print(f"\nfb_bits   ({len(fb_bits):>4} bits): {fb_bits}")
# 内容的比特长度
print(f"fval_bits ({len(fval_bits):>4} bits): {fval_bits}")
# 整个包的比特长度
print(f"pkt total = {len(pkt_bits)} bits")

# 搜索 fb_bits 在 pkt_bits 中的位置，暂时没问题
idx = pkt_bits.find(fb_bits)
print(f"\nfb_bits 在 pkt 中的位置: idx={idx}")

if idx >= 0:
    #获取目标字段前的16bit
    before = pkt_bits[max(0, idx-16):idx]
    #获取目标字段后的16bit
    after = pkt_bits[idx+len(fb_bits):idx+len(fb_bits)+16]
    print(f"  前 16 bit: {before}")
    print(f"  字段 bits: {fb_bits}")
    print(f"  后 16 bit: {after}")

# 检查 to_uper() 是否包含长度编码头
# 对于无约束 OCTET STRING，to_uper() 应该包含 length determinant + content
# fval 只是纯内容字节
print(f"\n--- 分析 fb 的结构 ---")
print(f"fval 长度 = {len(fval)} 字节")
# 无约束 OCTET STRING 的长度编码
enc = encode_unbound_length(len(fval))
enc_bits = bytes_to_bit_str(enc[0])
print(f"encode_unbound_length({len(fval)}) = {enc[0].hex()} = {enc_bits}")
print(f"如果 fb = 长度头 + 内容: {enc_bits}{fval_bits}")
print(f"实际 fb:                 {fb_bits}")
print(f"两者相符? {enc_bits + fval_bits == fb_bits}")

# 如果不相符，说明 to_uper() 的编码方式和我们的假设不同
if enc_bits + fval_bits != fb_bits:
    print("\n!!! to_uper() 编码与 encode_unbound_length() 不一致 !!!")
    # 看看 fb 里长度部分到底是什么
    if len(fval) <= 127:
        # 应该是 1 字节长度头
        print(f"  fb 第 1 字节 (假设长度头): {fb_bits[:8]}")
        print(f"  剩余内容: {fb_bits[8:]}")
        print(f"  fval_bits: {fval_bits}")
    else:
        # 应该是 2 字节长度头
        print(f"  fb 前 2 字节 (假设长度头): {fb_bits[:16]}")
        print(f"  剩余内容: {fb_bits[16:]}")
        print(f"  fval_bits: {fval_bits}")

# 模拟 gen(128, 0) 的替换效果
print(f"\n--- 模拟 gen(128, 0) 替换 ---")
enc128 = encode_unbound_length(128)
enc128_bits = bytes_to_bit_str(enc128[0])
mut_bits = enc128_bits  # 内容为空
print(f"变异比特: {mut_bits}  ({len(mut_bits)} bits)")
print(f"原始字段: {fb_bits}  ({len(fb_bits)} bits)")

if idx >= 0:
    result_bits = pkt_bits[:idx] + mut_bits + pkt_bits[idx + len(fb_bits):]
    # 查看替换点附近的比特
    start = max(0, idx - 8)
    end = min(len(result_bits), idx + len(mut_bits) + 8)
    print(f"\n替换后 [{start}:{end}]:")
    print(f"  {result_bits[start:idx]}|{result_bits[idx:idx+len(mut_bits)]}|{result_bits[idx+len(mut_bits):end]}")
    print(f"  {'前缀':^{idx-start}}|{'变异':^{len(mut_bits)}}|{'后缀'}")
