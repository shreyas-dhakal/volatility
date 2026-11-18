import type {DateInputProps} from '@astryxdesign/core/DateInput';
type CalendarDate = NonNullable<DateInputProps['value']>;

export type Evidence = {chunk_id:string; excerpt:string};
export type Entity = {id:string; evidence?:Evidence[]; [field:string]:unknown};
export type Component = Entity & {name:string; role:string; owns:string[]};
export type Contract = Entity & {owner_id:string; operations:{id:string; name:string}[]};
export type Dependency = Entity & {caller_id:string; callee_id:string; operation_id:string; reason:string};
export type Snapshot = {
  purpose?:string; actors:Entity[]; use_cases:Entity[]; implementation_findings:Entity[];
  volatilities:Entity[]; components:Component[]; contracts:Contract[]; dependencies:Dependency[];
  walkthroughs:Entity[]; change_probes:Entity[]; questions:Entity[]; findings:Entity[];
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
