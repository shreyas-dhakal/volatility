// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
vi.mock('@stylexjs/stylex',async original=>({...await original<object>(),create:(styles:Record<string,unknown>)=>Object.fromEntries(Object.keys(styles).map(k=>[k,{}]))}));
const identity=vi.hoisted(()=>({loaded:false,signedIn:false,userId:null as string|null,getToken:vi.fn(async()=>'synthetic-token'),signOut:vi.fn(async()=>{})}));
vi.mock('@clerk/nextjs',()=>({useAuth:()=>({isLoaded:identity.loaded,isSignedIn:identity.signedIn,userId:identity.userId,getToken:identity.getToken}),useClerk:()=>({signOut:identity.signOut}),UserButton:()=>null}));
import ClerkWorkspace from './clerk-workspace';
import {configureTokenGetter} from '../lib/api';
beforeEach(()=>{identity.loaded=false;identity.signedIn=false;identity.userId=null;identity.signOut.mockClear();Object.defineProperty(HTMLElement.prototype,'scrollIntoView',{configurable:true,value:vi.fn()});Object.defineProperty(window,'matchMedia',{configurable:true,value:vi.fn().mockReturnValue({matches:false,addEventListener:vi.fn(),removeEventListener:vi.fn(),addListener:vi.fn(),removeListener:vi.fn()})})});
afterEach(()=>{cleanup();configureTokenGetter(undefined);vi.unstubAllGlobals()});

it('does not load workspace data while Clerk is loading or signed out',()=>{
 const fetcher=vi.fn();vi.stubGlobal('fetch',fetcher);const {rerender}=render(<ClerkWorkspace/>);
 expect(screen.getByText('Checking your session…')).toBeTruthy();expect(fetcher).not.toHaveBeenCalled();
 identity.loaded=true;rerender(<ClerkWorkspace/>);expect(screen.getByRole('link',{name:'Sign in'})).toBeTruthy();expect(screen.getByRole('link',{name:'Create account'})).toBeTruthy();expect(fetcher).not.toHaveBeenCalled();
});

it('loads the local profile using a Clerk token and signs out through Clerk',async()=>{
 identity.loaded=true;identity.signedIn=true;identity.userId='user_a';
 const fetcher=vi.fn(async(url:string)=>new Response(JSON.stringify(url==='/api/auth/me'?{id:'local-a',name:'Alex',email:'a@example.com',github_connected:false}:url==='/api/health'?{ai_configured:false,github_configured:false}:[])));vi.stubGlobal('fetch',fetcher);
 render(<ClerkWorkspace/>);await screen.findByText('Alex');
 const me=fetcher.mock.calls.find(c=>c[0]==='/api/auth/me');expect((me as unknown as [string,RequestInit])[1].headers).toMatchObject({Authorization:'Bearer synthetic-token'});
 fireEvent.click(screen.getByRole('button',{name:'Settings'}));fireEvent.click(screen.getByRole('button',{name:'Sign out'}));
 await vi.waitFor(()=>expect(identity.signOut).toHaveBeenCalledWith({redirectUrl:'/sign-in'}));
});

it('removes the previous workspace immediately when the Clerk account changes',async()=>{
 identity.loaded=true;identity.signedIn=true;identity.userId='user_a';
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>new Response(JSON.stringify(url==='/api/auth/me'?{id:'a',name:'Previous Owner',email:'a@example.com',github_connected:false}:url==='/api/health'?{}:[]))));
 const {rerender}=render(<ClerkWorkspace/>);await screen.findByText('Previous Owner');
 identity.userId='user_b';vi.stubGlobal('fetch',vi.fn(()=>new Promise(()=>{})));rerender(<ClerkWorkspace/>);
 expect(screen.queryByText('Previous Owner')).toBe(null);expect(screen.getByText(/session|workspace/)).toBeTruthy();
});
