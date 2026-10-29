# Core lens

This lens always applies. Rules about formatting, naming, import order and types are out of scope when the repo says tools enforce them; a rule tagged `[ruff: codes]` is skipped for a file when any listed code is enabled for it.

Rule format: `ID · default severity · check — why`. Severity: Blocker = probable bug, vulnerability, data-loss risk; Major = clear design problem; Minor = small smell.

## Python best practice
- **PY-01** · Major · Mutable default argument (`[]`, `{}`, `set()`) — the default is shared across calls and leaks state. [ruff: B006]
- **PY-02** · Major · Bare `except:` or `except Exception` that swallows the error — hides failures and breaks cancellation. [ruff: E722, BLE001]
- **PY-03** · Minor · File, socket, lock or connection used without a context manager — leaks on the error path. [ruff: SIM115]
- **PY-04** · Minor · Wildcard import (`from x import *`) — hides where names come from. [ruff: F403]
- **PY-05** · Minor · Public function, class or module without a docstring — the contract is undocumented. [ruff: D100, D101, D102, D103, D104, D105, D106, D107]

## Clean code
- **CC-01** · Minor · Function longer than 30 lines — usually several jobs in one body.
- **CC-02** · Minor · More than 4 parameters — callers get order mistakes; group them or split the function. [ruff: PLR0913]
- **CC-03** · Minor · Nesting deeper than 3 levels — use early returns or extract a helper.
- **CC-04** · Minor · Magic number or string with no name — the reader cannot tell why the value is what it is. [ruff: PLR2004]
- **CC-05** · Minor · Boolean flag argument that switches behaviour — two behaviours in one function. [ruff: FBT001, FBT002]
- **CC-06** · Minor · Dead or commented-out code — git already keeps history. [ruff: ERA001]
- **CC-07** · Minor · Name that misleads about what the thing does or returns — wrong names cause wrong calls.
- **CC-08** · Minor · Duplicated block (3 or more near-identical blocks of 6 or more lines) — fixes must be repeated in every copy.
- **CC-09** · Minor (Major above 25) · Cognitive complexity above 15 — hard to read, hard to test.

## Patterns
- **PAT-01** · Minor · A named pattern (Strategy, Factory, Adapter, Repository) would remove a visible problem in the changed code — only when the problem is concrete.
- **PAT-02** · Minor · Abstraction, hierarchy or pattern with no second use or concrete benefit — over-engineering costs readers time.

## Security
- **SEC-01** · Blocker · Hardcoded secret, token or password — it ends up in git history. [ruff: S105, S106, S107]
- **SEC-02** · Blocker · `eval` or `exec` on data that is not a literal — arbitrary code execution. [ruff: S102, S307]
- **SEC-03** · Blocker · `subprocess` with `shell=True` or a shell string built from input — command injection. [ruff: S602, S604]
- **SEC-04** · Blocker · SQL built by string concatenation or f-string — SQL injection; use bound parameters. [ruff: S608]
- **SEC-05** · Major · MD5 or SHA-1 used for security (passwords, signatures, tokens) — broken or too fast to resist guessing. [ruff: S324]

## Estimated Sonar-style metrics
Emulated by Claude from reading the code, not measured; the repo's own limits win if set.

| Metric | Default |
|---|---|
| Cognitive complexity per function | ≤ 15 (Minor above, Major above 25) |
| Function length | ≤ 30 lines (soft) |
| Duplication | ≥ 3 near-identical blocks of ≥ 6 lines |
| Categories counted | bug, vulnerability, code smell, security hotspot |
| Security checks | hardcoded secrets, `eval`/`exec`, `shell=True`, SQL string concatenation, weak hashing |
