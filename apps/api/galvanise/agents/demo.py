"""Explicit synthetic fixture seed; no provider calls or fake integration state."""
import json
from pathlib import Path
from galvanise.models import Project, SourceDocument, TechnicalGraph, Conversation, Message, KnowledgeRecord
from galvanise.graph.core import normalize


def seed(db,user):
    root=Path(__file__).resolve().parents[4]
    document=(root/'examples/wholesale-requirements.md').read_text()
    nodes,edges,metadata=normalize(json.loads((root/'examples/wholesale-graphify.json').read_text()))
    metadata['synthetic']=True
    project=Project(user_id=user.id,name='Wholesale ERP Modernisation - synthetic demo',description='Explicitly seeded fictional requirements and structural graph. No live integration or AI analysis.',system_type='existing',objective='Explore supplier adapters and warehouse allocation boundaries')
    db.add(project);db.flush()
    doc=SourceDocument(project_id=project.id,name='Synthetic wholesale requirements',content=document,media_type='text/markdown',metadata_json={'synthetic':True})
    graph=TechnicalGraph(project_id=project.id,name='Synthetic legacy wholesale graph',nodes_json=nodes,edges_json=edges,metadata_json=metadata)
    conversation=Conversation(project_id=project.id,title='Wholesale modernisation discovery')
    db.add_all([doc,graph,conversation]);db.flush()
    db.add(Message(project_id=project.id,conversation_id=conversation.id,role='user',content="Synthetic scenario: We're expanding to five warehouses next year. We constantly change supplier integrations, but our order-processing rules rarely change.",metadata_json={'synthetic':True}))
    decision=KnowledgeRecord(project_id=project.id,kind='decision',title='Keep purchasing workflow stable during supplier expansion',description='Synthetic stakeholder statement supplied by the fixture; review before using.',status='pending',evidence_status='hypothesis',payload={'synthetic':True,'evidence_ids':[doc.id],'node_ids':[]})
    db.add(decision);db.flush()
    for kind,title,description,payload in [
        ('driver','Supplier expansion','Synthetic plan to onboard suppliers with distinct API protocols.',{}),
        ('volatility','Supplier protocols may change independently','Anticipated volatility; no historical measurement supplied.',{'volatility_type':'anticipated','stable_decisions':['Internal purchasing workflow'],'time_horizon':'Next year','uncertainty':'Supplier-dependent approval rules are unknown.'}),
        ('question','Do suppliers change purchasing approval rules or only protocols?','Ask the purchasing owner before choosing an adapter contract.',{'stakeholder_role':'Purchasing owner','priority':'Design-changing'})]:
        db.add(KnowledgeRecord(project_id=project.id,kind=kind,title=title,description=description,status='pending',evidence_status='hypothesis',payload={**payload,'synthetic':True,'evidence_ids':[doc.id],'node_ids':[]}))
    db.commit();return project
