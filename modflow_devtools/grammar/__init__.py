from os import PathLike
from pathlib import Path
from typing import Any, Optional, TypedDict
import jinja2

from modflow_devtools.dfn import Dfn, Var


def _mf6_to_lark_var_type(var_type: str) -> str:
    if var_type in ['integer', 'double precision']:
        return 'NUMBER'
    if 'recarray' in var_type:
        return 'recarray'
    return "word"


def _mf6_to_lark_var(var: Var) -> dict[str, Any]:
    return {
        'name': var['name'],
        'type': _mf6_to_lark_var_type(var['type']),
        'description': var["description"]
    }



class GrammarDescriptor(TypedDict):
    name: str
    blocks: dict[str, Any]
    variables: dict[str, Var]

    @classmethod
    def from_dfn(cls, dfn: Dfn) -> "GrammarDescriptor":
        """Create a GrammarDescriptor from a DFN."""
        return _get_grammar_spec(dfn)


def _get_template_env():
    loader = jinja2.PackageLoader("modflow_devtools", "grammar/")
    env = jinja2.Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    return env


def _get_grammar_spec(dfn: Dfn) -> dict[str, Any]:
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
                blocks[block_name] = {
                    'type': 'recarray',
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

    return GrammarDescriptor(
        name=dfn["name"],
        blocks=blocks,
        variables=variables
    )



def make_grammar(dfn: Dfn, outdir: PathLike, verbose: bool = False):
    outdir = Path(outdir).expanduser().resolve().absolute()
    env = _get_template_env()
    spec = _get_grammar_spec(dfn)
    template = env.get_template("component.lark.j2")
    grammar = template.render(**spec)
    target_path = outdir / 
    with open()


def make_all(dfns: dict[str, Dfn], outdir: PathLike) -> dict[str, str]:
    """Generate grammars for all components."""
    grammars = {}
    outdir = Path(outdir).expanduser().resolve().absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    for component_name in dfns:
        grammar = generate_component_grammar(component_name)
        grammars[component_name] = grammar
        target = outdir / f"{component_name}.lark"
        with open(target, 'w') as f:
            f.write(grammar)
    
    return grammars