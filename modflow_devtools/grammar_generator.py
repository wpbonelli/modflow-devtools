"""Grammar generation for MF6 components using DFN specifications and Jinja templates."""

from pathlib import Path
from typing import Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader
from itertools import groupby

from modflow_devtools.dfn import Dfn


class MF6GrammarGenerator:
    """Generates component-specific Lark grammars from DFN specifications."""
    
    def __init__(self, dfn_dir: Path, templates_dir: Optional[Path] = None, output_dir: Optional[Path] = None):
        self.dfn_dir = Path(dfn_dir)
        self.templates_dir = templates_dir or Path(__file__).parent / "grammars"
        self.output_dir = output_dir or Path(__file__).parent / "grammars" / "generated"
        
        # Set up Jinja environment
        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
        # Load DFN specifications
        self.dfns = Dfn.load_all(self.dfn_dir)
    
    def _get_grammar_spec(dfn: Dict[str, Any]) -> Dict[str, Any]:
        """Extract grammar generation specification from a DFN."""

        def _get_field_spec_from_dfn(field_name: str) -> Dict[str, Any]:
            """Get field specification from DFN data."""
            # Look through all variables in the current component's DFN
            # to find the field definition (should have in_record=True)
            # Search through all blocks in the DFN for this field
            for block in dfn.values():
                if isinstance(block, dict):
                    for var in block.values():
                        if (isinstance(var, dict) and 
                            var.get('name') == field_name and 
                            var.get('in_record')):
                            var_type = var.get('type', 'string')
                            if var_type in ['integer', 'double precision']:
                                lark_var_type = 'NUMBER'
                            else:
                                lark_var_type = 'word'
                            
                            return {
                                'type': lark_var_type,
                                'description': var.get('description', f'{field_name} field')
                            }

        def _parse_recarray_structure(var: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            """Parse the structure of a recarray variable from its DFN specification."""
            var_type = var.get('type', '')
            
            if not var_type.startswith('recarray'):
                return None
            
            # Extract field names from recarray type
            # Format: "recarray field1 field2 field3"
            parts = var_type.split()
            if len(parts) < 2:
                return None
            
            field_names = parts[1:]  # Skip 'recarray'
            
            # Get field specifications from the DFN - the fields should be defined
            # as separate variables with in_record=True in the same component
            fields = []
            for field_name in field_names:
                field_spec = _get_field_spec_from_dfn(field_name)
                fields.append({
                    'name': field_name,
                    'type': field_spec.get('type', 'NUMBER'),  # Default to NUMBER for recarray fields
                    'description': field_spec.get('description', f'{field_name} field')
                })
            
            return {
                'fields': fields,
                'regular': len(fields) > 0
            }
        
        # Get all dictionary items that look like variables
        all_vars = {}
        for name, value in dfn.items():
            if isinstance(value, dict) and 'type' in value:
                # Some DFNs might have variables as top-level blocks
                all_vars[name] = value
            elif isinstance(value, dict):
                # Some DFNs have nested structure - check for variables within
                for subname, subvalue in value.items():
                    if isinstance(subvalue, dict) and 'type' in subvalue:
                        all_vars[f"{name}_{subname}"] = subvalue
        
        blocks = {}
        variables = {}
        
        # Group by block
        for var_name, var in all_vars.items():
            block_name = var.get('block')
            var_type = var.get('type')
            
            # Skip invalid entries
            if not block_name or not var_type or block_name in ['None', None]:
                continue
                
            if block_name not in blocks:
                blocks[block_name] = {'type': 'dict', 'variables': []}
            
            # Remove block prefix from variable name if present
            clean_var_name = var_name
            if var_name.startswith(f"{block_name}_"):
                clean_var_name = var_name[len(block_name)+1:]
            
            # Handle recarray blocks - check if they have structured data
            if any(keyword in block_name.lower() for keyword in ['period', 'connectiondata', 'vertices']):
                if var_type.startswith('recarray'):
                    # Extract recarray structure from the variable type
                    recarray_spec = _parse_recarray_structure(var)
                    blocks[block_name] = {
                        'type': 'recarray',
                        'structure': recarray_spec,
                        'variables': []
                    }
                else:
                    blocks[block_name]['type'] = 'recarray'
                # Don't add variables to recarray blocks as separate rules
                continue
            
            blocks[block_name]['variables'].append(clean_var_name)
            variables[clean_var_name] = var
        
        # If no blocks found, create a minimal default structure
        if not blocks:
            print(f"Warning: No valid blocks found for component {dfn.get('name', 'unknown')}")
            print(f"Available keys: {list(dfn.keys())}")
            blocks['options'] = {'type': 'dict', 'variables': []}
        
        # Detect recarray blocks (typically have "period" in name or specific patterns)
        for block_name in blocks:
            if any(keyword in block_name.lower() for keyword in ['period', 'connectiondata', 'vertices']):
                blocks[block_name]['type'] = 'recarray'
        
        return {
            'component': dfn.get('name', 'unknown'),
            'blocks': blocks,
            'variables': variables
        }
    