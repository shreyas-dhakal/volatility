// @vitest-environment jsdom
import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
vi.mock('@stylexjs/stylex',async original=>({...await original<object>(),create:(styles:Record<string,unknown>)=>Object.fromEntries(Object.keys(styles).map(k=>[k,{}]))}));
import {ErrorNotice} from './workspace';
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
describe('account entry',()=>{
 it('announces actionable errors',()=>{render(<ErrorNotice message="Set OPENAI_API_KEY on the API server."/>);expect(screen.getByRole('alert').textContent).toContain('Set OPENAI_API_KEY')});
});
describe('explicit sample workspace',()=>{
 it('loads a sample only after user action and supports Promise-returning browser scroll',async()=>{
 const {default:Page}=await import('./workspace');
 Object.defineProperty(HTMLElement.prototype,'scrollIntoView',{configurable:true,value:vi.fn().mockResolvedValue(undefined)});
 Object.defineProperty(window,'matchMedia',{configurable:true,value:vi.fn().mockReturnValue({matches:false,addEventListener:vi.fn(),removeEventListener:vi.fn(),addListener:vi.fn(),removeListener:vi.fn()})});
 const user={id:'u',email:'a@example.com',name:'Alex',github_connected:false};let seeded=false;const project={id:'demo',name:'Sample ERP',system_type:'existing',description:'Synthetic project',objective:'Demonstrate architecture'};
 const fetcher=vi.fn(async(url:string)=>{let body:unknown=[];if(url==='/api/health')body={ai_configured:false,github_configured:false};if(url==='/api/auth/me')body=user;if(url==='/api/projects')body=seeded?[project]:[];if(url==='/api/projects/demo'){seeded=true;body=project}return new Response(JSON.stringify(body))});vi.stubGlobal('fetch',fetcher);
 const errors=vi.spyOn(console,'error');render(<Page onSignOut={async()=>{}}/>);await screen.findByRole('button',{name:'Explore sample project'});expect(seeded).toBe(false);fireEvent.click(screen.getByRole('button',{name:'Explore sample project'}));await screen.findByRole('heading',{name:'What is changing in your business?'});expect(fetcher.mock.calls.some(c=>c[0]==='/api/projects/demo')).toBe(true);expect(screen.getAllByText('Sample ERP').length).toBeGreaterThan(0);expect(errors.mock.calls.flat().join(' ')).not.toContain('useEffect must not return');errors.mockRestore();
 });
});

describe('guided design navigation',()=>{
 it('opens the process without replacing existing Designs, chat or source screens',async()=>{
 const {default:Page}=await import('./workspace');Object.defineProperty(HTMLElement.prototype,'scrollIntoView',{configurable:true,value:vi.fn()});
 const project={id:'p',name:'Architecture project',system_type:'new',description:'',objective:'Contain change'};const fetcher=vi.fn(async(url:string)=>{
 let body:unknown=[];if(url==='/api/health')body={ai_configured:false,github_configured:false};if(url==='/api/auth/me')body={id:'u',name:'Alex',email:'alex@example.com',github_connected:false};if(url==='/api/projects')body=[project];if(url.endsWith('/design'))body={use_cases:[],core_use_cases:[],volatilities:[],components:[],validations:[],findings:[],readiness:{use_cases:false,core_use_cases:false,volatility:false,decomposition:false,validation:false}};return new Response(JSON.stringify(body));
 });vi.stubGlobal('fetch',fetcher);render(<Page onSignOut={async()=>{}}/>);await screen.findByRole('button',{name:'Design process'});fireEvent.click(screen.getByRole('button',{name:'Design process'}));await screen.findByRole('heading',{name:'Gather detailed use cases'});expect(fetcher.mock.calls.some(([url])=>url==='/api/projects/p/design')).toBe(true);fireEvent.click(screen.getByRole('button',{name:'Designs'}));expect(await screen.findByRole('heading',{name:'Design options'})).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Files & code'}));expect(await screen.findByRole('heading',{name:'Files & code'})).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Chat'}));expect(await screen.findByRole('heading',{name:'What is changing in your business?'})).toBeTruthy();
 });
});
