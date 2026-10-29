# Agentic lens

Applies when the files call an LLM client, define tools, or contain an agent loop or graph node. Where the repo has its own rules for these areas, they take precedence.

- **AG-01** · Minor · Prompt text or tool schema inlined in business logic — prompts need versioning and review apart from code.
- **AG-02** · Major · Tool input or output not typed and validated — the model's arguments are untrusted data.
- **AG-03** · Major · LLM or HTTP call without a timeout, retry policy, or a cap on loop iterations — one bad response can hang or run up cost forever.
- **AG-04** · Major · Secret, full prompt or full model response written to logs — logs leak credentials and user data.
- **AG-05** · Minor · LLM client used directly instead of behind an interface — the provider cannot be swapped or mocked.
- **AG-06** · Blocker · Model output executed or interpolated into SQL, shell or code without validation — prompt injection becomes code execution.
