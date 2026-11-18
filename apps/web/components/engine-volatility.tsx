'use client';
import { useEffect, useRef, useState } from 'react';
import { Collapsible } from '@astryxdesign/core/Collapsible';
import { Divider } from '@astryxdesign/core/Divider';
import { Text as SourceText } from '@astryxdesign/core/Text';
import {
  activeRun,
  entityNames,
  type Decision,
  type Evidence,
  type Question,
  type Revision,
  decisionBoundary,
} from '../lib/design-engine';
import { request } from '../lib/api';
import { Button, Heading, HStack, Text, TextArea, VStack } from './ui';
import { Citations, label } from './engine-evidence';
import { useEngine } from './engine-session';

export function answeredDecision(revision: Revision) {
  return revision.snapshot.volatilities.find((v) =>
    v.answers?.some((a) => a.base_revision_id === revision.parent_revision_id),
  );
}

function QuestionForm({
  question,
  decision,
  revision,
}: {
  question: Question;
  decision: Decision;
  revision: Revision;
}) {
  const { busy, state, start, error, loadError } = useEngine();
  const [editing, setEditing] = useState(false),
    [answer, setAnswer] = useState('');
  const pending = activeRun(state?.run ?? null);
  const disabled = busy || pending || !!loadError;
  return (
    <VStack gap={2}>
      <Text weight="semibold">{question.question}</Text>
      <Text>{question.decision_impact}</Text>
      {editing ? (
        <VStack
          as="form"
          gap={2}
          onSubmit={(event: React.FormEvent) => {
            event.preventDefault();
            if (!disabled && answer.trim())
              void start('revise', {
                base_revision_id: revision.id,
                decision_id: decision.id,
                question_id: question.id,
                answer: answer.trim(),
              });
          }}
        >
          {!!question.alternatives?.length && (
            <HStack wrap="wrap" gap={2}>
              {question.alternatives.map((option) => (
                <Button
                  key={option}
                  size="sm"
                  label={option}
                  isDisabled={disabled}
                  onClick={() => setAnswer(option)}
                />
              ))}
            </HStack>
          )}
          <TextArea
            label="Your answer"
            value={answer}
            onChange={setAnswer}
            maxLength={2400}
            isDisabled={disabled}
          />
          <HStack gap={2}>
            <Button type="submit" label="Submit answer" isDisabled={disabled || !answer.trim()} />
            <Button label="Cancel" variant="ghost" onClick={() => setEditing(false)} />
          </HStack>
          {pending && <Text role="status">Revising the decision…</Text>}
          {(error || loadError || state?.run?.error) && (
            <Text role="alert">{error || loadError || state?.run?.error}</Text>
          )}
        </VStack>
      ) : (
        <Button
          size="sm"
          label="Answer this question"
          isDisabled={disabled}
          onClick={() => setEditing(true)}
        />
      )}
    </VStack>
  );
}

function Passages({ items }: { items: Evidence[] }) {
  return (
    <VStack gap={1}>
      {items.map((item, i) => (
        <SourceText key={i}>{item.excerpt}</SourceText>
      ))}
      <Citations items={items} />
    </VStack>
  );
}

function DecisionDiff({ revision, decision }: { revision: Revision; decision: Decision }) {
  const { path } = useEngine();
  const section = useRef<HTMLElement>(null);
  useEffect(() => {section.current?.focus()}, []);
  const [parent, setParent] = useState<Revision | null>(null),
    [error, setError] = useState(''),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    request<Revision>(path + '/revisions/' + encodeURIComponent(revision.parent_revision_id!))
      .then((value) => {
        if (current) setParent(value);
      })
      .catch((e) => {
        if (current) setError(e.message);
      });
    return () => {
      current = false;
    };
  }, [path, revision.parent_revision_id, attempt]);
  const previous = parent?.snapshot.volatilities.find((d) => d.id === decision.id);
  const earlier = previous?.explanation;
  const changed =
    parent &&
    JSON.stringify(decisionBoundary(parent.snapshot, decision.id)) !==
      JSON.stringify(decisionBoundary(revision.snapshot, decision.id));
  return (
    <VStack gap={2} as="section" aria-label="Decision changes" ref={section} tabIndex={-1}>
      <Heading level={4}>Decision changes</Heading>
      {error ? (
        <>
          <Text role="alert">{error}</Text>
          <Button
            label="Retry comparison"
            onClick={() => {
              setError('');
              setAttempt((n) => n + 1);
            }}
          />
        </>
      ) : parent ? (
        <>
          <Text weight="semibold">
            {changed
              ? 'The boundary changed.'
              : decision.explanation?.uncertainty
                ? 'The provisional boundary is unchanged.'
                : 'The answer confirms the existing boundary.'}
          </Text>
          <Text>
            Previous owner ·{' '}
            {parent.snapshot.components.find((c) => c.owns.includes(decision.id))?.name || 'Unassigned'}
          </Text>
          {earlier && <Text>Previous approach · {earlier.approach}</Text>}
          <Text>
            Current owner ·{' '}
            {revision.snapshot.components.find((c) => c.owns.includes(decision.id))?.name || 'Unassigned'}
          </Text>
          {decision.explanation && <Text>Current approach · {decision.explanation.approach}</Text>}
          <Collapsible defaultIsOpen={false} trigger={<Text>Inspect previous revision</Text>}>
            <Text>{parent.id}</Text>
            {previous && (
              <DecisionDetails
                revision={parent}
                decision={previous}
                names={entityNames(parent.snapshot)}
                historical
              />
            )}
          </Collapsible>
        </>
      ) : (
        <Text role="status">Loading the previous boundary…</Text>
      )}
    </VStack>
  );
}

type DetailsProps = {
  revision: Revision;
  decision: Decision;
  names: Map<string, string>;
  historical?: boolean;
};
function DecisionDetails({ revision, decision: v, names, historical }: DetailsProps) {
  const s = revision.snapshot,
    why = v.explanation,
    owner = s.components.find((c) => c.owns.includes(v.id));
  const probes = s.change_probes.filter((p) => p.volatility_id === v.id);
  const findings = s.findings.filter((f) => Array.isArray(f.target_ids) && f.target_ids.includes(v.id));
  const questions = s.questions.filter((q) => q.target_ids?.includes(v.id));
  const evidence = [...(why?.evidence ?? []), ...(v.evidence ?? [])].filter(
    (c, i, all) => all.findIndex((ref) => ref.chunk_id === c.chunk_id && ref.excerpt === c.excerpt) === i,
  );
  const answers = v.answers ?? [];
  return (
    <VStack gap={3} paddingBlock={2}>
      {!historical && answers.some((a) => a.base_revision_id === revision.parent_revision_id) && (
        <DecisionDiff revision={revision} decision={v} />
      )}
      <Text type="supporting">
        {label(v.status)} · {v.driver}
      </Text>
      {evidence.length > 0 && (
        <VStack gap={1}>
          <Heading level={4}>Source evidence</Heading>
          <Passages items={evidence} />
        </VStack>
      )}
      {why && (
        <>
          <Text weight="semibold">What the evidence establishes</Text>
          <Text>{why.established}</Text>
          {why.uncertainty && (
            <>
              <Text weight="semibold">Still uncertain</Text>
              <Text>{why.uncertainty}</Text>
            </>
          )}
        </>
      )}
      <VStack gap={1}>
        <Heading level={4}>
          {owner?.provisional || why?.uncertainty ? 'Provisional boundary' : 'Proposed boundary'}
        </Heading>
        <Text>{owner?.name || 'Unassigned'}</Text>
        {why && (
          <>
            <Text weight="semibold">{why.approach}</Text>
            <Text>{why.rationale}</Text>
            <Text weight="semibold">Reconsider when</Text>
            <Text>{why.reconsider_when}</Text>
            {why.hypothetical_alternative && (
              <Text>Hypothetical alternative · {why.hypothetical_alternative}</Text>
            )}
          </>
        )}
      </VStack>
      {!!v.alternatives?.length && (
        <VStack gap={1}>
          <Text weight="semibold">Variations</Text>
          {v.alternatives.map((a, i) => (
            <Text key={i}>
              {a.hypothetical ? 'Hypothetical · ' : ''}
              {a.description}
            </Text>
          ))}
        </VStack>
      )}
      {!!v.use_case_ids?.length && (
        <Text>Use cases · {v.use_case_ids.map((id) => names.get(id) || id).join(', ')}</Text>
      )}
      {probes.map((p) => (
        <VStack key={p.id} gap={1}>
          <Heading level={4}>Change probe</Heading>
          <Text>{p.change}</Text>
          <Text>
            Predicted edits · {p.predicted_edit_ids.map((id) => names.get(id) || id).join(', ') || 'None'}
          </Text>
          {p.consumers?.map((c) => (
            <Text key={c.component_id}>
              Consumer · {names.get(c.component_id)} · {c.reason}
            </Text>
          ))}
          {p.leaks.map((c) => (
            <Text key={c.component_id}>
              Rule leak · {names.get(c.component_id)} · {c.reason}
            </Text>
          ))}
        </VStack>
      ))}
      {findings.map((f) => (
        <VStack key={f.id} gap={1}>
          <Text weight="semibold">{label(String(f.code))}</Text>
          <Text>{String(f.message)}</Text>
          <Citations items={f.evidence} />
        </VStack>
      ))}
      {answers.map((a) => (
        <VStack key={a.base_revision_id} gap={1}>
          <Text weight="semibold">Recorded answer</Text>
          <Text>{a.question}</Text>
          <Passages items={[a.evidence]} />
        </VStack>
      ))}
      {questions.map((q) =>
        historical ? (
          <Text key={q.id}>{q.question}</Text>
        ) : (
          <QuestionForm key={q.id} question={q} decision={v} revision={revision} />
        ),
      )}
    </VStack>
  );
}
export function DecisionRows({ revision, names, historical = false }: Omit<DetailsProps, 'decision'>) {
  const focused = historical ? undefined : answeredDecision(revision)?.id;
  return (
    <VStack gap={2}>
      <Heading level={3}>{historical ? 'Previous decisions' : 'Decisions and owners'}</Heading>
      {revision.snapshot.volatilities.map((v) => (
        <VStack key={v.id} gap={1}>
          <Collapsible defaultIsOpen={v.id === focused} trigger={<Text weight="semibold">{v.decision}</Text>}>
            <DecisionDetails revision={revision} decision={v} names={names} historical={historical} />
          </Collapsible>
          <Divider />
        </VStack>
      ))}
      {!revision.snapshot.volatilities.length && <Text color="secondary">None recorded</Text>}
    </VStack>
  );
}
