# Testing lens

Applies when the diff adds or changes logic, or touches `tests/`. Where the repo has its own rules for test layout, they take precedence.

- **TS-01** · Major · New or changed behaviour has no test — regressions will go unnoticed.
- **TS-02** · Major · Test depends on a live LLM, network or clock — it is flaky and costs money; mock the boundary.
- **TS-03** · Minor · Test depends on another test's order or shared mutable state — failures become order-dependent.
- **TS-04** · Minor · Code under review is hard to test (hidden state, constructed dependencies, no seam) — untestable code is usually mis-factored.
