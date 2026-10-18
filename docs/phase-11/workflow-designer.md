# Read-only workflow designer

React Flow displays ordered tool graphs with draggable nodes. Users can select a reviewed recipe, add distinct allowlisted retrieval tools, remove or move tools, validate the graph and save an immutable explicitly active read-only version with AI configuration permission. A separate command creates a run from that version. Templates cannot themselves be dispatched or stepped as runs.

Graph validation rejects unknown tools, duplicates, cycles/backwards edges, out-of-range indices and disconnected nodes. Every template node is permission-checked at save and again on execution. Maximum twelve nodes. Only ordered acyclic retrieval graphs are supported; arbitrary code, unbounded branching, mutation nodes and visual embedded professional approval/notification nodes are not implemented. Approval proposals use the separate controlled inbox.
