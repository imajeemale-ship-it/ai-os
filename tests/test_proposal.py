import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ai_os.proposal import (
    decide_model_proposal, eligible_tasks, model_proposal, pending_model_proposals,
)
from ai_os.providers.openai_compatible import (
    OpenAICompatibleProvider, ProviderError, ProviderNotConfigured,
)
from ai_os.store import AIOS


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self):
        return json.dumps(self.payload).encode()


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AIOS(Path(self.temp.name) / "proposal.db")
        self.project = self.store.add_project("Project", "Goal")
        self.task = self.store.add_task(self.project["id"], "First task")

    def tearDown(self):
        self.temp.cleanup()

    def provider(self, task_id=None, reason="Best next step"):
        return OpenAICompatibleProvider(
            base_url="https://example.test/v1", model="test-model", api_key="secret"
        ), task_id or self.task["id"], reason

    def test_missing_config_fails_without_network(self):
        with patch.dict("os.environ", {
            "AI_OS_MODEL_BASE_URL": "", "AI_OS_MODEL_NAME": "", "AI_OS_MODEL_API_KEY": ""
        }), patch("ai_os.providers.openai_compatible.Path.home", return_value=Path(self.temp.name)):
            provider = OpenAICompatibleProvider()
            with self.assertRaises(ProviderNotConfigured):
                provider.propose([{"task_id": "one"}])

    @patch("ai_os.providers.openai_compatible.build_opener")
    def test_user_model_config_supplies_local_defaults_without_key(self, opener_factory):
        config = Path(self.temp.name) / ".ai-os"
        config.mkdir()
        (config / "model.json").write_text(json.dumps({
            "base_url": "http://127.0.0.1:11434/v1", "model": "qwen-local", "api_key": ""
        }))
        opener_factory.return_value.open.return_value = FakeResponse({
            "choices": [{"message": {"content": json.dumps({
                "task_id": self.task["id"], "reason": "Configured locally"
            })}}]
        })
        with patch("ai_os.providers.openai_compatible.Path.home", return_value=Path(self.temp.name)):
            provider = OpenAICompatibleProvider()
            result = provider.propose(eligible_tasks(self.store))
        self.assertEqual(result["task_id"], self.task["id"])
        self.assertEqual(provider.model, "qwen-local")
        request = opener_factory.return_value.open.call_args.args[0]
        self.assertNotIn("Authorization", request.headers)

    def test_model_config_rejects_non_string_values(self):
        config = Path(self.temp.name) / ".ai-os"
        config.mkdir()
        (config / "model.json").write_text('{"model": 7}')
        with patch("ai_os.providers.openai_compatible.Path.home", return_value=Path(self.temp.name)):
            with self.assertRaises(ProviderError):
                OpenAICompatibleProvider()

    @patch("ai_os.providers.openai_compatible.build_opener")
    def test_local_provider_status_checks_model_catalog_without_generation(self, opener_factory):
        provider = OpenAICompatibleProvider(
            base_url="http://127.0.0.1:11434/v1", model="qwen-local", api_key=""
        )
        opener_factory.return_value.open.return_value = FakeResponse({
            "data": [{"id": "qwen-local"}]
        })
        result = provider.status()
        self.assertEqual(result["availability"], "available")
        self.assertTrue(result["model_available"])
        self.assertFalse(result["credential_present"])
        request = opener_factory.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/v1/models")
        self.assertNotIn("Authorization", request.headers)

    @patch("ai_os.providers.openai_compatible.build_opener")
    def test_remote_provider_status_does_not_make_network_call_or_expose_key(self, opener_factory):
        provider, _, _ = self.provider()
        result = provider.status()
        self.assertEqual(result["availability"], "not_checked")
        self.assertTrue(result["credential_present"])
        self.assertNotIn("secret", json.dumps(result))
        opener_factory.assert_not_called()

    @patch("ai_os.providers.openai_compatible.build_opener")
    def test_local_provider_needs_no_api_key(self, opener_factory):
        provider = OpenAICompatibleProvider(
            base_url="http://127.0.0.1:11434/v1", model="local-model", api_key=""
        )
        task_id = self.task["id"]
        opener_factory.return_value.open.return_value = FakeResponse({
            "choices": [{"message": {"content": json.dumps({
                "task_id": task_id, "reason": "Local proposal"
            })}}]
        })
        result = provider.propose(eligible_tasks(self.store))
        self.assertEqual(result["task_id"], task_id)
        request = opener_factory.return_value.open.call_args.args[0]
        self.assertNotIn("Authorization", request.headers)

    @patch("ai_os.providers.openai_compatible.build_opener")
    def test_remote_http_endpoint_is_refused_before_network(self, opener_factory):
        provider = OpenAICompatibleProvider(
            base_url="http://provider.example/v1", model="test-model", api_key="secret"
        )
        with self.assertRaises(ProviderError):
            provider.propose(eligible_tasks(self.store))
        opener_factory.assert_not_called()

    @patch("ai_os.providers.openai_compatible.build_opener")
    def test_provider_returns_structured_recommendation(self, urlopen):
        provider, task_id, reason = self.provider()
        self.store.add_task(self.project["id"], "Second task", detail="private-notes-sentinel")
        urlopen.return_value.open.return_value = FakeResponse({
            "choices": [{"message": {"content": json.dumps({"task_id": task_id, "reason": reason})}}]
        })
        result = provider.propose(eligible_tasks(self.store))
        self.assertEqual(result, {"task_id": task_id, "reason": reason})
        request = urlopen.return_value.open.call_args.args[0]
        self.assertIn("Bearer secret", request.headers["Authorization"])
        request_body = json.loads(request.data)
        self.assertEqual(request_body["temperature"], 0)
        self.assertEqual(request_body["max_tokens"], 128)
        self.assertEqual(request_body["response_format"], {"type": "json_object"})
        self.assertNotIn("private-notes-sentinel", json.dumps(request_body))

    @patch("ai_os.providers.openai_compatible.build_opener")
    def test_external_task_id_is_rejected_and_never_mutates(self, urlopen):
        provider, _, _ = self.provider(task_id="invented-task")
        urlopen.return_value.open.return_value = FakeResponse({
            "choices": [{"message": {"content": json.dumps({
                "task_id": "invented-task", "reason": "Trust me"
            })}}]
        })
        result = model_proposal(self.store, provider)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(self.store.list_tasks()[0]["status"], "ready")

    @patch("ai_os.providers.openai_compatible.build_opener")
    def test_valid_proposal_does_not_start_task(self, urlopen):
        provider, task_id, reason = self.provider()
        urlopen.return_value.open.return_value = FakeResponse({
            "choices": [{"message": {"content": json.dumps({"task_id": task_id, "reason": reason})}}]
        })
        result = model_proposal(self.store, provider)
        self.assertEqual(result["status"], "proposed")
        self.assertEqual(result["proposal"]["task_id"], task_id)
        self.assertEqual(self.store.list_tasks()[0]["status"], "ready")
        pending = pending_model_proposals(self.store)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], result["id"])
        self.assertEqual(pending[0]["status"], "pending")
        events = self.store.recent_events()
        logged = next(e for e in events if e["id"] == result["event_id"])
        self.assertEqual(logged["event_type"], "model_proposal.proposed")
        self.assertEqual(logged["payload"]["task_id"], task_id)

    @patch("ai_os.providers.openai_compatible.build_opener")
    def test_existing_pending_proposal_prevents_duplicate_model_request(self, opener_factory):
        provider, task_id, reason = self.provider()
        opener_factory.return_value.open.return_value = FakeResponse({
            "choices": [{"message": {"content": json.dumps({"task_id": task_id, "reason": reason})}}]
        })
        first = model_proposal(self.store, provider)
        second = model_proposal(self.store, provider)
        self.assertEqual(first["status"], "proposed")
        self.assertEqual(second["status"], "no_tasks")
        opener_factory.return_value.open.assert_called_once()
        self.assertEqual(len(pending_model_proposals(self.store)), 1)

    @patch("ai_os.providers.openai_compatible.build_opener")
    def test_explicit_accept_starts_the_proposed_task_and_logs_decision(self, opener_factory):
        provider, task_id, reason = self.provider()
        opener_factory.return_value.open.return_value = FakeResponse({
            "choices": [{"message": {"content": json.dumps({"task_id": task_id, "reason": reason})}}]
        })
        proposal = model_proposal(self.store, provider)
        result = decide_model_proposal(self.store, proposal["id"], "accepted")
        self.assertEqual(result["task"]["status"], "in_progress")
        self.assertEqual(self.store.list_tasks()[0]["status"], "in_progress")
        self.assertEqual(pending_model_proposals(self.store), [])
        event = next(e for e in self.store.recent_events() if e["id"] == result["event_id"])
        self.assertEqual(event["event_type"], "model_proposal.accepted")
        with self.assertRaises(ValueError):
            decide_model_proposal(self.store, proposal["id"], "rejected")

    @patch("ai_os.providers.openai_compatible.build_opener")
    def test_explicit_reject_keeps_task_ready_and_logs_decision(self, opener_factory):
        provider, task_id, reason = self.provider()
        opener_factory.return_value.open.return_value = FakeResponse({
            "choices": [{"message": {"content": json.dumps({"task_id": task_id, "reason": reason})}}]
        })
        proposal = model_proposal(self.store, provider)
        result = decide_model_proposal(self.store, proposal["id"], "rejected")
        self.assertIsNone(result["task"])
        self.assertEqual(self.store.list_tasks()[0]["status"], "ready")
        event = next(e for e in self.store.recent_events() if e["id"] == result["event_id"])
        self.assertEqual(event["event_type"], "model_proposal.rejected")

    @patch("ai_os.providers.openai_compatible.build_opener")
    def test_malformed_or_extra_fields_fail_closed(self, urlopen):
        provider, task_id, _ = self.provider()
        urlopen.return_value.open.return_value = FakeResponse({
            "choices": [{"message": {"content": json.dumps({
                "task_id": task_id, "reason": "Go", "execute": True
            })}}]
        })
        with self.assertRaises(ProviderError):
            provider.propose(eligible_tasks(self.store))

    def test_empty_task_registry_does_not_call_provider(self):
        for task in self.store.list_tasks():
            self.store.set_task_status(task["id"], "done")
        provider, _, _ = self.provider()
        result = model_proposal(self.store, provider)
        self.assertEqual(result["status"], "no_tasks")


if __name__ == "__main__":
    unittest.main()
