"""Pending proposals are append-only with exact-content dedup; approval belongs to human routes."""
import json
from sqlalchemy import select
from galvanise.models import KnowledgeRecord, SourceDocument, Message, TechnicalGraph


def records_for(db, project_id):
    return list(db.scalars(select(KnowledgeRecord).where(KnowledgeRecord.project_id==project_id).order_by(KnowledgeRecord.created_at)).all())


def evidence_ids(db, project_id):
    ids = set(db.scalars(select(SourceDocument.id).where(SourceDocument.project_id==project_id)).all())
    ids.update(db.scalars(select(Message.id).where(Message.project_id==project_id)).all())
    ids.update(r.id for r in records_for(db,project_id))
    return ids


def node_ids(db, project_id):
    return {n['id'] for g in db.scalars(select(TechnicalGraph).where(TechnicalGraph.project_id==project_id)).all() for n in g.nodes_json}


def validate_references(payload, allowed_evidence, allowed_nodes):
    if isinstance(payload,dict):
        for key,value in payload.items():
            if key == 'evidence_ids' and not set(value)<=allowed_evidence: raise ValueError('Unknown or cross-project evidence id')
            if key == 'node_ids' and not set(value)<=allowed_nodes: raise ValueError('Unknown or cross-project technical node id')
            validate_references(value,allowed_evidence,allowed_nodes)
    elif isinstance(payload,list):
        for item in payload: validate_references(item,allowed_evidence,allowed_nodes)


def save_proposals(db, project_id, proposals):
    allowed_evidence, allowed_nodes = evidence_ids(db,project_id), node_ids(db,project_id)
    existing = records_for(db,project_id)
    prepared = []
    for p in proposals:
        value = p.model_dump() if hasattr(p,'model_dump') else dict(p)
        validate_references(value,allowed_evidence,allowed_nodes)
        # Validate all proposals before adding any; never mutate existing approved records.
        prepared.append(value)
    result=[]
    for value in prepared:
        kind,title = value.pop('kind'),value.pop('title')
        description=value.pop('description','')
        # Lineage is generated here and excluded from substantive content comparison.
        lineage={'supersedes_id','proposal_revision'}
        value={k:v for k,v in value.items() if k not in lineage}
        same_identity=[r for r in existing if r.kind==kind and r.title.casefold().strip()==title.casefold().strip() and (kind!='traceability' or (r.payload.get('graph_id'),r.payload.get('decision_id'))==(value.get('graph_id'),value.get('decision_id')))]
        duplicate=next((r for r in reversed(same_identity) if r.status!='rejected' and r.title==title and r.description==description and {k:v for k,v in r.payload.items() if k not in lineage}==value),None)
        if duplicate:
            result.append(duplicate)
            continue
        history=[]
        if same_identity:
            previous=same_identity[-1]
            value={**value,'supersedes_id':previous.id,'proposal_revision':previous.payload.get('proposal_revision',1)+1}
            history=[{'source_record_id':previous.id,'source_version':previous.version,'title':previous.title,'description':previous.description,'status':previous.status,'evidence_status':previous.evidence_status,'payload':previous.payload}]
        record=KnowledgeRecord(project_id=project_id,kind=kind,title=title,description=description,status='pending',evidence_status='ai_inferred' if value.get('evidence_ids') else 'hypothesis',payload=value,history=history)
        db.add(record); db.flush(); existing.append(record); result.append(record)
    db.commit()
    return result


def bounded_context(db, project_id, document_ids=None):
    docs=select(SourceDocument).where(SourceDocument.project_id==project_id)
    if document_ids is not None:
        docs=docs.where(SourceDocument.id.in_(document_ids))
    source=list(db.scalars(docs.limit(12)).all())
    if document_ids and len(source)!=len(set(document_ids)): raise ValueError('Unknown document id or selection exceeds 12 documents')
    messages=list(db.scalars(select(Message).where(Message.project_id==project_id).order_by(Message.created_at.desc()).limit(16)).all())
    records=records_for(db,project_id)
    # Approved context is consulted before pending proposals; keep answers independently
    # available even when their question is approved or the originating chat has aged out.
    ordered=sorted(enumerate(records),key=lambda item:(0 if item[1].status=='approved' else 1 if item[1].kind=='answer' else 2,-item[0]))
    def context_record(record):
        payload=record.payload
        encoded=json.dumps(payload,default=str)
        if len(encoded)>2500: payload={'bounded_excerpt':encoded[:2500],'truncated':True}
        return {'id':record.id,'kind':record.kind,'title':record.title[:300],'description':record.description[:2000],'status':record.status,'evidence_status':record.evidence_status,'payload':payload}
    answers=[context_record(r) for r in reversed(records) if r.kind=='answer' and r.status!='rejected'][:20]
    knowledge=[context_record(r) for _,r in ordered if r.status!='rejected'][:60]
    return {'stakeholder_answers':answers,'knowledge':knowledge,
            'context_limits':{'knowledge_records_omitted':max(0,sum(r.status!='rejected' for r in records)-len(knowledge)),'answer_records_omitted':max(0,sum(r.kind=='answer' and r.status!='rejected' for r in records)-len(answers))},
            'documents':[{'id':d.id,'name':d.name,'untrusted_text':d.content[:5000]} for d in source],
            'messages':[{'id':m.id,'role':m.role,'untrusted_text':m.content[:2000]} for m in reversed(messages)]}



def serialize(record):
    return {c.name:getattr(record,c.name) for c in record.__table__.columns}
