'use client';
import {Activity,useEffect,useId,useRef,useState} from 'react';
import {Drawer} from '@astryxdesign/core/Drawer';
import {Tab,TabList} from '@astryxdesign/core/TabList';
import {BookOpen,Layers,Upload} from 'lucide-react';
import {activeRun} from '../lib/design-engine';
import {request} from '../lib/api';
import type {Document,Job} from '../lib/types';
import {Button,FileInput,Heading,HStack,Text,VStack} from './ui';
import {AppIcon} from './workspace-ui';
import {useEngine} from './engine-session';
import {answeredDecision} from './engine-volatility';
import {RevisionPanel} from './engine-revision';
import {EvidenceInspector,label} from './engine-evidence';
import {ProjectPlan} from './engine-plan';

const count=(amount:number,noun:string)=>amount+' '+noun+(amount===1?'':'s');
const tabs=['Overview','Volatility','Architecture','Validation','Project'];
export function ApplyCorrection({messageId}:{messageId:string}){
  const {state,start,busy,loadError}=useEngine();
  const revision=state?.revision;
  if(!revision||messageId.startsWith('local-'))return null;
  return <Button size="sm" variant="ghost" label="Apply as correction" isDisabled={busy||!!loadError||activeRun(state.run)}
    onClick={()=>start('revise',{base_revision_id:revision.id,correction_message_id:messageId})}/>;
}

export function EngineChat({objective,base,documents,jobs,refresh,openSources,messageId,existing=false}:{
  objective:string;base:string;documents:Document[];jobs:Job[];refresh:()=>Promise<void>;openSources:()=>void;messageId?:string;existing?:boolean;
}){
  const engine=useEngine();
  const {state,error,busy,loadError}=engine;
  const revision=state?.revision,run=state?.run;
  const plan=state?.plan?.revision_id===revision?.id?state?.plan:null;
  const [open,setOpen]=useState(false),[tab,setTab]=useState('Overview'),[files,setFiles]=useState(false);
  const [selected,setSelected]=useState<string[]>([]),[file,setFile]=useState<File|null>(null);
  const [uploading,setUploading]=useState(false),[uploadError,setUploadError]=useState(''),[notice,setNotice]=useState('');
  const unique=useId();
  const isActive=activeRun(run??null);
  const lastRevision=useRef<string|null>(null);
  useEffect(()=>{
    if(!revision)return;
    if(lastRevision.current && lastRevision.current===revision.parent_revision_id && answeredDecision(revision)){
      setTab('Volatility');setOpen(true);
    }
    lastRevision.current=revision.id;
  },[revision]);
  const unavailable=!state||busy||isActive||!!loadError;
  const ingesting=jobs.some(j=>['pending','queued','running','processing'].includes(j.status)&&j.kind==='document');
  const uploadFailed=jobs.find(j=>j.kind==='document'&&j.status==='failed');
  const failed=run&&['failed','stale','conflict'].includes(run.status);
  async function upload(){
    if(!file||uploading)return;
    setUploading(true);setUploadError('');setNotice('');
    try{
      const form=new FormData();form.append('file',file);
      await request(base+'/documents',{method:'POST',body:form});
      setNotice('Uploaded '+file.name);setFile(null);await refresh();
    }catch(e){setUploadError((e as Error).message)}finally{setUploading(false)}
  }
  function openPlan(){
    if(!revision)return;
    setTab('Project');setOpen(true);
    if(!plan)void engine.plan(revision.id,{});
  }
  return <VStack gap={2} paddingBlock={2}>
    {revision&&<VStack gap={0}><Text weight="semibold">System design</Text>
      {typeof revision.snapshot.use_cases[0]?.outcome==='string'&&<Text maxLines={2}>{revision.snapshot.use_cases[0].outcome}</Text>}
      <Text type="supporting" color="secondary">{count(revision.snapshot.use_cases.length,'use case')} · {count(revision.snapshot.volatilities.length,'decision')} · {count(revision.snapshot.components.length,'proposed component')}</Text>
    </VStack>}
    {run&&isActive&&<Text role="status">Design {run.status} · {label(run.stage)}</Text>}
    {failed&&<VStack gap={1}><Text role="alert">Design run {run.status} · {run.error||'The revision could not be published.'}</Text>
      {revision&&<Text type="supporting">Showing the current saved revision.</Text>}
      <Button label={run.status==='failed'?'Retry design run':'Rerun on current revision'} size="sm" isDisabled={unavailable} onClick={()=>engine.retry(run)}/>

    </VStack>}
    {error&&<Text role="alert">{error}</Text>}
    {loadError&&<HStack gap={2} wrap="wrap"><Text role="alert">{loadError}</Text><Button size="sm" label="Reload design" onClick={engine.load}/></HStack>}
    <HStack gap={1} wrap="wrap" vAlign="center">
      <Button label="Design system" size="sm" icon={<AppIcon icon={Layers}/>} isDisabled={unavailable||uploading||ingesting}
        onClick={()=>engine.start('analyze',{...(selected.length?{selected_upload_ids:selected}:{}),...(messageId?{request_message_id:messageId}:{})})}/>
      {revision&&<><Button label="View design" size="sm" icon={<AppIcon icon={BookOpen}/>} onClick={()=>{setTab(answeredDecision(revision)?'Volatility':'Overview');setOpen(true)}}/>
        <Button label="Plan project" size="sm" isDisabled={unavailable} onClick={openPlan}/></>}
      <Button label={selected.length?'Design files ('+selected.length+')':'Add files'} size="sm" variant="ghost" icon={<AppIcon icon={Upload} color="secondary"/>} onClick={()=>setFiles(true)}/>
    </HStack>
    <Drawer label="Design files" width="32rem" isOpen={files} onOpenChange={setFiles}>
      {files&&<VStack gap={4}><HStack hAlign="between" vAlign="center"><Heading level={2}>Design files</Heading><Button label="Done" onClick={()=>setFiles(false)}/></HStack>
        <FileInput label="Choose a design file" value={file} onChange={f=>{setFile(Array.isArray(f)?f[0]??null:f);setNotice('')}}/>
        <Button label="Upload to project" isDisabled={!file} isLoading={uploading} onClick={upload}/>
        {uploadError&&<Text role="alert">{uploadError}</Text>}{notice&&<Text role="status">{notice}</Text>}
        {ingesting&&<Text role="status">Extracting uploaded material…</Text>}
        {uploadFailed&&<Text role="alert">{uploadFailed.error||'An uploaded file could not be read.'}</Text>}
        {!!documents.length&&<VStack gap={2}><Heading level={3}>Files for analysis</Heading>
          <Text type="supporting">Analyze all project material, or select individual files.</Text>
          <Button size="sm" label="All project material" aria-pressed={!selected.length} variant={selected.length?'ghost':'secondary'} onClick={()=>setSelected([])}/>
          {documents.map(doc=><Button key={doc.id} size="sm" label={doc.name} aria-pressed={selected.includes(doc.id)} variant={selected.includes(doc.id)?'secondary':'ghost'} onClick={()=>setSelected(prev=>prev.includes(doc.id)?prev.filter(k=>k!==doc.id):[...prev,doc.id])}/>)}
        </VStack>}
        <Button label="Manage files and repositories" variant="ghost" onClick={openSources}/>
      </VStack>}
    </Drawer>
    <Drawer label="System design" isOpen={open} onOpenChange={setOpen} width="52rem">
      {open&&revision&&<EvidenceInspector><VStack gap={4}>
        <HStack hAlign="between" vAlign="center"><VStack gap={0}><Heading level={2}>System design</Heading><Text type="supporting" color="secondary">Saved revision {revision.id}</Text></VStack><Button label="Close design" onClick={()=>setOpen(false)}/></HStack>
        <TabList value={tab} onChange={setTab} role="tablist" aria-label="Design sections" size="sm" hasDivider>
          {tabs.map(name=><Tab key={name} value={name} label={name} panelId={unique+name}/>)}
        </TabList>
        {tab!=='Project'&&<VStack id={unique+tab} role="tabpanel" aria-label={tab}><RevisionPanel revision={revision} tab={tab} objective={objective} existing={existing}/></VStack>}
        <Activity mode={tab==='Project'?'visible':'hidden'}><VStack id={unique+'Project'} role="tabpanel" aria-label="Project">
          {error&&<Text role="alert">{error}</Text>}
          <ProjectPlan key={revision.id+(plan?.id??'')} revisionId={revision.id} plan={plan??null}/>
        </VStack></Activity>
      </VStack></EvidenceInspector>}
    </Drawer>
  </VStack>;
}
