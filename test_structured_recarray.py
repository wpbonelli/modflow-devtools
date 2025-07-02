#!/usr/bin/env python3
"""Test structured recarray parsing."""

from pathlib import Path
from textwrap import dedent

from modflow_devtools.dfn import get_dfns
from modflow_devtools.grammar_generator import MF6GrammarGenerator  
from modflow_devtools.codec import MF6ParserFactory, MF6Transformer


def test_structured_recarray():
    """Test parsing structured recarray data."""
    
    # Setup directories
    base_dir = Path(__file__).parent
    dfn_dir = base_dir / "temp" / "dfn"
    
    print("=== Testing Structured Recarray Parsing ===\n")
    
    # Download DFNs if needed
    if not dfn_dir.exists() or not any(dfn_dir.glob("*.dfn")):
        print("Downloading DFNs...")
        get_dfns("MODFLOW-ORG", "modflow6", "develop", dfn_dir, verbose=False)
        print("✓ Downloaded\n")
    
    # Create grammar generator
    generator = MF6GrammarGenerator(dfn_dir)
    
    # Find a component with recarray data
    test_component = 'chf-cdb'  # Constant head boundary - has period data
    
    if test_component in generator.dfns:
        print(f"Testing component: {test_component}")
        
        # Check if we can extract recarray structure
        dfn = generator.dfns[test_component]
        spec = generator._extract_grammar_spec(dfn)
        
        print("Blocks found:")
        for block_name, block_spec in spec['blocks'].items():
            print(f"  {block_name}: {block_spec['type']}")
            if block_spec.get('structure'):
                structure = block_spec['structure']
                if structure.get('regular'):
                    field_names = [f['name'] for f in structure['fields']]
                    print(f"    Structured fields: {field_names}")
                else:
                    print("    Unstructured")
        print()
        
        # Generate and show grammar
        grammar = generator.generate_component_grammar(test_component)
        
        # Show period block part of grammar
        lines = grammar.split('\n')
        period_start = next((i for i, line in enumerate(lines) if 'PERIOD block' in line), None)
        if period_start:
            print("Period block grammar:")
            for i in range(period_start, min(period_start + 8, len(lines))):
                print(f"  {lines[i]}")
            print()
        
        # Create parser and test
        factory = MF6ParserFactory(dfn_dir)
        parser = factory.get_parser(test_component)
        
        # Test input with period data
        test_input = dedent("""
            BEGIN options
            END options
            
            BEGIN dimensions
                MAXBOUND 2
            END dimensions
            
            BEGIN period 1
                1 1 1 10.0
                2 1 1 20.0
            END period 1
        """).strip()
        
        print("Testing with structured transformer...")
        try:
            tree = parser.parse(test_input)
            
            # Use component-specific transformer
            transformer = MF6Transformer(component=test_component, dfn_dir=dfn_dir)
            result = transformer.transform(tree)
            
            print("✓ Parsing successful")
            
            # Show structured result
            for block in result['blocks']:
                if block['name'] == 'period':
                    print(f"Period block data:")
                    for i, line in enumerate(block['lines']):
                        if line.get('type') == 'record':
                            print(f"  Record {i+1}: {line['fields']}")
                        else:
                            print(f"  Line {i+1}: {line}")
                    break
            
        except Exception as e:
            print(f"✗ Error: {e}")
    
    else:
        print(f"Component {test_component} not found")
    
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_structured_recarray()