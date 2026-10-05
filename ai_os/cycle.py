"""Optional local model planning cycle; suggestions are saved for human review."""

from __future__ import annotations
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from ai_os.providers.openai_compatible import (
    OpenAICompatibleProvider, ProviderError, ProviderNotConfigured,
)
from ai_os.proposal import model_proposal, pending_model_proposals
from ai_os.report import render_daily_brief
from ai_os.store import AIOS


def render_cycle(store: AIOS, provider: OpenAICompatibleProvider,
                 generated_at: datetime | None = None) -> tuple[str, dict[str, Any]]:
    local_now = generated_at or datetime.now().astimezone()
    brief = render_daily_brief(store, local_now).replace(
        "_This brief is generated locally. It does not contact a model or perform external actions._",
        "_The deterministic brief is local; the optional Ollama suggestion is separate. No external actions are performed._",
    )
    try:
        proposal = model_proposal(store, provider)
    except (ProviderError, ProviderNotConfigured) as exc:
        proposal = {"status": "unavailable", "error": str(exc)}
    lines = [brief.rstrip(), "", "## Local model suggestion"]
    if proposal["status"] == "proposed":
        item = proposal["proposal"]
        lines.extend([
            f"- Suggested task: {item['title']} ({item['project']})",
            f"- Reason: {item['reason']}",
            f"- Proposal ID: `{proposal['id']}`",
            "- Review: run `python3 -m ai_os proposals`; accept or reject explicitly.",
        ])
    elif proposal["status"] == "no_tasks":
        lines.append("- No new suggestion. Ready tasks already have proposals, or no eligible tasks are ready.")
    else:
        lines.append(f"- Model suggestion unavailable: {proposal['error']}")
    pending = pending_model_proposals(store)
    lines.extend(["", f"Pending proposals: {sum(p['status'] == 'pending' for p in pending)}", ""])
    return "\n".join(lines), proposal


def save_daily_cycle(store: AIOS, provider: OpenAICompatibleProvider,
                     directory: str | Path | None = None,
                     generated_at: datetime | None = None) -> tuple[Path, dict[str, Any]]:
    local_now = generated_at or datetime.now().astimezone()
    output_dir = Path(directory or (Path.home() / ".ai-os" / "briefs"))
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{local_now.date().isoformat()}-ai-os-cycle.md"
    content, proposal = render_cycle(store, provider, local_now)
    fd, temp_name = tempfile.mkstemp(prefix=".cycle-", suffix=".tmp", dir=output_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return destination, proposal
