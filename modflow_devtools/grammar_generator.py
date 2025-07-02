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
    
    def _extract_grammar_spec(self, dfn: Dict[str, Any]) -> Dict[str, Any]:
        """Extract grammar generation specification from a DFN."""
        
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
                    recarray_spec = self._parse_recarray_structure(var)
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
    
    def _parse_recarray_structure(self, var: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
        current_component_name = var.get('block', '').split('_')[0]  # Try to get component name
        
        for field_name in field_names:
            field_spec = self._get_field_spec_from_dfn(field_name, current_component_name)
            fields.append({
                'name': field_name,
                'type': field_spec.get('type', 'NUMBER'),  # Default to NUMBER for recarray fields
                'description': field_spec.get('description', f'{field_name} field')
            })
        
        return {
            'fields': fields,
            'regular': len(fields) > 0
        }
    
    def _get_field_spec_from_dfn(self, field_name: str, component_name: str) -> Dict[str, Any]:
        """Get field specification from DFN data."""
        # Look through all variables in the current component's DFN
        # to find the field definition (should have in_record=True)
        if component_name in self.dfns:
            dfn = self.dfns[component_name]
            
            # Search through all blocks in the DFN for this field
            for block_name, block_data in dfn.items():
                if isinstance(block_data, dict):
                    # Check if this block contains variables
                    for var_name, var_data in block_data.items():
                        if (isinstance(var_data, dict) and 
                            var_data.get('name') == field_name and 
                            var_data.get('in_record')):
                            
                            # Found the field definition
                            dfn_type = var_data.get('type', 'string')
                            if dfn_type in ['integer', 'double precision']:
                                grammar_type = 'NUMBER'
                            else:
                                grammar_type = 'word'
                            
                            return {
                                'type': grammar_type,
                                'description': var_data.get('description', f'{field_name} field')
                            }
        
        # Fallback: default to NUMBER type for recarray fields
        return {'type': 'NUMBER', 'description': f'{field_name} field'}
    
    def generate_component_grammar(self, component_name: str) -> str:
        """Generate grammar for a specific component."""
        if component_name not in self.dfns:
            raise ValueError(f"Component {component_name} not found in DFN specifications")
        
        dfn = self.dfns[component_name]
        spec = self._extract_grammar_spec(dfn)
        
        # Render grammar template
        template = self.env.get_template("component.lark.j2")
        grammar = template.render(**spec)
        
        return grammar
    
    def generate_all_grammars(self) -> Dict[str, str]:
        """Generate grammars for all components."""
        grammars = {}
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        for component_name in self.dfns:
            try:
                grammar = self.generate_component_grammar(component_name)
                grammars[component_name] = grammar
                
                # Write to file
                output_file = self.output_dir / f"{component_name}.lark"
                with open(output_file, 'w') as f:
                    f.write(grammar)
                    
            except Exception as e:
                print(f"Failed to generate grammar for {component_name}: {e}")
        
        return grammars
    
    def write_component_grammar(self, component_name: str) -> Path:
        """Generate and write grammar for a specific component."""
        grammar = self.generate_component_grammar(component_name)
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_file = self.output_dir / f"{component_name}.lark"
        
        with open(output_file, 'w') as f:
            f.write(grammar)
            
        return output_file