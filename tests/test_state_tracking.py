from __future__ import annotations

import sys
import unittest
import importlib.util
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from usr.plugins.a0_scribe.helpers import state_events
from usr.plugins.a0_scribe.helpers import scribe_worker
from usr.plugins.a0_scribe.helpers import state_prompt
from usr.plugins.a0_scribe.helpers import pen_paper_writer


class StateTrackingTests(unittest.TestCase):
    def test_resolve_session_uses_existing_chat_workspace_without_focus(self):
        class FakeStore:
            def __init__(self):
                self.ensure_calls = []

            def read_focus(self, chat_id):
                return {}

            def list_sessions(self, chat_id=None, chat_only=False):
                return {
                    "sessions": [
                        {
                            "name": "scribe_quality_test_session",
                            "is_current_chat": True,
                            "is_chat_focus": False,
                        },
                        {
                            "name": "scribe_chat-1",
                            "is_current_chat": True,
                            "is_chat_focus": False,
                        },
                    ]
                }

            def ensure_session(self, name, chat_id):
                self.ensure_calls.append((name, chat_id))
                return {"ok": True, "created": False, "name": name}

        fake = FakeStore()
        original_store = pen_paper_writer._store
        pen_paper_writer._store = lambda: fake
        try:
            name = pen_paper_writer.resolve_session("chat-1", prefix="scribe", prefer_focus=True)
        finally:
            pen_paper_writer._store = original_store

        self.assertEqual(name, "scribe_quality_test_session")
        self.assertEqual(fake.ensure_calls, [("scribe_quality_test_session", "chat-1")])

    def test_resolve_session_prefers_user_named_scribe_workspace_over_exact_fallback(self):
        class FakeStore:
            def __init__(self):
                self.ensure_calls = []

            def read_focus(self, chat_id):
                return {}

            def list_sessions(self, chat_id=None, chat_only=False):
                return {
                    "sessions": [
                        {
                            "name": "scribe_chat-1",
                            "is_current_chat": True,
                            "is_chat_focus": False,
                        },
                        {
                            "name": "scribe_semantic_regression_003",
                            "is_current_chat": True,
                            "is_chat_focus": False,
                        },
                    ]
                }

            def ensure_session(self, name, chat_id):
                self.ensure_calls.append((name, chat_id))
                return {"ok": True, "created": False, "name": name}

        fake = FakeStore()
        original_store = pen_paper_writer._store
        pen_paper_writer._store = lambda: fake
        try:
            name = pen_paper_writer.resolve_session("chat-1", prefix="scribe", prefer_focus=True)
        finally:
            pen_paper_writer._store = original_store

        self.assertEqual(name, "scribe_semantic_regression_003")
        self.assertEqual(fake.ensure_calls, [("scribe_semantic_regression_003", "chat-1")])

    def test_normalize_observation_tags_errors_and_verification_results(self):
        event = state_events.normalize_observation(
            {
                "chat_id": "chat-1",
                "tool_name": "shell_command",
                "args_digest": "python -m py_compile helpers/sessions_store.py",
                "result_digest": "Exit code: 0",
            }
        )

        self.assertEqual(event["type"], "tool_result")
        self.assertIn("tool_call", event["tags"])
        self.assertIn("verification", event["tags"])
        self.assertIn("test_result", event["tags"])
        self.assertNotIn("tool_error", event["tags"])

    def test_normalize_observation_detects_py_compile_from_args_when_result_is_empty(self):
        event = state_events.normalize_observation(
            {
                "chat_id": "chat-1",
                "tool_name": "code_execution_tool",
                "args_digest": "command=python -m py_compile valid_test.py runtime=terminal",
                "result_digest": "(venv) root@container:/a0/usr/workdir#",
            }
        )

        self.assertIn("verification", event["tags"])
        self.assertIn("test_result", event["tags"])
        self.assertIn("compile_result", event["tags"])
        self.assertIn("py_compile passed", event["summary"])

    def test_normalize_observation_summarizes_py_compile_failure_concisely(self):
        event = state_events.normalize_observation(
            {
                "chat_id": "chat-1",
                "tool_name": "code_execution_tool",
                "args_digest": "None",
                "result_digest": (
                    "noise SIGNALS: python -m py_compile "
                    "definitely_missing_file_for_scribe_test.py [Errno 2] No such file "
                    "or directory"
                ),
            }
        )

        self.assertIn("tool_error", event["tags"])
        self.assertIn("verification", event["tags"])
        self.assertIn("py_compile failed", event["summary"])
        self.assertIn("definitely_missing_file_for_scribe_test.py", event["summary"])
        self.assertLessEqual(len(event["summary"]), 220)

    def test_source_read_does_not_activate_planning_from_file_contents(self):
        event = state_events.normalize_observation(
            {
                "chat_id": "chat-1",
                "tool_name": "code_execution_tool",
                "args_digest": "None",
                "result_digest": (
                    "=== ACTIVITY 1: Research-only ===\n"
                    "cat helpers/state_events.py\n"
                    "WORKFLOW_TAGS = {'planning': {'planning', 'design', 'architecture', "
                    "'decision_candidate'}, 'verification': {'verification'}}\n"
                ),
            }
        )

        self.assertIn("research", event["tags"])
        self.assertIn("file_read", event["tags"])
        self.assertNotIn("planning", event["tags"])
        self.assertNotIn("decision_candidate", event["tags"])

    def test_source_read_does_not_activate_debugging_from_file_contents(self):
        event = state_events.normalize_observation(
            {
                "chat_id": "chat-1",
                "tool_name": "code_execution_tool",
                "args_digest": (
                    "{'runtime': 'terminal', 'code': 'find /a0/usr/plugins/a0_scribe "
                    "-name \"state_events.py\" -print && cat "
                    "/a0/usr/plugins/a0_scribe/helpers/state_events.py | head -40'}"
                ),
                "result_digest": (
                    "/a0/usr/plugins/a0_scribe/helpers/state_events.py "
                    "WORKFLOW_TAGS = {\"debugging\": {\"tool_error\", \"error_log\", "
                    "\"test_failure\", \"unexpected_behavior\"}} "
                    "except Exception: return \"\" "
                    "SIGNALS: \"debugging\": {\"tool_error\", \"error_log\"} "
                    "except Exception: return \"\""
                ),
            }
        )

        self.assertIn("research", event["tags"])
        self.assertIn("file_read", event["tags"])
        self.assertNotIn("tool_error", event["tags"])
        self.assertNotIn("unexpected_behavior", event["tags"])
        self.assertNotIn("debugging", state_events.select_workflows(event, ["debugging"]))

    def test_truncated_source_read_signals_keep_command_context(self):
        event = state_events.normalize_observation(
            {
                "chat_id": "chat-1",
                "tool_name": "code_execution_tool",
                "args_digest": (
                    "{'runtime': 'terminal', 'session': 0, 'reset': False, "
                    "'code': 'find /a0/usr/plugins/a0_scribe -name \"state_events.py\" "
                    "-print && cat /a0/usr/plugins/a0_scribe/helpers/state_events.py | "
                    "head -40'} runtime=terminal"
                ),
                "result_digest": (
                    "/a0/usr/plugins/a0_scribe/helpers/state_events.py "
                    "\"\"\"Structured state events for the scribe State-DOX layer. "
                    "The scribe observes compact runtime events, tags them, and uses "
                    "those tags to activate per-session Pen & Paper workflow state "
                    "files. This module is deliberately pure so it can be tested "
                    "witho SIGNALS: \"debugging\": {\"tool_error\", \"error_log\", "
                    "\"test_failure\", \"unexpected_behavior\"}, value: Any, limit: "
                    "int = 700) -> str: try: text = value if isinstance(value, str) "
                    "else str(value) except Exception: return \"\""
                ),
            }
        )

        self.assertIn("research", event["tags"])
        self.assertIn("file_read", event["tags"])
        self.assertNotIn("tool_error", event["tags"])
        self.assertNotIn("unexpected_behavior", event["tags"])

    def test_directory_listing_with_test_path_does_not_activate_verification(self):
        event = state_events.normalize_observation(
            {
                "chat_id": "chat-1",
                "tool_name": "code_execution_tool",
                "args_digest": "None",
                "result_digest": "/a0/usr/workdir/scribe_test_env/state: session_state.yaml",
            }
        )

        self.assertIn("research", event["tags"])
        self.assertNotIn("verification", event["tags"])
        self.assertNotIn("test_result", event["tags"])

    def test_state_artifact_audit_does_not_route_to_research(self):
        event = state_events.normalize_observation(
            {
                "chat_id": "chat-1",
                "tool_name": "code_execution_tool",
                "args_digest": (
                    "tail -1 /a0/usr/pen_and_paper/sessions/active/"
                    "scribe_publish_contract_regression_002/state/events.jsonl && "
                    "cat /a0/usr/pen_and_paper/sessions/active/"
                    "scribe_publish_contract_regression_002/state/session_state.yaml"
                ),
                "result_digest": (
                    '{"tags":["code_review_trigger","tool_call"]}\n'
                    "active_workflows:\n- id: code_review_runtime\n"
                ),
            }
        )

        self.assertIn("state_audit", event["tags"])
        self.assertNotIn("research", event["tags"])
        self.assertEqual(state_events.select_workflows(event, state_events.workflow_ids()), [])

    def test_find_output_is_research_even_when_command_metadata_is_missing(self):
        event = state_events.normalize_observation(
            {
                "chat_id": "chat-1",
                "tool_name": "code_execution_tool",
                "args_digest": "None",
                "result_digest": (
                    "/a0/usr/workdir/scribe_test_env "
                    "/a0/usr/workdir/scribe_test_env/valid_test.py "
                    "/a0/usr/workdir/scribe_test_env/__pycache__/valid_test.cpython-313.pyc"
                ),
            }
        )

        self.assertIn("research", event["tags"])
        self.assertIn("file_read", event["tags"])
        self.assertNotIn("verification", event["tags"])

    def test_skill_listing_does_not_trigger_error_or_planning_from_names(self):
        event = state_events.normalize_observation(
            {
                "chat_id": "chat-1",
                "tool_name": "code_execution_tool",
                "args_digest": "None",
                "result_digest": (
                    "/a0/usr/workdir/skills: api-and-interface-design "
                    "debugging-and-error-recovery code-review-and-quality"
                ),
            }
        )

        self.assertIn("research", event["tags"])
        self.assertNotIn("tool_error", event["tags"])
        self.assertNotIn("planning", event["tags"])

    def test_latest_activity_ignores_old_signal_soup(self):
        event = state_events.normalize_observation(
            {
                "chat_id": "chat-1",
                "tool_name": "code_execution_tool",
                "args_digest": "None",
                "result_digest": (
                    "=== ACTIVITY 1: Research-only ===\n"
                    "cat helpers/state_events.py\n"
                    "planning research verification decision_candidate\n"
                    "SIGNALS: old tags: decision_candidate, planning, research, "
                    "test_failure, test_result, tool_error, verification\n"
                    "=== ACTIVITY 3: Intentional harmless failure ===\n"
                    "python -m py_compile definitely_missing_file_for_scribe_test.py\n"
                    "[Errno 2] No such file or directory: "
                    "'definitely_missing_file_for_scribe_test.py'\n"
                    "current_focus: old planning verification research dump"
                ),
            }
        )

        self.assertIn("tool_error", event["tags"])
        self.assertIn("verification", event["tags"])
        self.assertIn("test_failure", event["tags"])
        self.assertNotIn("research", event["tags"])
        self.assertNotIn("planning", event["tags"])
        self.assertNotIn("decision_candidate", event["tags"])

    def test_active_workflows_are_selected_from_event_tags(self):
        event = {
            "tags": ["tool_error", "test_result", "verification", "unexpected_behavior"],
        }

        active = state_events.select_workflows(event, ["debugging", "verification", "research"])

        self.assertEqual(active, ["debugging", "verification"])

    def test_build_state_envelope_includes_only_active_workflows(self):
        envelope = state_events.build_state_envelope(
            trigger_event={"id": 7, "tags": ["verification"], "summary": "tests passed"},
            recent_events=[{"id": 6, "summary": "ran compile"}],
            session_state={"session": {"goal": "ship state tracking"}},
            workflow_states={
                "verification": {"state": {"phase": "active"}},
                "debugging": {"state": {"phase": "inactive"}},
            },
            active_workflows=["verification"],
        )

        self.assertEqual(envelope["trigger_event"]["id"], 7)
        self.assertIn("verification", envelope["workflow_states"])
        self.assertNotIn("debugging", envelope["workflow_states"])
        self.assertEqual(
            envelope["active_skills"],
            [{"workflow": "verification", "skill": "scribe-workflow-verification"}],
        )

    def test_session_patch_links_active_workflows_to_scribe_skills(self):
        patch = state_events.session_patch_for_event(
            {"id": 9, "tags": ["verification"], "summary": "compiled"},
            ["verification"],
        )

        self.assertEqual(
            patch["active_workflows"][0]["skill"],
            "scribe-workflow-verification",
        )

    def test_session_patch_replaces_stale_active_workflows_with_current_focus(self):
        patch = state_events.session_patch_for_event(
            {"id": 10, "tags": ["research"], "summary": "read source"},
            ["research"],
            existing_active_workflows=[
                {
                    "id": "verification",
                    "state": "active",
                    "file": "workflows/verification.yaml",
                    "skill": "scribe-workflow-verification",
                    "reason": "previous verification",
                }
            ],
        )

        self.assertEqual(
            [item["id"] for item in patch["active_workflows"]],
            ["research"],
        )

    def test_session_patch_sets_next_action_for_verification_failure(self):
        patch = state_events.session_patch_for_event(
            {
                "id": 11,
                "tags": ["tool_error", "test_failure", "verification"],
                "summary": "code_execution_tool: py_compile failed for bad.py",
            },
            ["debugging", "verification"],
        )

        self.assertIn("next_action", patch["working_set"])
        self.assertIn("fix", patch["working_set"]["next_action"].lower())

    def test_observer_digest_preserves_signal_lines_in_long_output(self):
        observe_path = (
            ROOT
            / "usr"
            / "plugins"
            / "a0_scribe"
            / "extensions"
            / "python"
            / "tool_execute_after"
            / "_60_scribe_observe.py"
        )
        spec = importlib.util.spec_from_file_location("scribe_observe", observe_path)
        module = importlib.util.module_from_spec(spec)
        helpers_mod = types.ModuleType("helpers")
        extension_mod = types.ModuleType("helpers.extension")
        extension_mod.Extension = type("Extension", (), {})
        sys.modules.setdefault("helpers", helpers_mod)
        sys.modules.setdefault("helpers.extension", extension_mod)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        long_output = "noise " * 400
        long_output += " python -m py_compile definitely_missing_file_for_scribe_test.py "
        long_output += "[Errno 2] No such file or directory"

        digest = module._digest(long_output, limit=700)

        self.assertIn("py_compile", digest)
        self.assertIn("No such file", digest)

    def test_observer_digest_preserves_scribe_tags_in_long_output(self):
        observe_path = (
            ROOT
            / "usr"
            / "plugins"
            / "a0_scribe"
            / "extensions"
            / "python"
            / "tool_execute_after"
            / "_60_scribe_observe.py"
        )
        spec = importlib.util.spec_from_file_location("scribe_observe_tags", observe_path)
        module = importlib.util.module_from_spec(spec)
        helpers_mod = types.ModuleType("helpers")
        extension_mod = types.ModuleType("helpers.extension")
        extension_mod.Extension = type("Extension", (), {})
        sys.modules.setdefault("helpers", helpers_mod)
        sys.modules.setdefault("helpers.extension", extension_mod)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        long_output = "noise " * 400
        long_output += " SCRIBE_TAGS: code_review_trigger "
        long_output += "more noise " * 400

        digest = module._digest(long_output, limit=400)

        self.assertIn("SCRIBE_TAGS", digest)
        self.assertIn("code_review_trigger", digest)

    def test_observer_digest_prefers_latest_activity_block(self):
        observe_path = (
            ROOT
            / "usr"
            / "plugins"
            / "a0_scribe"
            / "extensions"
            / "python"
            / "tool_execute_after"
            / "_60_scribe_observe.py"
        )
        spec = importlib.util.spec_from_file_location("scribe_observe_latest", observe_path)
        module = importlib.util.module_from_spec(spec)
        helpers_mod = types.ModuleType("helpers")
        extension_mod = types.ModuleType("helpers.extension")
        extension_mod.Extension = type("Extension", (), {})
        sys.modules.setdefault("helpers", helpers_mod)
        sys.modules.setdefault("helpers.extension", extension_mod)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        old_output = (
            "=== ACTIVITY 1: Research-only ===\n"
            "cat helpers/state_events.py\n"
            "planning research verification decision_candidate\n"
        )
        latest_output = (
            "=== ACTIVITY 3: Intentional harmless failure ===\n"
            "python -m py_compile definitely_missing_file_for_scribe_test.py\n"
            "[Errno 2] No such file or directory\n"
        )

        digest = module._digest((old_output * 30) + latest_output, limit=400)

        self.assertIn("ACTIVITY 3", digest)
        self.assertIn("No such file", digest)
        self.assertNotIn("decision_candidate", digest)

    def test_observer_extracts_command_from_response_kvps(self):
        observe_path = (
            ROOT
            / "usr"
            / "plugins"
            / "a0_scribe"
            / "extensions"
            / "python"
            / "tool_execute_after"
            / "_60_scribe_observe.py"
        )
        spec = importlib.util.spec_from_file_location("scribe_observe_kvps", observe_path)
        module = importlib.util.module_from_spec(spec)
        helpers_mod = types.ModuleType("helpers")
        extension_mod = types.ModuleType("helpers.extension")
        extension_mod.Extension = type("Extension", (), {})
        sys.modules.setdefault("helpers", helpers_mod)
        sys.modules.setdefault("helpers.extension", extension_mod)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        class FakeResponse:
            message = "(venv) root@container:/a0/usr/workdir#"
            kvps = {
                "command": "python -m py_compile valid_test.py",
                "runtime": "terminal",
            }

        digest = module._args_digest(None, FakeResponse())

        self.assertIn("py_compile", digest)
        self.assertIn("valid_test.py", digest)

    def test_observer_extracts_command_from_current_tool_args(self):
        observe_path = (
            ROOT
            / "usr"
            / "plugins"
            / "a0_scribe"
            / "extensions"
            / "python"
            / "tool_execute_after"
            / "_60_scribe_observe.py"
        )
        spec = importlib.util.spec_from_file_location("scribe_observe_tool_args", observe_path)
        module = importlib.util.module_from_spec(spec)
        helpers_mod = types.ModuleType("helpers")
        extension_mod = types.ModuleType("helpers.extension")
        extension_mod.Extension = type("Extension", (), {})
        sys.modules.setdefault("helpers", helpers_mod)
        sys.modules.setdefault("helpers.extension", extension_mod)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        class FakeTool:
            args = {
                "command": "python -m py_compile valid_test.py",
                "runtime": "terminal",
            }

        class FakeLoopData:
            current_tool = FakeTool()

        class FakeAgent:
            loop_data = FakeLoopData()

        digest = module._args_digest(None, None, FakeAgent())

        self.assertIn("py_compile", digest)
        self.assertIn("valid_test.py", digest)

    def test_worker_prompt_includes_state_envelope_when_provided(self):
        messages = scribe_worker._build_prompt(
            [{"tool_name": "shell_command", "args_digest": "python -m unittest", "result_digest": "OK"}],
            "observe",
            state_envelope={
                "session_state": {"session": {"goal": "keep work state"}},
                "active_workflows": ["verification"],
                "workflow_states": {"verification": {"state": {"phase": "active"}}},
            },
        )

        self.assertIn("Scribe State Envelope", messages[1]["content"])
        self.assertIn("keep work state", messages[1]["content"])

    def test_model_session_patch_cannot_override_active_workflows(self):
        patch = scribe_worker._sanitize_model_session_patch(
            {
                "working_set": {"next_action": "keep going"},
                "active_workflows": [
                    {"id": "debugging"},
                    {"id": "planning"},
                    {"id": "verification"},
                    {"id": "implementation"},
                    {"id": "research"},
                ],
                "session": {"last_event_id": 999, "updated_by": "model"},
            }
        )

        self.assertNotIn("active_workflows", patch)
        self.assertEqual(patch["working_set"]["next_action"], "keep going")
        self.assertNotIn("last_event_id", patch["session"])

    def test_model_workflow_patches_are_limited_to_current_active_ids(self):
        patches = scribe_worker._filter_model_workflow_patches(
            {
                "debugging": {"state": {"phase": "active"}},
                "planning": {"state": {"phase": "active"}},
                "verification": {"state": {"phase": "active"}},
            },
            {"debugging"},
        )

        self.assertEqual(list(patches), ["debugging"])

    def test_worker_routing_uses_latest_routing_event_not_state_audit(self):
        active, trigger = scribe_worker._routing_decision(
            [
                {"id": 1, "tags": ["code_review_trigger", "tool_call"], "summary": "trigger"},
                {"id": 2, "tags": ["state_audit", "tool_call"], "summary": "audit"},
            ],
            ["code_review_runtime"],
            {"code_review_runtime": {"code_review_trigger"}},
        )

        self.assertEqual(active, ["code_review_runtime"])
        self.assertEqual(trigger["id"], 1)

    def test_render_working_state_prompt_is_compact_and_omits_events(self):
        rendered = state_prompt.render_working_state(
            {
                "session": {"goal": "preserve state", "last_event_id": 12},
                "working_set": {"current_focus": "wire ego injection", "next_action": "test"},
                "active_workflows": [{"id": "verification", "state": "active"}],
            },
            {"verification": {"state": {"phase": "active", "latest_result": "OK"}}},
            max_chars=1000,
        )

        self.assertIn("Pen & Paper working state", rendered)
        self.assertIn("preserve state", rendered)
        self.assertIn("verification", rendered)
        self.assertNotIn("events.jsonl", rendered)


class DataDrivenWorkflowMapTests(unittest.TestCase):
    """PR1a: state_events loads workflow maps from Pen & Paper with built-in fallback."""

    _BUILTINS = {"planning", "implementation", "debugging", "verification", "research"}

    def setUp(self):
        state_events.invalidate_workflow_cache()

    def tearDown(self):
        state_events.invalidate_workflow_cache()

    def _patch_pp(self, fn):
        original = state_events._pp_state_dox_templates
        state_events._pp_state_dox_templates = fn
        state_events.invalidate_workflow_cache()
        self.addCleanup(state_events.invalidate_workflow_cache)
        self.addCleanup(
            lambda: setattr(state_events, "_pp_state_dox_templates", original)
        )

    def test_workflow_ids_includes_runtime_published_template(self):
        self._patch_pp(
            lambda: [
                {
                    "id": "code_review",
                    "activation_tags": ["implementation", "file_change"],
                    "skill": "scribe-core",
                }
            ]
        )
        ids = state_events.workflow_ids()
        self.assertIn("code_review", ids)
        self.assertIn("debugging", ids)  # built-in still present

    def test_select_workflows_activates_runtime_id_from_tags(self):
        self._patch_pp(
            lambda: [
                {
                    "id": "code_review",
                    "activation_tags": ["implementation"],
                    "skill": "scribe-core",
                }
            ]
        )
        event = {"tags": ["implementation", "tool_call"]}
        active = state_events.select_workflows(event, state_events.workflow_ids())
        self.assertIn("code_review", active)

    def test_workflow_maps_fall_back_to_defaults_when_pp_raises(self):
        def boom():
            raise ImportError("a0_pen_paper missing")

        self._patch_pp(boom)
        self.assertEqual(set(state_events.workflow_ids()), self._BUILTINS)
        self.assertIn("tool_error", state_events.workflow_tags()["debugging"])

    def test_resolve_skill_falls_back_to_scribe_core_for_missing(self):
        self.assertEqual(
            state_events._resolve_skill("code_review", "nonexistent-skill"),
            "scribe-core",
        )

    def test_resolve_skill_keeps_existing_declared_skill(self):
        self.assertEqual(
            state_events._resolve_skill("debugging", "scribe-workflow-debugging"),
            "scribe-workflow-debugging",
        )

    def test_invalidate_then_reload_picks_up_new_template(self):
        self._patch_pp(lambda: [])
        self.assertNotIn("code_review", state_events.workflow_ids())
        state_events._pp_state_dox_templates = lambda: [
            {"id": "code_review", "activation_tags": ["implementation"], "skill": None}
        ]
        state_events.invalidate_workflow_cache()
        self.assertIn("code_review", state_events.workflow_ids())

    def test_normalize_observation_adds_runtime_activation_tag_from_explicit_signal(self):
        self._patch_pp(
            lambda: [
                {
                    "id": "code_review_runtime",
                    "activation_tags": ["code_review_trigger"],
                    "skill": "scribe-workflow-code-review-missing",
                }
            ]
        )

        event = state_events.normalize_observation(
            {
                "chat_id": "chat-1",
                "tool_name": "code_execution_tool",
                "args_digest": "echo 'SCRIBE_TAGS: code_review_trigger'",
                "result_digest": "SCRIBE_TAGS: code_review_trigger",
            }
        )
        active = state_events.select_workflows(event, state_events.workflow_ids())

        self.assertIn("code_review_trigger", event["tags"])
        self.assertIn("code_review_runtime", active)

    def test_normalize_observation_adds_runtime_activation_tag_from_non_read_only_keyword(self):
        self._patch_pp(
            lambda: [
                {
                    "id": "code_review_runtime",
                    "activation_tags": ["code_review_trigger"],
                    "skill": "scribe-workflow-code-review-missing",
                }
            ]
        )

        event = state_events.normalize_observation(
            {
                "chat_id": "chat-1",
                "tool_name": "code_execution_tool",
                "args_digest": "echo code_review_trigger",
                "result_digest": "code_review_trigger emitted",
            }
        )
        active = state_events.select_workflows(event, state_events.workflow_ids())

        self.assertIn("code_review_trigger", event["tags"])
        self.assertIn("code_review_runtime", active)

    def test_normalize_observation_does_not_add_runtime_tag_from_source_read(self):
        self._patch_pp(
            lambda: [
                {
                    "id": "code_review_runtime",
                    "activation_tags": ["code_review_trigger"],
                    "skill": "scribe-workflow-code-review-missing",
                }
            ]
        )

        event = state_events.normalize_observation(
            {
                "chat_id": "chat-1",
                "tool_name": "code_execution_tool",
                "args_digest": "cat /a0/usr/plugins/a0_scribe/helpers/state_events.py",
                "result_digest": "activation_tags = ['code_review_trigger']",
            }
        )
        active = state_events.select_workflows(event, state_events.workflow_ids())

        self.assertNotIn("code_review_trigger", event["tags"])
        self.assertNotIn("code_review_runtime", active)

    def test_fallback_to_scribe_core_is_visible_in_state_items(self):
        self._patch_pp(
            lambda: [
                {
                    "id": "code_review_runtime",
                    "activation_tags": ["code_review_trigger"],
                    "skill": "scribe-workflow-code-review-missing",
                }
            ]
        )
        event = {
            "id": 42,
            "tags": ["code_review_trigger", "tool_call"],
            "summary": "custom workflow trigger",
        }

        patch = state_events.session_patch_for_event(event, ["code_review_runtime"])
        envelope = state_events.build_state_envelope(
            trigger_event=event,
            recent_events=[event],
            session_state={},
            workflow_states={"code_review_runtime": {"state": {"phase": "active"}}},
            active_workflows=["code_review_runtime"],
        )

        self.assertEqual(patch["active_workflows"][0]["skill"], "scribe-core")
        self.assertIn("warning", patch["active_workflows"][0])
        self.assertEqual(envelope["active_skills"][0]["skill"], "scribe-core")
        self.assertIn("warning", envelope["active_skills"][0])


if __name__ == "__main__":
    unittest.main()
