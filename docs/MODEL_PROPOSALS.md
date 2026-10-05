# Optional model proposals

The deterministic planner remains the default. An optional model adapter is included for later use with OpenAI-compatible Chat Completions APIs.

Configure these environment variables only after choosing a provider:

- `AI_OS_MODEL_BASE_URL`: API base URL, including any `/v1` prefix
- `AI_OS_MODEL_NAME`: exact model identifier
- `AI_OS_MODEL_API_KEY`: API key for a remote provider; omitted for a local endpoint on localhost

AI-OS does not load a dotenv file, save the key, or contact the provider on startup. The explicit `python3 -m ai_os model-plan` command is the only invocation path. It requires a base URL, model name, and eligible tasks; remote endpoints also require an API key.

The model receives the current eligible task list and may recommend one existing task ID with a short reason. AI-OS rejects IDs outside that list. A proposal does not modify task state. Use `python3 -m ai_os proposal accept <proposal-id>` to explicitly start its task, or `proposal reject` to decline it. Both decisions are recorded in the event journal, and a proposal can be decided only once. Provider responses that are malformed or include extra fields fail closed.

The provider code uses Python's standard library and has a finite timeout. Its error messages do not include request headers or response bodies, so API keys are not printed through routine failures.
