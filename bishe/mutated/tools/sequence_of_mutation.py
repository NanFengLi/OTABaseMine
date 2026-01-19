"""
SEQUENCE OF Field Mutation Tool

Implements BASE mutation strategy for SEQUENCE OF type fields in RRC messages.
Based on OTABase fuzzing strategy.
"""

import math
import random
from typing import List, Dict, Any, Optional
from copy import deepcopy
from .mutation_utils import calculate_bit_length


def mutate_sequence_of_field(
    message: Dict[str, Any],
    target_path: List[str],
    message_type: str,
    lower_bound: int,
    upper_bound: int,
    current_value: Optional[List] = None,
    seed: int = None
) -> List[Dict[str, Any]]:
    """
    Mutate a SEQUENCE OF field using BASE strategy.
    
    The BASE strategy for SEQUENCE OF mutates the length field while keeping
    the content the same or varying it. This exploits mismatches between the
    declared number of elements and actual content.
    
    Mutations:
    1. Length = 0 with non-empty content
    2. Length = random value with original content
    3. Length = random value (different from actual)
    4. Length = maximum encoded value with original content
    
    Args:
        message: Complete RRC message dictionary
        target_path: Path to the SEQUENCE OF field
        message_type: Type of RRC message
        lower_bound: Minimum number of elements
        upper_bound: Maximum number of elements
        current_value: Current list of elements
        seed: Random seed for reproducibility
        
    Returns:
        List of mutated message dictionaries with metadata
        
    Example:
        >>> # Example: A SEQUENCE OF with elements
        >>> mutations = mutate_sequence_of_field(
        ...     message=dl_dcch_message,
        ...     target_path=['message', 'c1', 'someMessage', 'someSequenceOf'],
        ...     message_type='someMessage',
        ...     lower_bound=1,
        ...     upper_bound=8,
        ...     current_value=[elem1, elem2, elem3]
        ... )
    """
    if seed is not None:
        random.seed(seed)
    
    mutations = []
    
    # Calculate bit size for length encoding
    field_max_length = upper_bound - lower_bound
    len_bit_size = calculate_bit_length(0, field_max_length)
    field_max_encoded_length = 2**len_bit_size - 1
    
    # Get current value
    if current_value is None:
        current_value = []
    
    num_elements = len(current_value)
    
    # Mutation 1: Length = 0 with existing content
    # This tests if the decoder properly handles mismatch
    mutation1 = deepcopy(message)
    # Keep the content but claim length is 0
    mutations.append({
        'message': mutation1,
        'mutation_type': 'zero_length_with_content',
        'mutation_description': f'Length=0, Actual elements={num_elements} (length/content mismatch)',
        'target_field_path': target_path,
        'message_type': message_type,
        'declared_length': 0,
        'actual_elements': num_elements
    })
    
    # Mutation 2: Keep actual number of elements but with random length declaration
    mutation2 = deepcopy(message)
    random_length = random.randint(0, field_max_encoded_length)
    mutations.append({
        'message': mutation2,
        'mutation_type': 'random_length_original_content',
        'mutation_description': f'Length={random_length}, Actual elements={num_elements}',
        'target_field_path': target_path,
        'message_type': message_type,
        'declared_length': random_length,
        'actual_elements': num_elements
    })
    
    # Mutation 3: Random length between 0 and max with original content
    mutation3 = deepcopy(message)
    random_length2 = random.randint(0, field_max_encoded_length)
    mutations.append({
        'message': mutation3,
        'mutation_type': 'random_length_mismatch',
        'mutation_description': f'Length={random_length2}, Elements={num_elements} (mismatch)',
        'target_field_path': target_path,
        'message_type': message_type,
        'declared_length': random_length2,
        'actual_elements': num_elements
    })
    
    # Mutation 4: Max encoded length with original content
    mutation4 = deepcopy(message)
    mutations.append({
        'message': mutation4,
        'mutation_type': 'max_length_original_content',
        'mutation_description': f'Length={field_max_encoded_length}, Elements={num_elements} (max length)',
        'target_field_path': target_path,
        'message_type': message_type,
        'declared_length': field_max_encoded_length,
        'actual_elements': num_elements
    })
    
    # Additional mutation: Modify actual list size
    # Mutation 5: Empty list
    if num_elements > 0:
        mutation5 = deepcopy(message)
        mutation5 = _set_sequence_of_value(mutation5, target_path, [])
        mutations.append({
            'message': mutation5,
            'mutation_type': 'empty_list',
            'mutation_description': f'Empty SEQUENCE OF (0 elements)',
            'target_field_path': target_path,
            'message_type': message_type,
            'declared_length': 0,
            'actual_elements': 0
        })
    
    # Mutation 6: Add duplicate elements to exceed bounds
    if num_elements > 0 and upper_bound < 100:  # Avoid creating huge lists
        mutation6 = deepcopy(message)
        # Duplicate elements to create a longer list
        extended_list = current_value * ((upper_bound // num_elements) + 2)
        extended_list = extended_list[:upper_bound + 5]  # Slightly exceed upper bound
        mutation6 = _set_sequence_of_value(mutation6, target_path, extended_list)
        mutations.append({
            'message': mutation6,
            'mutation_type': 'exceed_upper_bound',
            'mutation_description': f'Exceed upper bound: {len(extended_list)} > {upper_bound}',
            'target_field_path': target_path,
            'message_type': message_type,
            'declared_length': len(extended_list),
            'actual_elements': len(extended_list)
        })
    
    return mutations


def _set_sequence_of_value(message: Dict[str, Any], path: List[str], value: List) -> Dict[str, Any]:
    """
    Helper function to set a SEQUENCE OF value at a specific path.
    
    Args:
        message: RRC message dictionary
        path: Path to the field
        value: List value to set
        
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
                modified_value = _set_sequence_of_value(current[1], remaining_path, value)
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
def sequence_of_mutation_tool(
    message: Dict[str, Any],
    target_path: List[str],
    message_type: str,
    lower_bound: int,
    upper_bound: int,
    current_value: Optional[List] = None,
    seed: int = None
) -> Dict[str, Any]:
    """
    Agent tool interface for SEQUENCE OF field mutation.
    
    Args:
        message: Complete RRC message dictionary
        target_path: Path to the SEQUENCE OF field
        message_type: RRC message type
        lower_bound: Minimum number of elements
        upper_bound: Maximum number of elements
        current_value: Current list of elements
        seed: Random seed
        
    Returns:
        Dictionary with mutations and metadata
        
    Example:
        >>> result = sequence_of_mutation_tool(
        ...     message=dl_dcch_message,
        ...     target_path=['message', 'c1', '...', 'someList'],
        ...     message_type='someMessage',
        ...     lower_bound=1,
        ...     upper_bound=8,
        ...     current_value=[elem1, elem2]
        ... )
    """
    mutations = mutate_sequence_of_field(
        message=message,
        target_path=target_path,
        message_type=message_type,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        current_value=current_value,
        seed=seed
    )
    
    return {
        'mutations': mutations,
        'count': len(mutations),
        'strategy': 'BASE',
        'field_type': 'SEQUENCE_OF',
        'target_path': target_path,
        'message_type': message_type,
        'bounds': f'[{lower_bound}, {upper_bound}]'
    }
