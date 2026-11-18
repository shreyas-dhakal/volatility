'use client';
import {displayText} from '../lib/text';
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {ReactFlow,Background,Controls,MiniMap,useNodesState,type NodeProps,type OnSelectionChangeParams} from '@xyflow/react';
import * as stylex from '@stylexjs/stylex';
import {VStack,HStack,Heading,Text,TextInput,Selector,Button,FileInput,Markdown} from './ui';
import {request} from '../lib/api';
import {adaptGraph,localNodeDetail} from '../lib/graph-view';
import {AppIcon,fieldLabel,plainValue} from './workspace-ui';
import {Search,Network,ArrowRight} from 'lucide-react';
import type {GraphData,GraphSummary,Knowledge,Job,Source} from '../lib/types';
const s=stylex.create({canvas:{height:'38rem',minHeight:'24rem',border:'1px solid var(--color-border)',borderRadius:'var(--radius-container)',overflow:'hidden'},detail:{borderTop:'1px solid var(--color-border)'},measure:{maxWidth:'70ch'}});
function BoundaryGroup({data}:NodeProps){return <VStack padding={4} gap={1}><Text weight="semibold">{String(data.label)}</Text><Text type="supporting">Proposed part · select for details</Text></VStack>}
const nodeTypes={boundaryGroup:BoundaryGroup};
function DetailFields({value}:{value:unknown}){
 if(value==null)return null;
 if(typeof value!=='object')return <Text>{typeof value==='string'?plainValue(value):typeof value==='boolean'?(value?'Yes':'No'):String(value)}</Text>;
 if(Array.isArray(value))return <VStack gap={2}>{value.map((v,i)=><DetailFields key={i} value={v}/>)}</VStack>;
 return <VStack gap={4}>{Object.entries(value as Record<string,unknown>).filter(([,v])=>v!=null&&v!==''&&!(Array.isArray(v)&&!v.length)).map(([key,v])=><VStack gap={1} key={key}><Text weight="semibold">{fieldLabel(key)}</Text><DetailFields value={v}/></VStack>)}</VStack>
}
type GraphWorkspaceProps = {
 base:string; graphs:GraphSummary[]; records:Knowledge[]; onError:(s:string)=>void;
 repositories?:Source[]; jobs?:Job[]; busy?:boolean; build?:(id:string)=>Promise<void>; openSources?:()=>void; uploadZip?:(file:File)=>Promise<string>;
};

export function GraphWorkspace({base,graphs:allGraphs,records,onError,repositories=[],jobs=[],busy,build,openSources,uploadZip}:GraphWorkspaceProps){
 const [archive,setArchive]=useState<File|null>(null);
 const [uploading,setUploading]=useState(false);
 const [pendingUpload,setPendingUpload]=useState('');
 async function uploadArchive(){
   if(!archive||!uploadZip||uploading)return;
   setUploading(true);
   try{setPendingUpload(await uploadZip(archive));setArchive(null)}
   catch(e){onError((e as Error).message)}
   finally{setUploading(false)}
 }
 const archiveInput=!repositories.length && uploadZip && <VStack gap={2}>
   <FileInput label="Repository ZIP" description="Upload your local source files, including uncommitted changes." accept=".zip" value={archive} onChange={value=>setArchive(Array.isArray(value)?value[0]??null:value)}/>
   <Button label="Upload ZIP and build code map" isDisabled={!archive||busy||uploading} isLoading={uploading} onClick={uploadArchive}/>
   {jobs.filter(j=>j.archive && j.status!=='completed').map(j=><Text key={j.id} role="status">{j.archive} · {j.status==='failed'?j.error:j.kind==='graphify'?'Building code map…':'Reading ZIP…'}</Text>)}
 </VStack>;
 const graphs=allGraphs.filter(g=>!(g.metadata?.provenance==='GitHub tree API' && g.metadata.dependencies_inferred===false));
 const unbuilt=repositories.filter(repo=>!graphs.some(g=>g.source_id===repo.id && g.metadata?.generator==='graphify'));
 // Repositories indexed before automatic builds can already have a saved file index.
 const requested=useRef(new Set<string>());
 useEffect(()=>{
   if(!build || busy)return;
   const legacy=unbuilt.find(repo=>repo.status==='ready' && !requested.current.has(repo.id)
     && !jobs.some(job=>job.kind==='graphify' && job.source_id===repo.id));
   if(legacy){requested.current.add(legacy.id);void build(legacy.id)}
 },[unbuilt,jobs,busy,build]);
 const buildControls=unbuilt.map(repo=>{
   const job=jobs.filter(j=>j.kind==='graphify' && j.source_id===repo.id).at(-1);
   const building=job?.status==='queued'||job?.status==='running';
   if(repo.status==='empty')return <VStack key={repo.id} gap={2}><Text weight="semibold">{repo.name}</Text><Text>This repository is empty.</Text></VStack>;
   const indexing=repo.status!=='ready' && repo.status!=='failed';
   return <VStack key={repo.id} gap={2}>
     <Text weight="semibold">{repo.name}</Text>
     <Text color="secondary">{building?'Graphify is building your code map.':indexing?'Indexing repository files…':repo.status==='failed'?'Repository indexing failed. Check Files & code.':job?.status==='failed'?job.error:'Preparing your code map…'}</Text>
     {job?.status==='failed' && <Button label="Retry Graphify build" isDisabled={busy} onClick={()=>build?.(repo.id)}/>}
   </VStack>;
 });
 const [id,setId]=useState(''),[query,setQuery]=useState(''),[focus,setFocus]=useState(''),[driver,setDriver]=useState(''),[candidate,setCandidate]=useState(''),[data,setData]=useState<GraphData|null>(null),[detail,setDetail]=useState<unknown>(null),[technicalDetail,setTechnicalDetail]=useState(false),[loading,setLoading]=useState(false),[source,setSource]=useState(''),[target,setTarget]=useState(''),[paths,setPaths]=useState<unknown>(null);
 useEffect(()=>{
   if(!pendingUpload)return;
   const result=allGraphs.find(g=>g.metadata?.upload_id===pendingUpload);
   if(result){setId(result.id);setPendingUpload('')}
 },[pendingUpload,allGraphs]);
 const currentGraph=graphs.find(g=>g.id===id)||graphs[0];
 const selected=currentGraph?.id||'';
 async function download(){
   try{
     const graph=await request(`${base}/graphs/${selected}/export`);
     const url=URL.createObjectURL(new Blob([JSON.stringify(graph,null,2)],{type:'application/json'}));
     const link=document.createElement('a');
     link.href=url;link.download='graph.json';link.click();
     setTimeout(()=>URL.revokeObjectURL(url),1000);
   }catch(e){onError((e as Error).message)}
 }
 async function load(){if(!selected)return;setLoading(true);try{const params=new URLSearchParams({query,focus,limit:'80'});if(driver)params.set('driver_id',driver);if(candidate)params.set('candidate_id',candidate);setData(await request(`${base}/graphs/${selected}?${params}`))}catch(e){onError((e as Error).message)}finally{setLoading(false)}}
 useEffect(()=>{setDetail(null);setFocus('');load()},[selected,base,driver,candidate]);
 const adapted=useMemo(()=>data?adaptGraph(data):{nodes:[],edges:[],boundaries:[]},[data]);
 const [flowNodes,setFlowNodes,onNodesChange]=useNodesState(adapted.nodes);
 useEffect(()=>{setFlowNodes(adapted.nodes)},[adapted.nodes,setFlowNodes]);
 const inspect=useCallback(async(nodeId:string)=>{if(!data)return;const local=localNodeDetail(nodeId,data,records);if(local){setTechnicalDetail(false);setDetail(local);return}try{setDetail(await request(`${base}/graphs/${selected}/nodes/${encodeURIComponent(nodeId)}`));setTechnicalDetail(true);setFocus(nodeId)}catch(e){onError((e as Error).message)}},[data,records,base,selected,onError]);
 const onSelection=useCallback(({nodes}:OnSelectionChangeParams)=>{if(nodes[0])void inspect(nodes[0].id)},[inspect]);
 if(!graphs.length)return <VStack gap={4}><Heading level={1}>Code map</Heading>
   {archiveInput}
   {buildControls}
   {!repositories.length && <><Text color="secondary">{busy?'Loading project…':'You can also connect GitHub or import a Graphify JSON file in Files & code.'}</Text>
     {!busy && <Button label="Open Files & code" onClick={openSources}/>}</>}
 </VStack>;
 return <VStack gap={5}>
 <Heading level={1}>Code map</Heading>
 <Text color="secondary" xstyle={s.measure}>See how your code connects. Select a part to view its details and sources.</Text>
 {archiveInput}
 {buildControls}
 {currentGraph?.metadata?.generator==='graphify' && <VStack gap={2}>
   <Text type="supporting" color="secondary">Built from the indexed snapshot{currentGraph.metadata.indexed_text_files!=null?` · ${currentGraph.metadata.indexed_text_files} files indexed`:''}{currentGraph.metadata.skipped_files?` · ${currentGraph.metadata.skipped_files} files skipped during indexing`:''}</Text>
   <Button label="Download graph.json" onClick={download}/>
 </VStack>}
 <HStack gap={4} wrap="wrap"><HStack gap={2} vAlign="center"><AppIcon icon={Network} color="purple"/><Text type="supporting">Proposed parts</Text></HStack><HStack gap={2} vAlign="center"><AppIcon icon={Network} color="orange"/><Text type="supporting">Related to a change</Text></HStack><Text type="supporting" color="secondary">Dashed connections need checking.</Text></HStack>
 <HStack gap={3} wrap="wrap"><Selector label="Code map" value={selected} onChange={setId} options={graphs.map(g=>({value:g.id,label:displayText(g.name)}))}/><Selector label="Reason for change" value={driver} onChange={setDriver} options={[{value:'',label:'All changes'},...records.filter(r=>r.kind==='driver').map(r=>({value:r.id,label:displayText(r.title)}))]}/><Selector label="Compare design" value={candidate} onChange={setCandidate} options={[{value:'',label:'Current system'},...records.filter(r=>r.kind==='architecture').map(r=>({value:r.id,label:displayText(r.title)}))]}/></HStack>
 <HStack gap={3} vAlign="end" wrap="wrap"><TextInput label="Find code" value={query} onChange={setQuery} onEnter={load} placeholder="Name or file path"/><Selector label="Show nearby code" value={focus} onChange={setFocus} options={[{value:'',label:'All parts'},...(data?.nodes||[]).filter(n=>!n.id.startsWith('business:')).map(n=>({value:n.id,label:displayText(n.label)}))]}/><Button label="Show results" icon={<AppIcon icon={Search} color="blue"/>} isLoading={loading} onClick={load}/></HStack>
 <VStack xstyle={s.canvas}><ReactFlow nodes={flowNodes} onNodesChange={onNodesChange} onNodeClick={(_,node)=>{void inspect(node.id)}} edges={adapted.edges} nodeTypes={nodeTypes} fitView fitViewOptions={{padding:0.2}} minZoom={0.15} key={`${selected}:${candidate}:${driver}:${adapted.nodes.map(n=>n.id).join(',')}`} onSelectionChange={onSelection}><Background/><Controls/><MiniMap/></ReactFlow></VStack>
 {data&&<Text type="supporting" color="secondary">Showing {data.nodes.length} parts and {data.edges.length} connections.</Text>}
 {adapted.boundaries.length>0&&<VStack gap={4}><Heading level={2}>Proposed parts</Heading>{adapted.boundaries.map(b=><VStack key={b.name} gap={2} paddingBlock={3} xstyle={s.detail}><Heading level={3}>{b.name}</Heading><Text>{b.responsibility||'Purpose needs review.'}</Text><Text>What stays the same: {b.stable_contract||'Not known yet'}</Text><Text type="supporting" color="secondary">{b.node_ids?.length||0} related code parts · needs review</Text><Button icon={<AppIcon icon={Search} color="purple"/>} label={displayText(`View ${b.name}`)} variant="ghost" onClick={()=>{setTechnicalDetail(false);setDetail(b)}}/></VStack>)}</VStack>}
 {detail!=null&&<VStack gap={4} paddingBlock={4} xstyle={s.detail} aria-live="polite"><Heading level={2}>Sources & connections</Heading><Button label="Show nearby parts" icon={<AppIcon icon={Network} color={technicalDetail?'teal':'disabled'}/>} isDisabled={!focus||!technicalDetail} onClick={load}/><DetailFields value={detail}/></VStack>}
 <Heading level={2}>Find a connection</Heading><HStack gap={3} wrap="wrap" vAlign="end"><Selector label="From" value={source} onChange={setSource} options={(data?.nodes||[]).filter(n=>!n.id.startsWith('business:')).map(n=>({value:n.id,label:displayText(n.label)}))}/><Selector label="To" value={target} onChange={setTarget} options={(data?.nodes||[]).filter(n=>!n.id.startsWith('business:')).map(n=>({value:n.id,label:displayText(n.label)}))}/><Button label="Find connection" icon={<AppIcon icon={ArrowRight} color={source&&target?'teal':'disabled'}/>} isDisabled={!source||!target} onClick={async()=>{try{setPaths(await request(`${base}/graphs/${selected}/paths?${new URLSearchParams({source,target})}`))}catch(e){onError((e as Error).message)}}}/></HStack>{paths!=null&&<VStack gap={3}>{((paths as {paths?:string[][]}).paths||[]).length?(paths as {paths:string[][]}).paths.map((path,i)=><Text key={i}>{path.map(id=>data?.nodes.find(n=>n.id===id)?.label||id).join(' → ')}</Text>):<Text color="secondary">No connection was found in this code map.</Text>}</VStack>}
 </VStack>
}
