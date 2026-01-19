"""
BIT_STRING Field Mutation Tool

Implements BASE mutation strategy for BIT_STRING type fields in RRC messages.
Based on OTABase fuzzing strategy.
"""

import math
import random
from typing import List, Dict, Any, Optional, Tuple
from copy import deepcopy
from .mutation_utils import (
    bytes_to_bit_str,
    bit_str_to_bytes,
    n_random_bits,
    encode_unbound_length,
    decode_unbound_length,
    generate_invalid_length_encoding,
    calculate_bit_length
)


# Constants from OTABase
MAX_OTA_RRC_PACKET_SIZE = 2048
OVERFLOW_LEN = 100


def mutate_bit_string_field(
    message: Dict[str, Any],
    target_path: List[str],
    message_type: str,
    constrained: bool = True,
    lower_bound: Optional[int] = None,
    upper_bound: Optional[int] = None,
    current_value: Optional[Tuple[int, int]] = None,
    seed: int = None
) -> List[Dict[str, Any]]:
    """
    Mutate a BIT_STRING field using BASE strategy.
    
    BIT_STRING in pycrate is represented as a tuple (value, bit_length).
    The BASE strategy operates on bits instead of bytes, similar to OCTET_STRING.
    
    For CONSTRAINED BIT_STRING:
    - Length is encoded in a fixed number of bits
    - Mutations test boundary conditions and length/content mismatches
    
    For UNCONSTRAINED BIT_STRING:
    - Length is encoded using PER unbounded length encoding
    - Mutations test various length encodings and invalid encodings
    
    Args:
        message: Complete RRC message dictionary
        target_path: Path to the BIT_STRING field
        message_type: Type of RRC message
        constrained: Whether the BIT_STRING has length constraints
        lower_bound: Lower bound of length constraint (for constrained, in bits)
        upper_bound: Upper bound of length constraint (for constrained, in bits)
        current_value: Current value as (bit_value, bit_length) tuple
        seed: Random seed for reproducibility
        
    Returns:
        List of mutated message dictionaries with metadata
        
    Example:
        >>> # Constrained BIT_STRING (e.g., RAND in CSFBParametersResponseCDMA2000)
        >>> mutations = mutate_bit_string_field(
        ...     message=dl_dcch_message,
        ...     target_path=['message', 'c1', 'csfbParametersResponseCDMA2000',
        ...                  'criticalExtensions', 'csfbParametersResponseCDMA2000-r8',
        ...                  'rand'],
        ...     message_type='csfbParametersResponseCDMA2000',
        ...     constrained=True,
        ...     lower_bound=32,
        ...     upper_bound=32,
        ...     current_value=(0, 32)
        ... )
    """
    if seed is not None:
        random.seed(seed)
    
    if constrained:
        return _mutate_constrained_bit_string(
            message, target_path, message_type,
            lower_bound, upper_bound, current_value
        )
    else:
        return _mutate_unconstrained_bit_string(
            message, target_path, message_type, current_value
        )


def _mutate_constrained_bit_string(
    message: Dict[str, Any],
    target_path: List[str],
    message_type: str,
    lower_bound: int,
    upper_bound: int,
    current_value: Optional[Tuple[int, int]]
) -> List[Dict[str, Any]]:
    """
    Mutate a constrained BIT_STRING field.
    
    Mutations for constrained BIT_STRING:
    1. Valid length with empty content
    2. Length = 0 with overflow content
    3. Length = content_length - 1 (underflow)
    4. Max encoded length with overflow content
    """
    mutations = []
    
    # Calculate bit size for length encoding
    field_max_length = upper_bound - lower_bound
    len_bit_size = calculate_bit_length(0, field_max_length)
    
    # Get current value
    if current_value is None:
        current_value = (0, 0)
    
    # Mutation 1: Length set to valid value, buffer content empty
    if field_max_length > 1:
        length = random.randint(0, field_max_length - 1)
    else:
        length = 0
    
    mutation1 = deepcopy(message)
    mutation1 = _set_bit_string_value(mutation1, target_path, (0, 0))
    mutations.append({
        'message': mutation1,
        'mutation_type': 'valid_length_empty_content',
        'mutation_description': f'Length={length} bits, Content=empty (length/content mismatch)',
        'target_field_path': target_path,
        'message_type': message_type,
        'length_value': length,
        'content_length': 0
    })
    
    # Mutation 2: Length set to 0, buffer content set to OVERFLOW_LEN
    mutation2 = deepcopy(message)
    overflow_bits = OVERFLOW_LEN + lower_bound
    overflow_value = int(n_random_bits(overflow_bits), 2) if overflow_bits > 0 else 0
    mutation2 = _set_bit_string_value(mutation2, target_path, (overflow_value, overflow_bits))
    mutations.append({
        'message': mutation2,
        'mutation_type': 'zero_length_overflow_content',
        'mutation_description': f'Length=0, Content={overflow_bits} bits (buffer overflow)',
        'target_field_path': target_path,
        'message_type': message_type,
        'length_value': 0,
        'content_length': overflow_bits
    })
    
    # Mutation 3: Length = content_length - 1 (underflow condition)
    if field_max_length > 1:
        length = random.randint(0, field_max_length - 1)
        content_length = length + lower_bound + 1
        mutation3 = deepcopy(message)
        content_value = int(n_random_bits(content_length), 2) if content_length > 0 else 0
        mutation3 = _set_bit_string_value(mutation3, target_path, (content_value, content_length))
        mutations.append({
            'message': mutation3,
            'mutation_type': 'length_underflow',
            'mutation_description': f'Length={length}, Content={content_length} bits (underflow)',
            'target_field_path': target_path,
            'message_type': message_type,
            'length_value': length,
            'content_length': content_length
        })
    
    # Mutation 4: Max encoded length with overflow content
    field_max_length_value = 2**len_bit_size - 1
    max_overflow_bits = field_max_length_value + OVERFLOW_LEN
    mutation4 = deepcopy(message)
    max_value = int(n_random_bits(max_overflow_bits), 2) if max_overflow_bits > 0 else 0
    mutation4 = _set_bit_string_value(mutation4, target_path, (max_value, max_overflow_bits))
    mutations.append({
        'message': mutation4,
        'mutation_type': 'max_length_overflow_content',
        'mutation_description': f'Length={field_max_length_value}, Content={max_overflow_bits} bits (overflow)',
        'target_field_path': target_path,
        'message_type': message_type,
        'length_value': field_max_length_value,
        'content_length': max_overflow_bits
    })
    
    return mutations


def _mutate_unconstrained_bit_string(
    message: Dict[str, Any],
    target_path: List[str],
    message_type: str,
    current_value: Optional[Tuple[int, int]]
) -> List[Dict[str, Any]]:
    """
    Mutate an unconstrained BIT_STRING field.
    
    Mutations for unconstrained BIT_STRING:
    - Various length encodings: 0, 127, 128
    - Invalid length encodings
    - Empty content
    - Content smaller than declared length
    - Content larger than declared length (overflow)
    """
    mutations = []
    
    # Length mutations based on PER encoding boundaries
    # Limited to avoid huge packets for OTA
    length_mutations = [0, 127, 128]
    
    if current_value is None:
        current_value = (0, 0)
    
    for length in length_mutations:
        # Mutation A: Empty content with declared length
        mutation_a = deepcopy(message)
        mutation_a = _set_bit_string_value(mutation_a, target_path, (0, 0))
        mutations.append({
            'message': mutation_a,
            'mutation_type': 'unconstrained_empty_content',
            'mutation_description': f'Declared length={length} bits, Content=empty',
            'target_field_path': target_path,
            'message_type': message_type,
            'declared_length': length,
            'content_length': 0
        })
        
        # Mutation B: Content length smaller than declared length
        if length > 0:
            actual_length = random.randint(1, min(MAX_OTA_RRC_PACKET_SIZE * 8, max(1, length - 1)))
            mutation_b = deepcopy(message)
            content_value = int(n_random_bits(actual_length), 2)
            mutation_b = _set_bit_string_value(mutation_b, target_path, (content_value, actual_length))
            mutations.append({
                'message': mutation_b,
                'mutation_type': 'unconstrained_length_mismatch',
                'mutation_description': f'Declared length={length}, Actual content={actual_length} bits',
                'target_field_path': target_path,
                'message_type': message_type,
                'declared_length': length,
                'content_length': actual_length
            })
        
        # Mutation C: Content larger than declared length (overflow)
        overflow_length = min(MAX_OTA_RRC_PACKET_SIZE * 8, length + OVERFLOW_LEN)
        mutation_c = deepcopy(message)
        overflow_value = int(n_random_bits(overflow_length), 2) if overflow_length > 0 else 0
        mutation_c = _set_bit_string_value(mutation_c, target_path, (overflow_value, overflow_length))
        mutations.append({
            'message': mutation_c,
            'mutation_type': 'unconstrained_overflow',
            'mutation_description': f'Declared length={length}, Content={overflow_length} bits (overflow)',
            'target_field_path': target_path,
            'message_type': message_type,
            'declared_length': length,
            'content_length': overflow_length
        })
    
    # Invalid length encoding mutations
    invalid_length_bytes = generate_invalid_length_encoding()
    invalid_length = int.from_bytes(invalid_length_bytes, 'big')
    
    # Mutation: Invalid length with empty content
    mutation_inv1 = deepcopy(message)
    mutation_inv1 = _set_bit_string_value(mutation_inv1, target_path, (0, 0))
    mutations.append({
        'message': mutation_inv1,
        'mutation_type': 'invalid_length_encoding',
        'mutation_description': f'Invalid length encoding (0x{invalid_length_bytes.hex()}), empty content',
        'target_field_path': target_path,
        'message_type': message_type,
        'declared_length': invalid_length,
        'content_length': 0
    })
    
    # Mutation: Invalid length with some content
    if invalid_length > 0:
        actual_length = random.randint(1, min(MAX_OTA_RRC_PACKET_SIZE * 8, max(1, invalid_length - 1)))
        mutation_inv2 = deepcopy(message)
        content_value = int(n_random_bits(actual_length), 2)
        mutation_inv2 = _set_bit_string_value(mutation_inv2, target_path, (content_value, actual_length))
        mutations.append({
            'message': mutation_inv2,
            'mutation_type': 'invalid_length_with_content',
            'mutation_description': f'Invalid length encoding, content={actual_length} bits',
            'target_field_path': target_path,
            'message_type': message_type,
            'declared_length': invalid_length,
            'content_length': actual_length
        })
    
    # Mutation: Invalid length with overflow content
    overflow_length = min(MAX_OTA_RRC_PACKET_SIZE * 8, invalid_length + OVERFLOW_LEN)
    mutation_inv3 = deepcopy(message)
    overflow_value = int(n_random_bits(overflow_length), 2) if overflow_length > 0 else 0
    mutation_inv3 = _set_bit_string_value(mutation_inv3, target_path, (overflow_value, overflow_length))
    mutations.append({
        'message': mutation_inv3,
        'mutation_type': 'invalid_length_overflow',
        'mutation_description': f'Invalid length encoding, content={overflow_length} bits (overflow)',
        'target_field_path': target_path,
        'message_type': message_type,
        'declared_length': invalid_length,
        'content_length': overflow_length
    })
    
    return mutations


def _set_bit_string_value(
    message: Dict[str, Any], 
    path: List[str], 
    value: Tuple[int, int]
) -> Dict[str, Any]:
    """
    Helper function to set a BIT_STRING value at a specific path.
    
    Args:
        message: RRC message dictionary
        path: Path to the field
        value: BIT_STRING value as (bit_value, bit_length) tuple
        
    Returns:
        Modified message
    """
    if not path:
        return value
    
    current = message
    for i, key in enumerate(path[:-1]):
        if isinstance(current, tuple):
            if current[0] == key:
                remaining_path = path[i+1:]
                modified_value = _set_bit_string_value(current[1], remaining_path, value)
                return (current[0], modified_value)
            else:
                raise KeyError(f"Choice mismatch in path")
        elif isinstance(current, dict):
            if key not in current:
                raise KeyError(f"Key '{key}' not found in message")
            if i == len(path) - 2:
                break
            current = current[key]
        else:
            raise TypeError(f"Unexpected type {type(current)} at path element {key}")
    
    final_key = path[-1]
    if isinstance(current, dict):
        current[final_key] = value
        
    return message


# Tool interface for agent
def bit_string_mutation_tool(
    message: Dict[str, Any],
    target_path: List[str],
    message_type: str,
    constrained: bool = True,
    lower_bound: Optional[int] = None,
    upper_bound: Optional[int] = None,
    current_value: Optional[Tuple[int, int]] = None,
    seed: int = None
) -> Dict[str, Any]:
    """
    Agent tool interface for BIT_STRING field mutation.
    
    Args:
        message: Complete RRC message dictionary
        target_path: Path to the BIT_STRING field
        message_type: RRC message type
        constrained: Whether the field has length constraints
        lower_bound: Lower bound in bits (for constrained)
        upper_bound: Upper bound in bits (for constrained)
        current_value: Current field value as (value, length) tuple
        seed: Random seed
        
    Returns:
        Dictionary with mutations and metadata
        
    Example:
        >>> result = bit_string_mutation_tool(
        ...     message=dl_dcch_message,
        ...     target_path=['message', 'c1', '...', 'rand'],
        ...     message_type='csfbParametersResponseCDMA2000',
        ...     constrained=True,
        ...     lower_bound=32,
        ...     upper_bound=32,
        ...     current_value=(0, 32)
        ... )
    """
    mutations = mutate_bit_string_field(
        message=message,
        target_path=target_path,
        message_type=message_type,
        constrained=constrained,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        current_value=current_value,
        seed=seed
    )
    
    constraint_type = "constrained" if constrained else "unconstrained"
    
    return {
        'mutations': mutations,
        'count': len(mutations),
        'strategy': 'BASE',
        'field_type': 'BIT_STRING',
        'constraint_type': constraint_type,
        'target_path': target_path,
        'message_type': message_type
    }
