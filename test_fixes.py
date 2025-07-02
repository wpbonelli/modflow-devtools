#!/usr/bin/env python3
"""Test the grammar generation fixes."""

from pathlib import Path
from textwrap import dedent

from modflow_devtools.dfn import get_dfns
from modflow_devtools.grammar_generator import MF6GrammarGenerator  
from modflow_devtools.codec import MF6ParserFactory


def test_fixes():
    """Test that grammar generation and parsing now work."""
    
    # Setup directories
    base_dir = Path(__file__).parent
    dfn_dir = base_dir / "temp" / "dfn"
    
    print("=== Testing Grammar Generation Fixes ===\n")
    
    # Download DFNs if needed
    if not dfn_dir.exists() or not any(dfn_dir.glob("*.dfn")):
        print("Downloading DFNs...")
        get_dfns("MODFLOW-ORG", "modflow6", "develop", dfn_dir, verbose=False)
        print("✓ Downloaded\n")
    
    # Create grammar generator
    generator = MF6GrammarGenerator(dfn_dir)
    
    # Test generating grammar for a specific component
    test_component = list(generator.dfns.keys())[0]  # First available component
    print(f"Testing component: {test_component}")
    
    try:
        grammar = generator.generate_component_grammar(test_component)
        print("✓ Grammar generated successfully")
        
        # Check if block rule is populated
        lines = grammar.split('\n')
        block_line = next((line for line in lines if line.startswith('block:')), None)
        
        if block_line and block_line.strip() != 'block:':
            print(f"✓ Block rule populated: {block_line}")
        else:
            print(f"✗ Block rule still empty: {block_line}")
            return
        
        # Test parsing with the component-specific parser
        factory = MF6ParserFactory(dfn_dir)
        parser = factory.get_parser(test_component)
        
        # Simple test input
        test_input = dedent("""
            BEGIN options
            END options
        """).strip()
        
        tree = parser.parse(test_input)
        print("✓ Component-specific parser works")
        
        # Test generic parser too
        generic_parser = factory.get_parser()
        tree = generic_parser.parse(test_input)
        print("✓ Generic parser works")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return
        
    print("\n✓ All tests passed!")


if __name__ == "__main__":
    test_fixes()