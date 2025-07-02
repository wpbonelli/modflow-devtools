#!/usr/bin/env python3
"""Debug script to examine DFN parsing issues."""

from pathlib import Path
from pprint import pprint

from modflow_devtools.dfn import get_dfns, Dfn
from modflow_devtools.grammar_generator import MF6GrammarGenerator


def main():
    """Debug DFN parsing and grammar generation."""
    
    # Setup directories
    base_dir = Path(__file__).parent
    dfn_dir = base_dir / "temp" / "dfn"
    
    # Download DFNs if needed
    if not dfn_dir.exists() or not any(dfn_dir.glob("*.dfn")):
        print("Downloading DFNs...")
        get_dfns("MODFLOW-ORG", "modflow6", "develop", dfn_dir, verbose=True)
    
    # Load DFNs
    print("Loading DFNs...")
    dfns = Dfn.load_all(dfn_dir)
    
    # Examine a few components
    sample_components = ['dis', 'gwe-ic', 'chf-cdb']
    
    for comp_name in sample_components:
        if comp_name in dfns:
            print(f"\n=== {comp_name} DFN ===")
            dfn = dfns[comp_name]
            print(f"Keys: {list(dfn.keys())}")
            
            # Look for variables with blocks
            vars_with_blocks = {k: v for k, v in dfn.items() 
                              if isinstance(v, dict) and v.get('block')}
            print(f"Variables with blocks: {len(vars_with_blocks)}")
            
            if vars_with_blocks:
                # Show first few
                for i, (name, var) in enumerate(vars_with_blocks.items()):
                    if i < 3:
                        print(f"  {name}: block='{var.get('block')}', type='{var.get('type')}'")
            
            # Test grammar generation
            try:
                generator = MF6GrammarGenerator(dfn_dir)
                spec = generator._extract_grammar_spec(dfn)
                print(f"Grammar spec blocks: {list(spec['blocks'].keys())}")
                print(f"Grammar spec variables: {len(spec['variables'])}")
                
                if spec['blocks']:
                    grammar = generator.generate_component_grammar(comp_name)
                    lines = grammar.split('\n')
                    block_line = next((line for line in lines if line.startswith('block:')), None)
                    print(f"Block rule: {block_line}")
                
            except Exception as e:
                print(f"Error generating grammar: {e}")


if __name__ == "__main__":
    main()