'use client';
import {displayText} from '../lib/text';
import {useEffect,useRef,useState, type ReactNode} from 'react';
import * as stylex from '@stylexjs/stylex';
import {ChatComposer,ChatMessage,ChatMessageBubble} from '@astryxdesign/core/Chat';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {Drawer} from '@astryxdesign/core/Drawer';
import {Theme} from '@astryxdesign/core/theme';
import {themes,defaultThemeSlug} from '../../../astryx-themes';
import {VStack,HStack,Button,Text,Heading,TextInput,TextArea,Selector,FileInput,Markdown} from './ui';
import {request,post,chat,ApiError} from '../lib/api';
import type {User,Project,Conversation,Message,Knowledge,Source,Job,Document,GraphSummary} from '../lib/types';
import {DesignWorkspace} from './design-workspace';
import {EngineSession} from './engine-session';
import {ApplyCorrection,EngineChat} from './engine-chat';
import {Brand} from './brand';
import {GraphWorkspace} from './graph';
import {AppIcon,NavigationItem,GitHubAction,ReviewState,evidenceLabel,fieldLabel,plainValue,navigation,toolActivity,type WorkspaceView} from './workspace-ui';
import {Plus,MessageSquare,SquarePen,RefreshCw,Menu,PanelLeftClose,BookOpen,FileText,Upload,GitBranch,LogOut,Check,X,Pencil,History,Search,ArrowRight,Info,TriangleAlert,Layers,Network,ClipboardCheck,Settings} from 'lucide-react';
const s=stylex.create({
 shell:{height:'100dvh',overflow:'hidden',backgroundColor:'var(--color-background-surface)'},
 frame:{flexGrow:1,minHeight:0,alignItems:'stretch'},
 rail:{width:'16rem',flexShrink:0,borderInlineEnd:'var(--border-width) solid var(--color-border)',backgroundColor:'var(--color-background-body)',display:{default:'flex','@media (max-width: 48rem)':'none'}},
 railBody:{minHeight:0,height:'100%'},
 railScroll:{flexGrow:1,minHeight:0,overflowY:'auto'},
 railFooter:{borderTop:'var(--border-width) solid var(--color-border)',flexShrink:0},
 railTop:{flexShrink:0},
 history:{maxHeight:'min(16rem, 30dvh)',overflowY:'auto'},
 sectionHeading:{fontFamily:'var(--font-family-code)',paddingInline:'var(--spacing-3)'},
 main:{flexGrow:1,minWidth:0,minHeight:0},
 header:{borderBottom:'var(--border-width) solid var(--color-border)',flexShrink:0,minHeight:'4rem'},
 content:{flexGrow:1,minHeight:0,overflowY:'auto'},
 measure:{width:'100%',maxWidth:'48rem',marginInline:'auto'},
 pageMeasure:{width:'100%',maxWidth:'72rem',marginInline:'auto'},
 center:{minHeight:'100dvh',backgroundColor:'var(--color-background-surface)'},
 auth:{width:'100%',maxWidth:'29rem'},
 composer:{flexShrink:0},
 chatLanding:{width:'100%',maxWidth:'48rem',marginInline:'auto',marginBlock:'auto'},
 chatTitle:{fontSize:'var(--font-size-3xl)',textAlign:'center',textWrap:'balance'},
 chatIntro:{textAlign:'center'},
 chatContent:{flexGrow:1,minHeight:0,overflowY:'auto',overscrollBehaviorY:'contain'},
 messageContent:{minWidth:0,overflowWrap:'anywhere'},
 row:{borderBottom:'var(--border-width) solid var(--color-border)'},
 empty:{flexGrow:1,minHeight:0,overflowY:'auto'},
 error:{border:'var(--border-width) solid var(--color-border)',borderRadius:'var(--radius-container)',backgroundColor:'var(--color-background-surface)'},
 tool:{fontSize:'var(--font-size-sm)',color:'var(--color-text-secondary)'},
 grow:{flexGrow:1},
 helper:{flexGrow:1,minWidth:0,whiteSpace:'normal'},
 action:{flexShrink:0},
 identity:{flexGrow:1,minWidth:0},
 mobileOnly:{display:{default:'none','@media (max-width: 48rem)':'flex'},flexShrink:0},
 navAction:{justifyContent:'flex-start'},
 headerActions:{flexShrink:0},
 notesLabel:{display:{default:'inline','@media (max-width: 40rem)':'none'}},
});
type View=WorkspaceView;
type GitHubRepo={full_name:string;project_id:string;private:boolean};
const views:View[]=['Chat','Sources','Decisions','Volatility','Questions','Design process','Designs','Graph'];
const human=(v:string)=>v.replaceAll('_',' ');
type AuthWiring={onSignOut:()=>Promise<void>;accountControl:ReactNode};
export default function Page(props:AuthWiring){return <Theme theme={themes[defaultThemeSlug]} mode="light"><Workspace {...props}/></Theme>}
function Workspace({onSignOut,accountControl}:AuthWiring){
 const [user,setUser]=useState<User|null>(null),[ready,setReady]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [health,setHealth]=useState<{ai_configured:boolean;github_configured:boolean}|null>(null);
 const [projects,setProjects]=useState<Project[]>([]),[projectId,setProjectId]=useState(''),[conversations,setConversations]=useState<Conversation[]>([]),[conversationId,setConversationId]=useState<string|null>(null);
 const [githubRepos,setGithubRepos]=useState<GitHubRepo[]>([]);
 const [repoLoadAttempt,setRepoLoadAttempt]=useState(0);
 const [repoLoadError,setRepoLoadError]=useState('');
 useEffect(()=>{
  if(!user?.github_connected)return;
  let active=true;
  setRepoLoadError('');
  request<typeof githubRepos>('/auth/github/repos').then(repos=>{
   if(active)setGithubRepos(repos);
  }).catch(e=>{if(active)setRepoLoadError(e.message||'Could not load GitHub repositories.')});
  return ()=>{active=false};
 },[user?.id,user?.github_connected,repoLoadAttempt]);
 const [messages,setMessages]=useState<Message[]>([]),[records,setRecords]=useState<Knowledge[]>([]),[sources,setSources]=useState<Source[]>([]),[jobs,setJobs]=useState<Job[]>([]),[documents,setDocuments]=useState<Document[]>([]),[graphs,setGraphs]=useState<GraphSummary[]>([]);
 const [view,setView]=useState<View>('Chat'),[showNav,setShowNav]=useState(false),[newProject,setNewProject]=useState(false),[draft,setDraft]=useState(''),[streaming,setStreaming]=useState(false),[stream,setStream]=useState(''),[tool,setTool]=useState('');
 const [designRefresh,setDesignRefresh]=useState(0);
 const controller=useRef<AbortController|null>(null),end=useRef<HTMLDivElement|null>(null),createdConversation=useRef<string|null>(null); const project=projects.find(p=>p.id===projectId); const base=`/projects/${projectId}`;
 async function run(action:()=>Promise<unknown>){setError('');setBusy(true);try{await action()}catch(e){setError(e instanceof Error?e.message:'Something went wrong. Please retry.')}finally{setBusy(false)}}
 async function loadProjects(){const p=await request<Project[]>('/projects');setProjects(p);setProjectId(prev=>p.some(x=>x.id===prev)?prev:p[0]?.id||'')}
 async function refresh(){if(!projectId)return;const [r,so,j,d,g,c]=await Promise.all([request<Knowledge[]>(`${base}/records`),request<Source[]>(`${base}/sources`),request<Job[]>(`${base}/jobs`),request<Document[]>(`${base}/documents`),request<GraphSummary[]>(`${base}/graphs`),request<Conversation[]>(`${base}/conversations`)]);setRecords(r);setSources(so);setJobs(j);setDocuments(d);setGraphs(g);setConversations(c);setConversationId(prev=>prev===''||c.some(x=>x.id===prev)?prev:c[0]?.id||'')}
 useEffect(()=>{request<typeof health>('/health').then(setHealth).catch(()=>{});request<User>('/auth/me').then(async u=>{setUser(u);await loadProjects()}).catch(e=>{if(!(e instanceof ApiError&&e.status===401))setError(e.message)}).finally(()=>setReady(true));return()=>controller.current?.abort()},[]);
 useEffect(()=>{setMessages([]);setConversationId(null);setConversations([]);setDraft('');setRecords([]);if(projectId)run(refresh)},[projectId]);
 useEffect(()=>{
  if(!projectId||!conversationId)return;
  if(createdConversation.current===conversationId){createdConversation.current=null;return}
  let current=true;
  run(async()=>{
   const history=await request<Message[]>(`${base}/conversations/${conversationId}/messages`);
   if(current)setMessages(history);
  });
  return()=>{current=false};
 },[projectId,conversationId]);
 useEffect(()=>{if(!jobs.some(j=>['pending','queued','running','processing'].includes(j.status)))return;const timer=setInterval(()=>refresh().catch(()=>{}),2500);return()=>clearInterval(timer)},[jobs,projectId]);
 useEffect(()=>{end.current?.scrollIntoView({behavior:'smooth'});},[stream,messages]);
 async function send(value:string){
  const content=value.trim();
  if(!content||streaming||!project||!health?.ai_configured)return;

  setError('');
  setStreaming(true);
  setStream('');
  setTool('');
  const abortController=new AbortController();
  controller.current=abortController;
  let id=conversationId;

  try{
   if(!id){
    const conversation=await post<Conversation>(`${base}/conversations`,{title:content.slice(0,65)});
    id=conversation.id;
    createdConversation.current=id;
    setConversations(previous=>[conversation,...previous]);
    setConversationId(id);
   }
   setMessages(previous=>[...previous,{id:`local-${Date.now()}`,role:'user',content}]);
   setDraft('');

   let failure='';
   await chat(`${base}/conversations/${id}/chat`,content,event=>{
    if(event.event==='delta')setStream(previous=>previous+String(event.data.text||''));
    if(event.event==='tool')setTool(toolActivity(String(event.data.name),String(event.data.status),event.data.result));
    if(event.event==='error')failure=String(event.data.message);
   },abortController.signal);
   const history=await request<Message[]>(`${base}/conversations/${id}/messages`);
   await refresh();
   setMessages(history);
   if(failure)setError(failure);
  }catch(error){
   if((error as Error).name!=='AbortError')setError((error as Error).message);
   if(id)setMessages(await request<Message[]>(`${base}/conversations/${id}/messages`).catch(()=>messages));
  }finally{
   controller.current=null;
   setStreaming(false);
   setStream('');
   setTool('');
  }
 }
 async function patch(record:Knowledge,change:Record<string,unknown>){await request(`${base}/records/${record.id}`,{method:'PATCH',body:JSON.stringify({...change,expected_version:record.version})});await refresh()}
 const choose=(v:View)=>{setView(v);setNewProject(false);setShowNav(false)};
 if(!ready)return <VStack padding={10}><Text>Opening your workspace…</Text></VStack>;
 if(!user)return <VStack padding={6} gap={4}><Heading level={1}>Your account needs attention</Heading><Text role="alert">{error||'Your profile could not be opened. Sign in again or request account recovery.'}</Text><Button label="Try again" onClick={()=>location.reload()}/><Button label="Sign out" onClick={()=>void onSignOut()}/></VStack>;
 const isChat=Boolean(project)&&view==='Chat'&&!newProject;
 const emptyChat=conversationId===''&&!messages.length&&!streaming;
 const currentConversation=conversations.find(conversation=>conversation.id===conversationId);
 const projectIds=new Set(projects.map(p=>p.id));
 const repoOptions=githubRepos.filter(repo=>!projectIds.has(repo.project_id)).map(repo=>({
  value:'github:'+repo.full_name,label:repo.full_name,description:repo.private?'Private':undefined,
 }));
 const sidebar=(mobile=false)=><VStack as="nav" aria-label="Workspace navigation" xstyle={s.railBody} gap={0}>
  <VStack xstyle={s.railTop} padding={4} gap={5}>
   <HStack hAlign="between" vAlign="center">
    <Brand/>
    {mobile&&<Button label="Close navigation" isIconOnly icon={<AppIcon icon={PanelLeftClose} color="secondary"/>} variant="ghost" onClick={()=>setShowNav(false)}/>}
   </HStack>
   <HStack gap={1} vAlign="end">
    <VStack xstyle={s.identity}>
     <Selector label="Project" isDisabled={streaming||busy} value={projectId} onChange={value=>{
      if(!value.startsWith('github:')){setProjectId(value);return}
      void run(async()=>{
       const opened=await post<Project>('/projects/github',{full_name:value.slice(7)});
       await loadProjects();setProjectId(opened.id);choose('Chat');
      });
     }} options={[
      ...projects.map(p=>({value:p.id,label:displayText(p.name)})),
      ...(repoOptions.length?[{type:'section' as const,title:'GitHub',options:repoOptions}]:[]),
     ]} placeholder="Select a project"/>
     {repoLoadError&&<VStack gap={1}><Text role="alert" type="supporting">{repoLoadError}</Text><Button size="sm" variant="ghost" label="Retry repositories" onClick={()=>setRepoLoadAttempt(n=>n+1)}/></VStack>}
    </VStack>
    <Button label="New project" tooltip="New project" isIconOnly icon={<AppIcon icon={Plus} color="secondary"/>} variant="ghost" isDisabled={streaming} onClick={()=>{setNewProject(true);setShowNav(false)}}/>
   </HStack>
   <Button label="New chat" icon={<AppIcon icon={SquarePen} color="inherit"/>} xstyle={s.navAction} isDisabled={streaming||!projectId} onClick={()=>{setConversationId('');setMessages([]);setDraft('');choose('Chat')}}/>
  </VStack>
  <VStack xstyle={s.railScroll} paddingInline={4} paddingBlockEnd={4} gap={5}>
   <VStack gap={1}>
    <Text type="supporting" weight="semibold" color="secondary" xstyle={s.sectionHeading}>Chat history</Text>
    <VStack gap={1} xstyle={s.history}>{conversations.length?conversations.map(c=><Button key={c.id} label={displayText(c.title||'New chat')} icon={<AppIcon icon={MessageSquare} color="secondary"/>} xstyle={s.navAction} size="sm" isDisabled={streaming} variant={isChat&&conversationId===c.id?'secondary':'ghost'} aria-current={isChat&&conversationId===c.id?'page':undefined} onClick={()=>{if(conversationId!==c.id){setMessages([]);setDraft('');setConversationId(c.id)}choose('Chat')}}/>):<Text type="supporting" color="secondary" xstyle={s.sectionHeading}>No conversations yet</Text>}</VStack>
   </VStack>
   {project&&<VStack gap={1}>
    <Text type="supporting" weight="semibold" color="secondary" xstyle={s.sectionHeading}>Project tools</Text>
    {views.map(v=><NavigationItem key={v} view={v} active={!newProject&&view===v&&(v!=='Chat'||!currentConversation)} onClick={()=>choose(v)}/>)}
   </VStack>}
  </VStack>
  <HStack xstyle={s.railFooter} padding={4} gap={2} vAlign="center">
   {accountControl}
   <Text type="label" maxLines={1} xstyle={s.identity}>{user.name}</Text>
   <Button label="Settings" tooltip="Settings" isIconOnly icon={<AppIcon icon={Settings} color="secondary"/>} variant={view==='Settings'?'secondary':'ghost'} aria-current={view==='Settings'?'page':undefined} xstyle={s.action} onClick={()=>choose('Settings')}/>
  </HStack>
 </VStack>;
 return <VStack xstyle={s.shell} gap={0}>
 <HStack xstyle={s.frame} gap={0}>
 <VStack xstyle={s.rail}>{sidebar()}</VStack>
 <Drawer label="Workspace navigation" side="start" width="19rem" padding={0} isOpen={showNav} onOpenChange={setShowNav}>{showNav&&sidebar(true)}</Drawer>
 <VStack as="main" xstyle={s.main} gap={0}>
 <HStack as="header" paddingInline={5} paddingBlock={2} gap={2} xstyle={s.header} vAlign="center">
  <Button xstyle={s.mobileOnly} label="Open navigation" isIconOnly icon={<AppIcon icon={Menu} color="secondary"/>} variant="ghost" onClick={()=>setShowNav(true)}/>
  <VStack gap={0} xstyle={s.identity}>
   <Text weight="semibold" maxLines={1}>{newProject?'New project':isChat?currentConversation?.title||'Chat':navigation[view].label}</Text>
   <Text type="supporting" color="secondary" maxLines={1}>{project?.name||'Galvanise workspace'}</Text>
  </VStack>
  {project&&<HStack gap={1} vAlign="center" xstyle={s.headerActions}>
   {view!=='Context'&&<Button label="Project notes" aria-label="Project notes" tooltip="Project notes" icon={<AppIcon icon={BookOpen} color="secondary"/>} variant="ghost" onClick={()=>choose('Context')}><Text type="label" xstyle={s.notesLabel}>Project notes</Text></Button>}
   <Button label="Refresh project" tooltip="Refresh project" isIconOnly icon={<AppIcon icon={RefreshCw} color="secondary"/>} variant="ghost" isLoading={busy} onClick={()=>{setDesignRefresh(v=>v+1);void run(refresh)}}/>
  </HStack>}
 </HStack>
 {error&&<VStack padding={4} hAlign="start"><ErrorNotice message={error}/><Button label="Dismiss" variant="ghost" size="sm" onClick={()=>setError('')}/></VStack>}
 {newProject?<VStack padding={6} xstyle={s.content}><ProjectForm busy={busy} cancel={()=>setNewProject(false)} save={data=>run(async()=>{const p=await post<Project>('/projects',data);await loadProjects();setProjectId(p.id);setNewProject(false);setView('Chat')})}/></VStack>:!project&&view!=='Settings'?<VStack padding={6} xstyle={s.empty} gap={4} hAlign="center" vAlign="center"><Heading level={1}>Start with a project</Heading><Text color="secondary">{user.github_connected?'Choose a repository from the Project menu or start a new project.':'Tell us what you want to improve. You can add files and code later.'}</Text><HStack gap={3} wrap="wrap"><Button label="Create your first project" icon={<AppIcon icon={Plus} color="inherit"/>} variant="primary" onClick={()=>setNewProject(true)}/><Button label="Explore sample project" icon={<AppIcon icon={BookOpen} color="blue"/>} isLoading={busy} onClick={()=>run(async()=>{const p=await post<Project>('/projects/demo');await loadProjects();setProjectId(p.id)})}/></HStack><Text type="supporting" color="secondary">The sample contains fictional information so you can try things out.</Text></VStack>:isChat?<EngineSession key={base} base={base} streaming={streaming} refreshKey={designRefresh}><VStack xstyle={s.chatContent} gap={0} paddingInline={5}>
 {!emptyChat&&<VStack xstyle={s.chatContent} paddingBlock={6}>
   <VStack xstyle={s.measure} gap={6}>
    {messages.map(message=>{
     const fromUser=message.role==='user';
     return <ChatMessage key={message.id} sender={fromUser?'user':'assistant'}>
      <ChatMessageBubble variant={fromUser?'filled':'ghost'} name={fromUser?undefined:<Text weight="semibold">Galvanise</Text>} width={fromUser?undefined:'100%'}>
       <VStack gap={2} xstyle={s.messageContent}>
        <Markdown>{message.content}</Markdown>
        {fromUser&&<ApplyCorrection messageId={message.id}/>}
        {message.metadata_json?.partial===true&&<Text type="supporting" color="secondary">Response stopped before it finished</Text>}
       </VStack>
      </ChatMessageBubble>
     </ChatMessage>;
    })}
    {streaming&&<ChatMessage sender="assistant"><ChatMessageBubble name={<Text weight="semibold">Galvanise</Text>} variant="ghost" width="100%">
     <VStack gap={2} xstyle={s.messageContent}>
      {stream?<Markdown>{stream}</Markdown>:<Text role="status" color="secondary">Reading your project…</Text>}
      {tool&&<Text role="status" xstyle={s.tool}>{tool}</Text>}
     </VStack>
    </ChatMessageBubble></ChatMessage>}
    <VStack ref={end}/>
   </VStack>
  </VStack>}
  <VStack xstyle={emptyChat?s.chatLanding:[s.measure,s.composer]} paddingBlockEnd={4} gap={emptyChat?5:2}>
   {emptyChat&&<VStack gap={2} hAlign="center">
    <Heading level={1} xstyle={s.chatTitle}>What is changing in your business?</Heading>
    <Text color="secondary" xstyle={s.chatIntro}>Describe a business change or ask about your system.</Text>
   </VStack>}
   <EngineChat base={base} objective={project?.objective??''} documents={documents} jobs={jobs} refresh={refresh} openSources={()=>choose('Sources')} messageId={[...messages].reverse().find(m=>m.role==='user'&&!m.id.startsWith('local-'))?.id}/>
   <ChatComposer value={draft} onChange={setDraft} onSubmit={send} placeholder="Message Galvanise" elevation="none" isDisabled={!health?.ai_configured} isStopShown={streaming} onStop={()=>controller.current?.abort()}/>
   {emptyChat&&<HStack gap={2} hAlign="center" wrap="wrap">
    <Button label="Open questions" icon={<AppIcon icon={Info} color="secondary"/>} size="sm" variant="ghost" onClick={()=>choose('Questions')}/>
   </HStack>}
   {health&&!health.ai_configured&&<HStack gap={2} hAlign="center" vAlign="center" wrap="wrap"><Text type="supporting" color="secondary">Chat needs to be set up.</Text><Button label="Open settings" size="sm" variant="ghost" onClick={()=>choose('Settings')}/></HStack>}
  </VStack>
 </VStack></EngineSession>:<VStack padding={6} xstyle={s.content}><VStack gap={6} xstyle={s.pageMeasure}>
 {view==='Sources'&&<Sources key={base} repos={githubRepos} githubAvailable={!!health?.github_configured} base={base} user={user} sources={sources} documents={documents} jobs={jobs} graphs={graphs} busy={busy} run={run} refresh={refresh}/>}
 {['Decisions','Volatility','Questions'].includes(view)&&<><HStack hAlign="between" vAlign="center" wrap="wrap"><Heading level={1}>{view==='Decisions'?'Decisions':view==='Volatility'?'What might change':'Questions to answer'}</Heading><Button label="Find suggestions" icon={<AppIcon icon={Search} color={health?.ai_configured?'blue':'disabled'}/>} isDisabled={!health?.ai_configured} tooltip={!health?.ai_configured?'Set up chat in Settings first':undefined} isLoading={busy} onClick={()=>run(async()=>{await post(`${base}/analyse`);await refresh()})}/></HStack><Text color="secondary">Check each suggestion before keeping it. You can edit it or leave it out.</Text><KnowledgeList records={records.filter(r=>view==='Decisions'?['requirement','decision','driver','traceability','evidence'].includes(r.kind):view==='Volatility'?r.kind==='volatility':r.kind==='question')} busy={busy} patch={(r,c)=>run(()=>patch(r,c))} answer={(r,answer)=>run(async()=>{await post(`${base}/questions/${r.id}/answer`,{answer});await refresh()})} map={r=>run(async()=>{if(!graphs[0])throw new Error('Import a technical graph before linking a decision.');await post(`${base}/traceability`,{decision_id:r.id,graph_id:graphs[0].id});await refresh()})}/></>}
 {view==='Design process'&&<DesignWorkspace key={base} base={base} aiAvailable={health?health.ai_configured:null} records={records} onChange={refresh} onSettings={()=>choose('Settings')}/>}
 {view==='Designs'&&<Designs aiAvailable={!!health?.ai_configured} records={records} graphs={graphs} base={base} busy={busy} run={run} refresh={refresh} patch={(r,c)=>run(()=>patch(r,c))}/>}
 {view==='Graph'&&<GraphWorkspace base={base} graphs={graphs} records={records} onError={setError}/>}
 {view==='Context'&&project&&<VStack gap={5}><Heading level={1}>Project notes</Heading><Heading level={2}>Project goal</Heading><Text>{project.objective||'Tell us your project goal in chat.'}</Text><Context title="Decisions to review" records={records.filter(r=>r.status==='pending'&&['decision','requirement'].includes(r.kind))} open={()=>choose('Decisions')}/><Context title="Reasons for change" records={records.filter(r=>r.kind==='driver')} open={()=>choose('Volatility')}/><Context title="Questions to answer" records={records.filter(r=>r.kind==='question')} open={()=>choose('Questions')}/><Button label="Back to chat" icon={<AppIcon icon={MessageSquare} color="blue"/>} onClick={()=>choose('Chat')}/></VStack>}
 {view==='Settings'&&<VStack gap={5}><Heading level={1}>Workspace settings</Heading><Heading level={2}>Account</Heading><Text>{user.name} · {user.email}</Text><GitHubAction available={!!health?.github_configured} connected={user.github_connected}/><Heading level={2}>Connections</Heading><HStack gap={2} vAlign="center"><AppIcon icon={health?.ai_configured?Check:Info} color={health?.ai_configured?'success':'warning'}/><Text>{health?.ai_configured?'AI chat is set up':'AI chat needs setup'}</Text></HStack>{!health?.ai_configured&&<Text color="secondary">The person running Galvanise needs to add an OpenAI API key before chat can respond.</Text>}<Button label="Sign out" icon={<AppIcon icon={LogOut} color="secondary"/>} isDisabled={streaming} onClick={()=>run(onSignOut)}/></VStack>}
 </VStack></VStack>}
 </VStack></HStack></VStack>
}
export function ErrorNotice({message}:{message:string}){return <VStack role="alert" padding={4} xstyle={s.error}><HStack gap={2} vAlign="center"><AppIcon icon={TriangleAlert} color="error"/><Text weight="semibold">Something needs attention</Text></HStack><Text>{message}</Text></VStack>}
function ProjectForm({save,cancel,busy}:{save:(data:Record<string,string>)=>void;cancel:()=>void;busy:boolean}){const [name,setName]=useState(''),[description,setDescription]=useState(''),[objective,setObjective]=useState(''),[type,setType]=useState('existing');return <VStack as="form" xstyle={s.measure} gap={5} onSubmit={(e:React.FormEvent)=>{e.preventDefault();save({name,description,objective,system_type:type})}}><Heading level={1}>Create a project</Heading><Text color="secondary">What are you working on? You can connect code later.</Text><TextInput label="Project name" value={name} onChange={setName} isRequired/><TextArea label="Short description" value={description} onChange={setDescription}/><Selector label="System" value={type} onChange={setType} options={[{value:'existing',label:'An existing system'},{value:'new',label:'A new system'}]}/><TextArea label="What do you want to improve?" value={objective} onChange={setObjective} placeholder="For example, make it easier to add a new supplier."/><HStack gap={3}><Button label="Create project" icon={<AppIcon icon={Plus} color="inherit"/>} type="submit" variant="primary" isLoading={busy} isDisabled={!name.trim()}/><Button label="Cancel" onClick={cancel}/></HStack></VStack>}
function Context({title,records,open}:{title:string;records:Knowledge[];open:()=>void}){return <VStack gap={3}><HStack hAlign="between" vAlign="center"><Text weight="semibold">{title}</Text><Button label="View" icon={<AppIcon icon={ArrowRight} color="blue"/>} size="sm" variant="ghost" onClick={open}/></HStack>{records.length?records.map(r=><VStack key={r.id} gap={1}><Text>{r.title}</Text><Text type="supporting" color="secondary">{evidenceLabel(r.evidence_status)}</Text></VStack>):<Text type="supporting" color="secondary">No findings yet.</Text>}</VStack>}
function Sources({base,user,repos,sources,documents,jobs,graphs,busy,run,refresh,githubAvailable}:{repos:GitHubRepo[];githubAvailable:boolean;base:string;user:User;sources:Source[];documents:Document[];jobs:Job[];graphs:GraphSummary[];busy:boolean;run:(fn:()=>Promise<unknown>)=>Promise<void>;refresh:()=>Promise<void>}){
 const [file,setFile]=useState<File|File[]|null>(null),[graphFile,setGraphFile]=useState<File|File[]|null>(null),[repo,setRepo]=useState(''),[document,setDocument]=useState<Document|null>(null);
 const [removing,setRemoving]=useState<string|null>(null);
 async function removeRepository(source:Source){
   await request(base+'/sources/github/'+encodeURIComponent(source.id),{method:'DELETE'});
   if(document?.source_id===source.id)setDocument(null);
   setRemoving(null);
   await refresh();
 }
 async function upload(path:string,value:File|File[]|null){if(!value||Array.isArray(value))return;const form=new FormData();form.append('file',value);await request(`${base}/${path}`,{method:'POST',body:form});await refresh()}
 return <VStack gap={6}><Heading level={1}>Files & code</Heading><Text color="secondary">Add documents, notes, or code so suggestions can refer to your system.</Text><VStack gap={4}><Heading level={2}>Documents</Heading><FileInput label="Choose a document" accept=".txt,.md,.pdf,.docx" value={file} onChange={setFile} description="TXT, Markdown, PDF or DOCX"/><Button label="Upload document" icon={<AppIcon icon={Upload} color={file?'blue':'disabled'}/>} isLoading={busy} isDisabled={!file} onClick={()=>run(async()=>{await upload('documents',file);setFile(null)})}/>{documents.map(d=><HStack key={d.id} xstyle={s.row} paddingBlock={3} hAlign="between"><Text xstyle={s.helper} maxLines={2}>{d.name}</Text><Button xstyle={s.action} label="Open file" icon={<AppIcon icon={FileText} color="blue"/>} size="sm" onClick={()=>run(async()=>setDocument(await request<Document>(`${base}/documents/${d.id}`)))}/></HStack>)}{document&&<VStack gap={3}><HStack hAlign="between"><Heading level={3}>{document.name}</Heading><Button label="Close file" onClick={()=>setDocument(null)}/></HStack><Markdown>{document.content||'No extracted text available.'}</Markdown></VStack>}</VStack><VStack gap={4}><Heading level={2}>Code map</Heading><Text color="secondary">Have a Graphify export? Upload it to see how parts of your code connect.</Text><FileInput label="Choose a Graphify file" accept=".json" value={graphFile} onChange={setGraphFile}/><Button label="Upload code map" icon={<AppIcon icon={Network} color={graphFile?'teal':'disabled'}/>} isLoading={busy} isDisabled={!graphFile} onClick={()=>run(async()=>{await upload('graphs/import',graphFile);setGraphFile(null)})}/>{graphs.map(g=><Text key={g.id}>{g.name} · {g.node_count} parts · {g.edge_count} connections</Text>)}</VStack><VStack gap={4}><Collapsible defaultIsOpen={false} trigger={<HStack gap={2} vAlign="center"><AppIcon icon={GitBranch} color="secondary"/><Text>GitHub</Text></HStack>}><VStack gap={3} paddingBlock={2}>{!user.github_connected?<GitHubAction available={githubAvailable}/>:<><Selector label="Repository" options={repos.map(r=>({value:r.full_name,label:r.full_name+(r.private?' (private)':'')}))} value={repo} onChange={setRepo}/><Button label="Add repository" icon={<AppIcon icon={Plus} color={repo?'blue':'disabled'}/>} isDisabled={!repo} isLoading={busy} onClick={()=>run(async()=>{await post(`${base}/sources/github`,{full_name:repo});await refresh()})}/></>}</VStack></Collapsible>{sources.map(source=><VStack key={source.id} gap={2} paddingBlock={3} xstyle={s.row}>
   <HStack hAlign="between" gap={2} vAlign="center" wrap="wrap">
     <Text>{source.name} · {source.status}</Text>
     {source.kind==='github'&&removing!==source.id&&<Button size="sm" variant="ghost" label="Delete from project" aria-label={'Delete '+source.name+' from project'} isDisabled={busy} onClick={()=>setRemoving(source.id)}/>}
   </HStack>
   {removing===source.id&&<VStack gap={2}>
     <Text>Remove {source.name}, its imported files, and its code map from this project? Saved design revisions retain their cited excerpts.</Text>
     <HStack gap={2}><Button size="sm" variant="destructive" label="Confirm removal" isDisabled={busy} onClick={()=>run(()=>removeRepository(source))}/><Button size="sm" label="Cancel" isDisabled={busy} onClick={()=>setRemoving(null)}/></HStack>
   </VStack>}
 </VStack>)}</VStack>{jobs.length>0&&<VStack gap={3}><Heading level={2}>Upload progress</Heading>{jobs.map(j=><VStack key={j.id} paddingBlock={3} xstyle={s.row}><HStack gap={2} vAlign="center"><AppIcon icon={j.status==='completed'?Check:j.status==='failed'?TriangleAlert:Info} color={j.status==='completed'?'success':j.status==='failed'?'error':'warning'}/><Text>{j.kind==='document'?'Document':'Repository'} · {plainValue(j.status)}</Text></HStack>{j.error&&<Text>{j.error}</Text>}</VStack>)}</VStack>}</VStack>
}
function KnowledgeList({records,busy,patch,answer,map}:{records:Knowledge[];busy:boolean;patch:(r:Knowledge,c:Record<string,unknown>)=>void;answer?:(r:Knowledge,a:string)=>void;map?:(r:Knowledge)=>void}){return <VStack gap={0}>{records.length?records.map(r=><RecordRow key={r.id} record={r} busy={busy} patch={patch} answer={answer} map={map}/>):<VStack paddingBlock={8} gap={3}><Heading level={2}>Nothing to review yet</Heading><Text color="secondary">Add files or tell us about your business in chat. Suggestions will appear here for you to review.</Text></VStack>}</VStack>}
function RecordRow({record:r,busy,patch,answer,map}:{record:Knowledge;busy:boolean;patch:(r:Knowledge,c:Record<string,unknown>)=>void;answer?:(r:Knowledge,a:string)=>void;map?:(r:Knowledge)=>void}){const [editing,setEditing]=useState(false),[title,setTitle]=useState(r.title),[description,setDescription]=useState(r.description),[response,setResponse]=useState(''),[details,setDetails]=useState(false);return <VStack paddingBlock={5} gap={3} xstyle={s.row}><HStack hAlign="between" vAlign="center" wrap="wrap"><Heading level={3}>{r.title}</Heading><ReviewState status={r.status}/></HStack><Text type="supporting" color="secondary">{evidenceLabel(r.evidence_status)}</Text><Text>{r.description}</Text>{editing&&<VStack gap={3}><TextInput label="Title" value={title} onChange={setTitle}/><TextArea label="Description" value={description} onChange={setDescription}/><HStack gap={3}><Button label="Save changes" icon={<AppIcon icon={Check} color="success"/>} isLoading={busy} onClick={()=>{patch(r,{title,description});setEditing(false)}}/><Button label="Cancel" onClick={()=>setEditing(false)}/></HStack></VStack>}<HStack gap={2} wrap="wrap">{r.status!=='approved'&&<Button label="Approve" icon={<AppIcon icon={Check} color="success"/>} size="sm" isLoading={busy} onClick={()=>patch(r,{status:'approved'})}/>} {r.status!=='rejected'&&<Button label="Leave out" icon={<AppIcon icon={X} color="error"/>} size="sm" variant="ghost" isLoading={busy} onClick={()=>patch(r,{status:'rejected'})}/>}<Button label="Edit" icon={<AppIcon icon={Pencil} color="blue"/>} size="sm" variant="ghost" onClick={()=>setEditing(!editing)}/><Button icon={<AppIcon icon={BookOpen} color="secondary"/>} label={details?'Hide details':'Sources & history'} size="sm" variant="ghost" onClick={()=>setDetails(!details)}/>{r.kind==='decision'&&map&&<Button label="Find related code" icon={<AppIcon icon={Search} color="teal"/>} size="sm" onClick={()=>map(r)}/>}</HStack>{details&&<VStack gap={3}><ReadableFields value={r.payload}/>{r.history?.length>0&&<VStack gap={3}><Heading level={3}>Previous versions</Heading><ReadableFields value={r.history}/></VStack>}</VStack>}{r.kind==='question'&&answer&&<VStack gap={3}><TextArea label="Your answer" value={response} onChange={setResponse}/><Button label="Save answer" icon={<AppIcon icon={Check} color={response.trim()?'success':'disabled'}/>} isDisabled={!response.trim()} isLoading={busy} onClick={()=>{answer(r,response);setResponse('')}}/></VStack>}</VStack>}
function ReadableFields({value}:{value:unknown}){
 if(value==null)return <Text color="secondary">Not known yet</Text>;
 if(typeof value==='string'||typeof value==='number'||typeof value==='boolean')return <Text>{typeof value==='string'?plainValue(value):typeof value==='boolean'?(value?'Yes':'No'):String(value)}</Text>;
 if(Array.isArray(value))return <VStack gap={2}>{value.length?value.map((item,i)=><VStack key={i} gap={2}>{typeof item==='object'?<ReadableFields value={item}/>:<Text>• {String(item)}</Text>}</VStack>):<Text color="secondary">None identified</Text>}</VStack>;
 return <VStack gap={4}>{Object.entries(value as Record<string,unknown>).filter(([,v])=>v!==''&&v!==null&&!(Array.isArray(v)&&v.length===0)).map(([key,item])=><VStack key={key} gap={2}><Text weight="semibold">{fieldLabel(key)}</Text><ReadableFields value={item}/></VStack>)}</VStack>
}
function CandidateContent({record}:{record:Knowledge}){const payload=record.payload;return <VStack gap={5}>{typeof payload.approach==='string'&&<Text weight="semibold">{fieldLabel(payload.approach)}</Text>}{typeof payload.rationale==='string'&&<Text>{payload.rationale}</Text>}{Array.isArray(payload.boundaries)&&payload.boundaries.map((item,i)=>{const b=item as Record<string,unknown>;return <VStack key={i} paddingBlock={4} gap={3} xstyle={s.row}><Heading level={3}>{String(b.name||'Proposed part')}</Heading><ReadableFields value={Object.fromEntries(Object.entries(b).filter(([key])=>key!=='name'))}/></VStack>})}{Array.isArray(payload.assumptions)&&<VStack gap={3}><Heading level={3}>Things to confirm</Heading><ReadableFields value={payload.assumptions}/></VStack>}</VStack>}
function Designs({records,graphs,base,busy,run,refresh,patch,aiAvailable}:{aiAvailable:boolean;records:Knowledge[];graphs:GraphSummary[];base:string;busy:boolean;run:(fn:()=>Promise<unknown>)=>Promise<void>;refresh:()=>Promise<void>;patch:(r:Knowledge,c:Record<string,unknown>)=>void}){
 const candidates=records.filter(r=>r.kind==='architecture');
 const [scenario,setScenario]=useState(''),[candidate,setCandidate]=useState(''),[graphId,setGraphId]=useState(''),[nodeId,setNodeId]=useState(''),[nodes,setNodes]=useState<{id:string;label:string}[]>([]),[evaluation,setEvaluation]=useState<{mode:string;scenario:string;current:unknown;proposed:unknown;assumptions:unknown}|null>(null);
 const graph=graphId||graphs[0]?.id||'';
 useEffect(()=>{setNodeId('');if(graph)request<{nodes:{id:string;label:string}[]}>(`${base}/graphs/${graph}?limit=80`).then(d=>setNodes(d.nodes)).catch(()=>setNodes([]));else setNodes([])},[graph,base]);
 return <VStack gap={6}><HStack hAlign="between" wrap="wrap" vAlign="center"><Heading level={1}>Design options</Heading><Button label="Create design options" icon={<AppIcon icon={Layers} color="inherit"/>} isDisabled={!aiAvailable} tooltip={!aiAvailable?'Set up chat in Settings first':undefined} variant="primary" isLoading={busy} onClick={()=>run(async()=>{await post(`${base}/architectures/generate`);await refresh()})}/></HStack><Text color="secondary">Compare small improvements with a design that separates the parts likely to change.</Text>
 {!candidates.length&&<Text color="secondary">Start with your project notes, then create options to compare.</Text>}
 {candidates.map(c=><VStack key={c.id} gap={5} paddingBlock={5} xstyle={s.row}><HStack gap={3} hAlign="between" wrap="wrap"><Heading level={2}>{c.title}</Heading><ReviewState status={c.status}/></HStack><Text>{c.description}</Text><CandidateContent record={c}/><CandidateReview record={c} busy={busy} patch={patch}/></VStack>)}
 {records.some(r=>r.kind==='boundary')&&<><Heading level={2}>Proposed parts</Heading>{records.filter(r=>r.kind==='boundary').map(r=><VStack key={r.id} paddingBlock={4} gap={3} xstyle={s.row}><Heading level={3}>{r.title}</Heading><Text>{r.description}</Text><ReadableFields value={r.payload}/></VStack>)}</>}
 <VStack gap={4}><Heading level={2}>Try a change</Heading><TextArea label="What might change?" value={scenario} onChange={setScenario} placeholder="For example, add a new supplier."/><Selector label="Proposed design" value={candidate} onChange={setCandidate} options={[{value:'',label:'Current system only'},...candidates.map(c=>({value:c.id,label:displayText(c.title)}))]}/>{graphs.length>0&&<><Selector label="Code map" value={graph} onChange={setGraphId} options={graphs.map(g=>({value:g.id,label:displayText(g.name)}))}/><Selector label="Where would the change start?" value={nodeId} onChange={setNodeId} options={[{value:'',label:'Not sure yet'},...nodes.filter(n=>!n.id.startsWith('business:')).map(n=>({value:n.id,label:displayText(n.label)}))]}/><Text type="supporting" color="secondary">Choose a code part to see what else it connects to. You can leave this blank if you are unsure.</Text></>}<Button label="Compare the impact" icon={<AppIcon icon={Search} color={scenario.trim()?'blue':'disabled'}/>} isDisabled={!scenario.trim()} isLoading={busy} onClick={()=>run(async()=>setEvaluation(await post(`${base}/evaluate`,{scenario,...(candidate?{candidate_id:candidate}:{}),...(graph?{graph_id:graph}:{}),...(nodeId?{node_ids:[nodeId]}:{})})))}/>
 {evaluation&&<VStack gap={5}><Heading level={2}>What could be affected</Heading><Text>{evaluation.mode==='structural'?'Based on the code connections you supplied.':'There is not enough code information to count affected parts yet.'}</Text><Text color="secondary">This is a guide, not a prediction. Check the affected code and tests before making changes.</Text><HStack gap={6} wrap="wrap" vAlign="start"><VStack gap={4} xstyle={s.grow}><Heading level={3}>Current system</Heading><ReadableFields value={evaluation.current}/></VStack><VStack gap={4} xstyle={s.grow}><Heading level={3}>Proposed design</Heading><ReadableFields value={evaluation.proposed}/></VStack></HStack><Heading level={3}>What to check</Heading><ReadableFields value={evaluation.assumptions}/></VStack>}</VStack></VStack>
}
function CandidateReview({record,busy,patch}:{record:Knowledge;busy:boolean;patch:(r:Knowledge,c:Record<string,unknown>)=>void}){
 const [editing,setEditing]=useState(false),[history,setHistory]=useState(false),[title,setTitle]=useState(record.title),[description,setDescription]=useState(record.description);
 return <VStack gap={4}><HStack gap={3} wrap="wrap"><Button label="Approve design" icon={<AppIcon icon={Check} color={record.status==='approved'?'disabled':'success'}/>} isDisabled={record.status==='approved'} isLoading={busy} onClick={()=>patch(record,{status:'approved'})}/><Button label="Leave design out" icon={<AppIcon icon={X} color={record.status==='rejected'?'disabled':'error'}/>} variant="ghost" isDisabled={record.status==='rejected'} isLoading={busy} onClick={()=>patch(record,{status:'rejected'})}/><Button label="Edit summary" icon={<AppIcon icon={Pencil} color="blue"/>} variant="ghost" onClick={()=>setEditing(!editing)}/><Button label="History" icon={<AppIcon icon={History} color="secondary"/>} variant="ghost" onClick={()=>setHistory(!history)}/></HStack>{editing&&<VStack gap={3}><TextInput label="Design name" value={title} onChange={setTitle}/><TextArea label="Design summary" value={description} onChange={setDescription}/><Button label="Save changes" icon={<AppIcon icon={Check} color="success"/>} isLoading={busy} onClick={()=>{patch(record,{title,description});setEditing(false)}}/></VStack>}{history&&<VStack gap={3}><Heading level={3}>Previous versions</Heading><ReadableFields value={record.history||[]}/></VStack>}</VStack>
}
