"""Acceptance tests for spec M0 (a0_scribe side): the scribe calls Imperium only.

The client contract is:
  complete(messages, *, max_tokens, temperature, cfg=None) -> str | None
  health() -> dict[str, int]   reset() -> None   ping(cfg=None) -> dict

Stdlib only; a fake Imperium runs on 127.0.0.1. Run from usr/plugins/a0_scribe/:
    python -m unittest tests.test_imperium_client -v
"""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
import urllib.error
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from usr.plugins.a0_scribe.helpers import scribe_client  # noqa: E402

KEY_ENV = "A0_SCRIBE_TEST_IMPERIUM_KEY"
OK = (200, {"choices": [{"message": {"role": "assistant", "content": "[notes] ok"}}]})


class FakeImperium(BaseHTTPRequestHandler):
    script: list = []
    seen: list = []

    def _reply(self):
        status, payload = self.script.pop(0) if self.script else OK
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        if 300 <= status < 400:
            self.send_header("Location", "/redirect-target")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        self.seen.append(("POST", self.path, dict(self.headers), body))
        self._reply()

    def do_GET(self):
        self.seen.append(("GET", self.path, dict(self.headers), None))
        self._reply()

    def log_message(self, *args):
        pass


class ImperiumClientContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeImperium)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        port = cls.server.server_address[1]
        cls.base = f"http://127.0.0.1:{port}/harnesses/a0_scribe/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        FakeImperium.script, FakeImperium.seen = [], []
        scribe_client.reset()
        self.env = patch.dict(os.environ, {
            KEY_ENV: "test-key",
            "HTTP_PROXY": "http://127.0.0.1:9", "http_proxy": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9",
            "NO_PROXY": "", "no_proxy": "",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(scribe_client.reset)
        # A proxy in the container must never carry scribe content off-machine.
        bypass = patch("urllib.request.proxy_bypass", return_value=False)
        bypass.start()
        self.addCleanup(bypass.stop)

    def cfg(self, **imperium):
        return {
            "imperium": {
                "base_url": self.base,
                "api_key_env": KEY_ENV,
                "timeout_seconds": 5,
                "priority": "low",
                "circuit_threshold": 2,
                "circuit_cooldown_seconds": 60,
                **imperium,
            }
        }

    def call(self, **imperium):
        return scribe_client.complete(
            [{"role": "user", "content": "log"}], max_tokens=32, temperature=0.1, cfg=self.cfg(**imperium)
        )

    def test_one_request_to_the_pinned_harness_with_identity_and_local_only(self):
        self.assertEqual(self.call(), "[notes] ok")
        self.assertEqual(len(FakeImperium.seen), 1)
        method, path, headers, body = FakeImperium.seen[0]
        self.assertEqual((method, path), ("POST", "/harnesses/a0_scribe/v1/chat/completions"))
        self.assertEqual(headers.get("Authorization"), "Bearer test-key")
        self.assertEqual(headers.get("X-Agent-Id"), "a0_scribe")
        self.assertEqual(headers.get("X-Agent-Type"), "scribe")
        self.assertEqual(headers.get("X-Priority"), "low")
        self.assertEqual(headers.get("X-App-Id"), "a0_scribe")
        self.assertIs(body["routing"]["local_only"], True)
        self.assertEqual(body["routing"]["role"], "scribe")
        self.assertEqual(body["routing"]["task_type"], "documentation")
        self.assertEqual((body["max_tokens"], body["temperature"]), (32, 0.1))
        self.assertIs(body["stream"], False)
        self.assertEqual(scribe_client.health()["ok"], 1)

    def test_busy_lane_is_skipped_once_and_never_retried_elsewhere(self):
        FakeImperium.script = [(429, {"error": {"code": "queue_full"}})]
        self.assertIsNone(self.call())
        self.assertEqual(len(FakeImperium.seen), 1)
        self.assertEqual(scribe_client.health()["busy"], 1)

    def test_circuit_opens_after_consecutive_unavailable_answers(self):
        FakeImperium.script = [(503, {"error": {"code": "harness_model_unavailable"}})] * 2
        self.assertIsNone(self.call())
        self.assertIsNone(self.call())
        self.assertIsNone(self.call())  # circuit open: no request leaves the container
        self.assertEqual(len(FakeImperium.seen), 2)
        health = scribe_client.health()
        self.assertEqual((health["unavailable"], health["circuit_open_skips"]), (2, 1))

    def test_busy_answers_do_not_open_the_circuit(self):
        FakeImperium.script = [(429, {"error": {"code": "queue_full"}})] * 3
        for _ in range(3):
            self.assertIsNone(self.call())
        self.assertEqual(self.call(), "[notes] ok")
        self.assertEqual(scribe_client.health()["circuit_open_skips"], 0)

    def test_auth_errors_are_counted_not_hidden(self):
        FakeImperium.script = [(401, {"error": {"code": "unauthorized"}})]
        self.assertIsNone(self.call())
        self.assertEqual(scribe_client.health()["auth"], 1)

    def test_missing_key_sends_no_authorization_header(self):
        os.environ.pop(KEY_ENV, None)
        self.assertEqual(self.call(), "[notes] ok")
        self.assertNotIn("Authorization", FakeImperium.seen[0][2])

    def test_ping_checks_the_harness_models_endpoint(self):
        FakeImperium.script = [(200, {"object": "list", "data": [{"id": "scribe-model"}]})]
        result = scribe_client.ping(cfg=self.cfg())
        self.assertTrue(result["ok"])
        self.assertEqual(FakeImperium.seen[0][:2], ("GET", "/harnesses/a0_scribe/v1/models"))
        self.assertEqual(FakeImperium.seen[0][2]["Authorization"], "Bearer test-key")
        self.assertEqual(sum(scribe_client.health().values()), 0)

    def test_success_and_busy_reset_consecutive_failures(self):
        unavailable = (503, {"error": {"code": "harness_model_unavailable"}})
        for recovery in (OK, (429, {"error": {"code": "queue_full"}})):
            with self.subTest(recovery=recovery[0]):
                scribe_client.reset()
                FakeImperium.script = [unavailable, recovery, unavailable, OK]
                for _ in range(3):
                    self.call()
                self.assertEqual(self.call(), "[notes] ok")
                self.assertEqual(scribe_client.health()["circuit_open_skips"], 0)

    def test_cooldown_reopens_on_failure_and_closes_on_success(self):
        unavailable = (503, {"error": {"code": "harness_model_unavailable"}})
        with patch.object(scribe_client.time, "monotonic", return_value=100) as clock:
            FakeImperium.script = [unavailable, unavailable, unavailable, OK]
            self.call()
            self.call()
            clock.return_value = 159
            self.assertIsNone(self.call())
            self.assertEqual(scribe_client.ping(cfg=self.cfg())["status"], "circuit_open")
            self.assertEqual(len(FakeImperium.seen), 2)
            clock.return_value = 160
            self.assertIsNone(self.call())
            clock.return_value = 219
            self.assertIsNone(self.call())
            clock.return_value = 220
            self.assertEqual(self.call(), "[notes] ok")
            self.assertEqual(self.call(), "[notes] ok")
        self.assertEqual(len(FakeImperium.seen), 5)

    def test_transport_errors_are_counted_without_content(self):
        for error, counter in (
            (TimeoutError("secret-body"), "timeout"),
            (urllib.error.URLError(TimeoutError("secret-body")), "timeout"),
            (urllib.error.URLError(ConnectionRefusedError("secret-body")), "unavailable"),
        ):
            with self.subTest(counter=counter):
                scribe_client.reset()
                with patch("urllib.request.OpenerDirector.open", side_effect=error) as opened:
                    self.assertIsNone(self.call())
                    self.assertEqual(opened.call_count, 1)
                    self.assertEqual(opened.call_args.kwargs["timeout"], 5)
                self.assertEqual(scribe_client.health()[counter], 1)
                self.assertNotIn("secret-body", str(scribe_client.health()))

    def test_nonqueue_errors_and_redirects_never_retry(self):
        for status, payload, counter in (
            (403, {}, "auth"),
            (429, {"error": {"code": "rate_limit"}}, "error"),
            (429, b"not json", "error"),
            (500, {"content": "secret-body"}, "error"),
            (302, {}, "error"),
            (307, {}, "error"),
            (308, {}, "error"),
        ):
            with self.subTest(status=status, payload=payload):
                scribe_client.reset()
                FakeImperium.seen = []
                FakeImperium.script = [(status, payload)]
                self.assertIsNone(self.call())
                self.assertEqual(len(FakeImperium.seen), 1)
                self.assertEqual(scribe_client.health()[counter], 1)

    def test_malformed_success_is_not_a_note(self):
        for payload in (b"not json", {}, [], {"choices": []}, {"choices": [{"message": {"content": []}}]},
                        {"choices": [{"message": {"content": "  "}}]}):
            with self.subTest(payload=payload):
                scribe_client.reset()
                FakeImperium.script = [(200, payload)]
                self.assertIsNone(self.call())
                self.assertEqual(scribe_client.health()["invalid_response"], 1)

    def test_invalid_config_sends_nothing(self):
        for overrides in (
            {"base_url": self.base.replace("/harnesses/a0_scribe", "")},
            {"base_url": self.base + "?key=private"},
            {"timeout_seconds": 0}, {"timeout_seconds": float("nan")},
            {"circuit_threshold": 0}, {"circuit_threshold": "three"},
            {"priority": "urgent"},
        ):
            with self.subTest(overrides=overrides):
                scribe_client.reset()
                self.assertIsNone(self.call(**overrides))
                self.assertEqual(FakeImperium.seen, [])
                self.assertEqual(scribe_client.health()["error"], 1)

    def test_ping_rejects_empty_models_and_redirects_without_changing_counters(self):
        for status, payload in ((200, {}), (200, {"data": []}), (200, {"data": [None]}), (302, {}), (401, {})):
            FakeImperium.script = [(status, payload)]
            self.assertFalse(scribe_client.ping(cfg=self.cfg())["ok"])
        self.assertEqual(len(FakeImperium.seen), 5)
        self.assertEqual(sum(scribe_client.health().values()), 0)

    def test_reset_clears_counters_and_open_circuit(self):
        FakeImperium.script = [(503, {})] * 2
        self.call()
        self.call()
        scribe_client.reset()
        self.assertEqual(sum(scribe_client.health().values()), 0)
        self.assertEqual(self.call(), "[notes] ok")

    def test_default_config_is_loaded_when_not_supplied(self):
        with patch.object(scribe_client.config, "load_config", return_value=self.cfg()):
            self.assertEqual(scribe_client.complete([], max_tokens=1, temperature=0), "[notes] ok")



class WorkerIntegrationContract(unittest.TestCase):
    def test_effective_config_is_forwarded_and_failures_do_not_block_events(self):
        from usr.plugins.a0_scribe.helpers import budget, scribe_worker
        cfg = {"imperium": {"base_url": "isolated"}, "budget": {"max_calls_per_chat": 3}}
        budget.reset("client-worker-contract")
        self.addCleanup(budget.reset, "client-worker-contract")
        with patch.object(scribe_worker, "_record_state", return_value=None) as record, \
             patch.object(scribe_client, "complete", return_value=None) as complete, \
             patch.object(scribe_worker, "_write") as write:
            for _ in range(5):
                scribe_worker._process([{"chat_id": "client-worker-contract", "tool_name": "x"}], cfg)
            self.assertEqual(record.call_count, 5)
            self.assertEqual(complete.call_count, 3)
            self.assertIs(complete.call_args.kwargs["cfg"], cfg)
            write.assert_not_called()

    def test_private_keys_and_github_tokens_are_redacted_in_normalized_events(self):
        from usr.plugins.a0_scribe.helpers import state_events
        secrets = ["ghp_SYNTHETIC123", "gho_SYNTHETIC456", "github_pat_SYNTHETIC789", "SYNTHETIC_PRIVATE_MATERIAL"]
        raw = " ".join(secrets[:3]) + "\n-----BEGIN PRIVATE KEY-----\n" + secrets[3] + "\n-----END PRIVATE KEY-----"
        event = state_events.normalize_observation({"tool_name": "test", "args_digest": raw, "result_digest": raw})
        blob = json.dumps(event)
        for secret in secrets:
            self.assertNotIn(secret, blob)

if __name__ == "__main__":
    unittest.main()
