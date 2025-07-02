#!/usr/bin/env python3
"""
Example demonstrating MF6 component-specific grammar generation and parsing.
"""

from pathlib import Path
from textwrap import dedent

from modflow_devtools.dfn import get_dfns
from modflow_devtools.grammar_generator import MF6GrammarGenerator  
from modflow_devtools.codec import MF6ParserFactory


def main():
    """Demonstrate component-specific parsing."""
    
    # Setup directories
    base_dir = Path(__file__).parent
    dfn_dir = base_dir / "temp" / "dfn"
    
    print("=== MF6 Component-Specific Grammar Generation Demo ===\n")
    
    # Download DFNs if needed
    if not dfn_dir.exists() or not any(dfn_dir.glob("*.dfn")):
        print("Downloading MODFLOW 6 DFN files...")
        get_dfns("MODFLOW-ORG", "modflow6", "develop", dfn_dir, verbose=True)
        print("✓ DFN files downloaded\n")
    
    # Create grammar generator
    print("Creating grammar generator...")
    generator = MF6GrammarGenerator(dfn_dir)
    print(f"✓ Loaded {len(generator.dfns)} component specifications\n")
    
    # List available components
    components = sorted(generator.dfns.keys())
    print(f"Available components ({len(components)}):")
    for i, comp in enumerate(components):
        print(f"  {i+1:2d}. {comp}")
    print()
    
    # Generate grammar for a simple component
    target_component = 'dis'  # Discretization package - usually simple
    if target_component in components:
        print(f"Generating grammar for '{target_component}' component...")
        try:
            grammar = generator.generate_component_grammar(target_component)
            print(f"✓ Generated {len(grammar)} character grammar")
            
            # Show first few lines
            lines = grammar.split('\n')[:15]
            print("First 15 lines of generated grammar:")
            for line in lines:
                print(f"  {line}")
            if len(grammar.split('\n')) > 15:
                print("  ...")
            print()
            
        except Exception as e:
            print(f"✗ Failed to generate grammar: {e}\n")
            return
    
    # Create parser factory and test parsing
    print("Creating parser factory...")
    factory = MF6ParserFactory(dfn_dir)
    
    # Test generic parser
    print("Testing generic parser...")
    generic_parser = factory.get_parser()
    
    sample_input = dedent("""
        BEGIN options
        END options
        
        BEGIN dimensions
            NLAY 3
            NROW 10  
            NCOL 15
        END dimensions
    """).strip()
    
    try:
        tree = generic_parser.parse(sample_input)
        print("✓ Generic parser works")
        print("Parse tree structure:")
        print(f"  {tree.pretty()[:200]}...")
        print()
    except Exception as e:
        print(f"✗ Generic parser failed: {e}\n")
    
    # Test component-specific parser
    if target_component in components:
        print(f"Testing component-specific parser for '{target_component}'...")
        try:
            specific_parser = factory.get_parser(target_component)
            tree = specific_parser.parse(sample_input)
            print("✓ Component-specific parser works")
            print("Parse tree structure:")
            print(f"  {tree.pretty()[:200]}...")
            print()
        except Exception as e:
            print(f"✗ Component-specific parser failed: {e}")
            print("This is expected - the component grammar may need refinement")
            print()
    
    # Generate all grammars
    print("Generating all component grammars...")
    try:
        grammars = generator.generate_all_grammars()
        successful = len([g for g in grammars.values() if g])
        print(f"✓ Generated {successful}/{len(components)} grammars successfully")
        
        # Show output directory
        print(f"Grammar files written to: {generator.output_dir}")
        grammar_files = list(generator.output_dir.glob("*.lark"))
        print(f"Found {len(grammar_files)} grammar files")
        
    except Exception as e:
        print(f"✗ Failed to generate grammars: {e}")
    
    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    main()