'use client';
import {useState} from 'react';
import {NumberInput} from '@astryxdesign/core/NumberInput';
import {DateInput} from '@astryxdesign/core/DateInput';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {Button,Heading,HStack,Text,TextArea,TextInput,VStack} from './ui';
import {Citations} from './engine-evidence';
import {useEngine} from './engine-session';
import type {Activity,EffortCase,Inputs,Person,Plan,Roster} from '../lib/design-engine';

const scenarios:EffortCase[]=['likely','optimistic','pessimistic'];
const list=(value:string)=>value.split(',').map(v=>v.trim()).filter(Boolean);
const id=(prefix:string)=>prefix+'-'+crypto.randomUUID().slice(0,8);

function ListInput({label,value,onChange,description}:{label:string;value:string[]|null;onChange:(list:string[])=>void;description?:string}){
  const [text,setText]=useState((value??[]).join(', '));
  return <TextInput label={label} value={text} description={description||'Separate entries with commas.'} onChange={v=>{setText(v);onChange(list(v))}}/>;
}
function NumberField({label,value,onChange}:{label:string;value?:number|null;onChange:(n:number|null)=>void}){
  return <NumberInput label={label} value={value} hasClear isWheelEnabled={false} onChange={onChange}/>;
}
function ActivityEditor({row,update,available,remove}:{row:Activity;update:(row:Activity)=>void;available:Activity[];remove:()=>void}){
  const patch=(change:Partial<Activity>)=>update({...row,...change});
  return <Collapsible defaultIsOpen={false} trigger={<Text weight="semibold">{row.deliverable||'New activity'}</Text>}>
    <VStack gap={3} paddingBlock={2}>
      <TextInput label="Deliverable" value={row.deliverable} onChange={deliverable=>patch({deliverable})}/>
      <Text type="supporting">Activity {row.id}</Text>
      {!!row.related_ids?.length&&<Text type="supporting">Related design items · {row.related_ids.join(', ')}</Text>}
      <VStack gap={2}><Text weight="semibold">Predecessors</Text>
        <HStack wrap="wrap" gap={1}>{available.filter(a=>a.id!==row.id).map(a=>{
          const checked=row.predecessors.includes(a.id);
          return <Button key={a.id} size="sm" variant={checked?'secondary':'ghost'} aria-pressed={checked}
            label={a.deliverable||a.id} onClick={()=>patch({predecessors:checked?row.predecessors.filter(p=>p!==a.id):[...row.predecessors,a.id]})}/>;
        })}</HStack>
      </VStack>
      <ListInput label="Required skills" value={row.skills} onChange={skills=>patch({skills})}/>
      {row.skills==null&&<Button size="sm" label="Mark as general work" onClick={()=>patch({skills:[]})}/>}
      {scenarios.map(s=><NumberField key={s} label={s+' effort (person-days)'} value={row.effort?.[s]} onChange={n=>patch({effort:{...row.effort,[s]:n}})}/>)}
      <TextInput label="Estimate source" value={row.estimate_source??''} onChange={estimate_source=>patch({estimate_source})}/>
      <Button size="sm" label={row.estimate_confirmed?'Estimate confirmed':'Confirm estimate'} aria-pressed={!!row.estimate_confirmed} onClick={()=>patch({estimate_confirmed:!row.estimate_confirmed})}/>
      <Citations items={row.sources}/><Button size="sm" variant="ghost" label="Remove activity" onClick={remove}/>
    </VStack>
  </Collapsible>;
}
function PersonEditor({person,update,remove}:{person:Person;update:(p:Person)=>void;remove:()=>void}){
  const patch=(change:Partial<Person>)=>update({...person,...change});
  const commitments=person.commitments??[];
  return <Collapsible defaultIsOpen trigger={<Text weight="semibold">{person.name||'New team member'}</Text>}>
    <VStack gap={3} paddingBlock={2}>
      <TextInput label="Person name" value={person.name} onChange={name=>patch({name})}/>
      <ListInput label="Person skills" value={person.skills} onChange={skills=>patch({skills})}/>
      <NumberField label="Availability (0 to 1 full-time)" value={person.availability} onChange={availability=>patch({availability})}/>
      <DateInput label="Available from" presentation="native" value={person.available_from??undefined} onChange={v=>patch({available_from:v||null})}/>
      <DateInput label="Available until" presentation="native" value={person.available_until??undefined} onChange={v=>patch({available_until:v||null})}/>
      <NumberField label="Rate per full day" value={person.daily_rate} onChange={daily_rate=>patch({daily_rate})}/>
      {commitments.map((c,index)=>{
        const set=(change:Partial<typeof c>)=>patch({commitments:commitments.map((v,i)=>i===index?{...v,...change}:v)});
        return <VStack key={index} gap={2}>
          <DateInput presentation="native" label="Commitment starts" value={c.start||undefined} onChange={v=>set({start:v??''})}/>
          <DateInput presentation="native" label="Commitment ends" value={c.end||undefined} onChange={v=>set({end:v??''})}/>
          <NumberField label="Committed fraction" value={c.fraction} onChange={fraction=>set({fraction})}/>
          <Button label="Remove commitment" size="sm" onClick={()=>patch({commitments:commitments.filter((_,i)=>i!==index)})}/>
        </VStack>;
      })}
      <HStack wrap="wrap" gap={2}><Button label="Add commitment" onClick={()=>patch({commitments:[...commitments,{start:'',end:'',fraction:null}]})}/>
        <Button label="Remove person" variant="ghost" onClick={remove}/></HStack>
    </VStack>
  </Collapsible>;
}
function RosterEditor({roster,update,remove}:{roster:Roster;update:(r:Roster)=>void;remove:()=>void}){
  const patch=(change:Partial<Roster>)=>update({...roster,...change});
  return <VStack gap={3}><TextInput label="Roster name" value={roster.name} onChange={name=>patch({name})}/>
    {roster.people.map(p=><PersonEditor key={p.id} person={p}
      update={next=>patch({people:roster.people.map(v=>v.id===p.id?next:v)})} remove={()=>patch({people:roster.people.filter(v=>v.id!==p.id)})}/>)}
    <HStack gap={2} wrap="wrap">
      <Button label="Add person" onClick={()=>patch({people:[...roster.people,{id:id('person'),name:'',skills:[],availability:null,daily_rate:null,commitments:[]}]})}/>
      <Button label="Remove roster" variant="ghost" onClick={remove}/>
    </HStack>
  </VStack>;
}
function ScheduleResults({plan}:{plan:Plan}){
  const {result}=plan;
  const activities=new Map(result.activities.map(a=>[a.id,a.deliverable]));
  const rosters=plan.input.rosters??[];
  return <VStack gap={4} aria-label="Schedule results">
    {!!result.missing_inputs.length&&<VStack gap={1}><Heading level={3}>Inputs needed</Heading>{result.missing_inputs.map((m,i)=><Text key={i}>{m.message}</Text>)}</VStack>}
    {!!result.assumptions?.length&&<Collapsible defaultIsOpen={false} trigger={<Text weight="semibold">Scheduling assumptions</Text>}>
      <VStack gap={2}>{result.assumptions.map((note,i)=><Text key={i}>{note}</Text>)}</VStack>
    </Collapsible>}
    {result.warnings.map((w,i)=><Text key={i}>{w.message}</Text>)}
    {result.runs.map(run=>{
      const roster=rosters.find(r=>r.id===run.roster_id);
      return <VStack key={run.roster_id+run.scenario} gap={2}>
        <Heading level={3}>{roster?.name||run.roster_id} · {run.scenario}</Heading>
        <Text>{run.status.replaceAll('_',' ')}</Text>
        {run.critical_path_days!=null&&<Text>Dependency critical path · {run.critical_path_days} workdays · {run.critical_path.map(k=>activities.get(k)||k).join(' → ')}</Text>}
        {run.finish_date&&<Text>Roster-constrained finish · {run.finish_date} ({run.makespan_days} workdays)</Text>}
        <Text>Total cost · {run.total_cost??'Unknown'}</Text>
        {run.assignments.map(a=><VStack key={a.activity_id} gap={0}>
          <Text weight="semibold">{activities.get(a.activity_id)||a.activity_id}</Text>
          <Text>{roster?.people.find(p=>p.id===a.person_id)?.name||a.person_id} · {a.start_date} to {a.finish_date} · {a.effort_days} person-days · Cost {a.cost??'unknown'}</Text>
        </VStack>)}
        {run.blockers.map((b,i)=><Text key={i}>{activities.get(b.activity_id)||b.activity_id} · {b.reason} {b.skills?.join(', ')}</Text>)}
        {run.warnings.map((w,i)=><Text key={i}>{w.message}</Text>)}
      </VStack>;
    })}
  </VStack>;
}
export function ProjectPlan({revisionId,plan}:{revisionId:string;plan:Plan|null}){
  const engine=useEngine();
  const [inputs,setInputs]=useState<Inputs>(()=>({...plan?.input,activities:plan?.input.activities??plan?.result.activities??[],rosters:plan?.input.rosters??[],scenarios:plan?.input.scenarios??['likely']}));
  const patch=(change:Partial<Inputs>)=>setInputs(prev=>({...prev,...change}));
  const activities=inputs.activities??[],rosters=inputs.rosters??[],selected=inputs.scenarios??[];
  const [assumptions,setAssumptions]=useState((inputs.assumptions??[]).join('\n'));
  if(!plan)return <VStack gap={3}><Text>Generate activities from the proposed design to estimate the project.</Text>
    <Button label="Generate activities" isLoading={engine.busy} onClick={()=>engine.plan(revisionId,{})}/></VStack>;
  return <VStack gap={5}>
    <ScheduleResults plan={plan}/>
    <Heading level={3}>Planning inputs</Heading>
    <DateInput label="Project start date" presentation="native" value={inputs.start_date||undefined} onChange={start_date=>patch({start_date})}/>
    <VStack gap={2}><Text weight="semibold">Effort scenarios</Text><HStack gap={2} wrap="wrap">{scenarios.map(s=><Button key={s} size="sm" label={s} aria-pressed={selected.includes(s)} variant={selected.includes(s)?'secondary':'ghost'} onClick={()=>patch({scenarios:selected.includes(s)?selected.filter(v=>v!==s):[...selected,s]})}/>)}</HStack></VStack>
    <Heading level={3}>Activities</Heading>
    {activities.map(a=><ActivityEditor key={a.id} row={a} available={activities} update={next=>patch({activities:activities.map(v=>v.id===a.id?next:v)})}
      remove={()=>patch({activities:activities.filter(v=>v.id!==a.id).map(v=>({...v,predecessors:v.predecessors.filter(p=>p!==a.id)}))})}/>)}
    <Button label="Add activity" onClick={()=>patch({activities:[...activities,{id:id('activity'),deliverable:'',related_ids:[],predecessors:[],skills:null,effort:{}}]})}/>
    <Heading level={3}>Staffing options</Heading>
    {rosters.map(r=><RosterEditor key={r.id} roster={r} update={next=>patch({rosters:rosters.map(v=>v.id===r.id?next:v)})} remove={()=>patch({rosters:rosters.filter(v=>v.id!==r.id)})}/>)}
    <Button label={rosters.length?'Add alternative roster':'Add roster'} onClick={()=>patch({rosters:[...rosters,{id:id('roster'),name:'',people:[]}]})}/>
    <TextArea label="Planning assumptions" description="Enter one assumption per line." value={assumptions} onChange={v=>{setAssumptions(v);patch({assumptions:v.split('\n').map(x=>x.trim()).filter(Boolean)})}}/>
    <Button label="Calculate schedule" variant="primary" isDisabled={!selected.length} isLoading={engine.busy} onClick={()=>engine.plan(revisionId,inputs)}/>
  </VStack>;
}
