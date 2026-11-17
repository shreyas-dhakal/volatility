'use client';
import {useCallback,useEffect,useMemo,useState} from 'react';
import {ReactFlow,Background,Controls,MiniMap,useNodesState,type NodeProps,type OnSelectionChangeParams} from '@xyflow/react';
import * as stylex from '@stylexjs/stylex';
import {VStack,HStack,Heading,Text,TextInput,Selector,Button,Markdown} from './ui';
import {request} from '../lib/api';
import {adaptGraph,localNodeDetail} from '../lib/graph-view';
import type {GraphData,GraphSummary,Knowledge} from '../lib/types';
const s=stylex.create({canvas:{height:'38rem',minHeight:'24rem',border:'1px solid var(--color-border)',borderRadius:'var(--radius-container)',overflow:'hidden'},detail:{borderTop:'1px solid var(--color-border)'},measure:{maxWidth:'70ch'}});
function BoundaryGroup({data}:NodeProps){return <VStack padding={4} gap={1}><Text weight="semibold">{String(data.label)}</Text><Text type="supporting">Proposed boundary · select to inspect</Text></VStack>}
const nodeTypes={boundaryGroup:BoundaryGroup};
function DetailFields({value}:{value:unknown}){
 if(value==null)return null;
 if(typeof value!=='object')return <Text>{String(value)}</Text>;
 if(Array.isArray(value))return <VStack gap={2}>{value.map((v,i)=><DetailFields key={i} value={v}/>)}</VStack>;
 return <VStack gap={4}>{Object.entries(value as Record<string,unknown>).filter(([,v])=>v!=null&&v!==''&&!(Array.isArray(v)&&!v.length)).map(([key,v])=><VStack gap={1} key={key}><Text weight="semibold">{key.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase())}</Text><DetailFields value={v}/></VStack>)}</VStack>
}
export function GraphWorkspace({base,graphs,records,onError}:{base:string;graphs:GraphSummary[];records:Knowledge[];onError:(s:string)=>void}){
 const [id,setId]=useState(''),[query,setQuery]=useState(''),[focus,setFocus]=useState(''),[driver,setDriver]=useState(''),[candidate,setCandidate]=useState(''),[data,setData]=useState<GraphData|null>(null),[detail,setDetail]=useState<unknown>(null),[technicalDetail,setTechnicalDetail]=useState(false),[loading,setLoading]=useState(false),[source,setSource]=useState(''),[target,setTarget]=useState(''),[paths,setPaths]=useState<unknown>(null);
 const selected=id||graphs[0]?.id||'';
 async function load(){if(!selected)return;setLoading(true);try{const params=new URLSearchParams({query,focus,limit:'80'});if(driver)params.set('driver_id',driver);if(candidate)params.set('candidate_id',candidate);setData(await request(`${base}/graphs/${selected}?${params}`))}catch(e){onError((e as Error).message)}finally{setLoading(false)}}
 useEffect(()=>{setDetail(null);setFocus('');load()},[selected,base,driver,candidate]);
 const adapted=useMemo(()=>data?adaptGraph(data):{nodes:[],edges:[],boundaries:[]},[data]);
 const [flowNodes,setFlowNodes,onNodesChange]=useNodesState(adapted.nodes);
 useEffect(()=>{setFlowNodes(adapted.nodes)},[adapted.nodes,setFlowNodes]);
 const inspect=useCallback(async(nodeId:string)=>{if(!data)return;const local=localNodeDetail(nodeId,data,records);if(local){setTechnicalDetail(false);setDetail(local);return}try{setDetail(await request(`${base}/graphs/${selected}/nodes/${encodeURIComponent(nodeId)}`));setTechnicalDetail(true);setFocus(nodeId)}catch(e){onError((e as Error).message)}},[data,records,base,selected,onError]);
 const onSelection=useCallback(({nodes}:OnSelectionChangeParams)=>{if(nodes[0])void inspect(nodes[0].id)},[inspect]);
 if(!graphs.length)return <VStack gap={4}><Heading level={1}>Explore technical evidence</Heading><Text color="secondary">Import a Graphify export in Sources to explore dependencies, or index a public repository to browse its files.</Text></VStack>;
 return <VStack gap={5}>
 <Heading level={1}>Architecture graph</Heading>
 <Text color="secondary" xstyle={s.measure}>Explore up to 80 nodes. Purple groups are proposed boundaries; orange nodes match the selected change driver; blue nodes represent business decisions. Dashed edges are unverified source claims or inferred relationships. Solid edges are explicitly verified or human confirmed.</Text>
 <Text type="supporting" color="secondary">Source confidence labels preserve upstream claims; they are not Galvanise verification. Tab to a node and press Enter to select its evidence.</Text>
 <HStack gap={3} wrap="wrap"><Selector label="Technical graph" value={selected} onChange={setId} options={graphs.map(g=>({value:g.id,label:g.name}))}/><Selector label="Change driver" value={driver} onChange={setDriver} options={[{value:'',label:'All drivers'},...records.filter(r=>r.kind==='driver').map(r=>({value:r.id,label:r.title}))]}/><Selector label="Design overlay" value={candidate} onChange={setCandidate} options={[{value:'',label:'Current system'},...records.filter(r=>r.kind==='architecture').map(r=>({value:r.id,label:r.title}))]}/></HStack>
 <HStack gap={3} vAlign="end" wrap="wrap"><TextInput label="Find nodes" value={query} onChange={setQuery} onEnter={load} placeholder="Name or file path"/><TextInput label="Focus node ID" value={focus} onChange={setFocus}/><Button label="Apply filters" isLoading={loading} onClick={load}/></HStack>
 <VStack xstyle={s.canvas}><ReactFlow nodes={flowNodes} onNodesChange={onNodesChange} onNodeClick={(_,node)=>{void inspect(node.id)}} edges={adapted.edges} nodeTypes={nodeTypes} fitView fitViewOptions={{padding:0.2}} minZoom={0.15} key={`${selected}:${candidate}:${driver}:${adapted.nodes.map(n=>n.id).join(',')}`} onSelectionChange={onSelection}><Background/><Controls/><MiniMap/></ReactFlow></VStack>
 {data&&<Text type="supporting" color="secondary">Showing {data.nodes.length} nodes and {data.edges.length} source relationships.</Text>}
 {adapted.boundaries.length>0&&<VStack gap={4}><Heading level={2}>Proposed boundary contracts</Heading>{adapted.boundaries.map(b=><VStack key={b.name} gap={2} paddingBlock={3} xstyle={s.detail}><Heading level={3}>{b.name}</Heading><Text>{b.responsibility||'Responsibility requires review.'}</Text><Text>Stable contract: {b.stable_contract||'Not established'}</Text><Text type="supporting" color="secondary">{b.node_ids?.length||0} mapped technical components · proposed, pending human validation</Text><Button label={`Inspect ${b.name}`} variant="ghost" onClick={()=>{setTechnicalDetail(false);setDetail(b)}}/></VStack>)}</VStack>}
 {detail!=null&&<VStack gap={4} paddingBlock={4} xstyle={s.detail} aria-live="polite"><Heading level={2}>Node evidence & dependencies</Heading><Button label="Focus technical neighbourhood" isDisabled={!focus||!technicalDetail} onClick={load}/><DetailFields value={detail}/></VStack>}
 <Heading level={2}>Trace an actual dependency path</Heading><HStack gap={3} wrap="wrap" vAlign="end"><TextInput label="Source node ID" value={source} onChange={setSource}/><TextInput label="Target node ID" value={target} onChange={setTarget}/><Button label="Find paths" isDisabled={!source||!target} onClick={async()=>{try{setPaths(await request(`${base}/graphs/${selected}/paths?${new URLSearchParams({source,target})}`))}catch(e){onError((e as Error).message)}}}/></HStack>{paths!=null&&<Markdown>{'```json\n'+JSON.stringify(paths,null,2)+'\n```'}</Markdown>}
 </VStack>
}
