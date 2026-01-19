"""
OCTET_STRING Field Mutation Tool

Implements BASE mutation strategy for OCTET_STRING type fields in RRC messages.
Based on OTABase fuzzing strategy.
"""

import math
import random
from typing import List, Dict, Any, Optional, Tuple
from copy import deepcopy
from .mutation_utils import (
    bytes_to_bit_str,
    bit_str_to_bytes,
    generate_random_bytes,
    encode_unbound_length,
    decode_unbound_length,
    generate_invalid_length_encoding,
    calculate_bit_length
)


# Constants from OTABase
MAX_OTA_RRC_PACKET_SIZE = 2048
OVERFLOW_LEN = 100


def mutate_octet_string_field(
    message: Dict[str, Any],
    target_path: List[str],
    message_type: str,
    constrained: bool = True,
    lower_bound: Optional[int] = None,
    upper_bound: Optional[int] = None,
    current_value: Optional[bytes] = None,
    seed: int = None
) -> List[Dict[str, Any]]:
    """
    Mutate an OCTET_STRING field using BASE strategy.
    
    The BASE strategy mutates both the length field and content of OCTET_STRING,
    exploiting mismatches between declared length and actual content.
    
    For CONSTRAINED OCTET_STRING:
    - Length is encoded in a fixed number of bits
    - Mutations test boundary conditions and length/content mismatches
    
    For UNCONSTRAINED OCTET_STRING:
    - Length is encoded using PER unbounded length encoding
    - Mutations test various length encodings and invalid encodings
    
    Args:
        message: Complete RRC message dictionary
        target_path: Path to the OCTET_STRING field
        message_type: Type of RRC message
        constrained: Whether the OCTET_STRING has length constraints
        lower_bound: Lower bound of length constraint (for constrained)
        upper_bound: Upper bound of length constraint (for constrained)
        current_value: Current value of the field (bytes)
        seed: Random seed for reproducibility
        
    Returns:
        List of mutated message dictionaries with metadata
        
    Example:
        >>> # Constrained OCTET_STRING
        >>> mutations = mutate_octet_string_field(
        ...     message=dl_dcch_message,
        ...     target_path=['message', 'c1', 'csfbParametersResponseCDMA2000',
        ...                  'criticalExtensions', 'csfbParametersResponseCDMA2000-r8',
        ...                  'mobilityParameters'],
        ...     message_type='csfbParametersResponseCDMA2000',
        ...     constrained=True,
        ...     lower_bound=0,
        ...     upper_bound=255,
        ...     current_value=b'\\x00'
        ... )
    """
    if seed is not None:
        random.seed(seed)
    
    if constrained:
        return _mutate_constrained_octet_string(
            message, target_path, message_type, 
            lower_bound, upper_bound, current_value
        )
    else:
        return _mutate_unconstrained_octet_string(
            message, target_path, message_type, current_value
        )


def _mutate_constrained_octet_string(
    message: Dict[str, Any],
    target_path: List[str],
    message_type: str,
    lower_bound: int,
    upper_bound: int,
    current_value: Optional[bytes]
) -> List[Dict[str, Any]]:
    """
    Mutate a constrained OCTET_STRING field.
    
    Mutations for constrained OCTET_STRING:
    1. Valid length with empty content
    2. Length = 0 with overflow content
    3. Length = content_length - 1 (underflow)
    4. Max encoded length with max content
    """
    mutations = []
    
    # Calculate bit size for length encoding
    field_max_length = upper_bound - lower_bound
    len_bit_size = calculate_bit_length(0, field_max_length)
    field_max_encoded_length = 2**len_bit_size - 1
    
    # Get current field value
    if current_value is None:
        current_value = b''
    
    # Mutation 1: Length set to valid value, buffer content empty
    length = random.randint(0, field_max_length - 1) if field_max_length > 1 else 0
    mutation1 = deepcopy(message)
    mutation1 = _set_octet_value(mutation1, target_path, b'')
    mutations.append({
        'message': mutation1,
        'mutation_type': 'valid_length_empty_content',
        'mutation_description': f'Length={length}, Content=empty (length/content mismatch)',
        'target_field_path': target_path,
        'message_type': message_type,
        'length_value': length,
        'content_length': 0
    })
    
    # Mutation 2: Length set to 0, buffer content set to OVERFLOW_LEN
    mutation2 = deepcopy(message)
    overflow_content = generate_random_bytes(OVERFLOW_LEN)
    mutation2 = _set_octet_value(mutation2, target_path, overflow_content)
    mutations.append({
        'message': mutation2,
        'mutation_type': 'zero_length_overflow_content',
        'mutation_description': f'Length=0, Content={OVERFLOW_LEN} bytes (buffer overflow)',
        'target_field_path': target_path,
        'message_type': message_type,
        'length_value': 0,
        'content_length': OVERFLOW_LEN
    })
    
    # Mutation 3: Length = content_length - 1 (underflow condition)
    if field_max_length > 1:
        length = random.randint(0, field_max_length - 1)
        content_length = length + lower_bound + 1
        mutation3 = deepcopy(message)
        content = generate_random_bytes(content_length)
        mutation3 = _set_octet_value(mutation3, target_path, content)
        mutations.append({
            'message': mutation3,
            'mutation_type': 'length_underflow',
            'mutation_description': f'Length={length}, Content={content_length} bytes (underflow)',
            'target_field_path': target_path,
            'message_type': message_type,
            'length_value': length,
            'content_length': content_length
        })
    
    # Mutation 4: Max encoded length with max content size
    mutation4 = deepcopy(message)
    max_content = generate_random_bytes(upper_bound)
    mutation4 = _set_octet_value(mutation4, target_path, max_content)
    mutations.append({
        'message': mutation4,
        'mutation_type': 'max_length_max_content',
        'mutation_description': f'Length={field_max_encoded_length}, Content={upper_bound} bytes (max values)',
        'target_field_path': target_path,
        'message_type': message_type,
        'length_value': field_max_encoded_length,
        'content_length': upper_bound
    })
    
    return mutations


def _mutate_unconstrained_octet_string(
    message: Dict[str, Any],
    target_path: List[str],
    message_type: str,
    current_value: Optional[bytes]
) -> List[Dict[str, Any]]:
    """
    Mutate an unconstrained OCTET_STRING field.
    
    Mutations for unconstrained OCTET_STRING:
    - Various length encodings: 0, 127, 128, 2^14-1, 2^14, etc.
    - Invalid length encodings
    - Empty content
    - Content smaller than declared length
    """
    mutations = []
    
    # Length mutations based on PER encoding boundaries
    length_mutations = [0, 127, 128, 2**14 - 1, 2**14, 
                       2*(2**14), 2*(2**14) + 1, 
                       3*(2**14), 3*(2**14) + 1, 
                       2**16 - 1]
    
    if current_value is None:
        current_value = b''
    
    for length in length_mutations:
        # Mutation A: Empty content with declared length
        mutation_a = deepcopy(message)
        mutation_a = _set_octet_value(mutation_a, target_path, b'')
        mutations.append({
            'message': mutation_a,
            'mutation_type': 'unconstrained_empty_content',
            'mutation_description': f'Declared length={length}, Content=empty',
            'target_field_path': target_path,
            'message_type': message_type,
            'declared_length': length,
            'content_length': 0
        })
        
        # Mutation B: Content length smaller than declared length
        if length > 0:
            actual_length = random.randint(1, min(MAX_OTA_RRC_PACKET_SIZE, max(1, length - 1)))
            mutation_b = deepcopy(message)
            content = generate_random_bytes(actual_length)
            mutation_b = _set_octet_value(mutation_b, target_path, content)
            mutations.append({
                'message': mutation_b,
                'mutation_type': 'unconstrained_length_mismatch',
                'mutation_description': f'Declared length={length}, Actual content={actual_length} bytes',
                'target_field_path': target_path,
                'message_type': message_type,
                'declared_length': length,
                'content_length': actual_length
            })
    
    # Invalid length encoding mutations
    invalid_length_bytes = generate_invalid_length_encoding()
    invalid_length = int.from_bytes(invalid_length_bytes, 'big')
    
    # Mutation: Invalid length with empty content
    mutation_inv1 = deepcopy(message)
    mutation_inv1 = _set_octet_value(mutation_inv1, target_path, b'')
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
        actual_length = random.randint(1, min(MAX_OTA_RRC_PACKET_SIZE, max(1, invalid_length - 1)))
        mutation_inv2 = deepcopy(message)
        content = generate_random_bytes(actual_length)
        mutation_inv2 = _set_octet_value(mutation_inv2, target_path, content)
        mutations.append({
            'message': mutation_inv2,
            'mutation_type': 'invalid_length_with_content',
            'mutation_description': f'Invalid length encoding, content={actual_length} bytes',
            'target_field_path': target_path,
            'message_type': message_type,
            'declared_length': invalid_length,
            'content_length': actual_length
        })
    
    return mutations


def _set_octet_value(message: Dict[str, Any], path: List[str], value: bytes) -> Dict[str, Any]:
    """
    Helper function to set an OCTET_STRING value at a specific path.
    
    Args:
        message: RRC message dictionary
        path: Path to the field
        value: Bytes value to set
        
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
                modified_value = _set_octet_value(current[1], remaining_path, value)
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
def octet_string_mutation_tool(
    message: Dict[str, Any],
    target_path: List[str],
    message_type: str,
    constrained: bool = True,
    lower_bound: Optional[int] = None,
    upper_bound: Optional[int] = None,
    current_value: Optional[bytes] = None,
    seed: int = None
) -> Dict[str, Any]:
    """
    Agent tool interface for OCTET_STRING field mutation.
    
    Args:
        message: Complete RRC message dictionary
        target_path: Path to the OCTET_STRING field
        message_type: RRC message type
        constrained: Whether the field has length constraints
        lower_bound: Lower bound (for constrained)
        upper_bound: Upper bound (for constrained)
        current_value: Current field value
        seed: Random seed
        
    Returns:
        Dictionary with mutations and metadata
        
    Example:
        >>> result = octet_string_mutation_tool(
        ...     message=dl_dcch_message,
        ...     target_path=['message', 'c1', '...', 'mobilityParameters'],
        ...     message_type='csfbParametersResponseCDMA2000',
        ...     constrained=True,
        ...     lower_bound=0,
        ...     upper_bound=255
        ... )
    """
    mutations = mutate_octet_string_field(
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
        'field_type': 'OCTET_STRING',
        'constraint_type': constraint_type,
        'target_path': target_path,
        'message_type': message_type
    }
