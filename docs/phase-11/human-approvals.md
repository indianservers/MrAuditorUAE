# Human approval gateway

The implemented action is create-draft-workpaper. A completed source collection proposes a title and editable narrative linked to collected approved record IDs. Its exact before value (no record), after values, requesting user, agent and source versions are hashed. An independent reviewer needs both AI decision and workpaper approval permissions. Decisions preserve reviewer, timestamp, comments and exact payload hash.

The requester executes only the approved exact payload. Both requester and reviewer permissions and dependencies are checked again. Execution creates an IN_PROGRESS workpaper through the existing audit service, verifies that state and stores one execution receipt. Retrying returns the same created record. Source reopening rejects the prior approval. The new workpaper still follows the original independent professional review chain.

There are no AI executors for financial posting, tax-treatment adoption, risk approval, approved note changes, finding closure, final publication, rule interpretation, ML deployment or external messaging. These remain governed domain workflows. Proposal inbox decisions are not substitutes for those approvals. Database step/extraction/match history is immutable; mutable proposal lifecycle is exposed only through controlled service operations.
