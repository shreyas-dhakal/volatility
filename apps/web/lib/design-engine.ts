import type {DateInputProps} from '@astryxdesign/core/DateInput';
type CalendarDate = NonNullable<DateInputProps['value']>;

export type Evidence = {chunk_id:string; excerpt:string};
export type Entity = {id:string; evidence?:Evidence[]; [field:string]:unknown};
export type Explanation = {
  owner_id:string; established:string; uncertainty:string|null; approach:string; rationale:string;
  reconsider_when:string; hypothetical_alternative:string|null; evidence:Evidence[];
};
export type Decision = Entity & {
  decision:string; driver:string; status:string; alternatives:{description:string;hypothetical:boolean}[];
  use_case_ids:string[]; explanation?:Explanation|null;
  answers?:{base_revision_id:string;question_id:string;question:string;evidence:Evidence}[];
};
export type Question = Entity & {question:string;target_ids:string[];alternatives:string[]|null;decision_impact:string};
type Impact = {component_id:string;reason:string};
type Probe = Entity & {volatility_id:string;change:string;predicted_edit_ids:string[];consumers?:Impact[];leaks:Impact[]};
export type Component = Entity & {name:string; role:string; owns:string[]};
export type Contract = Entity & {owner_id:string; operations:{id:string; name:string}[]};
export type Dependency = Entity & {caller_id:string; callee_id:string; operation_id:string; reason:string};
export type Snapshot = {
  purpose?:string; actors:Entity[]; use_cases:Entity[]; implementation_findings:Entity[];
  volatilities:Decision[]; components:Component[]; contracts:Contract[]; dependencies:Dependency[];
  walkthroughs:Entity[]; change_probes:Probe[]; questions:Question[]; findings:Entity[];
  manifest:Record<string,unknown>[];
};
export type Revision = {
  id:string; parent_revision_id:string|null; snapshot:Snapshot;
  diff:Record<'added'|'changed'|'removed',{collection:string;id:string;reason:string}[]>;
};
export type Run = {id:string;status:string;stage:string;error:string|null};
export type Chunk = {id:string;locator:Record<string,unknown>|string;text:string};
export type EffortCase = 'likely'|'optimistic'|'pessimistic';
export type Activity = {
  id:string;deliverable:string;related_ids:string[];predecessors:string[];skills:string[]|null;
  effort:Partial<Record<EffortCase,number|null>>;estimate_source?:string|null;estimate_confirmed?:boolean;sources?:Evidence[];
};
export type Commitment = {start:CalendarDate|null;end:CalendarDate|null;fraction:number|null};
export type Person = {
  id:string;name?:string|null;skills:string[]|null;availability:number|null;daily_rate:number|null;
  available_from?:CalendarDate|null;available_until?:CalendarDate|null;commitments:Commitment[];
};
export type Roster = {id:string;name?:string|null;people?:Person[]|null};
export type Inputs = {start_date?:CalendarDate;activities?:Activity[];rosters?:Roster[];scenarios?:EffortCase[];assumptions?:string[]};
type Warning = {message:string; code:string};
type Schedule = {
  roster_id:string;scenario:string;status:string;critical_path:string[];critical_path_days:number|null;
  finish_date:string|null;makespan_days:number|null;total_cost:number|null;warnings:Warning[];
  assignments:{activity_id:string;person_id:string;start_date:string;finish_date:string;effort_days:number;cost:number|null}[];
  blockers:{activity_id:string;skills:string[];reason:string}[];
};
export type Plan = {id:string;revision_id:string;input:Inputs;result:{
  activities:Activity[];assumptions?:string[];missing_inputs:{path:string;message:string}[];warnings:Warning[];runs:Schedule[];
}};
export type EngineState = {revision:Revision|null;run:Run|null;plan:Plan|null};
export const activeRun = (run:Run|null) => !!run && ['queued','running','pending','processing'].includes(run.status);
export function entityTitle(row:Record<string,unknown>):string {
  const value = row.name ?? row.title ?? row.decision ?? row.question ?? row.change ?? row.message ?? row.outcome ?? row.filename ?? row.path ?? row.id;
  return typeof value === 'string' ? value : '';
}
export function entityNames(snapshot:Snapshot){
  const names = new Map<string,string>();
  for(const collection of Object.values(snapshot)){
    if(Array.isArray(collection))for(const row of collection){
      if(typeof row.id==='string')names.set(row.id,entityTitle(row));
    }
  }
  for(const contract of snapshot.contracts)for(const op of contract.operations)names.set(op.id,op.name);
  return names;
}

// Ownership, contracts and the calls crossing them describe the boundary. Evidence
// and rationale can change even when the resulting architecture is confirmed.
export function decisionBoundary(snapshot: Snapshot, id: string) {
  const owner = snapshot.components.find((c) => c.owns.includes(id));
  const contracts = snapshot.contracts.filter((c) => c.owner_id === owner?.id);
  const calls = snapshot.dependencies.filter(
    (d) => owner && (d.callee_id === owner.id || d.caller_id === owner.id),
  );
  return {
    owner: owner?.id,
    role: owner?.role,
    responsibility: owner?.responsibility,
    contracts: contracts
      .map((c) => [c.id, c.hides, [...c.operations].sort((a, b) => a.id.localeCompare(b.id))])
      .sort(),
    calls: calls.map((d) => [d.caller_id, d.callee_id, d.operation_id]).sort(),
  };
}
