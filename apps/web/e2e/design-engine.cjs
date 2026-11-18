// Run against a legacy-mode production build with npm run test:e2e --workspace @galvanise/web.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const net=require('node:net');
const {chromium}=require('playwright');

const quote='North and South use different tariffs.';
const original='System notes\nNorth and South use different tariffs.\nEach gate reports the stay.';
const correction='All sites now use one tariff.';
const evidence=[{chunk_id:'chunk-file',excerpt:quote}];
function revision(corrected=false){
  const decision=corrected?'All sites share a tariff':'Tariff by site';
  const snapshot={
    actors:[{id:'driver',name:'Driver',kind:'actor',evidence}],
    use_cases:[{id:'park',name:'Pay for parking',actor_id:'driver',outcome:'Collect payment for the stay.',evidence}],
    implementation_findings:[{id:'fixed',title:'Current gate tariff',description:'The gate contains a fixed tariff.',evidence}],
    volatilities:[{id:'tariff',decision,driver:'Pricing policy',status:corrected?'user_confirmed':'observed',alternatives:[{description:'Site-specific tariffs',hypothetical:false}],evidence:corrected?[{chunk_id:'chunk-user',excerpt:correction}]:evidence}],
    components:[{id:'gate',name:'Gate manager',role:'manager',owns:[],evidence},{id:'pricing',name:'Pricing engine',role:'engine',owns:['tariff'],rationale:'Encapsulate tariff choice.',evidence}],
    contracts:[{id:'price-contract',name:'Parking price',owner_id:'pricing',operations:[{id:'quote',name:'Quote stay',inputs:['stay'],outputs:['price'],failures:[]}],evidence}],
    dependencies:[{id:'edge',caller_id:'gate',callee_id:'pricing',operation_id:'quote',reason:'Quote before collecting payment',evidence}],
    walkthroughs:[{id:'walk',use_case_id:'park',steps:[],outcome:'Paid',evidence}],
    change_probes:[{id:'probe',volatility_id:'tariff',change:'Introduce weekend pricing',predicted_owner_ids:['pricing'],predicted_edit_ids:['pricing'],leaks:[],evidence}],
    questions:[{id:'q',question:'Who sets tariffs?',alternatives:['Site','Operator'],decision_impact:'Determines the owner.',evidence}],
    findings:[],manifest:[{id:'source',path:'parking.md',status:'analyzed'}],
  };
  return {id:corrected?'r2':'r1',parent_revision_id:corrected?'r1':null,snapshot,
    diff:{added:[],removed:[],changed:corrected?[{collection:'volatilities',id:'tariff',reason:'The operator confirmed one tariff across sites.'}]:[]}};
}

async function fixture(page){
  let documents=[],messages=[],conversations=[],head=null,plan=null,run=null;
  const calls=[],errors=[];
  const json=(route,data)=>route.fulfill({json:data});
  await page.route('**/api/**',async route=>{
    const req=route.request(),url=new URL(req.url()).pathname,method=req.method();
    const path=url.replace(/^\/api\/projects\/parking/,'');
    calls.push({path,method});
    try{
      if(url==='/api/auth/me')return json(route,{id:'u1',name:'Operator',email:'operator@example.test'});
      if(url==='/api/health')return json(route,{ai_configured:true});
      if(url==='/api/projects')return json(route,[{id:'parking',name:'Parking',objective:'Collect parking payments'}]);
      if(path==='/documents'&&method==='POST'){
        assert.match(req.postDataBuffer().toString(),/parking\.md/);assert.ok(req.postDataBuffer().includes(Buffer.from(original)));
        documents=[{id:'doc1',name:'parking.md'}];return json(route,{id:'job1',kind:'document',status:'completed'});
      }
      if(path==='/documents')return json(route,documents);
      if(path==='/conversations'&&method==='POST'){conversations=[{id:'conversation',title:'Parking correction'}];return json(route,conversations[0])}
      if(path==='/conversations')return json(route,conversations);
      if(path==='/conversations/conversation/messages')return json(route,messages);
      if(path==='/conversations/conversation/chat'){
        assert.equal(req.postDataJSON().content,correction);
        messages=[{id:'message1',role:'user',content:correction},{id:'message2',role:'assistant',content:'Recorded the tariff update.'}];
        return route.fulfill({contentType:'text/event-stream',body:'event: delta\ndata: {"text":"Recorded the tariff update."}\n\nevent: done\ndata: {}\n\n'});
      }
      if(path==='/design-engine/analyze'){
        assert.deepEqual(req.postDataJSON().selected_upload_ids,['doc1']);assert.ok(req.postDataJSON().idempotency_key);
        run={id:'run1',status:'running',stage:'inventory',error:null};return json(route,run);
      }
      if(path==='/design-engine/revise'){
        const body=req.postDataJSON();assert.equal(body.base_revision_id,'r1');assert.equal(body.correction_message_id,'message1');assert.ok(body.idempotency_key);
        run={id:'run2',status:'failed',stage:'volatility',error:'Fixture stage interrupted'};return json(route,run);
      }
      if(path==='/design-engine/runs/run2/retry'){
        run={...run,status:'completed',error:null};head=revision(true);return json(route,run);
      }
      if(path==='/design-engine/runs/stale-run/retry'){
        run={id:'rerun',stage:'review',status:'completed',error:null};return json(route,run);
      }
      if(path==='/design-engine')return json(route,{revision:head,run,plan});
      if(path==='/design-engine/chunks/chunk-file')return json(route,{id:'chunk-file',text:original,locator:{path:'parking.md',line_start:2,line_end:2}});
      if(path==='/design-engine/chunks/chunk-user')return json(route,{id:'chunk-user',text:correction,locator:{kind:'message',message_id:'message1',role:'user'}});
      if(path==='/design-engine/revisions/r1')return json(route,revision());
      if(path==='/design-engine/plan'){
        const {revision_id,planning_inputs:input}=req.postDataJSON();assert.equal(revision_id,'r2');
        const activity={id:'a',deliverable:'Publish price contract',related_ids:['price-contract'],predecessors:[],skills:null,effort:{},sources:evidence};
        const saved=!!plan;
        const runs=[];
        if(saved){
          assert.deepEqual(input.assumptions,['Team works weekdays']);
          const person=input.rosters[0].people[0];
          assert.equal(person.name,'Sam');assert.equal(input.activities[0].effort.likely,2);
          assert.equal(input.start_date,'2026-11-23');assert.equal(person.availability,1);assert.equal(person.daily_rate,200);
          assert.deepEqual(person.skills,['design']);assert.deepEqual(input.activities[0].skills,['design']);
          runs.push({roster_id:input.rosters[0].id,scenario:'likely',status:'scheduled',critical_path:['a'],
            critical_path_days:2,finish_date:'2026-11-24',makespan_days:2,total_cost:400,blockers:[],warnings:[],
            assignments:[{activity_id:'a',person_id:person.id,start_date:'2026-11-23',finish_date:'2026-11-24',effort_days:2,cost:400}]});
        }
        plan={id:saved?'plan2':'plan1',revision_id,input,result:{activities:input.activities??[activity],warnings:[],runs,assumptions:['Monday through Friday'],missing_inputs:saved?[]:[{path:'start_date',message:'Enter the project start date.'}]}};
        return json(route,plan);
      }
      if(['/records','/sources','/jobs','/graphs'].includes(path))return json(route,[]);
      throw Error('Unexpected request '+method+' '+url);
    }catch(e){errors.push(e);return route.fulfill({status:500,json:{detail:e.message}})}
  });
  return {calls,errors,stale(){run={id:'stale-run',stage:'review',status:'stale',error:'Base revision changed'}},complete(){head=revision();run={...run,status:'completed',stage:'review'}}};
}

test('upload, recover a run, inspect evidence, correct a revision and plan in rendered chat',{timeout:90000},async t=>{
  const listener=net.createServer();
  listener.listen(0,'127.0.0.1');await once(listener,'listening');
  const port=listener.address().port;await new Promise(resolve=>listener.close(resolve));
  const url='http://127.0.0.1:'+port;
  const server=spawn(process.execPath,[require.resolve('next/dist/bin/next'),'start','--hostname','127.0.0.1','--port',String(port)],{
    cwd:require('node:path').resolve(__dirname,'..'),env:{...process.env,AUTH_MODE:'legacy',NEXT_TELEMETRY_DISABLED:'1'},stdio:'pipe',
  });
  t.after(()=>server.kill());
  let logs='';server.stderr.on('data',d=>logs+=d);server.stdout.on('data',d=>logs+=d);
  for(let i=0;i<100;i++){
    if(server.exitCode!==null)throw Error(logs);
    if(await fetch(url).then(r=>r.ok).catch(()=>false))break;
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  const browser=await chromium.launch();t.after(()=>browser.close());
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  page.setDefaultTimeout(7000);
  const errors=[];page.on('pageerror',e=>errors.push(e));
  const transport=await fixture(page);
  const button=name=>page.getByRole('button',{name,exact:true});
  const heading=name=>page.getByRole('heading',{name,exact:true});
  const tab=name=>page.getByRole('tab',{name,exact:true});
  await page.goto(url);
  await button('Add files').click();
  await page.locator('input[type=file]').setInputFiles({name:'parking.md',mimeType:'text/markdown',buffer:Buffer.from(original)});
  await button('Upload to project').click();
  await button('parking.md').click();await button('Done').click();
  await button('Design system').click();
  await page.getByText('Design running · Inventory').waitFor();
  await page.reload();await page.getByText('Design running · Inventory').waitFor();
  transport.complete();
  await button('View design').click();
  await heading('Current implementation').waitFor();
  await tab('Volatility').click();await button('Tariff by site').click();
  await page.getByText('Pricing engine',{exact:true}).waitFor();await button('View source 1').click();
  await heading('Cited excerpt').waitFor();await page.getByText(quote,{exact:true}).waitFor();
  await page.getByText('parking.md',{exact:true}).waitFor();await button('Close source').click();
  await tab('Architecture').click();
  const diagram=page.getByRole('figure',{name:'Component dependency diagram'});
  await diagram.getByText('Gate manager',{exact:true}).waitFor();
  await diagram.getByText('Pricing engine',{exact:true}).waitFor();
  await diagram.getByText('Quote stay',{exact:true}).waitFor();
  await tab('Validation').click();await heading('Predicted change containment').waitFor();
  await button('Close design').click();
  const composer=page.getByRole('main').getByRole('textbox');
  await composer.click();await composer.pressSequentially(correction);assert.equal(await composer.innerText(),correction);
  await button('Send').click();
  await button('Apply as correction').click();
  await page.getByText(/Fixture stage interrupted/).waitFor();await button('View design').click();
  await page.getByText('Saved revision r1',{exact:true}).waitFor();await button('Close design').click();
  await button('Retry design run').click();
  await button('View design').click();await heading('Revision changes').waitFor();
  await page.getByText('The operator confirmed one tariff across sites.').waitFor();
  await button('Inspect previous revision').click();await heading('Previous decisions').waitFor();
  await tab('Volatility').click();await button('All sites share a tariff').click();await button('View source 1').click();
  await page.getByText('message1',{exact:true}).waitFor();await page.getByText(correction,{exact:true}).last().waitFor();await button('Close source').click();
  await button('Close design').click();await button('Plan project').click();
  await heading('Inputs needed').waitFor();await button('Publish price contract').click();
  await page.getByLabel('Project start date',{exact:true}).fill('2026-11-23');
  await page.getByLabel('Required skills',{exact:true}).fill('design');
  await page.getByLabel('likely effort (person-days)',{exact:true}).fill('2');
  await button('Add roster').click();await page.getByLabel('Roster name',{exact:true}).fill('Current team');
  await button('Add person').click();await page.getByLabel('Person name',{exact:true}).fill('Sam');
  await page.getByLabel('Person skills',{exact:true}).fill('design');
  await page.getByLabel('Availability (0 to 1 full-time)',{exact:true}).fill('1');
  await page.getByLabel('Rate per full day',{exact:true}).fill('200');
  await page.getByLabel('Planning assumptions',{exact:true}).fill('Team works weekdays');
  const calculated=page.waitForResponse(r=>r.url().endsWith('/design-engine/plan'));
  await button('Calculate schedule').click();assert.equal((await calculated).status(),200);
  await page.getByText('Total cost · 400',{exact:true}).waitFor();
  await page.getByText('Roster-constrained finish · 2026-11-24 (2 workdays)',{exact:true}).waitFor();
  assert.deepEqual(transport.errors,[]);assert.deepEqual(errors,[]);
  assert.equal(transport.calls.filter(x=>x.path==='/design-engine/analyze').length,1);
  await page.reload();await button('View design').click();await tab('Project').click();
  assert.equal(await page.getByLabel('Planning assumptions',{exact:true}).inputValue(),'Team works weekdays');
  await button('Close design').click();transport.stale();await button('Refresh project').click();
  await page.getByText('Design run stale · Base revision changed').waitFor();await button('View design').click();
  await page.getByText('Saved revision r2',{exact:true}).waitFor();await button('Close design').click();
  await button('Rerun on current revision').click();await button('Rerun on current revision').waitFor({state:'hidden'});
  assert.deepEqual(transport.errors,[]);assert.deepEqual(errors,[]);
});
