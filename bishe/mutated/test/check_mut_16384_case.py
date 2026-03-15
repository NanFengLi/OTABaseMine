from bishe.mutated.tools import mutate_octet_string
from bishe.pycrate_asn1obj.eutran_4g import RRCLTE
from pycrate.pycrate_asn1rt.asnobj import ASN1Obj

ASN1Obj._SAFE_BND = False
ASN1Obj._SILENT = True

orig = "0220a61a1e100f3f6139bc5330e49a8c3e03f26ab1b74de1e2005939225c669d4bf88d73288380"
mut = "0220a61a1e600080"
path = [
    "message", "c1", "csfbParametersResponseCDMA2000",
    "criticalExtensions", "csfbParametersResponseCDMA2000-r8",
    "mobilityParameters",
]


def bits(hexs: str) -> str:
    return "".join(f"{b:08b}" for b in bytes.fromhex(hexs))


pkt = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
pkt.from_uper(bytes.fromhex(orig))
fld = pkt.get_at(path)
fld.set_val(pkt.get_val_at(path))
fld_bits = bits(fld.to_uper().hex())
pkt_bits = bits(pkt.to_uper().hex())
idx = pkt_bits.find(fld_bits)

print("field_idx:", idx)
print("orig field first 24 bits:", " ".join([pkt_bits[idx + i: idx + i + 8] for i in range(0, 24, 8)]))

mbits = bits(mut)
print("mut total bits:", len(mbits))
print("mut bits at field start first 24:", " ".join([mbits[idx + i: idx + i + 8] for i in range(0, 24, 8)]))
print("mut bits at field start first 32:", " ".join([mbits[idx + i: idx + i + 8] for i in range(0, 32, 8)]))

muts = mutate_octet_string(orig, "csfbParametersResponseCDMA2000", path, seed=42)
found = None
for i, (h, _, _, _strategy) in enumerate(muts):
    if h == mut:
        found = i
        break
print("found index:", found)

for i, (h, _, _, _strategy) in enumerate(muts):
    if i in [6, 7, 8, 9, 10, 11, 12, 13, 14]:
        print(i, h)
