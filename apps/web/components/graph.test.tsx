// @vitest-environment jsdom
import React,{useEffect} from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {NodeChangeset,type ReactFlowProps} from '@xyflow/react';
vi.mock('@stylexjs/stylex',async original=>({...await original<object>(),create:(styles:Record<string,unknown>)=>Object.fromEntries(Object.keys(styles).map(k=>[k,{}]))}));
// Keep the real useNodesState/applyNodeChanges. Replace only the measured canvas
// with an accessible event harness, so selected state must flow through the
// component's supplied onNodesChange before the selection callback can fire.
vi.mock('@xyflow/react',async original=>{const actual=await original<object>();return {...actual,Background:()=>null,Controls:()=>null,MiniMap:()=>null,ReactFlow:(props:ReactFlowProps)=>{
 useEffect(()=>{props.onSelectionChange?.({nodes:(props.nodes||[]).filter(n=>n.selected),edges:[]})},[props.nodes,props.onSelectionChange]);
 return <section aria-label="Graph event harness">{props.nodes?.map(node=><button key={node.id} aria-label={node.ariaLabel} aria-pressed={!!node.selected} onKeyDown={e=>{if(e.key==='Enter')props.onNodesChange?.(new NodeChangeset([{id:node.id,type:'select',selected:true}]))}} onClick={e=>props.onNodeClick?.(e,node)}>{String(node.data.label)}</button>)}</section>;
}}});
import {GraphWorkspace} from './graph';
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
it('persists keyboard graph selection and inspects pointer-activated business evidence locally',async()=>{
 const data={id:'g',name:'ERP',nodes:[{id:'orders',label:'Orders',type:'module',metadata:{}},{id:'business:d',label:'Supplier expansion',type:'decision',metadata:{evidence_status:'human_confirmed'}}],edges:[],summary:{}};
 const fetcher=vi.fn(async(url:string)=>new Response(JSON.stringify(url.includes('/nodes/')?{label:'Orders implementation',file_path:'src/orders.ts',dependencies:[]}:data)));vi.stubGlobal('fetch',fetcher);
 render(<GraphWorkspace base="/projects/p" graphs={[{id:'g',name:'ERP',node_count:2,edge_count:0}]} records={[{id:'d',kind:'decision',title:'Supplier expansion',description:'Confirmed by purchasing lead',status:'approved',evidence_status:'human_confirmed',version:1,payload:{evidence_ids:['document-1']},history:[]}]} onError={vi.fn()}/>);
 const orders=await screen.findByRole('button',{name:/Orders, module/});fireEvent.keyDown(orders,{key:'Enter'});
 await waitFor(()=>expect(screen.getByRole('button',{name:/Orders, module/}).getAttribute('aria-pressed')).toBe('true'));
 expect(await screen.findByText('Orders implementation')).toBeTruthy();expect(await screen.findByRole('heading',{name:'Sources & connections'})).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:/Supplier expansion, decision/}));expect(await screen.findByText('Confirmed by purchasing lead')).toBeTruthy();expect(screen.getByText('document-1')).toBeTruthy();expect(fetcher.mock.calls.some(([url])=>url.includes('/nodes/business'))).toBe(false);
});
it('automatically builds a legacy file index and loads the saved map on return',async()=>{
 const build=vi.fn();
 const fetcher=vi.fn(async()=>new Response(JSON.stringify({nodes:[],edges:[],summary:{}})));
 vi.stubGlobal('fetch',fetcher);
 const props={base:'/projects/p',repositories:[{id:'s',name:'shop/cart',kind:'github',status:'ready'}],records:[],onError:vi.fn(),build};
 const index={id:'index',name:'file index',node_count:2,edge_count:0,source_id:'s',metadata:{provenance:'GitHub tree API',dependencies_inferred:false}};
 const view=render(<GraphWorkspace {...props} graphs={[index]}/>);

 expect(build).toHaveBeenCalledWith('s');
 expect(fetcher).not.toHaveBeenCalled();
 view.rerender(<GraphWorkspace {...props} graphs={[index]} jobs={[{id:'j',kind:'graphify',status:'running',source_id:'s'}]}/>);
 expect(screen.getByText('Graphify is building your code map.')).toBeTruthy();
 view.unmount();
 render(<GraphWorkspace {...props} graphs={[index,{...index,id:'saved',metadata:{generator:'graphify'}}]}/>);
 await waitFor(()=>expect(fetcher.mock.calls.length).toBe(1));
 expect(screen.queryByRole('button',{name:'Build code map with Graphify'})).toBeNull();
 expect(build).toHaveBeenCalledTimes(1);
});

it('shows only the empty state for an empty GitHub repository',()=>{
 const build=vi.fn();
 render(<GraphWorkspace base="/projects/p" graphs={[]} records={[]} onError={vi.fn()} build={build}
   repositories={[{id:'s',name:'shop/cart',kind:'github',status:'empty'}]} uploadZip={vi.fn()}/>);
 expect(screen.getByText('This repository is empty.')).toBeTruthy();
 expect(screen.queryByRole('button')).toBeNull();
 expect(build).not.toHaveBeenCalled();
});
