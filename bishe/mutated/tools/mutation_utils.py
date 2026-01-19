"""
Mutation Utilities

Helper functions for RRC message mutation based on OTABase fuzzing strategy.
"""

import math
import random
import secrets
from typing import List, Tuple, Dict, Any, Optional


def bytes_to_bit_str(data: bytes) -> str:
    """
    Convert bytes to a bit string.
    
    Args:
        data: Bytes to convert
        
    Returns:
        String of '0' and '1' characters
    """
    return ''.join(format(byte, '08b') for byte in data)


def bit_str_to_bytes(bit_str: str) -> bytes:
    """
    Convert a bit string to bytes.
    
    Args:
        bit_str: String of '0' and '1' characters
        
    Returns:
        Bytes representation
    """
    # Pad to make length multiple of 8
    padding = (8 - len(bit_str) % 8) % 8
    bit_str += '0' * padding
    return bytes(int(bit_str[i:i+8], 2) for i in range(0, len(bit_str), 8))


def n_random_bits(n: int) -> str:
    """
    Generate a random bit string of length n.
    
    Args:
        n: Length of bit string
        
    Returns:
        Random bit string
    """
    if n == 0:
        return ''
    return format(secrets.randbits(n), f'0{n}b')


def generate_random_bytes(n: int) -> bytes:
    """
    Generate n random bytes.
    
    Args:
        n: Number of bytes to generate
        
    Returns:
        Random bytes
    """
    return bytes(random.getrandbits(8) for _ in range(n))


def encode_unbound_length(length: int) -> List[bytes]:
    """
    Encode unbounded length according to PER encoding rules.
    
    3 different cases:
    1. If length in (0, 127), encoded in 1 byte
    2. If length in (128, 16383), encoded in 2 bytes, bit 8 of octet 0 is 1, bit 7 is 0
    3. If length >= 16384, encoded in fragments
    
    Args:
        length: Length value to encode
        
    Returns:
        List of encoded length bytes
    """
    assert length < 2**16, "Length must be less than 64K"
    
    if length <= 127:
        return [length.to_bytes(1, byteorder='big')]
    elif length < 2**14:
        # Set bit 15 to 1, bit 14 to 0
        return [(length | 2**15).to_bytes(2, byteorder='big')]
    else:
        # Fragmentation case
        counter = length // 2**14
        remainder = length % 2**14
        return [(0b11 << 14 | counter).to_bytes(2, byteorder='big')] + encode_unbound_length(remainder)


def decode_unbound_length(bytes_encoding: bytes) -> int:
    """
    Decode unbounded length encoding.
    
    Args:
        bytes_encoding: Bytes to decode
        
    Returns:
        Decoded length value
    """
    byte_0 = bytes_encoding[0:1]
    encoding = int.from_bytes(byte_0, byteorder='big')
    
    if encoding & 2**7:
        # Length encoded on two bytes
        encoding = int.from_bytes(bytes_encoding[:2], byteorder='big')
        if encoding & 2**15 and encoding & 2**14:
            # Fragmentation
            counter = encoding & 0x3F  # Last 6 bits
            return 2**14 * counter
        elif encoding & 2**15:
            # Remove bit 15
            return encoding ^ 2**15
    return encoding


def generate_invalid_length_encoding() -> bytes:
    """
    Generate an invalid length encoding for testing.
    
    Returns:
        Invalid length encoding bytes
    """
    # Between 0b1100000000000101 and 0b1111111111111111
    return random.randrange(49157, 2**16 - 1).to_bytes(2, byteorder='big')


def get_path_value(message: Dict[str, Any], path: List[str]) -> Any:
    """
    Get value from a nested dictionary using a path.
    
    Args:
        message: The RRC message dictionary
        path: List of keys forming the path
        
    Returns:
        Value at the specified path
    """
    current = message
    for key in path:
        if isinstance(current, tuple):
            # Handle CHOICE: (choice_name, choice_value)
            if current[0] == key:
                current = current[1]
            else:
                raise KeyError(f"Choice mismatch: expected {key}, got {current[0]}")
        elif isinstance(current, dict):
            current = current[key]
        elif isinstance(current, list):
            # Handle SEQUENCE OF with integer index
            if isinstance(key, int):
                current = current[key]
            else:
                raise TypeError(f"List index must be int, got {type(key)}")
        else:
            raise TypeError(f"Cannot navigate through {type(current)}")
    return current


def set_path_value(message: Dict[str, Any], path: List[str], value: Any) -> Dict[str, Any]:
    """
    Set value in a nested dictionary using a path.
    
    Args:
        message: The RRC message dictionary
        path: List of keys forming the path
        value: Value to set
        
    Returns:
        Modified message dictionary
    """
    if not path:
        return value
    
    current = message
    for i, key in enumerate(path[:-1]):
        if isinstance(current, tuple):
            # Handle CHOICE
            if current[0] == key:
                # Navigate into the choice value
                current = current[1]
            else:
                raise KeyError(f"Choice mismatch: expected {key}, got {current[0]}")
        elif isinstance(current, dict):
            current = current[key]
        elif isinstance(current, list):
            if isinstance(key, int):
                current = current[key]
            else:
                raise TypeError(f"List index must be int, got {type(key)}")
        else:
            raise TypeError(f"Cannot navigate through {type(current)}")
    
    # Set the final value
    final_key = path[-1]
    if isinstance(current, dict):
        current[final_key] = value
    elif isinstance(current, tuple):
        # For tuple, we need to replace the whole tuple
        if current[0] == final_key:
            # Return modified tuple
            return (current[0], value)
    elif isinstance(current, list):
        if isinstance(final_key, int):
            current[final_key] = value
    
    return message


def calculate_bit_length(lower_bound: int, upper_bound: int) -> int:
    """
    Calculate the number of bits needed to represent a constrained integer.
    
    Args:
        lower_bound: Lower bound of the range
        upper_bound: Upper bound of the range
        
    Returns:
        Number of bits needed
    """
    range_size = upper_bound - lower_bound
    if range_size == 0:
        return 0
    return math.floor(math.log2(range_size)) + 1
