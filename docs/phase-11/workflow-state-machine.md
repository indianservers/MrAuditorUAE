# Durable execution

CREATED leads to RUNNING and then COMPLETED or PARTIALLY_COMPLETED. PAUSED, RESUMING, FAILED and CANCELLED are supported. Template configuration has a separate TEMPLATE_ACTIVE marker. Approval request state is stored separately. WAITING_FOR_DATA and an embedded graph approval node are not implemented.

Workflow state, immutable step events and hashes live in PostgreSQL. An advisory lock serializes each run. Every worker step commits independently. A crash before a step commit permits retry; committed steps are counted and not repeated. Redelivery reauthorizes the initiating user and validates source versions. Changing a source invalidates retrieval and continuation; start a new investigation rather than combine versions.

Explicit dispatch creates a queued event before Redis dispatch. Broker failure retains recoverable state. The scheduler outbox redispatches only explicitly queued work. Cancellation and pause are checked between steps, not inside an executing provider call. A worker is bounded to twelve steps; provider work remains in the existing gateway. The real worker and replay proof is in verification.json.
