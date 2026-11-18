export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }
type TokenGetter = () => Promise<string | null>;
let tokenGetter: TokenGetter | undefined;
export function configureTokenGetter(getter: TokenGetter | undefined) { tokenGetter = getter; }
async function authorizationHeaders(): Promise<Record<string,string>> {
  const getter = tokenGetter;
  if (!getter) return {};
  const token = await getter();
  if (!token || getter !== tokenGetter) throw new ApiError(401, 'Sign in required');
  return { Authorization: `Bearer ${token}` };
}
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const authorization = tokenGetter ? await authorizationHeaders() : {};
  let response: Response;
  try { response = await fetch(`/api${path}`, { credentials: 'same-origin', ...init, headers: { ...(init.body instanceof FormData ? {} : {'Content-Type':'application/json'}), ...Object.fromEntries(new Headers(init.headers)), ...authorization } }); }
  catch { throw new ApiError(0, 'Cannot reach the server. Check that the API is running, then try again.'); }
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new ApiError(response.status, typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map((e: {loc?: string[];msg?: string}) => `${e.loc?.slice(1).join('.') || 'Input'}: ${e.msg || 'Invalid value'}`).join('; ') : `Request failed (${response.status}). Please try again.`); }
  return response.status === 204 ? undefined as T : response.json();
}
export const post = <T>(path: string, body: unknown = {}) => request<T>(path, {method:'POST', body:JSON.stringify(body)});
export type StreamEvent = {event: string; data: Record<string, unknown>};
export async function consumeSSE(body: ReadableStream<Uint8Array>, receive: (event: StreamEvent) => void) {
  const reader = body.getReader(); const decoder = new TextDecoder(); let buffer = '';
  function parse(frame: string) { let event = 'message'; const data: string[] = []; for (const line of frame.split('\n')) { if (line.startsWith('event:')) event = line.slice(6).trim(); if (line.startsWith('data:')) data.push(line.slice(5).trimStart()); } if (data.length) receive({event, data:JSON.parse(data.join('\n'))}); }
  try { while (true) { const {value,done} = await reader.read(); buffer += decoder.decode(value, {stream:!done}); buffer=buffer.replace(/\r\n/g,'\n'); let end; while ((end=buffer.indexOf('\n\n'))>=0) { parse(buffer.slice(0,end)); buffer=buffer.slice(end+2); } if (done) { if (buffer.trim()) parse(buffer); break; } } } finally { reader.releaseLock(); }
}
export async function chat(path: string, content: string, receive: (event: StreamEvent) => void, signal?: AbortSignal) {
 const authorization = tokenGetter ? await authorizationHeaders() : {};
 let r: Response; try { r = await fetch(`/api${path}`, {method:'POST', credentials:'same-origin',headers:{'Content-Type':'application/json',...authorization},body:JSON.stringify({content}),signal}); } catch(e) { if ((e as Error).name === 'AbortError') throw e; throw new ApiError(0, 'Cannot reach the server. Check that the API is running, then try again.'); }
 if (!r.ok) { const data=await r.json().catch(()=>({})); throw new ApiError(r.status,data.detail || 'Conversation failed. Please try again.'); } if(!r.body) throw new Error('Streaming unavailable'); await consumeSSE(r.body,receive);
}
