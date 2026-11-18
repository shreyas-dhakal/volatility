"""Reusable deterministic provider double. Patch pipeline.call_model only.

Upload PARKING_TEXT, DUPLICATE_RECEIPT_TEXT or FIXED_TARIFF_CODE normally so
all generated citations use real, project-scoped chunk IDs.
"""

PARKING_POLICY = "North charges hourly while South charges per visit."
COMMON = "Every site uses the same hourly formula. North sets its rate to two credits and South to five."
FORMULA = "Each site chooses its own charging formula."
AMBIGUOUS = "North charges two credits and South charges five credits."
QUESTION = (
    "Can each site choose its own charging formula, or does it only set the rate?"
)
UNSURE = "We are unsure whether each site chooses the formula."
GATES = "North uses a LiftCo gate and South uses a PivotWorks gate."
EXIT = "A driver pays the charge, receives a receipt and exits through the gate."
RECEIPT = "def receipt(amount):\n    return print_amount(amount)"
DUPLICATE = "def receipt(site, hours):\n    charge = hours * 2 if site == 'North' else 5\n    return print_amount(charge)"
GATE_FAILURE = "If the gate fails to open, the visit stays open."
PARKING_TEXT = f"{EXIT}\n{PARKING_POLICY}\n{GATES}\n{RECEIPT}\n{GATE_FAILURE}"
DUPLICATE_RECEIPT_TEXT = PARKING_TEXT.replace(RECEIPT, DUPLICATE)
FIXED_TARIFF_CODE = "def exit_parking(ticket):\n    charge = 500\n    print_receipt(charge)\n    open_gate(ticket)\n"
CORRECTION_TEXT = "All sites will use one tariff. Gate vendors still differ."


class ParkingModel:
    def __init__(self):
        self.stages = []

    async def __call__(self, stage, context):
        self.stages.append(stage)
        prior = context["prior"]
        chunks = context["chunks"]

        def cite(quote):
            return [
                {"chunk_id": c["id"], "excerpt": quote}
                for c in chunks
                if quote in c["text"]
            ]

        hints = context.get("prior_ids", [])

        def existing(collection, field, value, default, evidence=()):
            previous = [
                h["id"]
                for h in hints
                if h["collection"] == collection
                and (
                    h["links"].get(field) == value
                    or any(c in h["evidence"] for c in evidence)
                )
            ]
            if len(previous) == 1:
                default = previous[0]
            return next(
                (r["id"] for r in prior.get(collection, []) if r[field] == value),
                default,
            )

        def entity(identity, evidence, **fields):
            return dict(id=identity, evidence=evidence, **fields)

        code_only = bool(cite("charge = 500")) and not cite(PARKING_POLICY)
        policy = next(
            (item for item in (COMMON, FORMULA, AMBIGUOUS) if cite(item)),
            PARKING_POLICY,
        )
        price_evidence = cite("charge = 500" if code_only else policy)
        case_evidence = cite("def exit_parking(ticket):" if code_only else EXIT)
        gate_evidence = cite("open_gate(ticket)" if code_only else GATES)
        receipt_evidence = cite(
            "print_receipt(charge)" if code_only else RECEIPT
        ) or cite(DUPLICATE)
        correction = context.get("correction")
        changed = bool(correction and "one tariff" in correction["text"].lower())
        answer = (
            correction["text"] if correction and correction.get("question_id") else None
        )
        if answer:
            price_evidence += cite(answer)
        uncertain = policy == AMBIGUOUS and answer not in (COMMON, FORMULA)
        configure = policy == COMMON or policy == AMBIGUOUS and answer != FORMULA
        actor = existing("actors", "name", "Driver", "driver", case_evidence)
        case = existing("use_cases", "name", "Exit parking", "exit", case_evidence)
        price = existing(
            "volatilities", "decision", "Tariff policy", "tariff", price_evidence
        )
        vendor = existing(
            "volatilities", "decision", "Gate vendor", "vendor", gate_evidence
        )
        pricing = existing("components", "name", "Pricing", "pricing", price_evidence)
        manager = existing(
            "components", "name", "Exit coordinator", "exit-manager", case_evidence
        )
        receipt = existing("components", "name", "Receipt", "receipt", receipt_evidence)
        gate = existing("components", "name", "Gate access", "gate", gate_evidence)

        if stage == "inventory":
            findings = []
            for key, quotes in [
                ("tariff", price_evidence),
                ("gate", gate_evidence),
                ("receipt", receipt_evidence),
            ]:
                if quotes:
                    findings.append(
                        entity(
                            existing(
                                "implementation_findings",
                                "description",
                                quotes[0]["excerpt"],
                                "obs-" + key,
                                quotes,
                            ),
                            quotes,
                            title=key.title(),
                            description=quotes[0]["excerpt"],
                            kind="implementation" if code_only else "workflow",
                        )
                    )
            return {
                "actors": [
                    entity(
                        actor,
                        case_evidence,
                        kind="actor",
                        name="Driver",
                        description="Leaves a parking site.",
                    )
                ]
                if case_evidence
                else [],
                "implementation_findings": findings,
            }
        if stage == "use_cases":
            return {
                "use_cases": [
                    entity(
                        case,
                        case_evidence,
                        name="Exit parking",
                        actor_id=actor,
                        trigger="The driver requests exit.",
                        outcome="The visit ends.",
                        steps=[
                            "Calculate the fee",
                            "Provide a receipt",
                            "Open the gate",
                        ],
                        exceptions=[] if code_only else [GATE_FAILURE],
                        basis="inferred" if code_only else "stated_requirement",
                    )
                ]
            }
        question = existing("questions", "question", QUESTION, "formula-question")
        if stage == "volatility":
            return {
                "volatilities": [
                    entity(
                        price,
                        cite(correction["text"]) if changed else price_evidence,
                        decision="Tariff policy",
                        use_case_ids=[case],
                        driver="One tariff for all sites."
                        if changed
                        else "Tariff terms may differ by site.",
                        status="user_confirmed"
                        if changed or answer in (COMMON, FORMULA)
                        else "hypothesis"
                        if code_only
                        else "observed",
                        alternatives=[
                            {
                                "description": "Hourly fee",
                                "hypothetical": not (
                                    cite(PARKING_POLICY) or cite(COMMON)
                                ),
                            },
                            {
                                "description": "Fixed fee per visit",
                                "hypothetical": not cite(PARKING_POLICY),
                            },
                        ],
                    ),
                    entity(
                        vendor,
                        gate_evidence,
                        decision="Gate vendor",
                        driver="Installed gate equipment.",
                        status="hypothesis" if code_only else "observed",
                        use_case_ids=[case],
                        alternatives=[
                            {"description": "LiftCo", "hypothetical": code_only},
                            {"description": "PivotWorks", "hypothetical": code_only},
                        ],
                    ),
                ],
                "questions": [
                    entity(
                        question,
                        price_evidence,
                        question=QUESTION,
                        alternatives=[COMMON, FORMULA, UNSURE],
                        target_ids=[price],
                        decision_impact="Determines whether pricing needs a separate calculation boundary.",
                    )
                ]
                if uncertain
                else [],
                "retire": [
                    {
                        "id": question,
                        "reason": "The operator specified who chooses the formula.",
                    }
                ]
                if answer and not uncertain and prior.get("questions")
                else [],
            }
        owners = [
            ("Pricing", pricing, "price-op", "Quote charge", "Final amount"),
            ("Receipt", receipt, "receipt-op", "Issue receipt", "Issued receipt"),
            ("Gate access", gate, "gate-op", "Open gate", "Gate state"),
        ]

        if configure:
            owners = owners[1:]
        price_owner = manager if configure else pricing

        def operation(owner_id, fallback):
            prior_ops = [
                op
                for h in hints
                if h["collection"] == "contracts"
                and h["links"].get("owner_id") == owner_id
                for op in h["operation_ids"]
            ]
            if len(prior_ops) == 1:
                fallback = prior_ops[0]
            return next(
                (
                    c["operations"][0]["id"]
                    for c in prior.get("contracts", [])
                    if c["owner_id"] == owner_id
                ),
                fallback,
            )

        def dependency(owner_id):
            return existing("dependencies", "callee_id", owner_id, "calls-" + owner_id)

        if stage == "boundaries":
            components = []
            for name, identity, role, owns, description, evidence in [
                (
                    "Exit coordinator",
                    manager,
                    "manager",
                    [price] if configure else [],
                    "Coordinate payment, receipt, and exit.",
                    case_evidence,
                ),
                (
                    "Pricing",
                    pricing,
                    "engine",
                    [price],
                    "Calculate the shared tariff."
                    if changed
                    else "Calculate the charge for a visit.",
                    price_evidence,
                ),
                (
                    "Receipt",
                    receipt,
                    "client",
                    [],
                    "Print the supplied amount.",
                    receipt_evidence,
                ),
                (
                    "Gate access",
                    gate,
                    "resource_access",
                    [vendor],
                    "Hide vendor-specific gate commands.",
                    gate_evidence,
                ),
            ]:
                if configure and identity == pricing:
                    continue
                components.append(
                    entity(
                        identity,
                        evidence,
                        name=name,
                        role=role,
                        owns=owns,
                        responsibility=description,
                        rationale=description,
                        use_case_ids=[case],
                        provisional=(code_only or uncertain and identity == price_owner)
                        and bool(owns),
                    )
                )
            contracts = []
            deps = []
            for name, identity, fallback, action, output in owners:
                contract = existing(
                    "contracts", "owner_id", identity, "contract-" + identity
                )
                op = operation(identity, fallback)
                contracts.append(
                    entity(
                        contract,
                        [],
                        name=name + " contract",
                        owner_id=identity,
                        hides="Mechanism used to " + action.lower() + ".",
                        operations=[
                            {
                                "id": op,
                                "name": action,
                                "inputs": [
                                    "Final amount" if name == "Receipt" else "Visit"
                                ],
                                "outputs": [output],
                                "failures": ["Unavailable"],
                            }
                        ],
                    )
                )
                deps.append(
                    entity(
                        dependency(identity),
                        [],
                        caller_id=manager,
                        callee_id=identity,
                        operation_id=op,
                        reason="The exit requires " + output.lower() + ".",
                    )
                )
            established = price_evidence[0]["excerpt"]
            if changed or answer in (COMMON, FORMULA):
                established = correction["text"]
            elif uncertain:
                established = "The listed amounts differ."
            return {
                "explanations": [
                    {
                        "volatility_id": price,
                        "owner_id": price_owner,
                        "evidence": cite(correction["text"])
                        if changed
                        else price_evidence,
                        "established": established,
                        "uncertainty": "Whether each site chooses the formula."
                        if uncertain
                        else None,
                        "approach": "Configure the site rate"
                        if configure
                        else "Encapsulate the formula in Pricing",
                        "rationale": "The current owner can calculate charges with one formula and a site rate."
                        if configure
                        else "Callers need only the final amount while pricing selects the calculation.",
                        "reconsider_when": "A site needs its own charging formula."
                        if configure
                        else "Every site adopts a common formula.",
                        "hypothetical_alternative": "Give pricing its own calculation boundary."
                        if configure
                        else "Keep a configurable rate in the exit coordinator.",
                    },
                    {
                        "volatility_id": vendor,
                        "owner_id": gate,
                        "evidence": gate_evidence,
                        "established": gate_evidence[0]["excerpt"],
                        "uncertainty": None,
                        "approach": "Adapt the gate protocol",
                        "rationale": "Callers need only the outcome of opening the gate.",
                        "reconsider_when": "All gates expose the same stable protocol.",
                        "hypothetical_alternative": None,
                    },
                ],
                "components": components,
                "contracts": contracts,
                "dependencies": deps,
                "findings": [],
            }
        if stage == "walkthroughs":
            steps = [
                {
                    "caller_id": manager,
                    "callee_id": owner,
                    "operation_id": operation(owner, fallback),
                    "dependency_id": dependency(owner),
                    "coverage_gap": None,
                    "description": action,
                    "outcome": outcome,
                    "path": "main",
                }
                for _, owner, fallback, action, outcome in owners
            ]
            if configure:
                steps.insert(
                    0,
                    {
                        "caller_id": manager,
                        "callee_id": manager,
                        "operation_id": None,
                        "dependency_id": None,
                        "coverage_gap": None,
                        "description": "Apply the configured site rate.",
                        "outcome": "Final amount",
                        "path": "main",
                    },
                )
            if not code_only:
                steps.append(
                    steps[-1] | {"path": GATE_FAILURE, "outcome": "Visit stays open"}
                )
            walk = entity(
                existing("walkthroughs", "use_case_id", case, "trace"),
                [],
                use_case_id=case,
                steps=steps,
                outcome="The visit ends after the gate opens.",
            )
            duplicate = bool(cite(DUPLICATE))
            probe = entity(
                existing("change_probes", "volatility_id", price, "weekend"),
                receipt_evidence,
                volatility_id=price,
                change="Introduce a weekend cap.",
                predicted_owner_ids=[price_owner],
                predicted_edit_ids=[price_owner, receipt]
                if duplicate
                else [price_owner],
                consumers=[]
                if duplicate
                else [
                    {
                        "component_id": receipt,
                        "reason": "The receipt prints the supplied amount; the weekend cap changes only the calculation.",
                    }
                ],
                leaks=[
                    {"component_id": receipt, "reason": "Receipt computes the charge."}
                ]
                if duplicate
                else [],
            )
            gate_probe = entity(
                existing("change_probes", "volatility_id", vendor, "replace-gate"),
                gate_evidence,
                volatility_id=vendor,
                change="Replace gate equipment.",
                predicted_owner_ids=[gate],
                predicted_edit_ids=[gate],
                leaks=[],
            )
            issues = (
                [
                    entity(
                        existing(
                            "findings", "code", "duplicate_knowledge", "duplicate"
                        ),
                        cite(DUPLICATE),
                        code="duplicate_knowledge",
                        severity="warning",
                        target_ids=[price, receipt, price_owner],
                        message="Receipt independently calculates the charge in the current implementation.",
                    )
                ]
                if duplicate
                else []
            )
            return {
                "walkthroughs": [walk],
                "change_probes": [probe, gate_probe],
                "findings": issues,
            }
        if stage == "review":
            return {
                "explanations": [],
                "components": [],
                "contracts": [],
                "dependencies": [],
                "walkthroughs": [],
                "change_probes": [],
                "findings": [],
                "questions": [],
                "retire": [],
            }
        raise AssertionError(stage)
