import json
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from galvanise.dependencies import require_project
from galvanise.models import TechnicalGraph
from galvanise.services.knowledge import records_for, save_proposals, bounded_context
from galvanise.agents.schemas import Proposal
from galvanise.graph.core import GraphIndex, evaluate


class Args(BaseModel):
    model_config=ConfigDict(extra='forbid')
    query: str = Field(max_length=300)
    graph_id: str
    node_id: str
    target_id: str
    proposal: Proposal | None


NAMES={'get_project_context','list_business_decisions','list_change_drivers','create_business_decision','create_change_driver','create_business_requirement','create_volatility_hypothesis','create_stakeholder_question','get_technical_graph_summary','search_code_nodes','get_node_dependencies','find_dependency_paths','get_architecture_candidate','evaluate_change_scenario','save_stakeholder_answer','generate_architecture_candidates','map_business_to_code'}


DESIGN_TOOLS = {
    "analyze_design": "Analyze the project evidence and queue a versioned system design.",
    "revise_design": "Apply the current user's explicit correction to the published architecture.",
    "plan_project": "Generate the editable activity graph for the published architecture.",
}


def definitions(user_content=None):
    from galvanise.agents.design_chat import command
    allowed = command(user_content) if user_content is not None else None
    design_tools = [
        {"type": "function", "name": name, "description": description,
         "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
         "strict": True}
        for name, description in DESIGN_TOOLS.items()
        if user_content is None or name == allowed
    ]
    return design_tools + [{'type':'function','name':name,'description':'Project-scoped '+name+'. For save_stakeholder_answer use node_id=known question ID, query=exact authenticated user answer; do not infer an answer. For map_business_to_code use node_id=decision ID, graph_id and query. Unused string arguments must be empty; proposal null unless creating pending knowledge.','parameters':Args.model_json_schema(),'strict':True} for name in sorted(NAMES)]


async def invoke(name, raw, db, project_id, user, client=None, user_content=None, *, message_id=None, revision_id=None):
    project=require_project(project_id,db,user)
    if name in DESIGN_TOOLS:
        from galvanise.agents.design_chat import command
        from galvanise.design_engine import service
        from galvanise.design_engine.sources import user_message

        if json.loads(raw) != {} or not message_id:
            raise ValueError("Design tools require the current authenticated chat message")
        message = user_message(db, project_id, message_id)
        if message.content != user_content or command(message.content) != name:
            raise ValueError("The current message does not request this design operation")
        if name == "analyze_design":
            return service.analyze_design(db, project_id, user, request_message_id=message_id,
                                          idempotency_key=message_id)
        if not revision_id:
            raise ValueError("Design the system first to publish an architecture")
        if name == "revise_design":
            return service.revise_design(db, project_id, user, base_revision_id=revision_id,
                                         correction_message_id=message_id, idempotency_key=message_id)
        return service.plan_project(db, project_id, user, revision_id=revision_id, planning_inputs={})
    if name not in NAMES: raise ValueError('Unknown tool')
    args=Args.model_validate_json(raw)
    records=records_for(db,project_id)
    if name=='get_project_context': return {'name':project.name,'description':project.description,'objective':project.objective,**bounded_context(db,project_id)}
    if name in {'list_business_decisions','list_change_drivers','get_architecture_candidate'}:
        kind={'list_business_decisions':'decision','list_change_drivers':'driver','get_architecture_candidate':'architecture'}[name]
        return [{'id':r.id,'title':r.title,'payload':r.payload,'status':r.status} for r in records if r.kind==kind][:30]
    if name=='save_stakeholder_answer':
        if not user_content or args.query.strip() not in user_content: raise ValueError('Answer must quote the current authenticated user statement verbatim')
        from galvanise.routes.intelligence import answer, AnswerInput
        record=answer(project_id,args.node_id,AnswerInput(answer=args.query),db,user)
        return {'record_ids':[record['id']],'status':'pending','evidence_status':'human_confirmed'}
    if name=='generate_architecture_candidates':
        from galvanise.routes.intelligence import generate_candidates
        result=await generate_candidates(project_id,db,client)
        return {**result,'record_ids':[r['id'] for r in result['records']]}
    if name=='map_business_to_code':
        from galvanise.routes.intelligence import generate_traceability, TraceInput
        result=await generate_traceability(project_id,TraceInput(decision_id=args.node_id,graph_id=args.graph_id,query=args.query),db,client)
        return {**result,'record_ids':[r['id'] for r in result['records']]}
    if name.startswith('create_'):
        expected={'create_change_driver':'driver','create_business_requirement':'requirement','create_business_decision':'decision','create_volatility_hypothesis':'volatility','create_stakeholder_question':'question'}[name]
        if args.proposal is None or args.proposal.kind != expected: raise ValueError('Proposal kind does not match tool')
        return {'record_ids':[r.id for r in save_proposals(db,project_id,[args.proposal])],'status':'pending'}
    graphs=list(db.scalars(select(TechnicalGraph).where(TechnicalGraph.project_id==project_id)).all())
    if name=='get_technical_graph_summary': return [{'id':g.id,'name':g.name,'nodes':len(g.nodes_json),'edges':len(g.edges_json)} for g in graphs[:20]]
    graph=next((g for g in graphs if g.id==args.graph_id),None)
    if not graph: raise ValueError('Unknown project graph')
    index=GraphIndex(graph.nodes_json,graph.edges_json,graph.metadata_json.get('directed',True))
    if name=='search_code_nodes': return index.search(args.query)
    if name=='get_node_dependencies': return index.dependencies(args.node_id)
    if name=='find_dependency_paths': return {'paths':index.paths(args.node_id,args.target_id)}
    return evaluate(args.query,index,[args.node_id] if args.node_id else [],[])
