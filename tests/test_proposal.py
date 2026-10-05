import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ai_os.proposal import eligible_tasks, model_proposal
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
        provider = OpenAICompatibleProvider(base_url="", model="", api_key="")
        with self.assertRaises(ProviderNotConfigured):
            provider.propose([{"task_id": "one"}])

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
        urlopen.return_value.open.return_value = FakeResponse({
            "choices": [{"message": {"content": json.dumps({"task_id": task_id, "reason": reason})}}]
        })
        result = provider.propose(eligible_tasks(self.store))
        self.assertEqual(result, {"task_id": task_id, "reason": reason})
        request = urlopen.return_value.open.call_args.args[0]
        self.assertIn("Bearer secret", request.headers["Authorization"])
        request_body = json.loads(request.data)
        self.assertEqual(request_body["temperature"], 0)
        self.assertEqual(request_body["response_format"], {"type": "json_object"})

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
        events = self.store.recent_events()
        logged = next(e for e in events if e["id"] == result["event_id"])
        self.assertEqual(logged["event_type"], "model_proposal.proposed")
        self.assertEqual(logged["payload"]["task_id"], task_id)

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
