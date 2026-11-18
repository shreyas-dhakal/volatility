'use client';
import {createContext,useContext,useEffect,useRef,useState,type ReactNode} from 'react';
import {Drawer} from '@astryxdesign/core/Drawer';
import {Text as SourceText} from '@astryxdesign/core/Text';
import {request} from '../lib/api';
import type {Chunk,Evidence} from '../lib/design-engine';
import {Button,Heading,HStack,Text,VStack} from './ui';
import {useEngine} from './engine-session';

const EvidenceContext=createContext<(citation:Evidence)=>void>(()=>{});
export const label=(key:string)=>key.replace(/_ids?$/,'').replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());

export function DetailValue({value,names=new Map<string,string>()}:{value:unknown;names?:Map<string,string>}){
  if(value==null || value==='')return <Text color="secondary">Unspecified</Text>;
  if(Array.isArray(value)){
    if(!value.length)return <Text color="secondary">None listed</Text>;
    if(value.every(x=>typeof x==='string'))return <Text>{value.map(x=>names.get(x)||x).join(' · ')}</Text>;
    return <VStack gap={3}>{value.map((item,i)=><DetailValue key={i} value={item} names={names}/>)}</VStack>;
  }
  if(typeof value==='object'){
    return <VStack gap={2}>{Object.entries(value).map(([key,item])=><VStack gap={0} key={key}>
      <Text type="supporting" color="secondary">{label(key)}</Text><DetailValue value={item} names={names}/>
    </VStack>)}</VStack>;
  }
  if(typeof value==='boolean')return <Text>{value?'Yes':'No'}</Text>;
  return <Text>{names.get(String(value))||String(value)}</Text>;
}
export function Citations({items}:{items?:Evidence[]}){
  const inspect=useContext(EvidenceContext);
  if(!items?.length)return null;
  return <HStack gap={1} wrap="wrap">{items.map((citation,i)=><Button key={citation.chunk_id+i}
    size="sm" variant="ghost" label={'View source '+(i+1)} onClick={()=>inspect(citation)}/>)}</HStack>;
}
// Citation validation permits normalized whitespace. Recover the original source characters for display.
export function sourceExcerpt(text:string,excerpt:string):string|null{
  const words=excerpt.trim().split(/\s+/);
  if(!words[0])return null;
  const escaped=words.map(word=>Array.from(word,c=>'\\^$.*+?()[]{}|'.includes(c)?'\\'+c:c).join(''));
  return new RegExp(escaped.join('\\s+')).exec(text)?.[0]??null;
}
export function EvidenceInspector({children}:{children:ReactNode}){
  const {path}=useEngine();
  const [citation,setCitation]=useState<Evidence|null>(null),[chunk,setChunk]=useState<Chunk|null>(null);
  const [error,setError]=useState('');
  const ticket=useRef(0);
  useEffect(()=>()=>{ticket.current++},[]);
  async function inspect(item:Evidence){
    const version=++ticket.current;setCitation(item);setChunk(null);setError('');
    try{
      const source=await request<Chunk>(path+'/chunks/'+encodeURIComponent(item.chunk_id));
      if(ticket.current===version)setChunk(source);
    }catch(e){if(ticket.current===version)setError((e as Error).message)}
  }
  const quote=chunk && citation && sourceExcerpt(chunk.text,citation.excerpt);
  const close=()=>{ticket.current++;setCitation(null)};
  return <EvidenceContext.Provider value={inspect}>{children}
    <Drawer label="Source evidence" width="32rem" isOpen={!!citation} onOpenChange={open=>{if(!open)close()}}>
      {citation&&<VStack gap={4}>
        <HStack hAlign="between" vAlign="center"><Heading level={2}>Source evidence</Heading><Button label="Close source" onClick={close}/></HStack>
        {error?<><Text role="alert">{error}</Text><Button label="Retry source" onClick={()=>inspect(citation)}/></>:chunk?
          <><Heading level={3}>Source location</Heading><DetailValue value={chunk.locator}/>
            <Heading level={3}>Cited excerpt</Heading>{quote?<SourceText as="p" style={{whiteSpace:'pre-wrap'}}>{quote}</SourceText>:
              <Text role="alert">The cited passage could not be located in this source.</Text>}
          </>:<Text role="status">Loading source…</Text>}
      </VStack>}
    </Drawer>
  </EvidenceContext.Provider>;
}
