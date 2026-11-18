"""Generate an editable delivery graph and compare deterministic staffing options."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from itertools import pairwise
from math import ceil, isfinite
from typing import Annotated, Literal

import networkx as nx
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

Scenario = Literal["optimistic", "likely", "pessimistic"]
SCENARIOS = ("optimistic", "likely", "pessimistic")
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Capacity = Annotated[Number, Field(ge=0, le=1)]
Effort = Annotated[Number, Field(gt=0)]

ASSUMPTIONS = [
    "The calendar uses Monday through Friday, with inclusive finish dates.",
    "A successor starts on a later workday than every predecessor's finish.",
    "Each activity occupies one person with all required skills until completion.",
    "Daily availability and existing commitments limit capacity. A fully booked workday breaks a continuous slot.",
    "The dependency-only path assumes full-time capacity and rounds each activity up to whole workdays.",
    "Ready activities use longest remaining dependency path, then activity ID. Available people use earliest finish, then person ID.",
    "Scheduled options are feasible estimates. Cost uses effort times the assigned person's daily rate in a common unit.",
]


def _calendar_date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Enter a date in YYYY-MM-DD format")
    return date.fromisoformat(value)


CalendarDate = Annotated[date, BeforeValidator(_calendar_date)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Citation(InputModel):
    chunk_id: Label
    excerpt: str


class Estimates(InputModel):
    optimistic: Effort | None = None
    likely: Effort | None = None
    pessimistic: Effort | None = None

    @model_validator(mode="after")
    def ordered(self):
        values = [getattr(self, s) for s in SCENARIOS if getattr(self, s) is not None]
        if values != sorted(values):
            raise ValueError(
                "Efforts must be ordered optimistic ≤ likely ≤ pessimistic"
            )
        return self


class Activity(InputModel):
    id: Label
    deliverable: Label
    related_ids: list[Label] = Field(default_factory=list)
    predecessors: list[Label] = Field(default_factory=list)
    skills: list[Label] | None = None
    effort: Estimates = Field(default_factory=Estimates)
    estimate_source: str | None = None
    estimate_confirmed: bool = False
    sources: list[Citation] = Field(default_factory=list)


class Commitment(InputModel):
    start: CalendarDate
    end: CalendarDate
    fraction: Capacity = 1

    @model_validator(mode="after")
    def ordered(self):
        if self.end < self.start:
            raise ValueError("Commitment end must be on or after its start")
        return self


class Person(InputModel):
    id: Label
    name: Label | None = None
    skills: list[Label] | None = None
    availability: Capacity | None = None
    available_from: CalendarDate | None = None
    available_until: CalendarDate | None = None
    commitments: list[Commitment] = Field(default_factory=list)
    daily_rate: Annotated[Number, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def ordered(self):
        if (
            self.available_from
            and self.available_until
            and self.available_until < self.available_from
        ):
            raise ValueError("Availability end must be on or after its start")
        return self


class Roster(InputModel):
    id: Label
    name: Label | None = None
    people: list[Person] | None = None


class Inputs(InputModel):
    start_date: CalendarDate | None = None
    activities: list[Activity] | None = None
    rosters: list[Roster] = Field(default_factory=list)
    scenarios: list[Scenario] | None = Field(default=None, min_length=1)


def _draft(kind, entity, deliverable, related_ids, predecessors=()):
    return Activity(
        id=f"{kind}:{entity['id']}",
        deliverable=deliverable,
        related_ids=sorted({entity["id"], *related_ids}),
        predecessors=sorted(set(predecessors)),
        sources=entity.get("evidence", []),
    )


def _generate(snapshot):
    """Callers can implement against a defined contract before its owner is built."""
    activities = []
    contracts_for = defaultdict(set)
    participants = defaultdict(set)
    operation_contract = {}
    components = snapshot.get("components", [])
    for contract in snapshot.get("contracts", []):
        owner = contract["owner_id"]
        task = _draft(
            "contract", contract, f"Define {contract['name']} contract", [owner]
        )
        activities.append(task)
        contracts_for[owner].add(task.id)
        for op in contract["operations"]:
            operation_contract[op["id"]] = task

    integrations = []
    for dep in snapshot.get("dependencies", []):
        caller, callee = dep["caller_id"], dep["callee_id"]
        contract = operation_contract[dep["operation_id"]]
        contracts_for[caller].add(contract.id)
        task = _draft(
            "integration",
            dep,
            f"Integrate {dep['reason']}",
            [caller, callee, *contract.related_ids],
            [f"component:{caller}", f"component:{callee}"],
        )
        activities.append(task)
        integrations.append((task.id, caller, callee))

    for component in components:
        cid = component["id"]
        task = _draft(
            "component",
            component,
            f"Implement {component['name']}",
            component.get("owns", []),
            contracts_for[cid],
        )
        activities.append(task)
        for uid in component.get("use_case_ids", []):
            participants[uid].add(cid)

    for walk in snapshot.get("walkthroughs", []):
        for step in walk["steps"]:
            participants[walk["use_case_id"]].update(
                ref for ref in (step.get("caller_id"), step.get("callee_id")) if ref
            )

    if activities:
        cases = snapshot.get("use_cases", [])
        validation_tasks = []
        covered = set()
        for case in cases:
            involved = participants[case["id"]]
            predecessors = {f"component:{cid}" for cid in involved}
            predecessors.update(
                t for t, a, b in integrations if a in involved and b in involved
            )
            if predecessors:
                covered.update(predecessors)
                validation_tasks.append(
                    _draft(
                        "validation",
                        case,
                        f"Validate {case['name']}",
                        involved,
                        predecessors,
                    )
                )
        uncovered = [
            a
            for a in activities
            if a.id not in covered and not a.id.startswith("contract:")
        ]
        if uncovered:
            validation_tasks.append(
                Activity(
                    id="validation:architecture:remaining",
                    deliverable="Validate remaining component behavior and integrations",
                    related_ids=sorted({i for a in uncovered for i in a.related_ids}),
                    predecessors=sorted(a.id for a in uncovered),
                )
            )
        activities.extend(validation_tasks)
    return sorted(activities, key=lambda a: a.id)


def _indexed(items, label):
    indexed = {}
    for item in items:
        if item.id in indexed:
            raise ValueError(f"Duplicate {label} ID: {item.id}")
        indexed[item.id] = item
    return indexed


def _graph(activities):
    graph = nx.DiGraph()
    graph.add_nodes_from(activities)
    for activity in activities.values():
        for pred in activity.predecessors:
            if pred not in activities:
                raise ValueError(
                    f"Activity {activity.id} has unknown predecessor {pred}"
                )
            graph.add_edge(pred, activity.id)
    if not nx.is_directed_acyclic_graph(graph):
        cycle = nx.find_cycle(graph)
        raise ValueError(
            "Activity dependency cycle: "
            + " -> ".join([a for a, _ in cycle] + [cycle[0][0]])
        )
    return graph


def _priority(graph, efforts):
    """Longest full-time path from each activity; reconstruct one deterministic path."""
    lengths, next_on_path = {}, {}
    for aid in reversed(list(nx.topological_sort(graph))):
        child = min(graph.successors(aid), key=lambda k: (-lengths[k], k), default=None)
        lengths[aid] = ceil(efforts[aid]) + (lengths[child] if child else 0)
        next_on_path[aid] = child
    aid = min(lengths, key=lambda k: (-lengths[k], k))
    path = []
    while aid is not None:
        path.append(aid)
        aid = next_on_path[aid]
    return lengths, path


def _day_index(day):
    """Number of weekdays strictly before this date. A weekend maps to next Monday."""
    weeks, offset = divmod(day.toordinal() - 1, 7)
    return 5 * weeks + min(offset, 5)


def _after_day(day):
    return _day_index(day) + (day.weekday() < 5)


def _iso(index):
    weeks, offset = divmod(index, 5)
    return date.fromordinal(7 * weeks + offset + 1).isoformat()


def _calendar(person, start):
    """Constant-capacity calendar segments, represented by half-open workday ranges."""
    first = max(
        start, _day_index(person.available_from) if person.available_from else start
    )
    stop = _after_day(person.available_until or date.max)
    if first >= stop:
        return []
    changes = defaultdict(Decimal)
    changes[first] = Decimal(str(person.availability))
    changes[stop] = Decimal(0)
    for commitment in person.commitments:
        a, b = (
            max(first, _day_index(commitment.start)),
            min(stop, _after_day(commitment.end)),
        )
        if a < b:
            fraction = Decimal(str(commitment.fraction))
            changes[a] -= fraction
            changes[b] += fraction
    boundaries = sorted(changes)
    capacity = Decimal(0)
    segments = []
    for a, b in pairwise(boundaries):
        capacity += changes[a]
        segments.append((a, b, max(capacity, Decimal(0))))
    return segments


def _slot(segments, first, effort):
    """Earliest uninterrupted slot, aggregating repeated weekdays within each segment."""
    start = None
    left = effort
    for a, b, capacity in segments:
        a = max(a, first)
        if a >= b:
            continue
        if capacity == 0:
            start, left = None, effort
            continue
        if start is None:
            start = a
        work = (b - a) * capacity
        if work >= left:
            return start, a + ceil(left / capacity) - 1
        left -= work
    return None


def _cost_number(amount):
    value = float(amount)
    if not isfinite(value):
        raise ValueError(
            "Cost exceeds the supported numeric range. Check the supplied daily rates."
        )
    return value


def _warning(code, message, ids):
    return {"code": code, "message": message, "activity_ids": ids}


def _schedule(run, graph, activities, people, start, efforts, lengths):
    calendars = {p.id: _calendar(p, start) for p in people.values()}
    qualified = {}
    for aid, a in activities.items():
        qualified[aid] = [
            p.id for p in people.values() if set(a.skills).issubset(p.skills)
        ]
        coverage = [
            pid for pid in qualified[aid] if _slot(calendars[pid], start, efforts[aid])
        ]
        if len(coverage) == 1:
            run["warnings"].append(
                _warning(
                    "single_person_coverage",
                    f"Only {coverage[0]} can cover {a.deliverable}.",
                    [aid],
                )
            )
    finishes, free = {}, {}
    ready = {a for a in graph if not graph.in_degree(a)}
    today = start
    while ready:
        # Dispatch in calendar order. Future reservations could otherwise delay a
        # higher-priority successor that becomes ready before the reservation.
        choices = []
        for aid in sorted(ready):
            earliest = max(
                (finishes[p] + 1 for p in graph.predecessors(aid)), default=start
            )
            for pid in qualified[aid]:
                first = max(today, earliest, free.get(pid, start))
                slot = _slot(calendars[pid], first, efforts[aid])
                if slot:
                    begin, finish = slot
                    choices.append((begin, -lengths[aid], aid, finish, pid))
        if not choices:
            run["status"] = "infeasible"
            for aid in sorted(ready):
                reason = (
                    "No single person has all required skills."
                    if not qualified[aid]
                    else "No qualified person has a continuous available slot for this effort."
                )
                run["blockers"].append(
                    {
                        "activity_id": aid,
                        "skills": activities[aid].skills,
                        "reason": reason,
                    }
                )
            return
        today, _, aid, finish, pid = min(choices)
        person = people[pid]
        cost = (
            None
            if person.daily_rate is None
            else _cost_number(efforts[aid] * Decimal(str(person.daily_rate)))
        )
        run["assignments"].append(
            {
                "activity_id": aid,
                "person_id": pid,
                "start_date": _iso(today),
                "finish_date": _iso(finish),
                "effort_days": float(efforts[aid]),
                "cost": cost,
            }
        )
        finishes[aid], free[pid] = finish, finish + 1
        ready.remove(aid)
        ready.update(
            s
            for s in graph.successors(aid)
            if all(p in finishes for p in graph.predecessors(s))
        )
    last = max(finishes.values())
    run.update(
        status="scheduled",
        start_date=run["assignments"][0]["start_date"],
        finish_date=_iso(last),
        makespan_days=last - start + 1,
    )
    costs = [a["cost"] for a in run["assignments"]]
    if all(c is not None for c in costs):
        run["total_cost"] = _cost_number(sum(Decimal(str(c)) for c in costs))


def plan(snapshot_dict, planning_inputs_dict):
    inputs = Inputs.model_validate(planning_inputs_dict)
    rows = (
        inputs.activities if inputs.activities is not None else _generate(snapshot_dict)
    )
    activities = _indexed(sorted(rows, key=lambda a: a.id), "activity")
    graph = _graph(activities)
    rosters = _indexed(inputs.rosters, "roster")
    scenarios = inputs.scenarios or [
        s
        for s in SCENARIOS
        if s == "likely" or any(getattr(a.effort, s) is not None for a in rows)
    ]
    if len(set(scenarios)) != len(scenarios):
        raise ValueError("Scenario names must be unique")

    missing, warnings, runs = [], [], []

    def request(path, message):
        missing.append({"path": path, "message": message})

    if not activities:
        request(
            "activities", "Add architecture deliverables or supply project activities."
        )
    if inputs.start_date is None:
        request("start_date", "Enter the project start date.")
    if not rosters:
        request(
            "rosters",
            "Supply the baseline roster with people, their skills and availability.",
        )
    for aid, activity in activities.items():
        if activity.skills is None:
            request(
                f"activities.{aid}.skills",
                f"Specify the required skills for {activity.deliverable}.",
            )
        for scenario in scenarios:
            if getattr(activity.effort, scenario) is None:
                request(
                    f"activities.{aid}.effort.{scenario}",
                    f"Estimate {scenario} effort in person-days for {activity.deliverable}.",
                )
        estimated = any(getattr(activity.effort, s) is not None for s in scenarios)
        if estimated and (
            not activity.estimate_confirmed or not activity.estimate_source
        ):
            warnings.append(
                _warning(
                    "unconfirmed_estimate",
                    f"Confirm the effort and record its source for {activity.deliverable}.",
                    [aid],
                )
            )

    ready_graph = bool(activities) and all(a.skills is not None for a in rows)
    for roster in rosters.values():
        people = _indexed(roster.people or [], f"person in roster {roster.id}")
        ready_roster = roster.people is not None
        if not ready_roster:
            request(
                f"rosters.{roster.id}.people",
                f"List the people on roster {roster.name or roster.id}.",
            )
        for pid, person in people.items():
            path = f"rosters.{roster.id}.people.{pid}"
            if person.skills is None:
                request(
                    path + ".skills", f"Specify the skills of {person.name or pid}."
                )
                ready_roster = False
            if person.availability is None:
                request(
                    path + ".availability",
                    f"Specify the fraction of each workday available for {person.name or pid}.",
                )
                ready_roster = False

        missing_rates = set()
        for scenario in scenarios:
            run = {
                "roster_id": roster.id,
                "scenario": scenario,
                "status": "missing_inputs",
                "critical_path": [],
                "critical_path_days": None,
                "start_date": None,
                "finish_date": None,
                "makespan_days": None,
                "total_cost": None,
                "assignments": [],
                "blockers": [],
                "warnings": [],
            }
            runs.append(run)
            raw = {aid: getattr(a.effort, scenario) for aid, a in activities.items()}
            if not raw or any(e is None for e in raw.values()):
                continue
            efforts = {aid: Decimal(str(e)) for aid, e in raw.items()}
            lengths, path = _priority(graph, efforts)
            run.update(critical_path=path, critical_path_days=lengths[path[0]])
            if len(path) >= 3:
                run["warnings"].append(
                    _warning(
                        "long_dependency_chain",
                        f"{len(path)} sequential activities span {lengths[path[0]]} full-time workdays.",
                        path,
                    )
                )
            if ready_graph and ready_roster and inputs.start_date is not None:
                _schedule(
                    run,
                    graph,
                    activities,
                    people,
                    _day_index(inputs.start_date),
                    efforts,
                    lengths,
                )
                missing_rates.update(
                    a["person_id"] for a in run["assignments"] if a["cost"] is None
                )
        for pid in sorted(missing_rates):
            request(
                f"rosters.{roster.id}.people.{pid}.daily_rate",
                f"Enter a daily rate for {people[pid].name or pid} to calculate cost.",
            )
    return {
        "activities": [a.model_dump(mode="json") for a in activities.values()],
        "assumptions": ASSUMPTIONS.copy(),
        "missing_inputs": missing,
        "warnings": warnings,
        "runs": runs,
    }
