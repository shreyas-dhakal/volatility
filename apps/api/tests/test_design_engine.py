"""Design workflow tests use real persistence/routes and mock only the AI provider."""
import os
os.environ.update(DATABASE_URL='sqlite://', APP_ENV='test', AUTH_SECRET='test-secret-that-is-at-least-32-characters', AUTO_CREATE_TABLES='true')
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from galvanise.main import app
from galvanise.database import Base, engine, SessionLocal
from galvanise.models import KnowledgeRecord, SourceDocument


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        c.post('/api/auth/register', json={'email':'design@example.com','password':'long-password-123','name':'Architect'})
        yield c


def project(c):
    return c.post('/api/projects', json={'name':'Purchasing','system_type':'new'}).json()['id']


def intake(c, pid, **changes):
    body=dict(title='Place order',description='Buy supplies',actor='Buyer',trigger='Stock low',preconditions=['Buyer authorized'],steps=['Select supplies','Submit order'],outcome='Order accepted',variations=['Rush order','Supplier unavailable'],evidence_ids=[])
    return c.post(f'/api/projects/{pid}/design/use-cases',json={**body,**changes})


def approve(c,pid,r):
    response=c.patch(f"/api/projects/{pid}/records/{r['id']}",json={'expected_version':r['version'],'status':'approved'})
    assert response.status_code==200,response.text
    return response.json()


def generate(c,pid,stage):
    return c.post(f'/api/projects/{pid}/design/generate',json={'stage':stage})


def provider(monkeypatch, records):
    import galvanise.routes.design as routes
    async def parse(**kwargs):
        return SimpleNamespace(status='completed',output_parsed=kwargs['text_format'].model_validate({'records':records}))
    fake=SimpleNamespace(responses=SimpleNamespace(parse=AsyncMock(side_effect=parse)),close=AsyncMock())
    monkeypatch.setattr(routes,'configured_client',lambda:fake)
    return fake


def core(uid, **changes):
    return dict(title='Acquire supplies',description='Business outcome independent of ordering channel',use_case_ids=[uid],rationale='Rush and normal orders share the acquisition outcome',unresolved_use_case_ids=[],evidence_ids=[],uncertainty='Confirm cancellations',open_questions=['Are cancellations included?'],**changes)


def volatility(cid):
    return dict(title='Supplier protocol',description='Protocol can change independently of acquisition',core_use_case_ids=[cid],axis='over_time',what_changes='Supplier request protocol',why_plausible='Supplier migration is planned',stable_aspects=['Acquisition outcome'],examples=['REST to messages'],evidence_ids=[],uncertainty='Migration date unknown',open_questions=['When will supplier migrate?'])


def component(vid,title='Supplier access',dependencies=None):
    return dict(title=title,description='Encapsulate protocol',component_role='resource_access',volatility_ids=[vid],responsibility='Translate purchase requests',hidden_change='Supplier protocol',stable_contract='submit(PurchaseRequest) -> OrderReceipt',excluded_responsibilities=['Approval orchestration'],dependencies=dependencies or [],evidence_ids=[],uncertainty='Error semantics need agreement',open_questions=[])


def validation(cid,vid,bid):
    return dict(title='Acquisition review',description='Qualitative proposed collaboration and change scenario',collaborations=[dict(core_use_case_id=cid,component_ids=[bid],steps=['Submit through stable contract'])],scenarios=[dict(title='Supplier moves to messages',volatility_id=vid,changed_component_ids=[bid],unchanged_component_ids=[],rationale='Only protocol translation changes')],assumptions=['No execution verified'],evidence_ids=[])


def stages(c,pid,monkeypatch):
    u=approve(c,pid,intake(c,pid).json())
    provider(monkeypatch,[core(u['id'])]); response=generate(c,pid,'core');assert response.status_code==200,response.text
    co=approve(c,pid,response.json()['records'][0])
    provider(monkeypatch,[volatility(co['id'])]); response=generate(c,pid,'volatility');assert response.status_code==200,response.text
    v=approve(c,pid,response.json()['records'][0])
    provider(monkeypatch,[component(v['id'])]); response=generate(c,pid,'decomposition');assert response.status_code==200,response.text
    b=approve(c,pid,response.json()['records'][0])
    return u,co,v,b


def test_manual_intake_validation_evidence_and_owner_isolation(client):
    pid=project(client)
    response=intake(client,pid)
    assert response.status_code==200,response.text
    r=response.json()
    assert (r['kind'],r['status'],r['evidence_status'],r['version'])==('use_case','pending','human_confirmed',1)
    assert r['payload']['variations']==['Rush order','Supplier unavailable']
    for changes in [{'title':' '},{'steps':[]},{'steps':[' ']},{'outcome':''},{'evidence_ids':['outside']},{'actor':'a'*10001}]:
        assert intake(client,pid,**changes).status_code==422
    other=project(client)
    with SessionLocal() as db:
        d=SourceDocument(project_id=other,name='Outside',content='Private');db.add(d);db.commit();did=d.id
    assert intake(client,pid,evidence_ids=[did]).status_code==422
    client.post('/api/auth/logout')
    assert client.get(f'/api/projects/{pid}/design').status_code==401
    client.post('/api/auth/register',json={'email':'outside@example.com','password':'long-password-123','name':'Outside'})
    for method,path,body in [('get','',None),('post','/use-cases',{}),('post','/generate',{'stage':'core'})]:
        response=getattr(client,method)(f'/api/projects/{pid}/design{path}',**({'json':body} if body is not None else {}))
        assert response.status_code in (404,422)
    assert client.get(f'/api/projects/{pid}/design').status_code==404


def test_prerequisites_config_and_pending_inputs(client,monkeypatch):
    from galvanise.config import settings
    monkeypatch.setattr(settings,'openai_api_key','')
    pid=project(client)
    for stage in ['core','volatility','decomposition','validation']:
        response=generate(client,pid,stage)
        assert response.status_code==422,response.text
        assert 'require' in response.text.lower()
    u=intake(client,pid).json()
    assert generate(client,pid,'core').status_code==503
    fake=provider(monkeypatch,[core(u['id'])])
    response=generate(client,pid,'core');assert response.status_code==200,response.text
    assert generate(client,pid,'volatility').status_code==422
    co=approve(client,pid,response.json()['records'][0])
    provider(monkeypatch,[volatility(co['id'])])
    assert generate(client,pid,'volatility').status_code==200
    sent=json.loads(fake.responses.parse.call_args.kwargs['input'])
    assert u['id'] in str(sent) and 'Rush order' in str(sent)
    assert 'untrusted' in fake.responses.parse.call_args.kwargs['instructions']
    fake.close.assert_awaited_once()


@pytest.mark.parametrize('bad_link',['missing','wrong_kind','cross_project'])
def test_generated_references_are_typed_owned_and_atomic(client,monkeypatch,bad_link):
    pid=project(client);u=intake(client,pid).json();foreign=intake(client,project(client)).json()
    with SessionLocal() as db:
        d=SourceDocument(project_id=pid,name='Evidence',content='Notes');db.add(d);db.commit();did=d.id
    link={'missing':'invented','wrong_kind':did,'cross_project':foreign['id']}[bad_link]
    provider(monkeypatch,[core(u['id']),{**core(link),'title':'Invalid'}])
    response=generate(client,pid,'core')
    assert response.status_code==422,response.text
    assert client.get(f'/api/projects/{pid}/design').json()['core_use_cases']==[]


def test_generation_preserves_approved_and_tracks_versions_and_variations(client,monkeypatch):
    pid=project(client);u,co,v,b=stages(client,pid,monkeypatch)
    provider(monkeypatch,[core(u['id'])])
    response=generate(client,pid,'core')
    assert response.json()['records'][0]['id']==co['id']
    provider(monkeypatch,[{**core(u['id']),'description':'A revised hypothesis'}])
    revised=generate(client,pid,'core').json()['records'][0]
    assert revised['id']!=co['id'] and revised['status']=='pending'
    assert revised['payload']['supersedes_id']==co['id']
    records=client.get(f'/api/projects/{pid}/records').json()
    original=next(r for r in records if r['id']==co['id'])
    assert original==co
    assert next(r for r in records if r['id']==u['id'])['payload']['variations']==u['payload']['variations']


def test_complete_journey_and_stale_validation_after_upstream_review(client,monkeypatch):
    pid=project(client);u,co,v,b=stages(client,pid,monkeypatch)
    provider(monkeypatch,[validation(co['id'],v['id'],b['id'])])
    response=generate(client,pid,'validation');assert response.status_code==200,response.text
    val=approve(client,pid,response.json()['records'][0])
    assert b['id'] in val['payload']['input_versions']
    view=client.get(f'/api/projects/{pid}/design').json()
    assert all(view['readiness'].values()),view
    assert view['validations'][0]['payload']['stale'] is False
    patch=client.patch(f"/api/projects/{pid}/records/{u['id']}",json={'expected_version':u['version'],'status':'rejected'})
    assert patch.status_code==200,patch.text
    view=client.get(f'/api/projects/{pid}/design').json()
    assert not view['readiness']['validation']
    assert any(f['code']=='stale_validation' for f in view['findings'])
    assert view['validations'][0]['payload']['stale'] is True
    assert client.patch(f"/api/projects/{pid}/records/{u['id']}",json={'expected_version':u['version'],'status':'approved'}).status_code==409


def test_patch_rejects_invalid_design_payload_without_mutation(client,monkeypatch):
    pid=project(client);u,co,v,b=stages(client,pid,monkeypatch)
    for payload in [{**b['payload'],'volatility_ids':[co['id']]},{**b['payload'],'dependencies':['invented']},{**b['payload'],'stable_contract':' '},{**b['payload'],'component_role':'service'}]:
        response=client.patch(f"/api/projects/{pid}/records/{b['id']}",json={'expected_version':b['version'],'payload':payload})
        assert response.status_code==422,response.text
    assert next(r for r in client.get(f'/api/projects/{pid}/records').json() if r['id']==b['id'])==b


def test_decomposition_resolves_batch_dependencies_and_rejects_invalid_contract(client,monkeypatch):
    pid=project(client);u,co,v,b=stages(client,pid,monkeypatch)
    provider(monkeypatch,[component(v['id'],'Workflow',['Policy']),{**component(v['id'],'Policy',['Workflow']),'component_role':'engine'}])
    response=generate(client,pid,'decomposition');assert response.status_code==200,response.text
    rows=response.json()['records'];by_title={r['title']:r for r in rows}
    assert by_title['Workflow']['payload']['dependencies']==[by_title['Policy']['id']]
    assert by_title['Policy']['payload']['dependencies']==[by_title['Workflow']['id']]
    view=client.get(f'/api/projects/{pid}/design').json()
    assert any(f['code']=='dependency_cycle' for f in view['findings'])
    provider(monkeypatch,[{**component(v['id'],'Broken'),'stable_contract':''}])
    assert generate(client,pid,'decomposition').status_code==422
    assert len(client.get(f'/api/projects/{pid}/design').json()['components'])==3


def test_failed_provider_saves_nothing_and_closes(client,monkeypatch):
    pid=project(client);intake(client,pid)
    fake=provider(monkeypatch,[])
    fake.responses.parse.side_effect=RuntimeError('provider-secret')
    response=generate(client,pid,'core')
    assert response.status_code==502 and 'provider-secret' not in response.text
    fake.close.assert_awaited_once()
    assert client.get(f'/api/projects/{pid}/design').json()['core_use_cases']==[]


def test_deterministic_coverage_contracts_dependencies_and_containment(client,monkeypatch):
    pid=project(client)
    u,co,v,b=stages(client,pid,monkeypatch)
    unlinked=intake(client,pid,title='Cancel order').json()
    # Historical/malformed stored artifacts must be diagnosed even if they predate
    # strict write checks. Keep their original records visible for remediation.
    with SessionLocal() as db:
        broken=KnowledgeRecord(project_id=pid,kind='boundary',title='Legacy boundary',status='approved',payload={'design_engine':True,'volatility_ids':[],'dependencies':['unknown'],'stable_contract':''})
        db.add(broken);db.commit();broken_id=broken.id
    view=client.get(f'/api/projects/{pid}/design').json()
    codes={f['code'] for f in view['findings']}
    assert {'uncovered_use_case','missing_contract','unknown_dependency','missing_collaboration','missing_change_scenario','invalid_reference_or_payload'}<=codes
    assert any(unlinked['id'] in f['record_ids'] for f in view['findings'] if f['code']=='uncovered_use_case')
    assert any(broken_id in f['record_ids'] for f in view['findings'] if f['code']=='missing_contract')


def test_invalid_stored_artifacts_are_not_ready(client):
    pid=project(client)
    with SessionLocal() as db:
        db.add(KnowledgeRecord(project_id=pid,kind='use_case',title='Incomplete imported case',status='approved',payload={}))
        db.commit()
    view=client.get(f'/api/projects/{pid}/design').json()
    assert view['readiness']['use_cases'] is False
    assert generate(client,pid,'core').status_code==422


def test_validation_references_and_disjoint_scenarios_checked_before_save(client,monkeypatch):
    pid=project(client);u,co,v,b=stages(client,pid,monkeypatch)
    valid=validation(co['id'],v['id'],b['id'])
    invalids=[{**valid,'collaborations':[{'core_use_case_id':u['id'],'component_ids':[b['id']],'steps':['Try']} ]},
              {**valid,'scenarios':[{**valid['scenarios'][0],'volatility_id':co['id']}]},
              {**valid,'scenarios':[{**valid['scenarios'][0],'unchanged_component_ids':[b['id']]}]},
              {**valid,'scenarios':[{**valid['scenarios'][0],'changed_component_ids':[v['id']]}]}]
    for invalid in invalids:
        provider(monkeypatch,[valid,{**invalid,'title':'Invalid scenario'}])
        assert generate(client,pid,'validation').status_code==422
        assert client.get(f'/api/projects/{pid}/design').json()['validations']==[]


def test_incomplete_and_empty_output_never_create_fake_artifacts(client,monkeypatch):
    pid=project(client);u=intake(client,pid).json()
    fake=provider(monkeypatch,[core(u['id'])])
    fake.responses.parse.side_effect=None
    for response in [SimpleNamespace(status='incomplete',output_parsed=None),SimpleNamespace(status='completed',output_parsed=None)]:
        fake.responses.parse.return_value=response
        assert generate(client,pid,'core').status_code==422
    provider(monkeypatch,[])
    assert generate(client,pid,'core').status_code==422
    assert client.get(f'/api/projects/{pid}/design').json()['core_use_cases']==[]


def test_server_owned_provenance_cannot_be_forged_or_removed(client,monkeypatch):
    pid=project(client);u,co,v,b=stages(client,pid,monkeypatch)
    for payload in [{**b['payload'],'design_engine':False},{**b['payload'],'input_versions':{}},{k:v for k,v in b['payload'].items() if k!='input_versions'}]:
        assert client.patch(f"/api/projects/{pid}/records/{b['id']}",json={'expected_version':b['version'],'payload':payload}).status_code==422


def test_generation_detects_inputs_changed_during_provider_call(client,monkeypatch):
    from galvanise.agents.design_schemas import CoreResult
    pid=project(client);u=intake(client,pid).json()
    fake=provider(monkeypatch,[core(u['id'])])
    async def change_inputs(**kwargs):
        with SessionLocal() as db:
            row=db.get(KnowledgeRecord,u['id']);row.version+=1;row.description='Changed during request';db.commit()
        return SimpleNamespace(status='completed',output_parsed=CoreResult.model_validate({'records':[core(u['id'])]}))
    fake.responses.parse.side_effect=change_inputs
    response=generate(client,pid,'core')
    assert response.status_code==409,response.text
    assert client.get(f'/api/projects/{pid}/design').json()['core_use_cases']==[]


def test_context_is_bounded_and_truncation_visible(client,monkeypatch):
    pid=project(client)
    with SessionLocal() as db:
        for i in range(110):
            db.add(KnowledgeRecord(project_id=pid,kind='use_case',title=f'Case {i}',status='approved',description='Original',payload={'actor':'Buyer','trigger':'Stock low','preconditions':[],'steps':['Order supplies'],'outcome':'Accepted','variations':['v'*6000]*10,'evidence_ids':[]}))
        db.commit()
        uid=db.scalar(select(KnowledgeRecord.id).where(KnowledgeRecord.project_id==pid))
    fake=provider(monkeypatch,[core(uid)])
    response=generate(client,pid,'core');assert response.status_code==200,response.text
    text=fake.responses.parse.call_args.kwargs['input'];context=json.loads(text)
    assert len(text)<110000
    assert context['context_limits']['design_records_omitted']>0
    assert context['context_limits']['design_payloads_truncated']>0
    assert response.json()['records'][0]['payload']['context_limits']['design_records_omitted']>0
    assert any(f['code']=='context_truncated' for f in client.get(f'/api/projects/{pid}/design').json()['findings'])


def test_same_batch_component_cycle_rerun_preserves_approved_records(client,monkeypatch):
    pid=project(client);u,co,v,b=stages(client,pid,monkeypatch)
    proposals=[component(v['id'],'Workflow',['Policy']),component(v['id'],'Policy',['Workflow'])]
    provider(monkeypatch,proposals)
    first=generate(client,pid,'decomposition').json()['records']
    approved=[approve(client,pid,r) for r in first]
    provider(monkeypatch,proposals)
    again=generate(client,pid,'decomposition')
    assert again.status_code==200,again.text
    assert again.json()['records']==approved
