from pprint import pprint
from pathlib import Path

import pytest

import modflow_devtools.models as models
from modflow_devtools.codec import MF6Transformer, make_parser

import pytest
from textwrap import dedent

from modflow_devtools.codec import make_parser, parse_mf6_input

MODELS = [name for name in models.get_models().keys() if name.startswith("mf6/")]
PARSER = make_parser()


@pytest.mark.parametrize("model_name", MODELS)
def test_parse_namefiles(model_name, function_tmpdir):
    workspace = models.copy_to(function_tmpdir, model_name)
    
    # Test simulation namefile
    sim_nam = workspace / "mfsim.nam"
    if sim_nam.exists():
        text = sim_nam.read_text()
        print(f"\nTesting simulation namefile: {sim_nam.name}")
        pprint(text)
        tree = PARSER.parse(text)
        print(tree.pretty())
    
    # Test model namefiles
    for nam_path in workspace.glob("*.nam"):
        if nam_path.name != "mfsim.nam":
            text = nam_path.read_text()
            print(f"\nTesting model namefile: {nam_path.name}")
            pprint(text)
            tree = PARSER.parse(text)
            print(tree.pretty())


    input_files = list(workspace.glob("*"))
    exclude_extensions = [
        ".hds", ".cbc", ".lst", ".out", ".bud", ".head", 
        ".bin", ".ucn", ".txt", ".log", ".csv", ".nam"
    ]
    
    for file_path in workspace.iterdir():
        if (file_path.is_file() and 
            file_path.suffix not in exclude_extensions and
            file_path not in input_files and
            file_path.name not in ["mfsim.nam"] and
            not file_path.name.endswith(".nam")):
            input_files.append(file_path)
    
    success_count = 0
    failure_count = 0
    
    for file_path in sorted(input_files):
        try:
            text = file_path.read_text()
            print(f"\n{'='*60}")
            print(f"Testing input file: {file_path.name}")
            print(f"{'='*60}")
            pprint(text[:500] + "..." if len(text) > 500 else text)
            tree = PARSER.parse(text)
            print("✓ PARSED SUCCESSFULLY")
            print(tree.pretty())
            success_count += 1
        except Exception as e:
            print(f"✗ FAILED TO PARSE: {e}")
            failure_count += 1
    
    print(f"\n{'='*60}")
    print(f"SUMMARY for {model_name}:")
    print(f"Successfully parsed: {success_count}")
    print(f"Failed to parse: {failure_count}")
    print(f"Total files tested: {success_count + failure_count}")
    print(f"{'='*60}")


def test_simple_block_transformation():
    """Test transformation of a simple block."""
    text = dedent("""
        BEGIN options
        END options
    """).strip()
    
    result = parse_mf6_input(text)
    
    assert result['type'] == 'mf6_input'
    assert len(result['blocks']) == 1
    
    block = result['blocks'][0]
    assert block['type'] == 'block'
    assert block['name'] == 'options'
    assert block['index'] is None
    assert block['lines'] == []

def test_block_with_index():
    """Test transformation of a block with an index."""
    text = dedent("""
        BEGIN solutiongroup 1
        END solutiongroup 1
    """).strip()
    
    result = parse_mf6_input(text)
    
    assert len(result['blocks']) == 1
    block = result['blocks'][0]
    assert block['name'] == 'solutiongroup'
    assert block['index'] == 1

def test_block_with_content():
    """Test transformation of a block with content."""
    text = dedent("""
        BEGIN timing
            TDIS6  ex-gwe-ates.tdis
        END timing
    """).strip()
    
    result = parse_mf6_input(text)
    
    assert len(result['blocks']) == 1
    block = result['blocks'][0]
    assert block['name'] == 'timing'
    assert len(block['lines']) == 1
    
    line = block['lines'][0]
    assert line['type'] == 'line'
    assert len(line['items']) == 2
    assert line['items'][0] == 'TDIS6'
    assert line['items'][1] == 'ex-gwe-ates.tdis'

def test_multiple_blocks():
    """Test transformation of multiple blocks."""
    text = dedent("""
        BEGIN options
        END options
        
        BEGIN timing
            TDIS6  ex-gwe-ates.tdis
        END timing
    """).strip()
    
    result = parse_mf6_input(text)
    
    assert len(result['blocks']) == 2
    assert result['blocks'][0]['name'] == 'options'
    assert result['blocks'][1]['name'] == 'timing'

def test_number_parsing():
    """Test that numbers are parsed correctly."""
    text = dedent("""
        BEGIN test
            integer_value 42
            float_value 3.14
            scientific 1.5e-3
        END test
    """).strip()
    
    result = parse_mf6_input(text)
    
    block = result['blocks'][0]
    lines = block['lines']
    
    # Check integer
    assert lines[0]['items'][1] == 42
    assert isinstance(lines[0]['items'][1], int)
    
    # Check float
    assert lines[1]['items'][1] == 3.14
    assert isinstance(lines[1]['items'][1], float)
    
    # Check scientific notation
    assert lines[2]['items'][1] == 1.5e-3
    assert isinstance(lines[2]['items'][1], float)

def test_complex_structure():
    """Test transformation of a more complex structure."""
    text = dedent("""
        BEGIN options
        END options
        
        BEGIN models
            gwf6  gwf-model.nam  gwf-model
            gwe6  gwe-model.nam  gwe-model
        END models
        
        BEGIN solutiongroup 1
            ims6  gwf-model.ims  gwf-model
        END solutiongroup 1
    """).strip()
    
    result = parse_mf6_input(text)
    
    assert len(result['blocks']) == 3
    
    # Options block
    assert result['blocks'][0]['name'] == 'options'
    assert len(result['blocks'][0]['lines']) == 0
    
    # Models block
    models_block = result['blocks'][1]
    assert models_block['name'] == 'models'
    assert len(models_block['lines']) == 2
    
    # First model line
    first_model = models_block['lines'][0]
    assert first_model['items'] == ['gwf6', 'gwf-model.nam', 'gwf-model']
    
    # Second model line
    second_model = models_block['lines'][1]
    assert second_model['items'] == ['gwe6', 'gwe-model.nam', 'gwe-model']
    
    # Solution group block
    solution_block = result['blocks'][2]
    assert solution_block['name'] == 'solutiongroup'
    assert solution_block['index'] == 1
    assert len(solution_block['lines']) == 1

def test_transformer_directly():
    """Test using the transformer directly."""
    parser = make_parser()
    text = dedent("""
        BEGIN test
            word1 word2 123
        END test
    """).strip()
    
    tree = parser.parse(text)
    transformer = MF6Transformer()
    result = transformer.transform(tree)
    
    assert result['type'] == 'mf6_input'
    assert len(result['blocks']) == 1
    
    block = result['blocks'][0]
    assert block['name'] == 'test'
    assert len(block['lines']) == 1
    assert block['lines'][0]['items'] == ['word1', 'word2', 123]

