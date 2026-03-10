"""
验证 UPER 无约束 OCTET STRING 长度=128 时的长度决定子编码。

根据 ASN.1 X.691 §11.9：
  - 0~127:    1 字节  0xxxxxxx
  - 128~16383: 2 字节  10xxxxxx xxxxxxxx

"""

from pycrate.pycrate_asn1rt.asnobj import ASN1Obj
ASN1Obj._SAFE_BND = False
ASN1Obj._SILENT = True

from pycrate.pycrate_asn1rt.asnobj_str import OCT_STR

for length in [0, 1, 32, 127, 128, 129, 255, 256, 16383, 16384]:
    obj = OCT_STR()
    obj.set_val(b'\x00' * length)
    uper = obj.to_uper()
    bits = ''.join(format(b, '08b') for b in uper)

    # 解析长度头
    if bits[0] == '0':
        hdr = bits[:8]
        hdr_val = int(hdr, 2)
        hdr_desc = f'{hdr}  (8 bit, 值={hdr_val})'
    elif bits[:2] == '10':
        hdr = bits[:16]
        hdr_val = int(hdr[2:], 2)
        hdr_desc = f'{hdr}  (16 bit, 值={hdr_val})'
    else:
        hdr = bits[:8]
        hdr_val = int(hdr[2:], 2)
        hdr_desc = f'{hdr}  (分片, 值={hdr_val})'

    print(f'length={length:>5}  总bits={len(bits):>6}  长度头: {hdr_desc}')
