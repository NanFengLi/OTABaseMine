"""
Example usage of RRC mutation tools

This demonstrates how to use the mutation tools with a sample RRC message.
"""

from bishe.mutated.tools import (
    integer_mutation_tool,
    octet_string_mutation_tool,
    bit_string_mutation_tool,
    sequence_of_mutation_tool
)
import json


# Example RRC message (csfbParametersResponseCDMA2000)
dl_dcch_message = {
    'message': (
        'c1',
        (
            'csfbParametersResponseCDMA2000',
            {
                'rrc-TransactionIdentifier': 0,
                'criticalExtensions': (
                    'csfbParametersResponseCDMA2000-r8',
                    {
                        'rand': (0, 32),
                        'mobilityParameters': b'\x00',
                        'nonCriticalExtension': {
                            'lateNonCriticalExtension': b'\x00'
                        }
                    }
                )
            }
        )
    )
}


def example_integer_mutation():
    """
    Example: Mutate INTEGER field (rrc-TransactionIdentifier)
    """
    print("=" * 60)
    print("INTEGER Field Mutation Example")
    print("=" * 60)
    
    result = integer_mutation_tool(
        message=dl_dcch_message,
        target_path=['message', 'c1', 'csfbParametersResponseCDMA2000', 
                     'rrc-TransactionIdentifier'],
        lower_bound=0,
        upper_bound=3,  # rrc-TransactionIdentifier is constrained to 0-3
        message_type='csfbParametersResponseCDMA2000',
        seed=42
    )
    
    print(f"Strategy: {result['strategy']}")
    print(f"Field Type: {result['field_type']}")
    print(f"Generated {result['count']} mutations\n")
    
    for i, mutation in enumerate(result['mutations'], 1):
        print(f"Mutation {i}: {mutation['mutation_type']}")
        print(f"  Description: {mutation['mutation_description']}")
        # print(f"  Message: {mutation['message']}")
        print()


def example_bit_string_mutation():
    """
    Example: Mutate BIT_STRING field (rand)
    """
    print("=" * 60)
    print("BIT_STRING Field Mutation Example")
    print("=" * 60)
    
    result = bit_string_mutation_tool(
        message=dl_dcch_message,
        target_path=['message', 'c1', 'csfbParametersResponseCDMA2000',
                     'criticalExtensions', 'csfbParametersResponseCDMA2000-r8',
                     'rand'],
        message_type='csfbParametersResponseCDMA2000',
        constrained=True,
        lower_bound=32,  # Fixed 32-bit RAND
        upper_bound=32,
        current_value=(0, 32),
        seed=42
    )
    
    print(f"Strategy: {result['strategy']}")
    print(f"Field Type: {result['field_type']}")
    print(f"Constraint Type: {result['constraint_type']}")
    print(f"Generated {result['count']} mutations\n")
    
    for i, mutation in enumerate(result['mutations'], 1):
        print(f"Mutation {i}: {mutation['mutation_type']}")
        print(f"  Description: {mutation['mutation_description']}")
        print()


def example_octet_string_mutation():
    """
    Example: Mutate OCTET_STRING field (mobilityParameters)
    """
    print("=" * 60)
    print("OCTET_STRING Field Mutation Example")
    print("=" * 60)
    
    result = octet_string_mutation_tool(
        message=dl_dcch_message,
        target_path=['message', 'c1', 'csfbParametersResponseCDMA2000',
                     'criticalExtensions', 'csfbParametersResponseCDMA2000-r8',
                     'mobilityParameters'],
        message_type='csfbParametersResponseCDMA2000',
        constrained=True,
        lower_bound=0,
        upper_bound=255,  # Example constraint
        current_value=b'\x00',
        seed=42
    )
    
    print(f"Strategy: {result['strategy']}")
    print(f"Field Type: {result['field_type']}")
    print(f"Constraint Type: {result['constraint_type']}")
    print(f"Generated {result['count']} mutations\n")
    
    for i, mutation in enumerate(result['mutations'], 1):
        print(f"Mutation {i}: {mutation['mutation_type']}")
        print(f"  Description: {mutation['mutation_description']}")
        print()


def example_sequence_of_mutation():
    """
    Example: Mutate SEQUENCE OF field
    """
    print("=" * 60)
    print("SEQUENCE OF Field Mutation Example")
    print("=" * 60)
    
    # Create a test message with a SEQUENCE OF field
    test_message = {
        'message': (
            'c1',
            (
                'testMessage',
                {
                    'testList': [1, 2, 3, 4, 5]  # Example SEQUENCE OF
                }
            )
        )
    }
    
    result = sequence_of_mutation_tool(
        message=test_message,
        target_path=['message', 'c1', 'testMessage', 'testList'],
        message_type='testMessage',
        lower_bound=1,
        upper_bound=8,
        current_value=[1, 2, 3, 4, 5],
        seed=42
    )
    
    print(f"Strategy: {result['strategy']}")
    print(f"Field Type: {result['field_type']}")
    print(f"Bounds: {result['bounds']}")
    print(f"Generated {result['count']} mutations\n")
    
    for i, mutation in enumerate(result['mutations'], 1):
        print(f"Mutation {i}: {mutation['mutation_type']}")
        print(f"  Description: {mutation['mutation_description']}")
        print()


if __name__ == '__main__':
    print("\n" + "="*60)
    print("RRC Message Mutation Tools - Examples")
    print("Based on OTABase BASE Strategy")
    print("="*60 + "\n")
    
    # Run all examples
    example_integer_mutation()
    example_bit_string_mutation()
    example_octet_string_mutation()
    example_sequence_of_mutation()
    
    print("="*60)
    print("Examples completed!")
    print("="*60)
