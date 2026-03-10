"""Test simplification: generate one packet, simplify for masterCellGroup target."""
import sys, time
sys.path.insert(0, '.')
import logging
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

from bishe.generate_new.rrc_protocol import RRCContext, RATType
from bishe.generate_new.rrc_generator import RRCGenerator
from bishe.generate_new.rrc_fields import Fields
from bishe.generate_new.rrc_utils import simplify_message, find_paths_to_delete_multi, reduce_paths
from copy import deepcopy

rrc_ctx = RRCContext(RATType.NR_5G)

generator = RRCGenerator(
    targets=[Fields.OCTET_STRING],
    seed=20,
    max_recur_depth=0,
    optional=True,
    rrc_ctx=rrc_ctx,
)

# Generate one packet
t0 = time.time()
uper_bytes, result, mutation_paths, optional_paths = generator.generate_packet()
t1 = time.time()
print(f"Generation took {t1-t0:.2f}s, hex length: {len(uper_bytes.hex())}")

# Find the masterCellGroup path
mcg_path = None
for path in mutation_paths:
    if path and path[-1] == 'masterCellGroup':
        mcg_path = path
        break

if mcg_path is None:
    print("masterCellGroup not found, listing OCTET STRING paths:")
    for path in mutation_paths:
        if path:
            print(f"  {','.join(str(x) for x in path[-3:])}")
    sys.exit(0)

print(f"Target path: ...{','.join(str(x) for x in mcg_path[-3:])}")

# Step 1: Find paths to delete
t2 = time.time()
paths_to_delete, _, childrens = find_paths_to_delete_multi([mcg_path], optional_paths)
t3 = time.time()
print(f"find_paths_to_delete: {t3-t2:.3f}s, to_delete={len(paths_to_delete)}, children={len(childrens)}")

# Step 2: Reduce paths
reduced = reduce_paths(paths_to_delete, childrens)
t4 = time.time()
print(f"reduce_paths: {t4-t3:.3f}s, reduced from {len(paths_to_delete)} to {len(reduced)}")

# Count how many are container paths
container_paths = [p for p in reduced if '*' in p]
direct_paths = [p for p in reduced if '*' not in p]
print(f"  Direct delete paths: {len(direct_paths)}")
print(f"  Container delete paths: {len(container_paths)}")

# Step 3: Actually delete and re-encode
t5 = time.time()
simplified = simplify_message(
    deepcopy(result), mcg_path, optional_paths,
    global_mod=rrc_ctx.global_mod)
t6 = time.time()
print(f"simplify_message: {t6-t5:.2f}s")

# Re-encode
bb = rrc_ctx.dl_dcch_message
bb.set_val(simplified)
simplified_hex = bb.to_uper().hex()
t7 = time.time()
print(f"re-encode: {t7-t6:.2f}s")
print(f"Result: {len(uper_bytes.hex())} -> {len(simplified_hex)} hex chars "
      f"({100*(1-len(simplified_hex)/len(uper_bytes.hex())):.1f}% smaller)")

# Verify by decoding
bb.from_uper(bytes.fromhex(simplified_hex))
val = bb.get_val()
ies = val['message'][1][1]['criticalExtensions'][1]
print(f"\nVerification - decoded simplified message:")
print(f"  rrcReconfiguration-IEs keys: {list(ies.keys())}")
if 'nonCriticalExtension' in ies:
    nce = ies['nonCriticalExtension']
    print(f"  v1530 keys: {list(nce.keys())}")
    if 'masterCellGroup' in nce:
        mcg_bytes = nce['masterCellGroup']
        print(f"  masterCellGroup bytes length: {len(mcg_bytes)}")
        print(f"  masterCellGroup hex: {mcg_bytes.hex()}")
        # Decode CellGroupConfig
        try:
            cell_grp = rrc_ctx.global_mod['CellGroupConfig']
            cell_grp.from_uper(mcg_bytes)
            cg_val = cell_grp.get_val()
            print(f"  CellGroupConfig keys: {list(cg_val.keys())}")
        except Exception as e:
            print(f"  CellGroupConfig decode error: {e}")
