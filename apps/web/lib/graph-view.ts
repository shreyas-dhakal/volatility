import {MarkerType, Position, type Edge, type Node} from '@xyflow/react';
import type {GraphData,GraphNode,Knowledge} from './types';
export type Boundary = {name:string;node_ids?:string[];responsibility?:string;stable_contract?:string;[key:string]:unknown};
export function graphBoundaries(graph:GraphData):Boundary[]{return Array.isArray(graph.summary.boundaries)?graph.summary.boundaries.filter((b):b is Boundary=>!!b&&typeof b==='object'&&typeof (b as Boundary).name==='string'):[]}
export function edgeEvidence(metadata:Record<string,unknown>={}){
 const declared=String(metadata.evidence_status||'').toLowerCase();const confidence=metadata.confidence;
 const upstream=String(confidence||'').toLowerCase();
 const verified=['verified','human_confirmed'].includes(declared);
 const inferred=['ai_inferred','hypothesis','inferred'].includes(declared)||upstream.includes('infer')||upstream.includes('hypothes')||typeof confidence==='number'&&confidence<1;
 return {dashed:!verified,label:verified?declared.replaceAll('_',' '):inferred?'inferred — unverified':'upstream claim — unverified',confidence};
}
function layeredPositions(nodes:GraphNode[],edges:GraphData['edges']){
 const ids=new Set(nodes.map(n=>n.id)),indegree=new Map(nodes.map(n=>[n.id,0])),rank=new Map(nodes.map(n=>[n.id,0]));
 for(const e of edges)if(ids.has(e.source)&&ids.has(e.target))indegree.set(e.target,(indegree.get(e.target)||0)+1);
 const queue=nodes.filter(n=>indegree.get(n.id)===0).map(n=>n.id),seen=new Set<string>();
 while(queue.length){const id=queue.shift()!;seen.add(id);for(const e of edges.filter(e=>e.source===id&&ids.has(e.target))){rank.set(e.target,Math.max(rank.get(e.target)||0,(rank.get(id)||0)+1));indegree.set(e.target,(indegree.get(e.target)||0)-1);if(indegree.get(e.target)===0)queue.push(e.target)}}
 if(seen.size!==nodes.length)return new Map(nodes.map((n,i)=>[n.id,{x:(i%3)*240,y:Math.floor(i/3)*150}]));
 const columns=new Map<number,number>();return new Map(nodes.map(n=>{const r=rank.get(n.id)||0,index=columns.get(r)||0;columns.set(r,index+1);return[n.id,{x:(index%3)*240,y:r*170+Math.floor(index/3)*120}]}));
}
export function adaptGraph(graph:GraphData):{nodes:Node[];edges:Edge[];boundaries:Boundary[]}{
 const boundaries=graphBoundaries(graph);const groups=new Map<string,GraphNode[]>();const membership=new Map<string,string>();
 for(const node of graph.nodes){const name=typeof node.metadata?.proposed_boundary==='string'?node.metadata.proposed_boundary:boundaries.find(b=>b.node_ids?.includes(node.id))?.name;if(name){membership.set(node.id,name);groups.set(name,[...(groups.get(name)||[]),node])}}
 const nodes:Node[]=[];let groupBottom=0,rowY=0;const groupLocations=new Map<string,{id:string;x:number;y:number}>();
 [...groups].forEach(([name,members],i)=>{if(i%2===0)rowY=groupBottom?groupBottom+40:0;const id=`boundary-group:${name}`,x=(i%2)*560,y=rowY,height=Math.max(220,100+Math.ceil(members.length/2)*125);groupLocations.set(name,{id,x,y});groupBottom=Math.max(groupBottom,y+height);nodes.push({id,type:'boundaryGroup',position:{x,y},data:{label:name,description:'Proposed boundary'},ariaLabel:`Proposed boundary ${name}. Press Enter to inspect its contract and evidence.`,focusable:true,selectable:true,draggable:false,style:{width:530,height,background:'var(--color-background-purple)',color:'var(--color-text-primary)',border:'1px dashed var(--color-border-purple)',borderRadius:'var(--radius-container)'}})});
 const positions=layeredPositions(graph.nodes.filter(n=>!membership.has(n.id)),graph.edges);
 for(const n of graph.nodes){const group=groupLocations.get(membership.get(n.id)||'');const siblings=groups.get(membership.get(n.id)||'')||[];const index=siblings.findIndex(x=>x.id===n.id);const highlighted=n.metadata?.highlighted===true;const evidence=String(n.metadata?.evidence_status||'upstream claim');nodes.push({id:n.id,parentId:group?.id,extent:group?'parent':undefined,position:group?{x:25+(index%2)*250,y:80+Math.floor(index/2)*125}:{x:positions.get(n.id)?.x||0,y:(positions.get(n.id)?.y||0)+(groupBottom?groupBottom+100:0)},data:{label:`${n.label} · ${n.type}${highlighted?' · Change driver match':''}`},sourcePosition:Position.Bottom,targetPosition:Position.Top,ariaLabel:`${n.label}, ${n.type}${group?`, proposed boundary ${membership.get(n.id)}`:''}${highlighted?', highlighted by selected change driver':''}, ${evidence.replaceAll('_',' ')}. Press Enter to inspect evidence.`,focusable:true,selectable:true,draggable:false,style:{width:210,minHeight:65,background:highlighted?'var(--color-background-orange)':n.type==='decision'?'var(--color-background-blue)':'var(--color-background-body)',color:'var(--color-text-primary)',border:highlighted?'2px solid var(--color-border-orange)':'1px solid var(--color-border)',borderRadius:'var(--radius-container)',fontWeight:highlighted?600:400}})}
 const ids=new Set(graph.nodes.map(n=>n.id));const edges:Edge[]=graph.edges.filter(e=>ids.has(e.source)&&ids.has(e.target)).map(e=>{const evidence=edgeEvidence(e.metadata);return {...e,type:'smoothstep',label:`${e.type} (${evidence.dashed?(evidence.label.startsWith('inferred')?'inferred':'source'):'verified'})`,ariaLabel:`${e.type}, ${evidence.label}${evidence.confidence!=null?`, upstream confidence ${evidence.confidence}`:''}`,markerEnd:{type:MarkerType.ArrowClosed},style:{stroke:'var(--color-text-secondary)',strokeDasharray:evidence.dashed?'6 4':undefined},labelStyle:{fill:'var(--color-text-secondary)',fontSize:10},labelBgStyle:{fill:'var(--color-background-body)'}}});return {nodes,edges,boundaries}
}
export function localNodeDetail(id:string,graph:GraphData,records:Knowledge[]):Record<string,unknown>|null{
 if(id.startsWith('boundary-group:')){const name=id.slice('boundary-group:'.length);const boundary=graphBoundaries(graph).find(b=>b.name===name);return {type:'Proposed boundary',...(boundary||{name}),evidence_status:graph.nodes.find(n=>n.metadata?.proposed_boundary===name)?.metadata?.boundary_evidence_status||'ai_inferred'}}
 if(id.startsWith('business:')){const record=records.find(r=>r.id===id.slice(9));if(record)return {type:'Business knowledge',title:record.title,description:record.description,status:record.status,evidence_status:record.evidence_status,payload:record.payload,version:record.version};const n=graph.nodes.find(n=>n.id===id);return n?{...n,category:'Business knowledge'}:null}
 return null;
}
