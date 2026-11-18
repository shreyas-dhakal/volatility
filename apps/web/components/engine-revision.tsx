'use client';
import {useState} from 'react';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {Divider} from '@astryxdesign/core/Divider';
import {entityNames,entityTitle,type Entity,type Snapshot,type Revision} from '../lib/design-engine';
import {request} from '../lib/api';
import {Button,Heading,HStack,Text,VStack} from './ui';
import {Citations,DetailValue,label} from './engine-evidence';
import {useEngine} from './engine-session';

export function DetailRows({title,rows,names}:{title:string;rows:Record<string,unknown>[];names:Map<string,string>}){
  return <VStack gap={2}><Heading level={3}>{title}</Heading>
    {rows.length?rows.map((row,i)=>{
      const titleText=String(row.display_title||entityTitle(row)||('Item '+(i+1)));
      return <VStack key={String(row.id??i)} gap={1}><Collapsible defaultIsOpen={false} trigger={<Text weight="semibold">{titleText}</Text>}>
        <VStack gap={3} paddingBlock={2}>
          {Object.entries(row).filter(([key,value])=>!['id','evidence','display_title'].includes(key)&&value!==titleText).map(([key,value])=><VStack gap={0} key={key}>
            <Text type="supporting" color="secondary">{label(key)}</Text><DetailValue value={value} names={names}/>
          </VStack>)}
          <Citations items={(row as Entity).evidence}/>
        </VStack>
      </Collapsible><Divider/></VStack>;
    }):<Text color="secondary">None recorded</Text>}
  </VStack>;
}

function DependencyDiagram({snapshot,names}:{snapshot:Snapshot;names:Map<string,string>}){
  const components=new Set(snapshot.components.map(c=>c.id));
  const owners=new Map(snapshot.contracts.flatMap(c=>c.operations.map(op=>[op.id,c.owner_id] as const)));
  const edges=snapshot.dependencies.filter(d=>components.has(d.caller_id)&&components.has(d.callee_id)&&owners.get(d.operation_id)===d.callee_id)
    .sort((a,b)=>a.caller_id.localeCompare(b.caller_id)||a.callee_id.localeCompare(b.callee_id)||a.id.localeCompare(b.id));
  return <VStack role="figure" aria-label="Component dependency diagram" gap={3}>
    <Heading level={3}>Component dependency diagram</Heading>
    {edges.length?edges.map(edge=><HStack key={edge.id} wrap="wrap" gap={2} vAlign="center">
      <Text weight="semibold">{names.get(edge.caller_id)}</Text>
      <Text color="secondary">→ {names.get(edge.operation_id)} →</Text>
      <Text weight="semibold">{names.get(edge.callee_id)}</Text>
    </HStack>):<Text color="secondary">No validated dependencies.</Text>}
  </VStack>;
}
export function RevisionPanel({revision,tab,objective}:{revision:Revision;tab:string;objective:string}){
  const s=revision.snapshot,names=entityNames(s);
  const rows=(title:string,items:Record<string,unknown>[]) => <DetailRows title={title} rows={items} names={names}/>;
  if(tab==='Overview')return <VStack gap={5}>
    <VStack gap={1}><Heading level={3}>System purpose</Heading><Text>{s.purpose||objective||s.use_cases.map(c=>c.outcome).filter(Boolean).join(' ')||'Purpose has not been established.'}</Text></VStack>
    {rows('Core use cases',s.use_cases)}{rows('Actors and external systems',s.actors)}
    {rows('Questions',s.questions.slice(0,3))}{rows('Source coverage',s.manifest)}
    {rows('Current implementation',s.implementation_findings)}
    <RevisionDiff key={revision.id} revision={revision} names={names}/>
  </VStack>;
  if(tab==='Volatility')return rows('Decisions and owners',s.volatilities.map(v=>({
    ...v,owner:s.components.find(c=>c.owns.includes(v.id))?.name||'Unassigned',
  })));
  if(tab==='Architecture')return <VStack gap={5}><Heading level={2}>Proposed design</Heading>
    <DependencyDiagram snapshot={s} names={names}/>{rows('Components',s.components)}{rows('Contracts',s.contracts)}
    {rows('Dependencies',s.dependencies.map(d=>({...d,display_title:(names.get(d.caller_id)||d.caller_id)+' → '+(names.get(d.callee_id)||d.callee_id)})))}
  </VStack>;
  return <VStack gap={5}><Heading level={2}>Design analysis</Heading>
    {rows('Use case walkthroughs',s.walkthroughs.map(w=>({...w,display_title:names.get(String(w.use_case_id))})))}
    {rows('Predicted change containment',s.change_probes)}{rows('Review findings',s.findings)}
  </VStack>;
}
function RevisionDiff({revision,names}:{revision:Revision;names:Map<string,string>}){
  const {path}=useEngine();
  const [parent,setParent]=useState<Revision|null>(null),[error,setError]=useState('');
  if(!revision.parent_revision_id)return null;
  const diffs=Object.entries(revision.diff??{}).flatMap(([kind,changes])=>changes.map(change=>({...change,kind})));
  const earlierNames=parent?entityNames(parent.snapshot):new Map<string,string>();
  return <VStack gap={3}><Heading level={3}>Revision changes</Heading>
    {diffs.length?diffs.map(change=><VStack key={change.kind+change.id} gap={1}>
      <Text weight="semibold">{label(change.kind)} · {names.get(change.id)||earlierNames.get(change.id)||change.id}</Text>
      <Text>{change.reason}</Text>
    </VStack>):<Text>No entity changes recorded.</Text>}
    {parent?<VStack gap={3}><Heading level={3}>Previous revision</Heading>
      <Text type="supporting">{parent.id}</Text><DetailRows title="Previous decisions" rows={parent.snapshot.volatilities} names={earlierNames}/>
      <Button label="Hide previous revision" onClick={()=>setParent(null)}/>
    </VStack>:<Button label="Inspect previous revision" onClick={async()=>{
      try{setError('');setParent(await request(path+'/revisions/'+encodeURIComponent(revision.parent_revision_id!)))}catch(e){setError((e as Error).message)}
    }}/>}
    {error&&<Text role="alert">{error}</Text>}
  </VStack>;
}
