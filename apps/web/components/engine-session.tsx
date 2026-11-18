'use client';
import {createContext,useCallback,useContext,useEffect,useRef,useState,type ReactNode} from 'react';
import {ApiError,post,request} from '../lib/api';
import {activeRun,type EngineState,type Inputs,type Plan,type Run} from '../lib/design-engine';

function useProjectEngine(base:string,streaming:boolean){
  const path = base+'/design-engine';
  const [state,setState]=useState<EngineState|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [loadError,setLoadError]=useState('');
  const sequence=useRef(0), locked=useRef(false);
  const pendingKey=useRef<{intent:string;key:string}|null>(null);

  const load=useCallback(async()=>{
    const version=++sequence.current;
    try {
      const current=await request<EngineState>(path);
      if(version===sequence.current){setState(current);setLoadError('')}
    }catch(e){if(version===sequence.current)setLoadError((e as Error).message)}
  },[path]);
  useEffect(()=>{
    if(!streaming)void load();
    return ()=>{sequence.current++};
  },[load,streaming]);
  const polling=activeRun(state?.run??null);
  useEffect(()=>{
    if(!polling)return;
    let stopped=false;
    let timer:ReturnType<typeof setTimeout>;
    const tick=async()=>{await load();if(!stopped)timer=setTimeout(tick,1400)};
    timer=setTimeout(tick,900);
    return ()=>{stopped=true;clearTimeout(timer)};
  },[polling,load]);

  async function mutate(action:()=>Promise<void>){
    if(locked.current)return;
    locked.current=true;setBusy(true);setError('');
    try{await action()}
    catch(e){
      if(e instanceof ApiError && e.status===409){
        await load();setError(e.message+' Review the current revision before trying again.');
      }else setError((e as Error).message);
    }finally{setBusy(false);locked.current=false}
  }
  async function start(operation:'analyze'|'revise',params:Record<string,unknown>){
    await mutate(async()=>{
      const intent=JSON.stringify([operation,params]);
      if(pendingKey.current?.intent!==intent)pendingKey.current={intent,key:crypto.randomUUID()};
      const run=await post<Run>(path+'/'+operation,{...params,idempotency_key:pendingKey.current.key});
      pendingKey.current=null;
      setState(prev=>prev && {...prev,run});
      await load();
    });
  }
  async function retry(run:Run){
    await mutate(async()=>{
      const next=await post<Run>(path+'/runs/'+encodeURIComponent(run.id)+'/retry');
      setState(prev=>prev && {...prev,run:next});await load();
    });
  }
  async function plan(revisionId:string,inputs:Inputs){
    await mutate(async()=>{
      const result=await post<Plan>(path+'/plan',{revision_id:revisionId,planning_inputs:inputs});
      setState(prev=>prev && {...prev,plan:result});
    });
  }
  return {path,state,error,loadError,busy:busy||streaming,load,start,retry,plan};
}
const EngineContext=createContext<ReturnType<typeof useProjectEngine>|null>(null);
export function EngineSession({base,streaming,children}:{base:string;streaming:boolean;children:ReactNode}){
  const engine=useProjectEngine(base,streaming);
  return <EngineContext.Provider value={engine}>{children}</EngineContext.Provider>;
}
export function useEngine(){
  const engine=useContext(EngineContext);
  if(!engine)throw new Error('Design engine requires a project session');
  return engine;
}
