"""Bounded structural analysis; imported relationships remain claims from their source."""
import networkx as nx

GRAPHIFY_COMMIT = '480b61ed91cbc08177dc2c60caa9ffd6c9b95749'


def normalize(data):
    if not isinstance(data, dict) or not isinstance(data.get('nodes'), list):
        raise ValueError('Expected Graphify object with nodes and links (or extraction edges) arrays')
    if 'graph' in data and not isinstance(data['graph'], dict): raise ValueError('Graph metadata must be an object')
    if 'directed' in data and not isinstance(data['directed'], bool): raise ValueError('Directed must be boolean')
    raw_edges = data.get('links', data.get('edges'))
    if not isinstance(raw_edges, list): raise ValueError('Missing links/edges array')
    for n in data['nodes']:
        if isinstance(n,dict):
            for key in ('label','type','file_type','source_file','file_path','source_id'):
                if key in n and n[key] is not None and not isinstance(n[key],str): raise ValueError(f'Node {key} must be a string or null')
    if len(data['nodes']) > 20000 or len(raw_edges) > 60000: raise ValueError('Graph exceeds 20,000 nodes / 60,000 edges')
    nodes, edges, seen = [], [], set()
    for raw in data['nodes']:
        if not isinstance(raw, dict) or not isinstance(raw.get('id'), str) or not raw['id'] or len(raw['id']) > 500:
            raise ValueError('Every node needs a bounded string id')
        if raw['id'] in seen: raise ValueError('Duplicate node id')
        seen.add(raw['id'])
        nodes.append({'id': raw['id'], 'label': str(raw.get('label', raw['id']))[:500], 'type': str(raw.get('type', raw.get('file_type', 'component')))[:100], 'file_path': raw.get('source_file', raw.get('file_path')), 'source_id': raw.get('source_id'), 'metadata': {k:v for k,v in raw.items() if k not in {'id','label'}}})
    for i, raw in enumerate(raw_edges):
        if not isinstance(raw, dict) or not isinstance(raw.get('source'), str) or not isinstance(raw.get('target'), str) or raw.get('source') not in seen or raw.get('target') not in seen: raise ValueError('Edge endpoint does not exist')
        edges.append({'id': f'e{i}', 'source': raw['source'], 'target': raw['target'], 'type': str(raw.get('relation', raw.get('type', 'related')))[:100], 'metadata': {k:v for k,v in raw.items() if k not in {'source','target'}}})
    return nodes, edges, {'dialect': 'graphify-node-link' if 'links' in data else 'graphify-extraction', 'directed': data.get('directed', True), 'provenance_url': 'https://github.com/Graphify-Labs/graphify', 'schema_inspected_commit': GRAPHIFY_COMMIT, 'hyperedges': data.get('hyperedges', data.get('graph', {}).get('hyperedges', [])), 'upstream_metadata':data.get('graph',{}), 'warning': 'Relationships preserve upstream claims and confidence; imports do not verify implementation, business meaning or runtime effects.'}


class GraphIndex:
    def __init__(self, nodes, edges, directed=True):
        self.nodes = {n['id']: n for n in nodes}
        self.edges = edges
        self.graph = nx.DiGraph() if directed else nx.Graph()
        self.graph.add_nodes_from(self.nodes)
        self.graph.add_edges_from((e['source'], e['target']) for e in edges)

    def search(self, query, limit=20):
        terms = query.casefold().split()[:12]
        ranked = [(sum(t in (n['label']+' '+str(n.get('file_path') or '')).casefold() for t in terms), n) for n in self.nodes.values()]
        return [n for score,n in sorted(ranked, key=lambda item: -item[0]) if score][:limit]

    def paths(self, source, target):
        if source not in self.nodes or target not in self.nodes: raise ValueError('Unknown node id')
        try: return [nx.shortest_path(self.graph, source, target)]
        except nx.NetworkXNoPath: return []

    def dependencies(self, node_id):
        if node_id not in self.nodes: raise ValueError('Unknown node id')
        return {'node': self.nodes[node_id], 'dependencies': [e for e in self.edges if node_id in (e['source'],e['target'])][:100]}

    def subgraph(self, query='', focus=None, limit=80):
        limit = min(max(limit,1),200)
        undirected = self.graph.to_undirected(as_view=True)
        if focus:
            if focus not in self.nodes: raise ValueError('Unknown focus node')
            chosen = [focus]
            for _,v in nx.bfs_edges(undirected, focus):
                if len(chosen) >= limit: break
                chosen.append(v)
        elif query: chosen = [n['id'] for n in self.search(query, limit)]
        else: chosen = sorted(self.nodes, key=lambda n: self.graph.degree(n), reverse=True)[:limit]
        selected = set(chosen)
        hubs = sorted(self.graph.degree, key=lambda pair: pair[1], reverse=True)[:8]
        view_edges = [e for e in self.edges if e['source'] in selected and e['target'] in selected]
        return {'nodes': [dict(self.nodes[n]) for n in chosen], 'edges': view_edges[:2000], 'summary': {'total_nodes': len(self.nodes), 'total_edges': len(self.edges), 'components': nx.number_connected_components(undirected), 'hubs': [{'id':n,'degree':d} for n,d in hubs], 'truncated': len(selected)<len(self.nodes), 'edges_truncated':len(view_edges)>2000}}


def evaluate(scenario, index, node_ids, boundaries):
    assumptions = ['Structural reachability is a potential impact envelope, not predicted code changes or measured savings.', 'Dependencies do not establish runtime effects or regression coverage.']
    if not index or not node_ids:
        return {'scenario':scenario,'mode':'qualitative','current':{'assessment':'Technical mappings are insufficient to calculate impact.'},'proposed':{'boundaries':boundaries,'assessment':'Review contracts and operational tradeoffs with stakeholders.'},'assumptions':assumptions}
    if not set(node_ids) <= index.nodes.keys(): raise ValueError('Unknown scenario node id')
    affected = set(node_ids)
    for node in node_ids: affected.update(nx.descendants(index.graph,node) if index.graph.is_directed() else nx.node_connected_component(index.graph,node))
    membership = {}
    for i,b in enumerate(boundaries):
        for n in b.get('node_ids',[]):
            if n not in index.nodes: raise ValueError('Unknown boundary node id')
            if n in membership: raise ValueError('Overlapping boundaries cannot be compared')
            membership[n] = i
    cross = sum(membership.get(e['source'],-1) != membership.get(e['target'],-1) for e in index.edges if e['source'] in affected or e['target'] in affected)
    return {'scenario':scenario,'mode':'structural','current':{'potentially_affected_nodes':sorted(affected),'dependency_edges_in_envelope':sum(e['source'] in affected and e['target'] in affected for e in index.edges),'regression_scope':'Review tests covering reachable components; coverage is not measured.'},'proposed':{'cross_boundary_dependencies':cross if membership else None,'boundaries':boundaries,'changed_interfaces':'Contracts are proposals requiring review; no code transformation is assumed.'},'assumptions':assumptions}
