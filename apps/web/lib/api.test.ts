import {afterEach,describe,expect,it,vi} from 'vitest';
import {ApiError,consumeSSE,request,chat} from './api';
afterEach(()=>vi.unstubAllGlobals());
describe('authenticated API requests',()=>{
 it('requires bearer authentication and accepts successful JSON',async()=>{const fetcher=vi.fn().mockResolvedValue(new Response('{"id":"p1"}'));vi.stubGlobal('fetch',fetcher);expect(await request('/projects')).toEqual({id:'p1'});expect(fetcher.mock.calls[0][1].credentials).toBe('omit')});
 it('preserves actionable server errors and stale review status',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{"detail":"Record changed. Refresh before reviewing."}',{status:409})));await expect(request('/record')).rejects.toMatchObject({status:409,message:'Record changed. Refresh before reviewing.'})});
 it('makes offline failures actionable',async()=>{vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new TypeError('network')));await expect(request('/projects')).rejects.toThrow('Check that the API is running')});
 it('does not set a JSON header on multipart uploads',async()=>{const fetcher=vi.fn().mockResolvedValue(new Response('{}'));vi.stubGlobal('fetch',fetcher);await request('/documents',{method:'POST',body:new FormData()});expect(fetcher.mock.calls[0][1].headers).toEqual({Authorization:'Bearer isolated-test-token'})});
});
describe('streamed conversations',()=>{
 it('decodes split UTF-8, CRLF and several event frames',async()=>{const bytes=new TextEncoder().encode('event: delta\r\ndata: {"text":"héllo"}\r\n\r\nevent: done\ndata: {"message_id":"m1"}\n\n');const stream=new ReadableStream<Uint8Array>({start(c){for(let i=0;i<bytes.length;i++)c.enqueue(bytes.slice(i,i+1));c.close()}});const result:unknown[]=[];await consumeSSE(stream,e=>result.push(e));expect(result).toEqual([{event:'delta',data:{text:'héllo'}},{event:'done',data:{message_id:'m1'}}])});
 it('surfaces missing credentials before reading a stream',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{"detail":"Set OPENAI_API_KEY"}',{status:503})));await expect(chat('/chat','hello',()=>{})).rejects.toMatchObject({status:503,message:'Set OPENAI_API_KEY'})});
 it('releases readers when a stream contains malformed data',async()=>{const stream=new ReadableStream<Uint8Array>({start(c){c.enqueue(new TextEncoder().encode('data: bad\n\n'));c.close()}});await expect(consumeSSE(stream,()=>{})).rejects.toThrow();expect(stream.locked).toBe(false)});
});
describe('validation feedback',()=>{
 it('names invalid inputs instead of hiding validation details',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{"detail":[{"loc":["body","name"],"msg":"At least 10 characters"}]}',{status:422})));await expect(request('/projects')).rejects.toThrow('name: At least 10 characters')});
 it('gives actionable offline errors for chat too',async()=>{vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new TypeError('network')));await expect(chat('/chat','hello',()=>{})).rejects.toThrow('Check that the API is running')});
});

describe('Clerk bearer transport',()=>{
 it('gets a token per JSON and multipart request without changing the multipart boundary',async()=>{
  const {configureTokenGetter}=await import('./api');let generation=0;configureTokenGetter(async()=>`token-${++generation}`);
  const fetcher=vi.fn().mockImplementation(async()=>new Response('{}'));vi.stubGlobal('fetch',fetcher);
  try {await request('/projects');await request('/documents',{method:'POST',body:new FormData()});
   expect(fetcher.mock.calls[0][1].headers.Authorization).toBe('Bearer token-1');
   expect(fetcher.mock.calls[1][1].headers).toEqual({Authorization:'Bearer token-2'});
  } finally {configureTokenGetter(undefined)}
 });
 it('authenticates streamed chat with the same bearer contract',async()=>{
  const {configureTokenGetter}=await import('./api');configureTokenGetter(async()=>'stream-token');
  const fetcher=vi.fn().mockResolvedValue(new Response('event: done\ndata: {}\n\n'));vi.stubGlobal('fetch',fetcher);
  try {await chat('/chat','hi',()=>{});expect(fetcher.mock.calls[0][1].headers.Authorization).toBe('Bearer stream-token')}finally{configureTokenGetter(undefined)}
 });
 it('rejects missing Clerk sessions before sending any request',async()=>{
  const {configureTokenGetter}=await import('./api');configureTokenGetter(async()=>null);const fetcher=vi.fn();vi.stubGlobal('fetch',fetcher);
  try {await expect(request('/projects')).rejects.toMatchObject({status:401});await expect(chat('/chat','hi',()=>{})).rejects.toMatchObject({status:401});expect(fetcher).not.toHaveBeenCalled()}finally{configureTokenGetter(undefined)}
 });
});

it('does not send an old request after the account token provider changes',async()=>{
 const {configureTokenGetter}=await import('./api');let release!:(token:string)=>void;
 configureTokenGetter(()=>new Promise(resolve=>{release=resolve}));const fetcher=vi.fn();vi.stubGlobal('fetch',fetcher);
 const pending=request('/projects');configureTokenGetter(async()=>'new-session');release('old-session');
 try{await expect(pending).rejects.toMatchObject({status:401});expect(fetcher).not.toHaveBeenCalled()}finally{configureTokenGetter(undefined)}
});
