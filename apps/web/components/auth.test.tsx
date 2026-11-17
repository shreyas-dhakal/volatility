// @vitest-environment jsdom
import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
vi.mock('@stylexjs/stylex',async original=>({...await original<object>(),create:(styles:Record<string,unknown>)=>Object.fromEntries(Object.keys(styles).map(k=>[k,{}]))}));
import {Auth,ErrorNotice} from './workspace';
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
describe('account entry',()=>{
 it('submits credentials and passes the persisted account to the workspace',async()=>{
 const account={id:'u',email:'a@example.com',name:'Alex',github_connected:false};const fetcher=vi.fn().mockResolvedValue(new Response(JSON.stringify(account)));vi.stubGlobal('fetch',fetcher);const success=vi.fn();render(<Auth busy={false} onSuccess={success} run={async fn=>{await fn()}}/>);fireEvent.change(screen.getByLabelText(/^Email/),{target:{value:'a@example.com'}});fireEvent.change(screen.getByLabelText(/^Password/),{target:{value:'strong-password'}});fireEvent.click(screen.getByRole('button',{name:'Sign in'}));await waitFor(()=>expect(success).toHaveBeenCalledWith(account));expect(JSON.parse(fetcher.mock.calls[0][1].body)).toMatchObject({email:'a@example.com',password:'strong-password'});expect(fetcher.mock.calls[0][0]).toBe('/api/auth/login');
 });
 it('makes registration and its name field available',()=>{render(<Auth busy={false} onSuccess={async()=>{}} run={async fn=>{await fn()}}/>);fireEvent.click(screen.getByRole('button',{name:'New here? Create an account'}));expect(screen.getByLabelText(/^Name/)).toBeTruthy();expect(screen.getByRole('button',{name:'Create account'})).toBeTruthy()});
 it('announces actionable errors',()=>{render(<ErrorNotice message="Set OPENAI_API_KEY on the API server."/>);expect(screen.getByRole('alert').textContent).toContain('Set OPENAI_API_KEY')});
});
describe('explicit sample workspace',()=>{
 it('loads a sample only after user action and supports Promise-returning browser scroll',async()=>{
 const {default:Page}=await import('./workspace');
 Object.defineProperty(HTMLElement.prototype,'scrollIntoView',{configurable:true,value:vi.fn().mockResolvedValue(undefined)});
 Object.defineProperty(window,'matchMedia',{configurable:true,value:vi.fn().mockReturnValue({matches:false,addEventListener:vi.fn(),removeEventListener:vi.fn(),addListener:vi.fn(),removeListener:vi.fn()})});
 const user={id:'u',email:'a@example.com',name:'Alex',github_connected:false};let seeded=false;const project={id:'demo',name:'Sample ERP',system_type:'existing',description:'Synthetic project',objective:'Demonstrate architecture'};
 const fetcher=vi.fn(async(url:string)=>{let body:unknown=[];if(url==='/api/health')body={ai_configured:false,github_configured:false};if(url==='/api/auth/me')body=user;if(url==='/api/projects')body=seeded?[project]:[];if(url==='/api/projects/demo'){seeded=true;body=project}return new Response(JSON.stringify(body))});vi.stubGlobal('fetch',fetcher);
 const errors=vi.spyOn(console,'error');render(<Page/>);await screen.findByRole('button',{name:'Explore sample project'});expect(seeded).toBe(false);fireEvent.click(screen.getByRole('button',{name:'Explore sample project'}));await screen.findByRole('heading',{name:'What is changing in your business?'});expect(fetcher.mock.calls.some(c=>c[0]==='/api/projects/demo')).toBe(true);expect(screen.getAllByText('Sample ERP').length).toBeGreaterThan(0);expect(errors.mock.calls.flat().join(' ')).not.toContain('useEffect must not return');errors.mockRestore();
 });
});
