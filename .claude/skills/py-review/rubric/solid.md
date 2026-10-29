# SOLID lens

This lens always applies. Report a violation only when the changed code shows a concrete problem; a class that merely could be split is not a finding. Repo rules for the same area take precedence.

- **SRP-01** · Major · Class or function with more than one reason to change (for example parsing, business rule and persistence together) — a change to one job risks the others.
- **OCP-01** · Major · Long `if/elif` or `match` on a type or kind that grows with every new case — each new case edits tested code instead of adding to it.
- **LSP-01** · Major · Subclass or implementation that breaks the base contract (raises where the base does not, narrows accepted input, returns a different shape) — callers of the base type fail.
- **ISP-01** · Major · Protocol or base class so wide that implementers stub methods they do not need — clients depend on methods they never call.
- **DIP-01** · Major · High-level code constructs its concrete dependency (client, store, provider) instead of receiving it — it cannot be tested or swapped without patching.
