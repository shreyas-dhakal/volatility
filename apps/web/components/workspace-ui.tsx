'use client';
import {useState} from 'react';
import {post} from '../lib/api';
import * as stylex from '@stylexjs/stylex';
import {Icon, type IconProps} from '@astryxdesign/core/Icon';
import {MessageSquare,FolderOpen,ClipboardCheck,TrendingUp,CircleHelp,Layers,Network,Settings,BookOpen,GitBranch,Check,Clock,X} from 'lucide-react';
import {Button,HStack,VStack,Text} from './ui';

export type WorkspaceView='Chat'|'Sources'|'Decisions'|'Volatility'|'Questions'|'Designs'|'Design process'|'Graph'|'Settings'|'Context';
export const navigation={
 Chat:{label:'Chat',icon:MessageSquare,color:'blue'},
 Sources:{label:'Files & code',icon:FolderOpen,color:'blue'},
 Decisions:{label:'Decisions',icon:ClipboardCheck,color:'purple'},
 Volatility:{label:'Changes',icon:TrendingUp,color:'orange'},
 Questions:{label:'Questions',icon:CircleHelp,color:'orange'},
 'Design process':{label:'Design process',icon:GitBranch,color:'purple'},
 Designs:{label:'Designs',icon:Layers,color:'purple'},
 Graph:{label:'Code map',icon:Network,color:'teal'},
 Settings:{label:'Settings',icon:Settings,color:'gray'},
 Context:{label:'Project notes',icon:BookOpen,color:'blue'},
} as const;
const s=stylex.create({nav:{justifyContent:'flex-start'},state:{flexShrink:0}});
export function AppIcon({icon,color='blue'}:{icon:IconProps['icon'];color?:IconProps['color']}){
 return <Icon icon={icon} color={color} size="sm"/>;
}
export function NavigationItem({view,active,available=true,onClick}:{view:WorkspaceView;active:boolean;available?:boolean;onClick:()=>void}){
 const item=navigation[view];
 return <Button label={item.label} icon={<AppIcon icon={item.icon} color={available?item.color:'disabled'}/>} variant={active?'secondary':'ghost'} width="100%" xstyle={s.nav} aria-current={active?'page':undefined} isDisabled={!available} tooltip={!available?'Create a project first':undefined} onClick={onClick}/>;
}
export function ReviewState({status}:{status:string}){
 const state=status==='approved'?{label:'Approved',icon:Check,color:'success' as const}:status==='rejected'?{label:'Not used',icon:X,color:'error' as const}:{label:'Needs review',icon:Clock,color:'warning' as const};
 return <HStack gap={2} vAlign="center" xstyle={s.state} data-review-state={status}><AppIcon icon={state.icon} color={state.color}/><Text type="supporting">{state.label}</Text></HStack>;
}
export function GitHubAction({available,connected=false,legacy=false}:{available:boolean;connected?:boolean;legacy?:boolean}){
 const [error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function connect(){setError('');setBusy(true);try{const {url}=await post<{url:string}>('/auth/github/start');const target=new URL(url);if(target.origin!=='https://github.com'||target.pathname!=='/login/oauth/authorize')throw new Error('GitHub returned an invalid connection address');location.assign(target.href)}catch(e){setError(e instanceof Error?e.message:'GitHub connection failed')}finally{setBusy(false)}}
 if(connected)return <HStack gap={2} vAlign="center"><AppIcon icon={Check} color="success"/><Text>GitHub connected</Text></HStack>;
 return <VStack gap={2}><Button label={available?'Connect GitHub':'GitHub not set up'} icon={<AppIcon icon={GitBranch} color={available?'blue':'disabled'}/>} href={available&&legacy?'/api/auth/github/start':undefined} onClick={legacy?undefined:()=>void connect()} isLoading={busy} isDisabled={!available}/>{error&&<Text role="alert">{error}</Text>}{!available&&<Text type="supporting" color="secondary">You can upload files now. GitHub can be set up later in Settings.</Text>}</VStack>;
}
export function evidenceLabel(value:string){return ({verified:'Checked against a source',human_confirmed:'Confirmed by a person',ai_inferred:'AI suggestion',hypothesis:'Source not confirmed'} as Record<string,string>)[value]||value.replaceAll('_',' ')}
export function fieldLabel(value:string){return ({change_driver:'Reason for change',change_drivers:'Reasons for change',affected_decisions:'Decisions that may change',stable_decisions:'What stays the same',stable_contract:'What stays the same',included_responsibilities:'Included',excluded_responsibilities:'Not included',responsibility:'Purpose',boundary_type:'Type of part',node_ids:'Code parts',evidence_ids:'Sources',evidence_status:'How we know',dependencies:'Connections',tradeoffs:'Things to consider',migration:'How to get there',open_questions:'Questions to answer',time_horizon:'When this might change',volatility_type:'Type of change',recommended_investigation:'What to check next',stakeholder_role:'Who to ask',potentially_affected_nodes:'Parts that may need changes',cross_boundary_dependencies:'Connections between parts',dependency_edges_in_envelope:'Connections to check',regression_scope:'Tests to check',changed_interfaces:'Connections that may change',boundaries:'Proposed parts',assessment:'Summary',approach:'Approach',conservative:'Keep most of the current system','volatility-aware':'Separate the parts likely to change',uncertainty:'What we still need to know',assumptions:'Things to confirm',rationale:'Why this helps'} as Record<string,string>)[value]||value.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase())}

export function toolActivity(name:string,status:string,result?:unknown){
 const resultValue=result as {error?:unknown}|undefined;
 if(resultValue?.error)return 'This step needs another look.';
 const activity=({get_project_context:'Reading project notes',list_business_decisions:'Reading decisions',list_change_drivers:'Reading planned changes',get_technical_graph_summary:'Reading the code map',search_code_nodes:'Finding related code',get_node_dependencies:'Checking code connections',find_dependency_paths:'Following code connections',create_business_decision:'Saving a decision',create_change_driver:'Saving a reason for change',create_business_requirement:'Saving a requirement',create_volatility_hypothesis:'Saving a possible change',create_stakeholder_question:'Saving a question',save_stakeholder_answer:'Saving your answer',generate_architecture_candidates:'Creating design options',map_business_to_code:'Finding related code',evaluate_change_scenario:'Comparing the impact',get_architecture_candidate:'Reading a design'} as Record<string,string>)[name]||'Working on your request';
 return status==='complete'?activity+' · done':activity+'…';
}

export function plainValue(value:string){return ({'Structural reachability is a potential impact envelope, not predicted code changes or measured savings.':'Connected code may be affected. This does not predict how much work will be needed.','Dependencies do not establish runtime effects or regression coverage.':'Connections alone do not tell us what happens when code runs or which tests cover it.','Technical mappings are insufficient to calculate impact.':'There is not enough code information to estimate the impact.','Review contracts and operational tradeoffs with stakeholders.':'Ask the people involved to review responsibilities, connections, and running costs.','Review tests covering reachable components; coverage is not measured.':'Check tests for these connected parts. Test coverage has not been measured.','Contracts are proposals requiring review; no code transformation is assumed.':'These are suggestions to review. No code has been changed.',pending:'Needs review',approved:'Approved',rejected:'Not used',verified:'Checked against a source',human_confirmed:'Confirmed by a person',ai_inferred:'AI suggestion',hypothesis:'Source not confirmed',anticipated:'Planned change',observed:'Seen before',technical_instability:'Fragile code',unspecified:'Not known yet',module:'Code part',adapter:'Integration layer',policy:'Business rule',configuration:'Settings',interface:'Connection',service:'Separate service',queued:'Waiting',running:'In progress',completed:'Done',failed:'Needs attention',conservative:'Keep most of the current system','volatility-aware':'Separate the parts likely to change'} as Record<string,string>)[value]||value}
