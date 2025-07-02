from typing import Any, Optional, Dict
from pathlib import Path
from lark import Lark, Token, Transformer

from modflow_devtools.grammar_generator import MF6GrammarGenerator


class MF6ParserFactory:
    """Factory for creating component-specific MF6 parsers."""
    
    def __init__(self, dfn_dir: Optional[Path] = None):
        self._parsers = {}
        self.grammar_generator = None
        if dfn_dir:
            self.grammar_generator = MF6GrammarGenerator(dfn_dir)
    
    def get_parser(self, component: Optional[str] = None, **kwargs) -> Lark:
        """Get a parser for the specified component, or generic parser if None."""
        if component is None:
            # Return generic parser for backward compatibility
            return Lark.open("mf6.lark", parser="lalr", rel_to=__file__, **kwargs)
        
        if component not in self._parsers:
            if not self.grammar_generator:
                raise ValueError("No DFN directory provided - cannot generate component-specific parsers")
            
            # Generate grammar file
            grammar_file = self.grammar_generator.write_component_grammar(component)
            
            # Create parser
            self._parsers[component] = Lark.open(
                str(grammar_file), 
                parser="lalr", 
                **kwargs
            )
        
        return self._parsers[component]


def make_parser(**kwargs) -> Lark:
    """Backward compatibility function - returns generic parser."""
    return Lark.open("mf6.lark", parser="lalr", rel_to=__file__, **kwargs)


def parse_mf6_input(text: str, **kwargs) -> dict:
    """
    Parse MF6 input text and transform to structured data.
    
    Args:
        text: The MF6 input file text to parse
        **kwargs: Additional arguments passed to parser
        
    Returns:
        Structured dictionary representation of the MF6 input
    """
    parser = make_parser(**kwargs)
    tree = parser.parse(text)
    return transform_mf6_input(tree)


class MF6Transformer(Transformer):
    """
    Transforms parsed MF6 input file tree into structured Python objects.
    
    The transformer converts the low-level parse tree into a hierarchical
    structure that represents the semantic meaning of MF6 input files.
    """
    
    def __init__(self, component: Optional[str] = None, dfn_dir: Optional[Path] = None):
        """Initialize transformer with optional component-specific behavior."""
        super().__init__()
        self.component = component
        self.dfn_dir = dfn_dir
        self._recarray_structures = {}
        
        # Load recarray structures if component is specified
        if component and dfn_dir:
            self._load_recarray_structures()
    
    def _load_recarray_structures(self):
        """Load recarray structures for the current component."""
        try:
            from modflow_devtools.grammar_generator import MF6GrammarGenerator
            generator = MF6GrammarGenerator(self.dfn_dir)
            if self.component in generator.dfns:
                dfn = generator.dfns[self.component]
                spec = generator._extract_grammar_spec(dfn)
                
                for block_name, block_spec in spec['blocks'].items():
                    if (block_spec.get('type') == 'recarray' and 
                        block_spec.get('structure') and 
                        block_spec['structure'].get('regular')):
                        self._recarray_structures[block_name] = block_spec['structure']
        except Exception:
            # Fallback gracefully if structures can't be loaded
            pass
    
    def start(self, items: list[Any]) -> dict[str, Any]:
        """Transform the root of the parse tree."""
        blocks = [item for item in items if isinstance(item, dict) and 'name' in item]
        return {
            'type': 'mf6_input',
            'blocks': blocks
        }
    
    def block(self, items: list[Any]) -> dict[str, Any]:
        """Transform a block (begin...end section)."""
        # Items: [begin_tag, block_name, optional_index, content, end_tag, block_name, optional_index]
        # With the updated grammar: [block_name, optional_index, content, block_name, optional_index]
        block_name = str(items[0])  # CNAME becomes a Token
        
        # Check if we have an index (items[1]) or content directly
        if len(items) >= 3 and isinstance(items[1], int):
            # We have: [block_name, index, content, block_name, index]
            block_index = items[1]
            content = items[2] if items[2] is not None else []
        else:
            # We have: [block_name, content, block_name] 
            block_index = None
            content = items[1] if items[1] is not None else []
        
        # Check if this is a structured recarray block
        if block_name.lower() in self._recarray_structures:
            structure = self._recarray_structures[block_name.lower()]
            content = self._structure_recarray_data(content, structure)
        
        return {
            'type': 'block',
            'name': block_name.lower(),
            'index': block_index,
            'lines': content
        }
    
    def _structure_recarray_data(self, content: list, structure: Dict[str, Any]) -> list:
        """Convert raw recarray lines into structured records."""
        structured_lines = []
        field_names = [field['name'] for field in structure['fields']]
        
        for line in content:
            if isinstance(line, dict) and line.get('type') == 'line':
                items = line.get('items', [])
                if len(items) >= len(field_names):
                    # Create structured record
                    record = {
                        'type': 'record',
                        'fields': {}
                    }
                    for i, field_name in enumerate(field_names):
                        if i < len(items):
                            record['fields'][field_name] = items[i]
                    # Include any extra items as overflow
                    if len(items) > len(field_names):
                        record['overflow'] = items[len(field_names):]
                    structured_lines.append(record)
                else:
                    # Not enough items for structured parsing, keep as raw line
                    structured_lines.append(line)
            else:
                structured_lines.append(line)
        
        return structured_lines
    
    def _block_index(self, items: list[Token]) -> int:
        """Transform block index."""
        return int(items[0])
    
    def _content(self, items: list[Any]) -> list[dict[str, Any]]:
        """Transform block content (list of lines)."""
        return [item for item in items if item is not None]
    
    def line(self, items: list[Any]) -> dict[str, Any]:
        """Transform a line of items."""
        # Filter out None items (whitespace)
        items_list = [item for item in items if item is not None]
        return {
            'type': 'line',
            'items': items_list
        }
    
    def item(self, items: list[Any]) -> str | float | int:
        """Transform an item (word or number)."""
        return items[0]
    
    def word(self, items: list[Token]) -> str:
        """Transform a word token."""
        return str(items[0])
    
    def NUMBER(self, token: Token) -> int | float:
        """Transform a number token."""
        value = str(token)
        try:
            if '.' in value or 'e' in value.lower():
                return float(value)
            else:
                return int(value)
        except ValueError:
            return float(value)
    
    def CNAME(self, token: Token) -> str:
        """Transform a CNAME token (block names)."""
        return str(token)
    
    def INT(self, token: Token) -> int:
        """Transform an INT token."""
        return int(token)


def transform_mf6_input(parse_tree) -> dict[str, Any]:
    transformer = MF6Transformer()
    return transformer.transform(parse_tree)
