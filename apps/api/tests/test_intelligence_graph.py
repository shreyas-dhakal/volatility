import pytest
from galvanise.graph.core import normalize, GraphIndex, evaluate


def fixture():
    return {'directed': True, 'nodes': [{'id': 'a', 'label': 'Supplier', 'source_file': 'supplier.py'}, {'id': 'b'}, {'id': 'c'}], 'links': [{'source': 'a', 'target': 'b', 'relation': 'calls'}, {'source': 'b', 'target': 'c', 'relation': 'imports'}]}


def test_graphify_export_preserves_provenance_and_real_paths():
    nodes, edges, metadata = normalize(fixture())
    assert nodes[0]['file_path'] == 'supplier.py'
    index = GraphIndex(nodes, edges)
    assert index.paths('a', 'c') == [['a', 'b', 'c']]
    assert index.search('supplier')[0]['id'] == 'a'
    assert len(index.subgraph(focus='a', limit=2)['nodes']) == 2
    assert metadata['dialect'] == 'graphify-node-link'


def test_import_rejects_dangling_duplicate_or_ambiguous_nodes():
    value = fixture()
    value['links'][0]['target'] = 'invented'
    with pytest.raises(ValueError): normalize(value)
    value = fixture()
    value['nodes'].append({'id': 'a'})
    with pytest.raises(ValueError): normalize(value)


def test_evaluation_is_grounded_and_never_invents_savings():
    nodes, edges, _ = normalize(fixture())
    result = evaluate('Add supplier', GraphIndex(nodes, edges), ['a'], [{'name': 'Adapter', 'node_ids': ['a']}])
    assert result['mode'] == 'structural'
    assert result['current']['potentially_affected_nodes'] == ['a', 'b', 'c']
    assert result['proposed']['cross_boundary_dependencies'] == 1
    assert evaluate('Unknown', None, [], [])['mode'] == 'qualitative'

@pytest.mark.parametrize('patch',[{'graph':None},{'graph':[]},{'directed':'yes'}])
def test_import_rejects_malformed_graph_metadata(patch):
    with pytest.raises(ValueError): normalize({**fixture(),**patch})

@pytest.mark.parametrize('endpoint',[[],{},None,123])
def test_import_rejects_nonstring_endpoints(endpoint):
    value=fixture();value['links'][0]['source']=endpoint
    with pytest.raises(ValueError): normalize(value)
