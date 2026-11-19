import {displayText} from './text';
import {type Edge, type Node} from '@xyflow/react';
import {forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum} from 'd3-force';
import type {GraphData,GraphNode,Knowledge} from './types';
export type Boundary = {name:string;node_ids?:string[];responsibility?:string;stable_contract?:string;[key:string]:unknown};
export function graphBoundaries(graph:GraphData):Boundary[]{return Array.isArray(graph.summary.boundaries)?graph.summary.boundaries.filter((b):b is Boundary=>!!b&&typeof b==='object'&&typeof (b as Boundary).name==='string'):[]}
export function edgeEvidence(metadata:Record<string,unknown>={}){
 const declared=String(metadata.evidence_status||'').toLowerCase();const confidence=metadata.confidence;
 const upstream=String(confidence||'').toLowerCase();
 const verified=['verified','human_confirmed'].includes(declared);
 const inferred=['ai_inferred','hypothesis','inferred'].includes(declared)||upstream.includes('infer')||upstream.includes('hypothes')||typeof confidence==='number'&&confidence<1;
 return {dashed:!verified,label:verified?declared.replaceAll('_',' '):inferred?'inferred - unverified':'upstream claim - unverified',confidence};
}
export function layeredPositions(nodes:{id:string}[],edges:{source:string;target:string}[]){
 const ids=new Set(nodes.map(n=>n.id)),indegree=new Map(nodes.map(n=>[n.id,0])),rank=new Map(nodes.map(n=>[n.id,0]));
 for(const e of edges)if(ids.has(e.source)&&ids.has(e.target))indegree.set(e.target,(indegree.get(e.target)||0)+1);
 const queue=nodes.filter(n=>indegree.get(n.id)===0).map(n=>n.id),seen=new Set<string>();
 while(queue.length){const id=queue.shift()!;seen.add(id);for(const e of edges.filter(e=>e.source===id&&ids.has(e.target))){rank.set(e.target,Math.max(rank.get(e.target)||0,(rank.get(id)||0)+1));indegree.set(e.target,(indegree.get(e.target)||0)-1);if(indegree.get(e.target)===0)queue.push(e.target)}}
 if(seen.size!==nodes.length)return new Map(nodes.map((n,i)=>[n.id,{x:(i%3)*240,y:Math.floor(i/3)*150}]));
 const columns=new Map<number,number>();return new Map(nodes.map(n=>{const r=rank.get(n.id)||0,index=columns.get(r)||0;columns.set(r,index+1);return[n.id,{x:(index%3)*240,y:r*170+Math.floor(index/3)*120}]}));
}
type Particle = SimulationNodeDatum & {id:string; radius:number};
type Link = {source:string; target:string};

function settle(particles:Particle[], links:Link[]){
 const simulation=forceSimulation(particles.sort((a,b)=>a.id.localeCompare(b.id)))
   .force('links',forceLink<Particle,Link>(links).id(p=>p.id).distance(62))
   .force('repel',forceManyBody<Particle>().strength(-170))
   .force('space',forceCollide<Particle>().radius(p=>p.radius+5).iterations(2))
   .force('x',forceX(0).strength(0.035)).force('y',forceY(0).strength(0.045))
   .stop();
 simulation.tick(180);
 return new Map(particles.map(p=>[p.id,{x:p.x!,y:p.y!}]));
}

export function adaptGraph(graph:GraphData):{nodes:Node[];edges:Edge[];boundaries:Boundary[]}{
 const boundaries=graphBoundaries(graph);
 const groups=new Map<string,GraphNode[]>(),membership=new Map<string,string>();
 const ids=new Set(graph.nodes.map(n=>n.id));
 const links=graph.edges.filter(e=>ids.has(e.source)&&ids.has(e.target));
 const degree=new Map<string,number>();
 for(const e of links){
   degree.set(e.source,(degree.get(e.source)||0)+1);
   degree.set(e.target,(degree.get(e.target)||0)+1);
 }
 const particles:Particle[]=[];
 for(const node of graph.nodes){
   const name=typeof node.metadata?.proposed_boundary==='string'?node.metadata.proposed_boundary:boundaries.find(b=>b.node_ids?.includes(node.id))?.name;
   if(name){
     membership.set(node.id,'boundary-group:'+name);
     const members=groups.get(name)||[];members.push(node);groups.set(name,members);
   }else particles.push({id:node.id,radius:20});
 }
 const memberPositions=new Map<string,{x:number;y:number}>();
 const groupSizes=new Map<string,number>();
 for(const [name,members] of groups){
   const id='boundary-group:'+name;
   const internal=links.filter(e=>membership.get(e.source)===id && membership.get(e.target)===id);
   const points=settle(members.map(n=>({id:n.id,radius:20})),internal.map(e=>({source:e.source,target:e.target})));
   const radius=55+Math.max(...Array.from(points.values(),p=>Math.hypot(p.x,p.y)));
   groupSizes.set(id,radius);
   particles.push({id,radius});
   for(const [key,p] of points)memberPositions.set(key,{x:p.x+radius-20,y:p.y+radius-20});
 }
 const external=links.map(e=>({source:membership.get(e.source)||e.source,target:membership.get(e.target)||e.target})).filter(e=>e.source!==e.target);
 const positions=settle(particles,external);
 const nodes:Node[]=[];
 for(const [name] of groups){
   const id='boundary-group:'+name,r=groupSizes.get(id)!,p=positions.get(id)!;
   nodes.push({id,type:'boundaryGroup',position:{x:p.x-r,y:p.y-r},data:{label:displayText(name),diameter:r*2},
     ariaLabel:displayText('Proposed boundary '+name),focusable:true,selectable:true,draggable:false,style:{width:r*2,height:r*2}});
 }
 const ranked=[...graph.nodes].sort((a,b)=>(degree.get(b.id)||0)-(degree.get(a.id)||0)||a.id.localeCompare(b.id));
 const overviewLabels=new Set(ranked.slice(0,graph.nodes.length<=18?18:8).map(n=>n.id));
 for(const n of graph.nodes){
   const parentId=membership.get(n.id),center=positions.get(n.id);
   const position=memberPositions.get(n.id) || {x:center!.x-20,y:center!.y-20};
   const highlighted=n.metadata?.highlighted===true;
   const color=highlighted?'orange':parentId?'purple':n.id.startsWith('business:')?'blue':'teal';
   const evidence=String(n.metadata?.evidence_status||'upstream claim').replaceAll('_',' ');
   nodes.push({id:n.id,type:'networkPoint',parentId,extent:parentId?'parent':undefined,position,
     data:{label:displayText(n.label),radius:5+Math.min(9,Math.sqrt(degree.get(n.id)||0)*1.6),color,
       overviewLabel:overviewLabels.has(n.id)||highlighted},
     ariaLabel:displayText(`${n.label}, ${n.type}${parentId?', proposed boundary '+parentId.slice(15):''}${highlighted?', highlighted by selected change driver':''}, ${evidence}. Press Enter to inspect evidence.`),
     focusable:true,selectable:true,draggable:false,style:{width:40,height:40}});
 }
 const edges:Edge[]=links.map(e=>{
   const evidence=edgeEvidence(e.metadata);
   return {id:e.id,source:e.source,target:e.target,type:e.source===e.target?'default':'straight',data:{relation:displayText(e.type)},
     ariaLabel:displayText(`${e.type}, ${evidence.label}${evidence.confidence!=null?', upstream confidence '+evidence.confidence:''}`),
     style:{stroke:'var(--color-text-secondary)',strokeWidth:1.25,opacity:0.48,strokeDasharray:evidence.dashed?'4 3':undefined}};
 });
 return {nodes,edges,boundaries};
}
export function localNodeDetail(id:string,graph:GraphData,records:Knowledge[]):Record<string,unknown>|null{
 if(id.startsWith('boundary-group:')){const name=id.slice('boundary-group:'.length);const boundary=graphBoundaries(graph).find(b=>b.name===name);return {type:'Proposed boundary',...(boundary||{name}),evidence_status:graph.nodes.find(n=>n.metadata?.proposed_boundary===name)?.metadata?.boundary_evidence_status||'ai_inferred'}}
 if(id.startsWith('business:')){const record=records.find(r=>r.id===id.slice(9));if(record)return {type:'Business knowledge',title:record.title,description:record.description,status:record.status,evidence_status:record.evidence_status,payload:record.payload,version:record.version};const n=graph.nodes.find(n=>n.id===id);return n?{...n,category:'Business knowledge'}:null}
 return null;
}
