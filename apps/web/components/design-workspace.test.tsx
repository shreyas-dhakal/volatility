// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
vi.mock('@stylexjs/stylex',async original=>({...await original<object>(),create:(styles:Record<string,unknown>)=>Object.fromEntries(Object.keys(styles).map(k=>[k,{}]))}));
import {DesignWorkspace} from './design-workspace';
import type {DesignSnapshot,Knowledge} from '../lib/types';
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
const record=(id:string,kind:string,payload:Record<string,unknown>={},status='approved'):Knowledge=>({id,kind,title:`Title ${id}`,description:`Reason ${id}`,status,evidence_status:'ai_inferred',version:4,payload,history:[]});
const empty=():DesignSnapshot=>({use_cases:[],core_use_cases:[],volatilities:[],components:[],validations:[],findings:[],readiness:{use_cases:false,core_use_cases:false,volatility:false,decomposition:false,validation:false}});
function setup(snapshot=empty(),aiAvailable:boolean|null=true){
 const fetcher=vi.fn(async(_url:string,init?:RequestInit)=>new Response(JSON.stringify(init?.method&&init.method!=='GET'?{records:[]}:snapshot)));
 vi.stubGlobal('fetch',fetcher);render(<DesignWorkspace base="/projects/p" aiAvailable={aiAvailable}/>);return fetcher;
}
async function stage(name:string){await screen.findByRole('heading',{name:'Gather detailed use cases'});fireEvent.click(screen.getByRole('button',{name}));}
it('saves detailed intake with normalized lines through the real API helper and keeps review separate',async()=>{
 const fetcher=setup();await screen.findByRole('heading',{name:'Gather detailed use cases'});
 for(const [label,value] of [['Use case title','Place order'],['Actor','Buyer'],['Trigger','Checkout'],['Preconditions','Signed in\nStock available'],['Steps','Choose items\n\nPay'],['Outcome','Order accepted'],['Variations','Card declined\nBackorder']])fireEvent.change(screen.getByLabelText(new RegExp(`^${label}`)),{target:{value}});
 fireEvent.click(screen.getByRole('button',{name:'Save use case'}));
 await waitFor(()=>expect(fetcher.mock.calls.some(([url,init])=>url==='/api/projects/p/design/use-cases'&&init?.method==='POST')).toBe(true));
 const call=fetcher.mock.calls.find(([url])=>url.endsWith('/use-cases'))!;
 expect(JSON.parse(call[1]!.body as string)).toEqual({title:'Place order',description:'',actor:'Buyer',trigger:'Checkout',preconditions:['Signed in','Stock available'],steps:['Choose items','Pay'],outcome:'Order accepted',variations:['Card declined','Backorder'],evidence_ids:[]});
 expect(fetcher.mock.calls.some(([,init])=>init?.method==='PATCH')).toBe(false);
});
it('explains missing configuration and reviewed prerequisites without generating fake artifacts',async()=>{
 const fetcher=setup(empty(),false);await stage('Core cases');
 expect(screen.getByText(/Ask the person running Galvanise to configure/)).toBeTruthy();
 expect(screen.getByRole('button',{name:'Propose core cases'}).getAttribute('aria-disabled')).toBe('true');
 fireEvent.click(screen.getByRole('button',{name:'Independent volatilities'}));expect(screen.getByText('Review and approve core cases before proposing volatilities.')).toBeTruthy();
 expect(fetcher.mock.calls.every(([,init])=>!init?.method||init.method==='GET')).toBe(true);
});
it('generates an explicit stage and refreshes without auto approval',async()=>{
 const data=empty();data.use_cases=[record('u','use_case')];data.readiness.use_cases=true;
 const fetcher=setup(data);await stage('Core cases');fireEvent.click(screen.getByRole('button',{name:'Propose core cases'}));
 await waitFor(()=>expect(fetcher.mock.calls.some(([url,init])=>url.endsWith('/generate')&&JSON.parse(init!.body as string).stage==='core')).toBe(true));
 expect(fetcher.mock.calls.filter(([url])=>url.endsWith('/design')).length).toBe(2);
 expect(fetcher.mock.calls.some(([,init])=>init?.method==='PATCH')).toBe(false);
});
it('reviews with the record version and makes reasoning links readable and navigable',async()=>{
 const data=empty();data.use_cases=[record('u','use_case',{variations:['Supplier refuses']})];data.core_use_cases=[record('c','core_use_case',{use_case_ids:['u'],rationale:'Same business outcome'},'pending')];
 const fetcher=setup(data);await stage('Core cases');fireEvent.click(screen.getByRole('button',{name:'Review Title c'}));
 fireEvent.click(screen.getByRole('button',{name:'Approve artifact'}));await waitFor(()=>expect(fetcher.mock.calls.some(([url,init])=>url==='/api/projects/p/records/c'&&init?.method==='PATCH')).toBe(true));
 expect(JSON.parse(fetcher.mock.calls.find(([url])=>url.endsWith('/records/c'))![1]!.body as string)).toEqual({status:'approved',expected_version:4});
 fireEvent.click(screen.getByRole('button',{name:'Title u · approved'}));expect(await screen.findByRole('heading',{name:'Gather detailed use cases'})).toBeTruthy();expect(screen.getByText('Supplier refuses')).toBeTruthy();
});
it('shows deterministic findings and invalidates a validation after its input changes',async()=>{
 const data=empty();data.components=[record('b','boundary',{component_role:'engine',stable_contract:'Price(input) → Quote'})];data.validations=[record('v','design_validation',{input_versions:{b:3},assumptions:['Tax policy may change']})];data.findings=[{code:'missing_coverage',severity:'warning',message:'Returns have no collaboration.',record_ids:['b']}];data.readiness.validation=false;
 setup(data);await stage('Coverage & containment');expect(screen.getByText('Returns have no collaboration.')).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Review Title v'}));expect(screen.getByText(/Historical validation: inputs have changed/)).toBeTruthy();expect(screen.queryByText('Design verified')).toBeNull();
});
it('keeps intake after an API error and reports an actionable setup failure',async()=>{
 const fetcher=setup();await screen.findByRole('heading',{name:'Gather detailed use cases'});
 fetcher.mockImplementation(async(_url,init)=>init?.method==='POST'?new Response(JSON.stringify({detail:'Check evidence ownership.'}),{status:422}):new Response(JSON.stringify(empty())));
 for(const label of ['Use case title','Steps','Outcome'])fireEvent.change(screen.getByLabelText(new RegExp(`^${label}`)),{target:{value:'Keep this draft'}});
 fireEvent.click(screen.getByRole('button',{name:'Save use case'}));expect((await screen.findByRole('alert')).textContent).toContain('Check evidence ownership.');expect((screen.getByLabelText(/^Use case title/) as HTMLInputElement).value).toBe('Keep this draft');
});
it('loads errors honestly and retries the design snapshot',async()=>{
 const fetcher=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({detail:'Design service unavailable.'}),{status:503})).mockResolvedValue(new Response(JSON.stringify(empty())));vi.stubGlobal('fetch',fetcher);
 render(<DesignWorkspace base="/projects/p" aiAvailable/>);expect((await screen.findByRole('alert')).textContent).toContain('Design service unavailable.');fireEvent.click(screen.getByRole('button',{name:'Reload design process'}));await screen.findByRole('heading',{name:'Gather detailed use cases'});
});
it.each([
 ['Independent volatilities','Propose volatilities','volatility'],
 ['Components & contracts','Propose components','decomposition'],
 ['Coverage & containment','Propose validation','validation'],
])('calls the exact %s stage endpoint with reviewed inputs',async(tab,action,expected)=>{
 const data=empty();data.readiness={use_cases:true,core_use_cases:true,volatility:true,decomposition:true,validation:false};const fetcher=setup(data);await stage(tab);fireEvent.click(screen.getByRole('button',{name:action}));
 await waitFor(()=>expect(fetcher.mock.calls.some(([url,init])=>url==='/api/projects/p/design/generate'&&init?.method==='POST'&&JSON.parse(init.body as string).stage===expected)).toBe(true));
});
it('never enables a downstream action with unreviewed inputs even when AI is configured',async()=>{
 const data=empty();data.core_use_cases=[record('c','core_use_case',{},'pending')];setup(data);await stage('Independent volatilities');expect(screen.getByRole('button',{name:'Propose volatilities'}).getAttribute('aria-disabled')).toBe('true');fireEvent.click(screen.getByRole('button',{name:'Components & contracts'}));expect(screen.getByRole('button',{name:'Propose components'}).getAttribute('aria-disabled')).toBe('true');fireEvent.click(screen.getByRole('button',{name:'Coverage & containment'}));expect(screen.getByRole('button',{name:'Propose validation'}).getAttribute('aria-disabled')).toBe('true');
});
it('offers owned evidence by readable title and submits its reference',async()=>{
 const data=empty();const fetcher=vi.fn(async()=>new Response(JSON.stringify(data)));vi.stubGlobal('fetch',fetcher);render(<DesignWorkspace base="/projects/p" aiAvailable={false} records={[record('e','evidence')]}/>);await screen.findByRole('heading',{name:'Gather detailed use cases'});
 for(const label of ['Use case title','Steps','Outcome'])fireEvent.change(screen.getByLabelText(new RegExp(`^${label}`)),{target:{value:'Case'}});
 fireEvent.click(screen.getByRole('button',{name:'Title e'}));fireEvent.click(screen.getByRole('button',{name:'Save use case'}));await waitFor(()=>expect(fetcher.mock.calls.length).toBeGreaterThan(1));
 expect(JSON.parse((fetcher.mock.calls as unknown as [string,RequestInit][]).find(([url])=>url.endsWith('/use-cases'))![1].body as string).evidence_ids).toEqual(['e']);
});
it('loads the current version after a conflict and requires another explicit review',async()=>{
 const data=empty();data.use_cases=[record('u','use_case',{},'pending')];const fetcher=setup(data);await screen.findByRole('button',{name:'Review Title u'});fireEvent.click(screen.getByRole('button',{name:'Review Title u'}));
 fetcher.mockImplementation(async(_url,init)=>init?.method==='PATCH'?new Response(JSON.stringify({detail:'Stale record.'}),{status:409}):new Response(JSON.stringify({...data,use_cases:[{...data.use_cases[0],version:5}]})));
 fireEvent.click(screen.getByRole('button',{name:'Approve artifact'}));expect((await screen.findByRole('alert')).textContent).toContain('changed since you opened it');expect(await screen.findByText(/Version 5/)).toBeTruthy();expect(fetcher.mock.calls.filter(([,init])=>init?.method==='PATCH')).toHaveLength(1);
});
it('shows upstream and downstream reasoning without hiding original variations',async()=>{
 const data=empty();data.use_cases=[record('u','use_case',{variations:['Alternate supplier']})];data.core_use_cases=[record('c','core_use_case',{use_case_ids:['u']})];setup(data);await screen.findByRole('button',{name:'Review Title u'});fireEvent.click(screen.getByRole('button',{name:'Review Title u'}));expect(screen.getByText('Alternate supplier')).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Title c · approved'}));expect(screen.getByRole('heading',{name:'Review the business essence'})).toBeTruthy();
});
it('retains component role, contracts and dependencies during human review and versioned edits',async()=>{
 const data=empty();data.components=[record('b','boundary',{design_engine:true,component_role:'engine',responsibility:'Price an order',stable_contract:'quote(order)',hidden_change:'Pricing policy',excluded_responsibilities:['Checkout'],dependencies:['r'],volatility_ids:[]}),record('r','boundary',{component_role:'resource'})];const fetcher=setup(data);await stage('Components & contracts');fireEvent.click(screen.getByRole('button',{name:'Review Title b'}));expect(screen.getByText('quote(order)')).toBeTruthy();expect(screen.getByText('Pricing policy')).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Edit artifact'}));fireEvent.change(screen.getByLabelText('Stable contract'),{target:{value:'quote(order, currency)'}});fireEvent.click(screen.getByRole('button',{name:'Save artifact changes'}));
 await waitFor(()=>expect(fetcher.mock.calls.some(([,init])=>init?.method==='PATCH')).toBe(true));expect(JSON.parse(fetcher.mock.calls.find(([,init])=>init?.method==='PATCH')![1]!.body as string)).toMatchObject({expected_version:4,status:'pending',payload:{component_role:'engine',stable_contract:'quote(order, currency)',dependencies:['r']}});
});
it('shows server generation errors and preserves approved artifacts',async()=>{
 const data=empty();data.use_cases=[record('u','use_case')];const fetcher=setup(data);await stage('Core cases');fetcher.mockImplementation(async(_url,init)=>init?.method==='POST'?new Response(JSON.stringify({detail:'Configure OPENAI_API_KEY on the API server.'}),{status:503}):new Response(JSON.stringify(data)));
 fireEvent.click(screen.getByRole('button',{name:'Propose core cases'}));expect((await screen.findByRole('alert')).textContent).toContain('Configure OPENAI_API_KEY');expect(fetcher.mock.calls.some(([,init])=>init?.method==='PATCH')).toBe(false);
});
it('keeps unknown truncation metadata visible and shows loading until the snapshot arrives',async()=>{
 let resolve!:(r:Response)=>void;vi.stubGlobal('fetch',vi.fn(()=>new Promise<Response>(r=>{resolve=r})));render(<DesignWorkspace base="/projects/p" aiAvailable={null}/>);expect(screen.getByText('Loading design artifacts…')).toBeTruthy();await waitFor(()=>expect(typeof resolve).toBe('function'));resolve(new Response(JSON.stringify({...empty(),truncated:true,input_limit_notice:'Only first 100 inputs included.'})));expect(await screen.findByText('Only first 100 inputs included.')).toBeTruthy();expect(screen.getByText(/Checking AI configuration/)).toBeTruthy();
});
it('opens evidence references as readable review details',async()=>{
 const data=empty();data.use_cases=[record('u','use_case',{evidence_ids:['e']})];vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify(data))));render(<DesignWorkspace base="/projects/p" aiAvailable records={[record('e','evidence',{quote:'Customer supplied the variation.'})]}/>);await screen.findByRole('button',{name:'Review Title u'});fireEvent.click(screen.getByRole('button',{name:'Review Title u'}));fireEvent.click(screen.getByRole('button',{name:'Title e · approved'}));expect(screen.getByText('Customer supplied the variation.')).toBeTruthy();
});
it('keeps existing cases immediately reviewable and reveals intake explicitly',async()=>{
 const data=empty();data.use_cases=[record('u','use_case')];setup(data);await screen.findByRole('button',{name:'Review Title u'});expect(screen.queryByLabelText(/^Use case title/)).toBeNull();fireEvent.click(screen.getByRole('button',{name:'Add detailed use case'}));expect(screen.getByLabelText(/^Use case title/)).toBeTruthy();
});
it('does not present stale readiness after a failed refresh',async()=>{
 const data=empty();data.readiness.validation=true;const fetcher=setup(data);await screen.findByRole('heading',{name:'Gather detailed use cases'});fetcher.mockResolvedValue(new Response(JSON.stringify({detail:'Connection lost; retry.'}),{status:503}));fireEvent.click(screen.getByRole('button',{name:'Reload design process'}));await screen.findByRole('alert');expect(screen.queryByText('Reviewed validation inputs are available. Check assumptions and findings before relying on this design.')).toBeNull();
});
it('distinguishes a saved review from a failed refresh and hides outdated readiness',async()=>{
 const data=empty();data.use_cases=[record('u','use_case',{},'pending')];const fetcher=setup(data);await screen.findByRole('button',{name:'Review Title u'});fireEvent.click(screen.getByRole('button',{name:'Review Title u'}));fetcher.mockImplementation(async(_url,init)=>init?.method==='PATCH'?new Response(JSON.stringify({...data.use_cases[0],status:'approved',version:5})):new Response(JSON.stringify({detail:'Snapshot unavailable.'}),{status:503}));fireEvent.click(screen.getByRole('button',{name:'Approve artifact'}));expect((await screen.findByRole('alert')).textContent).toContain('Your change was saved');expect(screen.queryByRole('region',{name:'Artifact review'})).toBeNull();expect(fetcher.mock.calls.filter(([,init])=>init?.method==='PATCH')).toHaveLength(1);
});
