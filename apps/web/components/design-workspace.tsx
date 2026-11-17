'use client';
import {useEffect,useRef,useState} from 'react';
import {VStack,HStack,Heading,Text,Button,TextInput,TextArea} from './ui';
import {AppIcon,ReviewState,evidenceLabel,fieldLabel,plainValue} from './workspace-ui';
import {GitBranch,RefreshCw,Plus,Check,X,Pencil,ArrowLeft,ArrowRight} from 'lucide-react';
import {request,post,ApiError} from '../lib/api';
import type {Knowledge,DesignSnapshot,DesignStage,UseCaseInput} from '../lib/types';

const stages = [
 {key:'use_cases',label:'Detailed use cases',title:'Gather detailed use cases',help:'Keep actors, steps, outcomes and every variation. Source code is optional.'},
 {key:'core_use_cases',label:'Core cases',title:'Review the business essence',help:'Map core cases to the original cases. Similar wording alone is not enough; keep unresolved cases visible.',generate:'core',action:'Propose core cases'},
 {key:'volatilities',label:'Independent volatilities',title:'Identify independent reasons for change',help:'Explain what could change over time or across customers, why it is plausible, and what stays stable. A variation alone is not an architectural volatility.',generate:'volatility',action:'Propose volatilities'},
 {key:'components',label:'Components & contracts',title:'Hide change behind stable contracts',help:'Separate workflow coordination from business activity. Classify client, manager, engine, resource access, resource and utility responsibilities; deployment is a separate decision.',generate:'decomposition',action:'Propose components'},
 {key:'validations',label:'Coverage & containment',title:'Check coverage and change containment',help:'Review use-case collaborations and change scenarios. Reference checks are deterministic; AI reasoning is a proposal, not verified execution or measured test coverage.',generate:'validation',action:'Propose validation'},
] as const;
type StageKey = typeof stages[number]['key'];
const lines=(value:string)=>value.split('\n').map(v=>v.trim()).filter(Boolean);
const allArtifacts=(data:DesignSnapshot)=>stages.flatMap(stage=>data[stage.key]);
const stageOf=(record:Knowledge):StageKey|undefined=>({use_case:'use_cases',core_use_case:'core_use_cases',volatility:'volatilities',boundary:'components',design_validation:'validations'} as Record<string,StageKey>)[record.kind];
const emptyInput=():UseCaseInput=>({title:'',description:'',actor:'',trigger:'',preconditions:[],steps:[],outcome:'',variations:[],evidence_ids:[]});
function prerequisite(data:DesignSnapshot,stage:number){
 if(stage===1&&!data.use_cases.some(r=>r.status!=='rejected'))return 'Gather at least one use case before proposing core cases.';
 if(stage===2&&!data.readiness.core_use_cases)return 'Review and approve core cases before proposing volatilities.';
 if(stage===3&&(!data.readiness.core_use_cases||!data.readiness.volatility))return 'Review and approve core cases and volatilities before proposing components.';
 if(stage===4&&!data.readiness.decomposition)return 'Review and approve components before proposing validation.';
 return '';
}
export function validationIsStale(record:Knowledge,data:DesignSnapshot){
 if(record.payload.stale===true||record.payload.is_stale===true)return true;
 if(data.findings.some(f=>/stale/i.test(f.code)&&(!f.record_ids.length||f.record_ids.includes(record.id))))return true;
 const versions=record.payload.input_versions;
 if(!versions||typeof versions!=='object'||Array.isArray(versions))return true;
 const entries=Object.entries(versions);if(!entries.length)return true;
 const inputs=allArtifacts(data).filter(r=>r.kind!=='design_validation');
 return entries.some(([id,version])=>{const current=inputs.find(r=>r.id===id);return !current||current.status==='rejected'||current.version!==version});
}

export function DesignWorkspace({base,aiAvailable,records=[],onChange,onSettings}:{base:string;aiAvailable:boolean|null;records?:Knowledge[];onChange?:()=>Promise<void>;onSettings?:()=>void}){
 const [data,setData]=useState<DesignSnapshot|null>(null),[stage,setStage]=useState(0),[selected,setSelected]=useState(''),[intakeOpen,setIntakeOpen]=useState(false);
 const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const epoch=useRef(0),detail=useRef<HTMLElement|null>(null);
 async function load(){const value=await request<DesignSnapshot>(`${base}/design`);setData(value)}
 useEffect(()=>{const current=++epoch.current;setData(null);setSelected('');setStage(0);setError('');setNotice('');setLoading(true);request<DesignSnapshot>(`${base}/design`).then(value=>{if(epoch.current===current)setData(value)}).catch(e=>{if(epoch.current===current)setError(e.message)}).finally(()=>{if(epoch.current===current)setLoading(false)});return()=>{epoch.current++}},[base]);
 async function reload(){setLoading(true);setError('');try{await load()}catch(e){setData(null);setError((e as Error).message)}finally{setLoading(false)}}
 async function mutate(action:()=>Promise<unknown>,success:string){
 setBusy(true);setError('');setNotice('');try{
 await action();setNotice(success);
 try{await load()}catch(e){setData(null);setError(`Your change was saved, but the current design could not be loaded. ${(e as Error).message} Reload the design process before continuing.`);return true}
 if(onChange){try{await onChange()}catch(e){setError(`Your change was saved. Project context could not be refreshed: ${(e as Error).message}`)}}
 return true;
 }catch(e){
 if(e instanceof ApiError&&e.status===409){setError('This artifact changed since you opened it. The latest version has been loaded. Review it before saving again.');await load().catch(()=>setData(null))}
 else setError((e as Error).message);return false;
 }finally{setBusy(false)}}
 const definition=stages[stage],artifacts=data?allArtifacts(data):[],lookup=new Map([...records,...artifacts].map(r=>[r.id,r]));
 const active=lookup.get(selected),blocked=data?prerequisite(data,stage):'';
 function open(record:Knowledge){const key=stageOf(record);if(key)setStage(stages.findIndex(s=>s.key===key));setSelected(record.id);setTimeout(()=>detail.current?.focus(),0)}
 async function patch(record:Knowledge,change:Record<string,unknown>){return mutate(()=>request(`${base}/records/${record.id}`,{method:'PATCH',body:JSON.stringify({...change,expected_version:record.version})}),'Review saved. Readiness and findings have been refreshed.')}
 return <VStack gap={6} maxWidth="75ch">
 <HStack gap={3} hAlign="between" vAlign="center" wrap="wrap"><Heading level={1}>Design process</Heading><Button label="Reload design process" icon={<AppIcon icon={RefreshCw}/>} isLoading={loading} isDisabled={busy} onClick={reload}/></HStack>
 <Text color="secondary">From gathered use cases to reviewed responsibilities. Follow the reasoning, keep variations, and check what a change could affect.</Text>
 {error&&<VStack gap={2} role="alert"><Heading level={2}>Design process needs attention</Heading><Text>{error}</Text></VStack>}
 {notice&&<Text role="status">{notice}</Text>}
 {loading&&<Text role="status">Loading design artifacts…</Text>}
 {!loading&&data&&<>
 <HStack as="nav" aria-label="Design stages" gap={2} wrap="wrap">{stages.map((item,index)=><Button key={item.key} label={item.label} size="sm" variant={index===stage?'secondary':'ghost'} aria-current={index===stage?'step':undefined} isDisabled={busy} onClick={()=>{setStage(index);setSelected('')}}/>)}</HStack>
 <VStack gap={3}><Heading level={2}>{definition.title}</Heading><Text>{definition.help}</Text><Text type="supporting" color="secondary">Readiness indicates reviewed usable inputs. Approval does not establish design correctness.</Text></VStack>
 {aiAvailable!==true&&<VStack gap={3}><Text>{aiAvailable===null?'Checking AI configuration. Manual intake and review remain available.':'AI proposals need setup. Ask the person running Galvanise to configure an OpenAI API key on the API server. Manual intake and review remain available.'}</Text>{onSettings&&<Button label="Open connection settings" onClick={onSettings}/>}</VStack>}
 {stage===0?<VStack gap={4}>{data.use_cases.length>0&&<Button label={intakeOpen?'Close use case intake':'Add detailed use case'} icon={<AppIcon icon={Plus}/>} isDisabled={busy} onClick={()=>setIntakeOpen(!intakeOpen)}/>} {(intakeOpen||!data.use_cases.length)&&<UseCaseForm busy={busy} evidence={records.filter(r=>r.kind==='evidence'&&r.status!=='rejected')} save={input=>mutate(()=>post(`${base}/design/use-cases`,input),'Use case saved for human review. Approve it when it reflects the gathered case.')}/>}</VStack>:<VStack gap={3}>
 {blocked&&<Text>{blocked}</Text>}
 {'generate' in definition&&<Button label={definition.action} icon={<AppIcon icon={GitBranch} color="inherit"/>} variant="primary" isLoading={busy} isDisabled={aiAvailable!==true||!!blocked} onClick={()=>mutate(()=>post(`${base}/design/generate`,{stage:definition.generate as DesignStage}),'Proposals saved for review. Previously approved artifacts are preserved.')}/>}
 <Text type="supporting" color="secondary">Generation is explicit. New proposals need human review; approved records are preserved.</Text>
 </VStack>}
 <VStack as="section" aria-label={`${definition.label} artifacts`} gap={4}>
 <Heading level={2}>Review {definition.label.toLowerCase()}</Heading>
 {data[definition.key].length?data[definition.key].map(record=><HStack key={record.id} as="article" gap={3} wrap="wrap" hAlign="between" vAlign="center" paddingBlock={3}><VStack gap={1}><Heading level={3}>{record.title}</Heading><ReviewState status={record.status}/>{record.kind==='boundary'&&<Text type="supporting">{fieldLabel(String(record.payload.component_role||'Role needs review'))}</Text>}{record.kind==='design_validation'&&<Text type="supporting">{validationIsStale(record,data)?'Historical validation · needs a fresh proposal':'Input versions match · review reasoning'}</Text>}</VStack><Button label={`Review ${record.title}`} icon={<AppIcon icon={ArrowRight}/>} size="sm" isDisabled={busy} onClick={()=>open(record)}/></HStack>):<Text color="secondary">No {definition.label.toLowerCase()} yet. {stage===0?'Save your first gathered case above.':'Meet the prerequisites, then request proposals.'}</Text>}
 </VStack>
 {active&&<VStack as="section" ref={detail} tabIndex={-1} aria-label="Artifact review" gap={5}>
 <ArtifactReview key={`${active.id}:${active.version}`} record={active} data={data} lookup={lookup} open={open} busy={busy} patch={patch}/>
 </VStack>}
 <VStack as="section" aria-label="Design findings" gap={3}><Heading level={2}>Coverage & reference findings</Heading><Text color="secondary">These checks inspect recorded links, coverage and dependencies. They do not execute software or measure test coverage.</Text>
 {data.findings.length?data.findings.map((finding,index)=><VStack key={`${finding.code}:${index}`} gap={2} paddingBlock={3}><Text weight="semibold">{fieldLabel(finding.severity)} · {fieldLabel(finding.code)}</Text><Text>{finding.message}</Text><HStack gap={2} wrap="wrap">{finding.record_ids.map(id=><Reference key={id} id={id} lookup={lookup} open={open}/>)}</HStack></VStack>):<Text>No reference findings reported. This does not establish a complete or correct design.</Text>}
 <Text>{data.readiness.validation?'Reviewed validation inputs are available. Check assumptions and findings before relying on this design.':'Validation is incomplete, awaiting review, or out of date. Resolve findings and review current proposals.'}</Text>
 </VStack>
 {Object.entries(data).filter(([key])=>!['use_cases','core_use_cases','volatilities','components','validations','findings','readiness'].includes(key)).map(([key,value])=><VStack key={key} gap={2}><Text weight="semibold">{fieldLabel(key)}</Text><ReadableDesignValue value={value} lookup={lookup} open={open}/></VStack>)}
 <HStack gap={3} wrap="wrap">{stage>0&&<Button label={`Back to ${stages[stage-1].label.toLowerCase()}`} icon={<AppIcon icon={ArrowLeft}/>} isDisabled={busy} onClick={()=>{setStage(stage-1);setSelected('')}}/>}{stage<stages.length-1&&<Button label={`Continue to ${stages[stage+1].label.toLowerCase()}`} icon={<AppIcon icon={ArrowRight}/>} isDisabled={busy} onClick={()=>{setStage(stage+1);setSelected('')}}/>}</HStack>
 </>}
 </VStack>
}

function UseCaseForm({busy,evidence,save}:{busy:boolean;evidence:Knowledge[];save:(input:UseCaseInput)=>Promise<boolean>}){
 const [input,setInput]=useState(emptyInput),[preconditions,setPreconditions]=useState(''),[steps,setSteps]=useState(''),[variations,setVariations]=useState('');
 const set=(key:keyof UseCaseInput,value:string)=>setInput(old=>({...old,[key]:value}));
 return <VStack as="form" gap={4} aria-label="Gather a use case" onSubmit={async(e:React.FormEvent)=>{e.preventDefault();if(!input.title.trim()||!lines(steps).length||!input.outcome.trim()||busy)return;const saved=await save({...input,title:input.title.trim(),outcome:input.outcome.trim(),preconditions:lines(preconditions),steps:lines(steps),variations:lines(variations)});if(saved){setInput(emptyInput());setPreconditions('');setSteps('');setVariations('')}}}>
 <TextInput label="Use case title" value={input.title} onChange={v=>set('title',v)} isRequired isDisabled={busy}/>
 <TextArea label="Description" value={input.description} onChange={v=>set('description',v)} isDisabled={busy}/>
 <HStack gap={4} wrap="wrap"><TextInput label="Actor" value={input.actor} onChange={v=>set('actor',v)} isDisabled={busy}/><TextInput label="Trigger" value={input.trigger} onChange={v=>set('trigger',v)} isDisabled={busy}/></HStack>
 <TextArea label="Preconditions" description="One precondition per line." value={preconditions} onChange={setPreconditions} isDisabled={busy}/>
 <TextArea label="Steps" description="One step per line, in order." value={steps} onChange={setSteps} isRequired isDisabled={busy}/>
 <TextArea label="Outcome" value={input.outcome} onChange={v=>set('outcome',v)} isRequired isDisabled={busy}/>
 <TextArea label="Variations" description="One variation per line. Keep exceptions and alternate paths." value={variations} onChange={setVariations} isDisabled={busy}/>
 <Text weight="semibold">Supporting evidence</Text>{evidence.length?<HStack gap={2} wrap="wrap">{evidence.map(record=><Button key={record.id} label={record.title} aria-pressed={input.evidence_ids.includes(record.id)} variant={input.evidence_ids.includes(record.id)?'secondary':'ghost'} isDisabled={busy} onClick={()=>setInput(old=>({...old,evidence_ids:old.evidence_ids.includes(record.id)?old.evidence_ids.filter(id=>id!==record.id):[...old.evidence_ids,record.id]}))}/>)}</HStack>:<Text type="supporting" color="secondary">No project evidence records yet. You can record the case now and add sources in Files & code.</Text>}
 <Text type="supporting" color="secondary">Human-authored cases are saved as needs review. Saving does not approve the case.</Text>
 <Button label="Save use case" type="submit" variant="primary" icon={<AppIcon icon={Plus} color="inherit"/>} isLoading={busy} isDisabled={!input.title.trim()||!lines(steps).length||!input.outcome.trim()}/>
 </VStack>
}

function Reference({id,lookup,open}:{id:string;lookup:Map<string,Knowledge>;open:(record:Knowledge)=>void}){
 const record=lookup.get(id);
 return record?<Button label={`${record.title} · ${plainValue(record.status)}`} aria-label={`${record.title} · ${record.status}`} variant="ghost" size="sm" onClick={()=>open(record)}/>:<Text type="supporting">Unresolved reference: {id}</Text>;
}
function ReadableDesignValue({value,lookup,open,field=''}:{value:unknown;lookup:Map<string,Knowledge>;open:(record:Knowledge)=>void;field?:string}){
 if(value===null||value===undefined)return <Text color="secondary">Not specified</Text>;
 if(typeof value==='string')return field.endsWith('_id')||field.endsWith('_ids')||field==='dependencies'?<Reference id={value} lookup={lookup} open={open}/>:<Text>{({over_time:'Over time',across_customers:'Across customers',client:'Client',manager:'Manager',engine:'Engine',resource_access:'Resource access',resource:'Resource',utility:'Utility'} as Record<string,string>)[value]||plainValue(value)}</Text>;
 if(typeof value==='boolean'||typeof value==='number')return <Text>{typeof value==='boolean'?(value?'Yes':'No'):String(value)}</Text>;
 if(Array.isArray(value))return <VStack gap={2}>{value.length?value.map((item,index)=><VStack key={index} gap={2}>{field==='steps'&&<Text type="supporting">Step {index+1}</Text>}<ReadableDesignValue value={item} field={field} lookup={lookup} open={open}/></VStack>):<Text color="secondary">None recorded</Text>}</VStack>;
 return <VStack gap={4}>{Object.entries(value as Record<string,unknown>).filter(([key])=>key!=='design_engine').map(([key,item])=><VStack key={key} gap={2}><Text weight="semibold">{field==='input_versions'?(lookup.get(key)?.title||`Unavailable input ${key}`):designLabel(key)}</Text><ReadableDesignValue value={item} field={key} lookup={lookup} open={open}/></VStack>)}</VStack>;
}
function designLabel(key:string){return ({use_case_ids:'Original detailed cases',core_use_case_ids:'Supporting core cases',core_use_case_id:'Core case',volatility_ids:'Hidden volatilities',volatility_id:'Reason for change',component_ids:'Collaborating components',changed_component_ids:'Components expected to change',unchanged_component_ids:'Components expected to stay stable',stable_contract:'Stable contract',component_role:'Component role',input_versions:'Input versions when proposed',design_engine:'From design process',axis:'Over time or across customers',hidden_change:'Change hidden by this component',dependencies:'Component dependencies'} as Record<string,string>)[key]||fieldLabel(key)}
function ArtifactReview({record,data,lookup,open,busy,patch}:{record:Knowledge;data:DesignSnapshot;lookup:Map<string,Knowledge>;open:(record:Knowledge)=>void;busy:boolean;patch:(record:Knowledge,change:Record<string,unknown>)=>Promise<boolean>}){
 const [editing,setEditing]=useState(false),[history,setHistory]=useState(false),[title,setTitle]=useState(record.title),[description,setDescription]=useState(record.description),[payload,setPayload]=useState(record.payload);
 const stale=record.kind==='design_validation'&&validationIsStale(record,data);
 const usedBy=allArtifacts(data).filter(candidate=>candidate.id!==record.id&&references(candidate.payload,record.id));
 return <>
 <Heading level={2}>{record.title}</Heading><ReviewState status={record.status}/><Text type="supporting">{evidenceLabel(record.evidence_status)} · Version {record.version}</Text><Text>{record.description}</Text>
 {stale&&<Text role="status">Historical validation: inputs have changed or cannot be confirmed. Generate and review a fresh validation before relying on these findings.</Text>}
 <Heading level={3}>Reasoning & linked artifacts</Heading><ReadableDesignValue value={record.payload} lookup={lookup} open={open}/>{usedBy.length>0&&<VStack gap={2}><Heading level={3}>Used by</Heading><HStack gap={2} wrap="wrap">{usedBy.map(item=><Reference key={item.id} id={item.id} lookup={lookup} open={open}/>)}</HStack></VStack>}
 <HStack gap={2} wrap="wrap"><Button label="Approve artifact" icon={<AppIcon icon={Check} color="success"/>} isDisabled={busy||record.status==='approved'||!!stale} onClick={()=>patch(record,{status:'approved'})}/><Button label="Leave artifact out" icon={<AppIcon icon={X} color="error"/>} variant="ghost" isDisabled={busy||record.status==='rejected'} onClick={()=>patch(record,{status:'rejected'})}/><Button label="Edit artifact" icon={<AppIcon icon={Pencil}/>} variant="ghost" isDisabled={busy} onClick={()=>setEditing(!editing)}/><Button label={history?'Hide version history':'Show version history'} variant="ghost" onClick={()=>setHistory(!history)}/></HStack>
 {editing&&<VStack as="form" gap={4} onSubmit={async(e:React.FormEvent)=>{e.preventDefault();if(await patch(record,{title,description,payload,status:'pending'}))setEditing(false)}}><Text>Edits return this artifact to human review and may invalidate downstream validation.</Text><TextInput label="Artifact title" value={title} onChange={setTitle} isRequired isDisabled={busy}/><TextArea label="Artifact description" value={description} onChange={setDescription} isDisabled={busy}/>{Object.entries(payload).filter(([key,value])=>!['design_engine','input_versions','stale','is_stale'].includes(key)&&(typeof value==='string'||Array.isArray(value)&&value.every(v=>typeof v==='string'))).map(([key,value])=>key.endsWith("_ids")||key==="dependencies"?<ReferenceChoices key={key} field={key} selected={Array.isArray(value)?value as string[]:[]} lookup={lookup} busy={busy} onChange={ids=>setPayload(old=>({...old,[key]:ids}))}/>:<TextArea key={key} label={designLabel(key)} description={Array.isArray(value)?"One item per line.":undefined} value={Array.isArray(value)?value.join("\n"):String(value)} isDisabled={busy} onChange={v=>setPayload(old=>({...old,[key]:Array.isArray(value)?lines(v):v}))}/>)}<HStack gap={3}><Button label="Save artifact changes" type="submit" variant="primary" isLoading={busy} isDisabled={!title.trim()}/><Button label="Cancel editing" isDisabled={busy} onClick={()=>{setEditing(false);setTitle(record.title);setDescription(record.description);setPayload(record.payload)}}/></HStack></VStack>}
 {history&&<VStack gap={3}><Heading level={3}>Previous versions</Heading><ReadableDesignValue value={record.history||[]} lookup={lookup} open={open}/></VStack>}
 </>
}

function references(value:unknown,id:string):boolean{
 if(Array.isArray(value))return value.some(item=>references(item,id));
 if(value&&typeof value==='object')return Object.entries(value).some(([key,item])=>key!=='input_versions'&&references(item,id));
 return value===id;
}
function ReferenceChoices({field,selected,lookup,busy,onChange}:{field:string;selected:string[];lookup:Map<string,Knowledge>;busy:boolean;onChange:(ids:string[])=>void}){
 const kind=({use_case_ids:'use_case',core_use_case_ids:'core_use_case',volatility_ids:'volatility',evidence_ids:'evidence',dependencies:'boundary'} as Record<string,string>)[field];
 const options=[...lookup.values()].filter(record=>record.kind===kind&&record.status!=='rejected');
 return <VStack gap={2}><Text weight="semibold">{designLabel(field)}</Text><Text type="supporting">Select the existing project artifacts that support this reasoning.</Text><HStack gap={2} wrap="wrap">{options.map(record=><Button key={record.id} label={record.title} aria-pressed={selected.includes(record.id)} variant={selected.includes(record.id)?'secondary':'ghost'} isDisabled={busy} onClick={()=>onChange(selected.includes(record.id)?selected.filter(id=>id!==record.id):[...selected,record.id])}/>)}</HStack>{!options.length&&<Text>No eligible artifacts yet.</Text>}{selected.filter(id=>!options.some(record=>record.id===id)).map(id=><HStack key={id} gap={2} wrap="wrap"><Text>{lookup.get(id)?.title||`Unavailable reference: ${id}`}</Text><Button label={`Remove ${lookup.get(id)?.title||id}`} size="sm" isDisabled={busy} onClick={()=>onChange(selected.filter(value=>value!==id))}/></HStack>)}</VStack>
}
