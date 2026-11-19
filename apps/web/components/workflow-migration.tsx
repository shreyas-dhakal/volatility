'use client';

import {useCallback, useEffect, useState} from 'react';
import {CheckboxInput} from '@astryxdesign/core/CheckboxInput';
import {CodeBlock} from '@astryxdesign/core/CodeBlock';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {List, ListItem} from '@astryxdesign/core/List';
import {Link} from '@astryxdesign/core/Link';
import {post, request} from '../lib/api';
import type {Evidence} from '../lib/design-engine';
import {Citations} from './engine-evidence';
import {useEngine} from './engine-session';
import {Button, Heading, HStack, Selector, Text, TextArea, TextInput, VStack} from './ui';

type Reference = {
  id?: string;
  kind: string;
  target?: string;
  basis: string;
  location: {path: string; line: number};
  evidence: Evidence[];
  transaction_evidence: Evidence[];
  transaction_markers?: string[];
  different_transaction_markers?: boolean;
  graph_id?: string;
};
type Discovery = {writes: Reference[]; reverse: Reference[]};
type SourceSelection = Partial<Discovery> & {query?: string};
type Job = {id: string; action: string; status: string; error: string | null; target: string | null; result_available: boolean};
type State = {
  workflow: string;
  selection: SourceSelection;
  scenarios: {name: string; evidence_ids: string[]}[];
  baseline: {id: string; source_commit: string} | null;
  jobs: Job[];
  targets: {name: string; draft_pr_configured: boolean}[];
  accepted: {job_id: string; reason: string}[];
  setup: string[];
};
type Difference = {path: string; legacy: unknown; replacement: unknown};
type Comparison = {
  name: string;
  status: string;
  gap?: string;
  first?: Difference;
  differences?: Difference[];
  difference_count?: number;
  unknown?: string[];
  legacy?: unknown;
  replacement?: unknown;
  reproduce?: unknown;
};
type Capture = {name: string; first?: unknown; second?: unknown; gap?: string; stability?: Comparison};
type Result = Job & {result: null | {
  source_commit?: string;
  patch?: string;
  url?: string;
  intentional_changes?: {scenario: string; path: string; reason: string}[];
  captures?: Capture[];
  comparisons?: Comparison[];
  scenarios?: unknown;
  focused_validation?: Comparison;
  evidence?: Record<string, Evidence[]>;
}};
const REPLAY = 'cd apps/api && uv run python -m galvanise.migration.replay workflow-replay.json';
const actionNames: Record<string, string> = {
  generate: 'Generate behavior tests',
  baseline: 'Run legacy baseline',
  compare: 'Compare replacement',
  generate_patch: 'Generate migration patch',
  repair: 'Request focused repair',
  draft_pr: 'Prepare migration PR',
};

const serialize = (value: unknown) => JSON.stringify(value, null, 2);
const statusText = (status: string) => status === 'not_run' ? 'Not run' :
  status.slice(0, 1).toUpperCase() + status.slice(1).replaceAll('_', ' ');

function download(name: string, body: string, type: string) {
  const url = URL.createObjectURL(new Blob([body], {type}));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function Json({value}: {value: unknown}) {
  return <CodeBlock code={serialize(value)} language="json" hasLineNumbers={false} isWrapped/>;
}

function SourceRows({title, rows, selected, toggle}: {
  title: string; rows: Reference[]; selected?: Set<string>; toggle?: (id: string, on: boolean) => void;
}) {
  return <VStack gap={2}>
    <Heading level={4}>{title}</Heading>
    {rows.length ? <List density="compact" hasDividers>
      {rows.map((item, index) => <ListItem key={item.id ?? `${item.location.path}:${item.location.line}:${index}`}
        label={`${item.location.path}:${item.location.line}`}
        description={`${item.kind} · ${item.basis}${item.graph_id ? ' · Graphify' : ''}${item.target ? ' · ' + item.target : ''}`}
        startContent={item.id && toggle && <CheckboxInput label={`Select ${item.kind} at ${item.location.path} line ${item.location.line}`}
          isLabelHidden value={!!selected?.has(item.id)} onChange={checked => toggle(item.id!, checked)}/>}
        endContent={<VStack gap={1}>
          <Citations items={item.evidence}/>
          {!!item.transaction_evidence.length && <Collapsible trigger={<Text type="supporting">{item.different_transaction_markers
              ? 'Different nearby transaction markers' : 'Transaction evidence'}</Text>}>
            {!!item.transaction_markers?.length && <Text type="supporting">{item.transaction_markers.join(' · ')}</Text>}
            <Citations items={item.transaction_evidence}/>
          </Collapsible>}
        </VStack>}/>)}
    </List> : <Text color="secondary">No matching references in this source snapshot.</Text>}
  </VStack>;
}

function Observations({name, status, first, unknown, old, next, left, right, gap, reproduce, evidence, differences, differenceCount}: {
  name: string; status: string; first?: Difference; unknown?: string[]; old: unknown; next: unknown;
  left: string; right: string; gap?: string; reproduce?: unknown; evidence?: Evidence[];
  differences?: Difference[]; differenceCount?: number;
}) {
  const count = (value: unknown) => {
    const run = value as {steps?: {http?: {count?: number}}[]} | undefined;
    return run?.steps?.at(-1)?.http?.count ?? 'Unknown';
  };
  return <Collapsible trigger={<Text weight="semibold">{name} · {statusText(status)}</Text>}>
    <VStack gap={2} paddingBlock={3}>
      {gap && <Text>Unverified · {gap}</Text>}
      <Citations items={evidence}/>
      {first && <><Text weight="semibold">Earliest observed difference · {first.path}</Text><Json value={first}/></>}
      {(differenceCount ?? 0) > 1 && <Collapsible trigger={<Text>{differenceCount} observed differences</Text>}>
        <Json value={differences}/>
      </Collapsible>}
      {!!unknown?.length && <Text>Unknown observations · {unknown.join(', ')}</Text>}
      {old !== undefined && next !== undefined && <HStack gap={4} wrap="wrap" vAlign="start">
        <VStack gap={1} width="min(100%, 22rem)"><Heading level={4}>{left}</Heading><Text>Execution · {count(old)} outgoing requests</Text><Json value={old}/></VStack>
        <VStack gap={1} width="min(100%, 22rem)"><Heading level={4}>{right}</Heading><Text>Execution · {count(next)} outgoing requests</Text><Json value={next}/></VStack>
      </HStack>}
      {reproduce !== undefined && !!first && <Collapsible trigger={<Text>Reproducing input</Text>}><Json value={reproduce}/></Collapsible>}
    </VStack>
  </Collapsible>;
}

export function WorkflowMigrationEntry({revisionId, operationId}: {revisionId: string; operationId: string}) {
  const [open, setOpen] = useState(false);
  return <VStack gap={4}>
    <Button size="sm" label={open ? 'Close workflow migration' : 'Migrate this workflow'}
      aria-expanded={open} onClick={() => setOpen(!open)}/>
    {open && <WorkflowMigration revisionId={revisionId} operationId={operationId}/>}
  </VStack>;
}

function WorkflowMigration({revisionId, operationId}: {revisionId: string; operationId: string}) {
  const {path} = useEngine();
  const url = path.replace(/\/design-engine$/, '') + '/workflow-migrations/' +
    encodeURIComponent(revisionId) + '/' + encodeURIComponent(operationId);
  const [state, setState] = useState<State>();
  const [query, setQuery] = useState('');
  const [sources, setSources] = useState<Discovery>();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [scenarioDraft, setScenarioDraft] = useState<string | null>(null);
  const [target, setTarget] = useState('');
  const [conventions, setConventions] = useState('');
  const [mappings, setMappings] = useState('[]');
  const [intent, setIntent] = useState('[]');
  const [rules, setRules] = useState('[]');
  const [repair, setRepair] = useState('');
  const [repairScenario, setRepairScenario] = useState('');
  const [acceptReason, setAcceptReason] = useState('');
  const [prReady, setPrReady] = useState(false);
  const [enablePR, setEnablePR] = useState(false);
  const [shown, setShown] = useState<Result>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const load = useCallback(() => request<State>(url).then(next => {
    setState(next);
    return next;
  }), [url]);

  useEffect(() => {
    let active = true;
    request<State>(url).then(next => {
      if (!active) return;
      setState(next);
      setQuery(next.selection.query ?? '');
      setSelected(new Set(next.selection.writes?.map(x => x.id!) ?? []));
    }).catch(e => {if (active) setError((e as Error).message)});
    return () => {active = false};
  }, [url]);

  const running = state?.jobs.some(j => j.status === 'queued' || j.status === 'running');
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => void load().catch(e => setError((e as Error).message)), 1600);
    return () => window.clearInterval(timer);
  }, [load, running]);

  async function action(task: () => Promise<void>) {
    if (pending) return;
    setPending(true);
    setError('');
    setNotice('');
    try { await task(); }
    catch (e) { setError((e as Error).message); }
    finally { setPending(false); }
  }

  function toggle(id: string, on: boolean) {
    setSelected(previous => {
      const next = new Set(previous);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  const replacement = () => ({target, conventions, mappings: JSON.parse(mappings), intentional_changes: JSON.parse(intent)});
  const enqueue = (name: string, data: Record<string, unknown> = {}) => action(async () => {
    await post(url + '/jobs', {action: name, request_id: crypto.randomUUID(), ...data});
    setEnablePR(false);
    await load();
    setNotice(actionNames[name] + ' queued.');
  });
  const save = (suffix: string, body: unknown) => request(url + suffix, {method: 'PUT', body: JSON.stringify(body)});
  const busy = pending || !!running;
  const captures = shown?.result?.captures;
  const comparisons = shown?.result?.comparisons;
  const isSelected = !!state?.selection.writes?.length;
  const accepted = state?.accepted.find(patch => patch.job_id === shown?.id);
  const failures = comparisons?.filter(row => row.status === 'different') ?? [];
  const sameTarget = target === shown?.target && !!target;
  const targetConfig = state?.targets.find(row => row.name === target);

  return <VStack gap={4} paddingBlock={3}>
    <Heading level={3}>{state?.workflow ?? 'Workflow migration'}</Heading>
    {error && <Text role="alert">{error}</Text>}
    {notice && <Text role="status">{notice}</Text>}
    {!state && !error && <Text role="status">Loading migration…</Text>}
    {state && <>
      <Text role="status">{state.baseline
        ? 'Approved legacy baseline · ' + state.baseline.source_commit
        : state.jobs.length ? actionNames[state.jobs[0].action] + ' · ' + statusText(state.jobs[0].status) : 'Not run'}</Text>
      {!!state.setup.length && <List header="Setup" density="compact">{state.setup.map(gap => <ListItem key={gap} label={gap}/>)}</List>}
      <VStack gap={2}>
        <TextInput label="Legacy entry point, helper, destination or table" value={query} onChange={setQuery}/>
        <HStack gap={2} wrap="wrap">
          <Button label="Find legacy writes" isDisabled={pending} onClick={() => action(async () => {
            const next = await request<Discovery>(url + '/sources?query=' + encodeURIComponent(query));
            setSources(next);
            setSelected(new Set(next.writes.filter(x => selected.has(x.id!)).map(x => x.id!)));
          })}/>
          <Button label="Save writes and find other callers" isDisabled={busy || !sources || !selected.size || !!state.baseline}
            onClick={() => action(async () => {
              await save('/selection', {query, selected: [...selected]});
              await load();
              setSources(undefined);
            })}/>
        </HStack>
        {sources && <SourceRows title="Candidate writes" rows={sources.writes} selected={selected}
          toggle={state.baseline ? undefined : toggle}/>}
        {isSelected && <SourceRows title="Saved writes" rows={state.selection.writes ?? []}/>}
        {(sources || state.selection.reverse) && <Collapsible trigger={<Text weight="semibold">Other callers, writers, schedulers and triggers</Text>}>
          <SourceRows title="Reverse source references" rows={sources?.reverse ?? state.selection.reverse ?? []}/>
        </Collapsible>}
      </VStack>
      <HStack gap={2} wrap="wrap">
        <Button label={actionNames.generate} isDisabled={busy || !isSelected || !!state.baseline} onClick={() => enqueue('generate')}/>
        <Button label={actionNames.baseline} isDisabled={busy || !state.scenarios.length || !!state.baseline || scenarioDraft !== null} onClick={() => enqueue('baseline')}/>
        {state.baseline && <Button label="Export legacy replay" isDisabled={pending} onClick={() => action(async () => {
          download('workflow-replay.json', serialize(await request(url + '/baseline/export')), 'application/json');
        })}/>}
      </HStack>
      {isSelected && !state.baseline && <Collapsible trigger={<Text weight="semibold">Behavior scenarios · {state.scenarios.length}</Text>}>
        <VStack gap={2}>
          <TextArea label="Editable scenario JSON" rows={12}
            description="Each scenario contains a name, category, seed, steps, observe and evidence_ids. Each input or fixture field has a name and JSON value."
            value={scenarioDraft ?? serialize({scenarios: state.scenarios})} onChange={setScenarioDraft}/>
          <HStack gap={2}>
            <Button label="Save scenarios" isDisabled={busy || scenarioDraft === null} onClick={() => action(async () => {
              await save('/scenarios', JSON.parse(scenarioDraft!));
              await load();
              setScenarioDraft(null);
            })}/>
            {scenarioDraft !== null && <Button label="Discard edits" onClick={() => setScenarioDraft(null)}/>}
          </HStack>
        </VStack>
      </Collapsible>}
      {!!state.jobs.length && <Collapsible defaultIsOpen trigger={<Text weight="semibold">Migration activity</Text>}>
        <List density="compact" hasDividers>
          {state.jobs.map(job => <ListItem key={job.id} label={actionNames[job.action]}
            description={job.error ?? statusText(job.status)}
            endContent={job.result_available && <Button size="sm" label="View result" isDisabled={pending} onClick={() => action(async () => {
              setShown(await request<Result>(url + '/jobs/' + encodeURIComponent(job.id)));
              setEnablePR(false);
              setPrReady(false);
              setRepairScenario('');
            })}/>}/>)}
        </List>
      </Collapsible>}
      {shown?.result?.scenarios !== undefined && <Collapsible trigger={<Text weight="semibold">Generated proposals</Text>}>
        <Json value={shown.result.scenarios}/>
      </Collapsible>}
      {captures && <VStack gap={2}>
        <Heading level={4}>Legacy observations · {shown.result?.source_commit}</Heading>
        {captures.map(row => <Observations key={row.name} name={row.name} status={row.stability?.status ?? 'not_run'}
          evidence={shown.result?.evidence?.[row.name]} first={row.stability?.first}
          differences={row.stability?.differences} differenceCount={row.stability?.difference_count} unknown={row.stability?.unknown} gap={row.gap}
          old={row.first} next={row.second} left="Legacy run 1" right="Legacy run 2"/>)}
        {!state.baseline && <VStack gap={2}>
          <TextArea label="ID and timestamp comparison rules" value={rules} onChange={setRules}
            description="Give the scenario name, observed field path, kind id or timestamp, and reason for each rule."/>
          <Button label="Approve immutable baseline" isDisabled={busy || captures.some(row => row.gap)} onClick={() => action(async () => {
            await post(url + '/baseline', {capture_id: shown.id, rules: JSON.parse(rules)});
            await load();
          })}/>
        </VStack>}
      </VStack>}
      {state.baseline && <VStack gap={3}>
        <Heading level={4}>Replacement</Heading>
        {state.targets.length ? <Selector label="Local Git target" value={target}
          options={state.targets.map(t => ({value: t.name, label: t.name}))}
          onChange={value => {setTarget(value ?? ''); setPrReady(false); setEnablePR(false)}}/>
          : <Text>Register a local Git target with the API operator to compare or generate a replacement.</Text>}
        {target && <>
          <TextArea label="Target conventions or accepted migration example" isOptional value={conventions} onChange={setConventions}/>
          <TextArea label="Approved business field mappings" description="Enter legacy and replacement paths such as /database/orders/order_total, with a reason for each mapping."
            value={mappings} onChange={setMappings}/>
          <TextArea label="Intentional behavior changes" isOptional value={intent} onChange={setIntent}
            description="Enter JSON with a scenario, observed field path, and reason for each intentional change."/>
          <HStack gap={2} wrap="wrap">
            <Button label={actionNames.compare} isDisabled={busy} onClick={() => action(async () => {
              await post(url + '/jobs', {action: 'compare', request_id: crypto.randomUUID(), replacement: replacement()});
              await load();
            })}/>
            <Button label={actionNames.generate_patch} isDisabled={busy} onClick={() => action(async () => {
              await post(url + '/jobs', {action: 'generate_patch', request_id: crypto.randomUUID(), replacement: replacement()});
              await load();
            })}/>
          </HStack>
        </>}
      </VStack>}
      {shown && comparisons && <VStack gap={3}>
        <Heading level={4}>Replacement observations · {shown.target}</Heading>
        {shown.result?.focused_validation && <Text>Focused repair check · {shown.result.focused_validation.name} · {statusText(shown.result.focused_validation.status)}</Text>}
        {!!shown.result?.intentional_changes?.length && <List header="Intentional behavior changes" hasDividers>
          {shown.result.intentional_changes.map(item => <ListItem key={item.scenario + item.path}
            label={item.scenario + ' · ' + item.path} description={<Text>{item.reason}</Text>}/>)}
        </List>}
        {comparisons.map(row => <Observations key={row.name} name={row.name} status={row.status} first={row.first}
          evidence={shown.result?.evidence?.[row.name]} differences={row.differences}
          differenceCount={row.difference_count} unknown={row.unknown} old={row.legacy} next={row.replacement} left="Approved legacy"
          right="Replacement" gap={row.gap} reproduce={row.reproduce}/>)}
        <HStack gap={2} wrap="wrap">
          <Button label="Download exact replay" isDisabled={pending} onClick={() => action(async () => {
            const bundle = await request(url + '/jobs/' + shown.id + '/replay');
            download('workflow-replay.json', serialize(bundle), 'application/json');
          })}/>
          {shown.result?.patch && sameTarget && <Button label="Compare this patch" isDisabled={busy}
            onClick={() => action(async () => {
              await post(url + '/jobs', {action: 'compare', request_id: crypto.randomUUID(),
                replacement: replacement(), prior_job_id: shown.id});
              await load();
            })}/>}
          {shown.result?.patch && <Button label="Download patch" onClick={() => download('migration.patch', shown.result!.patch!, 'text/x-diff')}/>}
        </HStack>
        <CodeBlock code={REPLAY} language="plaintext" hasLineNumbers={false} isWrapped/>
        {sameTarget && !!failures.length && <VStack gap={2}>
          <Selector label="Failing scenario to run first" value={repairScenario}
            options={failures.map(row => ({value: row.name, label: row.name}))}
            onChange={value => setRepairScenario(value ?? '')}/>
          <TextArea label="Focused repair instruction" value={repair} onChange={setRepair}/>
          <Button label={actionNames.repair} isDisabled={busy || !repair.trim() || !repairScenario}
            onClick={() => action(async () => {
              await post(url + '/jobs', {action: 'repair', request_id: crypto.randomUUID(),
                replacement: replacement(), prior_job_id: shown.id, scenario: repairScenario, repair});
              await load();
            })}/>
        </VStack>}
        {!!shown.result?.patch && (accepted ? <Text>Accepted patch · {accepted.reason}</Text> :
          <VStack gap={2}>
            <TextInput label="Patch acceptance reason" value={acceptReason} onChange={setAcceptReason}/>
            <Button label="Accept patch" isDisabled={pending || acceptReason.trim().length < 8}
              onClick={() => action(async () => {
                await post(url + '/accept-patch', {job_id: shown.id, reason: acceptReason});
                await load();
              })}/>
          </VStack>)}
        {accepted && sameTarget && targetConfig?.draft_pr_configured && (
          prReady ? <VStack gap={2}>
            <CheckboxInput label="Push the accepted patch to the configured remote and create a draft PR"
              value={enablePR} onChange={setEnablePR}/>
            <Button label={actionNames.draft_pr} isDisabled={busy || !enablePR}
              onClick={() => action(async () => {
                await post(url + '/jobs', {action: 'draft_pr', request_id: crypto.randomUUID(),
                  replacement: replacement(), prior_job_id: shown.id});
                setEnablePR(false);
                await load();
              })}/>
          </VStack> : <Button label="Check draft PR setup" isDisabled={pending} onClick={() => action(async () => {
            await request(url + '/pr-readiness?target=' + encodeURIComponent(target));
            setPrReady(true);
          })}/>
        )}
      </VStack>}
      {shown?.result?.url && <Link href={shown.result.url} isExternalLink>Open draft pull request</Link>}
    </>}
  </VStack>;
}
