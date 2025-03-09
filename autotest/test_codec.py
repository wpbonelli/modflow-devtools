from modflow_devtools.codec import make_parser


def test_parser():
    parser = make_parser()
    text = """
BEGIN OPTIONS
    AN OPTION
    ANOTHER OPTION
END OPTIONS
BEGIN PACKAGEDATA
END PACKAGEDATA
"""
    tree = parser.parse(text)
    print(tree.pretty())
