# Specialist registry

Twelve logical agents: Audit Orchestrator; Financial Data; External Audit; IFRS Reporting; UAE Corporate Tax; UAE VAT; Transfer Pricing; Pillar Two and DMTT; Internal Audit and GRC; Document Intelligence; TensorFlow.js ML Investigation; Quality and Professional Review.

The registry in `backend/app/modules/enterprise_ai/catalogue.py` defines identifiers, task recipes, allowlisted tools, required permissions, versioned contract names, prompt version, call/time/context/token limits, error handling and approval policy. Tools run in-process within the existing API/worker stack. This is typed deterministic delegation; no uncontrolled agent conversation or autonomous specialist legal reasoning is claimed. Quality checks source contracts and cannot grant professional approval.

`GET /api/v1/ai/agents` and `/ai/tools` expose safe metadata. Tool input/output contracts use strict Pydantic models. Twelve calls, depth one, parallelism one and 90 seconds per tool are the implementation limits. Explicit narrative generation uses the existing AI gateway and its token limits; the orchestrator has no model-controlled SQL, code, shell, network, training or deployment tool.
