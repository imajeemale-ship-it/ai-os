# Optional model proposals

The deterministic planner and 3:00 PM local brief remain unchanged. AI-OS can optionally use an OpenAI-compatible model through `python3 -m ai_os model-plan` or `python3 -m ai_os daily-cycle`. No model is contacted on startup.

Provider settings are read from `~/.ai-os/model.json`; environment variables override file values:

- `AI_OS_MODEL_BASE_URL`: API base URL, including any `/v1` prefix
- `AI_OS_MODEL_NAME`: exact model identifier
- `AI_OS_MODEL_API_KEY`: API key for a remote provider; omitted for local Ollama

The model receives task titles, project names and goals, status, priority, and due dates. Free-form task details are excluded. It may recommend one existing ready task ID with a short reason. Tasks already in progress are excluded so daily runs do not repeatedly recommend work that has already started. AI-OS rejects IDs outside that list. A proposal does not modify task state. While a ready task has a pending proposal, subsequent daily cycles skip it to avoid duplicate review items.

Use `python3 -m ai_os provider-status` to check the configured model and local Ollama model catalog without generating text. Remote provider status is not probed and credentials are never displayed. Use `python3 -m ai_os proposals` to review pending proposals. Use `python3 -m ai_os proposal accept <proposal-id>` to explicitly start a task, or `proposal reject` to decline it. Both decisions are recorded in the event journal, and a proposal can be decided only once.

`python3 -m ai_os daily-cycle --save` writes a separate `YYYY-MM-DD-ai-os-cycle.md` file combining the unchanged deterministic brief with the optional model suggestion. Provider errors are recorded in that report without hiding the regular daily brief. To schedule this separately for 3:05 PM local time, run `python3 -m ai_os schedule cycle-install`; use `cycle-status` and `cycle-uninstall` to inspect or remove it. The existing 3:00 PM brief schedule is independent.

Provider responses that are malformed or include extra fields fail closed. The provider uses Python's standard library, a finite timeout, and sanitized error messages. It does not print API keys or response bodies.
