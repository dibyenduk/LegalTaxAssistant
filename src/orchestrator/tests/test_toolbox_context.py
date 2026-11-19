"""Regression tests for trusted Foundry context on raw toolbox requests."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as orchestrator


class ToolboxContextTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "FOUNDRY_PROJECT_ENDPOINT": "https://example.services.ai.azure.com/api/projects/test",
            "DKWORKIQ_TOOLBOX_NAME": "test-toolbox",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        orchestrator._toolbox_tools_cache.clear()
        self.addCleanup(orchestrator._toolbox_tools_cache.clear)

    @staticmethod
    def response(data):
        response = MagicMock()
        response.json.return_value = data
        return response

    def test_platform_headers_reach_discovery_and_calls_for_all_namespaces(self):
        for namespace in ("WorkIQUser", "WorkIQMail", "WorkIQOneDrive", "WorkIQCopilot"):
            with self.subTest(namespace=namespace):
                tool_name = namespace + "___test"
                definition = {"name": tool_name, "inputSchema": {"type": "object"}}
                context = MagicMock()
                context.platform_headers.return_value = {"x-agent-foundry-call-id": "trusted-call"}
                with (
                    patch.object(orchestrator, "get_request_context", return_value=context),
                    patch.object(orchestrator, "_token_provider", return_value="workload-token"),
                    patch.object(orchestrator.httpx, "Client") as client_class,
                ):
                    client = client_class.return_value.__enter__.return_value
                    client.post.side_effect = [
                        self.response({"result": {"tools": [definition]}}),
                        self.response({"result": {"content": [{"type": "text", "text": "ok"}]}}),
                    ]
                    self.assertEqual(orchestrator._call_toolbox_mcp(tool_name, {}), "ok")
                    self.assertEqual(client.post.call_count, 2)
                    for request in client.post.call_args_list:
                        headers = request.kwargs["headers"]
                        self.assertEqual(headers["x-agent-foundry-call-id"], "trusted-call")
                        self.assertEqual(headers["Authorization"], "Bearer workload-token")
                        self.assertEqual(headers["Foundry-Features"], "Toolboxes=V1Preview")
                    context.platform_headers.assert_called_once_with()
                    self.assertEqual(
                        client.post.call_args.kwargs["json"]["params"]["_meta"]["tools"],
                        [definition],
                    )

    def test_cached_definitions_do_not_cache_request_context(self):
        tool_name = "WorkIQUser___GetMyDetails"
        context = MagicMock()
        context.platform_headers.side_effect = [
            {"x-agent-foundry-call-id": "first-call"},
            {"x-agent-foundry-call-id": "second-call"},
        ]
        with (
            patch.object(orchestrator, "get_request_context", return_value=context),
            patch.object(orchestrator, "_token_provider", return_value="workload-token"),
            patch.object(orchestrator.httpx, "Client") as client_class,
        ):
            client = client_class.return_value.__enter__.return_value
            client.post.side_effect = [
                self.response({"result": {"tools": [{"name": tool_name}]}}),
                self.response({"result": {"content": [{"type": "text", "text": "first"}]}}),
                self.response({"result": {"content": [{"type": "text", "text": "second"}]}}),
            ]
            self.assertEqual(orchestrator._call_toolbox_mcp(tool_name, {}), "first")
            self.assertEqual(orchestrator._call_toolbox_mcp(tool_name, {}), "second")
            self.assertEqual(client.post.call_count, 3)
            self.assertEqual(
                [call.kwargs["headers"]["x-agent-foundry-call-id"] for call in client.post.call_args_list],
                ["first-call", "first-call", "second-call"],
            )

    def test_context_failure_prevents_outbound_requests(self):
        with (
            patch.object(
                orchestrator, "get_request_context", side_effect=RuntimeError("Missing context")
            ),
            patch.object(orchestrator, "_token_provider", return_value="workload-token"),
            patch.object(orchestrator.httpx, "Client") as client_class,
        ):
            with self.assertRaisesRegex(RuntimeError, "Missing context"):
                orchestrator._call_toolbox_mcp("WorkIQUser___GetMyDetails", {})
            client_class.assert_not_called()

    def test_remote_errors_are_not_reported_as_success(self):
        with (
            patch.object(orchestrator, "get_request_context") as request_context,
            patch.object(orchestrator, "_token_provider", return_value="workload-token"),
            patch.object(orchestrator.httpx, "Client") as client_class,
        ):
            request_context.return_value.platform_headers.return_value = {}
            client = client_class.return_value.__enter__.return_value
            client.post.side_effect = [
                self.response({"result": {"tools": [{"name": "WorkIQUser___GetMyDetails"}]}}),
                self.response({"error": {"message": "Delegated context rejected"}}),
            ]
            result = orchestrator._call_toolbox_mcp("WorkIQUser___GetMyDetails", {})
            self.assertEqual(result, "Error from toolbox: Delegated context rejected")


if __name__ == "__main__":
    unittest.main()
