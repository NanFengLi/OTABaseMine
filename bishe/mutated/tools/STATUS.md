# Mutation Tools Status

## ✅ Completed: INTEGER Mutation

**File**: `integer_mutation.py`

**Status**: WORKING - Returns ASN.1 UPER encoded bytes

**Key Implementation Details**:
- Sets `DL_DCCH_Message._SAFE_BND = False` to allow out-of-bound values
- Uses `packet.set_val()` and `packet.set_val_at()` for mutations
- Returns `List[bytes]` (ASN.1 UPER encoded)
- Uses `deepcopy(packet._val)` for packet state reset

**Output Format**:
```python
{
    'mutations': [bytes, bytes, bytes],  # ASN.1 UPER encoded
    'count': 3,
    'strategy': 'BASE',
    'field_type': 'INTEGER',
    'target_path': [...],
    'message_type': 'csfbParametersResponseCDMA2000',
    'descriptions': [
        'Set INTEGER to random valid value: X',
        'Set INTEGER to max representable value: Y (bit overflow)',
        'Set INTEGER to overflow value: Z'
    ]
}
```

**Test Result**:
```
变异 1: Set INTEGER to random valid value: 0
  ASN.1编码(hex): 02800000000080602000
  ASN.1编码长度: 10 字节

变异 2: Set INTEGER to max representable value: 3 (bit overflow)
  ASN.1编码(hex): 06800000000080602000
  ASN.1编码长度: 10 字节

变异 3: Set INTEGER to overflow value: 4
  ASN.1编码(hex): 00800000000080602000
  ASN.1编码长度: 10 字节
```

---

## 🔄 Pending: OCTET_STRING Mutation

**File**: `octet_string_mutation.py`

**Current Status**: Returns dictionaries (WRONG)

**Required Changes**:
1. Set `_SAFE_BND = False`
2. Return ASN.1 bytes instead of dictionaries
3. Follow OTABase bit-level manipulation approach

**OTABase Strategy**:
- Mutation 1: Random length + random content
- Mutation 2: Manipulate length encoding in binary
- Mutation 3: Set max length + max content

---

## 🔄 Pending: BIT_STRING Mutation

**File**: `bit_string_mutation.py`

**Current Status**: Returns dictionaries (WRONG)

**Required Changes**:
1. Set `_SAFE_BND = False`
2. Return ASN.1 bytes instead of dictionaries
3. Implement bit-level length/content manipulation

**OTABase Strategy**:
- Similar to OCTET_STRING
- Manipulate bit string length encoding
- Manipulate bit content

---

## 🔄 Pending: SEQUENCE_OF Mutation

**File**: `sequence_of_mutation.py`

**Current Status**: Returns dictionaries (WRONG)

**Required Changes**:
1. Set `_SAFE_BND = False`
2. Return ASN.1 bytes instead of dictionaries
3. Implement sequence length manipulation at binary level

**OTABase Strategy**:
- Manipulate SEQUENCE OF length field
- Add/remove elements
- Overflow sequence count

---

## Critical Learnings

### 1. OTABase Mutation Approach
**NOT**: Modify dictionary → Encode to ASN.1
**BUT**: Encode to ASN.1 → Manipulate bits → Return bytes

### 2. Pycrate Safety Flags
- **`_SAFE_BND = False`**: Required to allow out-of-bound values
- **`_SAFE_VAL = False`**: May be needed for some mutations

### 3. Packet State Management
```python
# Save state
p = deepcopy(packet._val)

# Mutate
packet.set_val_at(target_path, new_value)
mutated = packet.to_uper()

# Reset
packet.set_val(p)
```

### 4. Message Format
Must use correct nested tuple/dict structure:
```python
{
    'message': ('c1', ('messageType', {
        'field1': value1,
        'field2': ('choice', {...})
    }))
}
```

### 5. Return Format
All tools should return:
```python
{
    'mutations': List[bytes],  # ASN.1 UPER encoded
    'count': int,
    'strategy': 'BASE',
    'field_type': str,
    'target_path': List[str],
    'message_type': str,
    'descriptions': List[str]
}
```
