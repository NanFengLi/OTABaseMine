"""
INTEGER Field Mutation Tool

Implements the BASE mutation strategy for INTEGER fields in RRC messages,
based on the OTABase fuzzing framework.

Reference: OTABase rrc_fuzzer.py - mutate_rrc_integer_field()
"""

import math
import random
from copy import deepcopy
from typing import Any, Dict, List

from bishe.mutated.tools.mutation_utils import calculate_bit_length

# Try to import pycrate for ASN.1 encoding
try:
    from pycrate_asn1dir import RRCLTE
    DL_DCCH_Message = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
    PYCRATE_AVAILABLE = True
except ImportError:
    PYCRATE_AVAILABLE = False
    DL_DCCH_Message = None


def mutate_integer_field(
    message: Dict[str, Any],
    target_path: List[str],
    lower_bound: int,
    upper_bound: int,
    message_type: str,
    seed: int = None
) -> List[bytes]:
    """
    Mutate an INTEGER field using BASE strategy.

    The BASE strategy for INTEGER fields exploits the fact that the number of bits
    allocated for the field can represent values beyond the specification constraints.
    For example, if a field is constrained to 0-9 (spec) but uses 4 bits, it can
    actually represent 0-15.

    Mutations:
    1. Random value within valid range
    2. Maximum value representable with allocated bits
    3. Overflow: upper_bound + 1

    Args:
        message: Complete RRC message dictionary
        target_path: Path to the INTEGER field to mutate
        lower_bound: Lower bound of the INTEGER constraint
        upper_bound: Upper bound of the INTEGER constraint
        message_type: Type of RRC message (e.g., 'csfbParametersResponseCDMA2000')
        seed: Random seed for reproducibility (optional)

    Returns:
        List of ASN.1 UPER encoded bytes (mutated packets)

    Example:
        >>> message = {
        ...     'message': ('c1', ('csfbParametersResponseCDMA2000', {
        ...         'rrc-TransactionIdentifier': 0,
        ...         'criticalExtensions': ('criticalExtensionsFuture', {})
        ...     }))
        ... }
        >>> mutations = mutate_integer_field(
        ...     message=message,
        ...     target_path=['message', 'c1', 'csfbParametersResponseCDMA2000',
        ...                  'rrc-TransactionIdentifier'],
        ...     lower_bound=0,
        ...     upper_bound=3,
        ...     message_type='csfbParametersResponseCDMA2000'
        ... )
        >>> len(mutations)
        3
        >>> all(isinstance(m, bytes) for m in mutations)
        True
    """
    if not PYCRATE_AVAILABLE:
        raise ImportError("pycrate is required for mutation. Install with: pip install pycrate")

    if seed is not None:
        random.seed(seed)

    # Get the DL-DCCH-Message ASN.1 object
    packet = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message

    # Disable boundary checking to allow out-of-bound values
    packet._SAFE_BND = False

    # Set initial message
    packet.set_val(message)

    # Save initial packet value for reset
    p = deepcopy(packet._val)

    mutated_packets = []

    # Calculate the number of bits used to represent this integer
    bit_length = calculate_bit_length(lower_bound, upper_bound)
    max_representable = (2 ** bit_length - 1) + lower_bound

    # Mutation 1: Random value within valid range
    packet.set_val(p)
    random_value = random.randint(lower_bound, upper_bound)
    packet.set_val_at(target_path, random_value)
    mutated_packets.append(packet.to_uper())

    # Mutation 2: Maximum representable value (exploits bit allocation)
    packet.set_val(p)
    packet.set_val_at(target_path, max_representable)
    mutated_packets.append(packet.to_uper())

    # Mutation 3: Overflow (upper_bound + 1)
    packet.set_val(p)
    overflow_value = upper_bound + 1
    packet.set_val_at(target_path, overflow_value)
    mutated_packets.append(packet.to_uper())

    return mutated_packets


def integer_mutation_tool(
    message: Dict[str, Any],
    target_path: List[str],
    lower_bound: int,
    upper_bound: int,
    message_type: str,
    seed: int = None
) -> Dict[str, Any]:
    """
    Agent tool interface for INTEGER field mutation.

    This is the function that should be registered as an agent tool.

    Args:
        message: Complete RRC message dictionary
        target_path: Path to the INTEGER field (list of strings)
        lower_bound: Lower bound of INTEGER constraint
        upper_bound: Upper bound of INTEGER constraint
        message_type: RRC message type
        seed: Random seed for reproducibility

    Returns:
        Dictionary containing:
            - mutations: List of ASN.1 UPER encoded bytes
            - count: Number of mutations generated
            - strategy: Mutation strategy used
            - descriptions: List of mutation descriptions
    """
    mutations = mutate_integer_field(
        message=message,
        target_path=target_path,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        message_type=message_type,
        seed=seed
    )

    # Calculate bit length for descriptions
    bit_length = calculate_bit_length(lower_bound, upper_bound)
    max_representable = (2 ** bit_length - 1) + lower_bound

    # Generate random value for description (same seed)
    if seed is not None:
        random.seed(seed)
    random_value = random.randint(lower_bound, upper_bound)

    descriptions = [
        f'Set INTEGER to random valid value: {random_value}',
        f'Set INTEGER to max representable value: {max_representable} (bit overflow)',
        f'Set INTEGER to overflow value: {upper_bound + 1}'
    ]

    return {
        'mutations': mutations,  # List of bytes
        'count': len(mutations),
        'strategy': 'BASE',
        'field_type': 'INTEGER',
        'target_path': target_path,
        'message_type': message_type,
        'descriptions': descriptions
    }
