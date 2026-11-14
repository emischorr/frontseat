"""Tests for cli/frontseat-cli, standard library only.

Run from the repository root:

    python3 -m unittest discover -s cli/tests
"""

import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CLI_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontseat-cli")


def load_cli():
    loader = importlib.machinery.SourceFileLoader("frontseat_cli", CLI_PATH)
    spec = importlib.util.spec_from_loader("frontseat_cli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


cli = load_cli()

TOKEN = "fs_pat_secretsecretsecretsecretsecretsecret"
TASK = {
    "id": 42,
    "title": "Add CSV export",
    "description": "x",
    "state": "planning",
    "creator": {"id": 3, "username": "ada"},
    "inserted_at": "2026-11-14T15:40:00Z",
    "updated_at": "2026-11-14T15:40:00Z",
    "url": "http://frontseat.test/projects/12/tasks/42",
}


class StubServer:
    """A FrontSeat stand-in: records requests, answers from a route table."""

    def __init__(self):
        self.requests = []
        self.routes = {}
        self.delay = 0
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _handle(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode("utf-8") if length else None
                stub.requests.append({
                    "method": self.command,
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": body,
                })
                if stub.delay:
                    time.sleep(stub.delay)
                status, payload, headers = stub.routes.get(
                    (self.command, self.path),
                    (404, {"error": {"code": "not_found", "message": "Not found."}}, {}),
                )
                raw = payload if isinstance(payload, str) else json.dumps(payload)
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    for key, value in headers.items():
                        self.send_header(key, value)
                    self.end_headers()
                    self.wfile.write(raw.encode("utf-8"))
                except (BrokenPipeError, ConnectionResetError):
                    pass

            do_GET = _handle
            do_POST = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()

    def route(self, method, path, status, payload, headers=None):
        self.routes[(method, path)] = (status, payload, headers or {})

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.stub = StubServer()
        self.addCleanup(self.stub.close)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.home)
        os.makedirs(os.path.join(self.repo, "sub", "dir"))
        self.env = {"HOME": self.home, "FRONTSEAT_URL": self.stub.url, "FRONTSEAT_TOKEN": TOKEN}
        self.stub.route("GET", "/api/v1/me", 200,
                        {"data": {"id": 3, "username": "ada", "role": "member"}})

    def run_cli(self, *argv, env=None, cwd=None, stdin=""):
        stdout, stderr = io.StringIO(), io.StringIO()
        code = cli.main(list(argv), env=self.env if env is None else env,
                        cwd=cwd or self.repo, stdin=io.StringIO(stdin), stdout=stdout, stderr=stderr)
        self.assertNotIn(TOKEN, stdout.getvalue())
        self.assertNotIn(TOKEN, stderr.getvalue())
        return code, stdout.getvalue(), stderr.getvalue()

    def write(self, path, content, mode=None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content if isinstance(content, str) else json.dumps(content))
        if mode is not None:
            os.chmod(path, mode)
        return path

    def user_config(self, data, mode=0o600):
        return self.write(os.path.join(self.home, ".config", "frontseat", "config.json"), data, mode)


class ConfigurationTest(CliTestCase):
    def test_missing_url_is_a_configuration_error(self):
        code, _out, err = self.run_cli("whoami", env={"HOME": self.home, "FRONTSEAT_TOKEN": TOKEN})
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("No FrontSeat instance URL configured", err)
        self.assertIn("FRONTSEAT_URL", err)

    def test_missing_token_is_a_configuration_error(self):
        code, _out, err = self.run_cli("whoami", env={"HOME": self.home, "FRONTSEAT_URL": self.stub.url})
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("No API token configured", err)
        self.assertEqual(self.stub.requests, [])

    def test_env_beats_project_file_beats_user_config_for_the_url(self):
        self.user_config({"url": "http://user-config.invalid", "token": TOKEN})
        self.write(os.path.join(self.repo, ".frontseat"), {"project": 12, "url": self.stub.url})

        env = {"HOME": self.home}
        code, out, _err = self.run_cli("whoami", env=env)
        self.assertEqual(code, 0)
        self.assertIn("from %s" % os.path.join(self.repo, ".frontseat"), out)

        env["FRONTSEAT_URL"] = self.stub.url + "/"
        code, out, _err = self.run_cli("whoami", env=env)
        self.assertEqual(code, 0)
        self.assertIn("(from FRONTSEAT_URL)", out)

    def test_user_config_supplies_url_and_token(self):
        path = self.user_config({"url": self.stub.url, "token": TOKEN})
        code, out, err = self.run_cli("whoami", env={"HOME": self.home})
        self.assertEqual(code, 0, err)
        self.assertIn("Token:    from %s" % path, out)
        self.assertEqual(self.stub.requests[0]["headers"]["Authorization"], "Bearer " + TOKEN)
        self.assertEqual(err, "")

    def test_xdg_config_home_is_honoured(self):
        xdg = os.path.join(self.tmp.name, "xdg")
        self.write(os.path.join(xdg, "frontseat", "config.json"), {"url": self.stub.url, "token": TOKEN})
        os.chmod(os.path.join(xdg, "frontseat", "config.json"), 0o600)
        code, _out, _err = self.run_cli("whoami", env={"HOME": self.home, "XDG_CONFIG_HOME": xdg})
        self.assertEqual(code, 0)

    def test_env_token_beats_user_config(self):
        self.user_config({"token": "fs_pat_other"})
        code, out, _err = self.run_cli("whoami")
        self.assertEqual(code, 0)
        self.assertIn("Token:    from FRONTSEAT_TOKEN", out)
        self.assertEqual(self.stub.requests[0]["headers"]["Authorization"], "Bearer " + TOKEN)

    def test_warns_when_the_user_config_is_readable_by_others(self):
        self.user_config({"url": self.stub.url, "token": TOKEN}, mode=0o644)
        code, _out, err = self.run_cli("whoami", env={"HOME": self.home})
        self.assertEqual(code, 0)
        self.assertIn("readable by other users", err)
        self.assertIn("chmod 600", err)

    def test_project_precedence_flag_env_file(self):
        self.write(os.path.join(self.repo, ".frontseat"), {"project": 1})
        for project in (1, 2, 3):
            self.stub.route("GET", "/api/v1/projects/%d/tasks" % project, 200, {"data": []})

        self.run_cli("task", "list", cwd=os.path.join(self.repo, "sub", "dir"))
        self.assertEqual(self.stub.requests[-1]["path"], "/api/v1/projects/1/tasks")

        env = dict(self.env, FRONTSEAT_PROJECT="2")
        self.run_cli("task", "list", env=env)
        self.assertEqual(self.stub.requests[-1]["path"], "/api/v1/projects/2/tasks")

        self.run_cli("task", "list", "--project", "3", env=env)
        self.assertEqual(self.stub.requests[-1]["path"], "/api/v1/projects/3/tasks")

    def test_project_file_is_found_by_walking_up(self):
        self.write(os.path.join(self.repo, ".frontseat"), {"project": 12})
        code, out, _err = self.run_cli("whoami", cwd=os.path.join(self.repo, "sub", "dir"))
        self.assertEqual(code, 0)
        self.assertIn("Project:  12  (from %s)" % os.path.join(self.repo, ".frontseat"), out)

    def test_missing_project_is_a_configuration_error(self):
        code, _out, err = self.run_cli("task", "list")
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("No project selected", err)
        self.assertIn("project list", err)

    def test_invalid_project_ids_are_refused(self):
        code, _out, err = self.run_cli("task", "list", "--project", "frontseat")
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("Invalid project id", err)

    def test_a_token_in_the_project_file_is_an_error(self):
        for data in ({"project": 1, "token": "anything"}, {"project": 1, "auth": TOKEN}):
            self.write(os.path.join(self.repo, ".frontseat"), data)
            code, _out, err = self.run_cli("task", "list")
            self.assertEqual(code, cli.EXIT_CONFIG)
            self.assertIn("contains an API token", err)
        self.assertEqual(self.stub.requests, [])

    def test_a_malformed_project_file_is_an_error(self):
        self.write(os.path.join(self.repo, ".frontseat"), "{not json")
        code, _out, err = self.run_cli("task", "list")
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("Cannot read", err)

    def test_an_invalid_url_is_an_error(self):
        code, _out, err = self.run_cli("whoami", env=dict(self.env, FRONTSEAT_URL="frontseat.example.com"))
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("Invalid instance URL", err)

    def test_usage_errors_exit_2(self):
        code, _out, err = self.run_cli("task", "create")
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("--title", err)
        code, _out, _err = self.run_cli("bogus")
        self.assertEqual(code, cli.EXIT_CONFIG)


class CommandTest(CliTestCase):
    def setUp(self):
        super().setUp()
        self.write(os.path.join(self.repo, ".frontseat"), {"project": 12})

    def test_requests_carry_user_agent_and_bearer(self):
        self.run_cli("whoami")
        headers = self.stub.requests[0]["headers"]
        self.assertEqual(headers["User-Agent"], "frontseat-cli/" + cli.VERSION)
        self.assertEqual(headers["Authorization"], "Bearer " + TOKEN)
        self.assertEqual(headers["Accept"], "application/json")

    def test_whoami(self):
        code, out, _err = self.run_cli("whoami")
        self.assertEqual(code, 0)
        self.assertIn("URL:      %s  (from FRONTSEAT_URL)" % self.stub.url, out)
        self.assertIn("User:     ada  (id 3, member)", out)
        self.assertIn("Token:    from FRONTSEAT_TOKEN", out)

    def test_project_list(self):
        payload = {"data": [{"id": 12, "name": "frontseat"}, {"id": 13, "name": "website"}]}
        self.stub.route("GET", "/api/v1/projects", 200, payload)
        code, out, _err = self.run_cli("project", "list")
        self.assertEqual(code, 0)
        self.assertIn("12", out)
        self.assertIn("website", out)

    def test_task_list_with_state(self):
        self.stub.route("GET", "/api/v1/projects/12/tasks?state=review", 200, {"data": [TASK]})
        code, out, _err = self.run_cli("task", "list", "--state", "review")
        self.assertEqual(code, 0)
        self.assertIn("#42", out)
        self.assertIn("Add CSV export", out)

    def test_task_list_rejects_unknown_states_locally(self):
        code, _out, _err = self.run_cli("task", "list", "--state", "archived")
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertEqual(self.stub.requests, [])

    def test_json_prints_the_api_body_unchanged(self):
        raw = '{"data":[{"id":12,"name":"frontseat"}],  "extra":"kept"}'
        self.stub.route("GET", "/api/v1/projects", 200, raw)
        code, out, _err = self.run_cli("project", "list", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(out, raw + "\n")

        self.stub.route("GET", "/api/v1/projects/12/tasks", 200, {"data": [TASK]})
        code, out, _err = self.run_cli("task", "list", "--json")
        self.assertEqual(json.loads(out), {"data": [TASK]})

    def test_task_create_prints_id_and_url(self):
        self.stub.route("POST", "/api/v1/projects/12/tasks", 201, {"data": TASK})
        code, out, _err = self.run_cli("task", "create", "--title", "Add CSV export",
                                       "--description", "Short", "--work-type", "content")
        self.assertEqual(code, 0)
        self.assertEqual(out, "Created task #42: Add CSV export\n" + TASK["url"] + "\n")
        sent = json.loads(self.stub.requests[-1]["body"])
        self.assertEqual(sent, {"title": "Add CSV export", "description": "Short", "work_type": "content"})
        self.assertEqual(self.stub.requests[-1]["headers"]["Content-Type"], "application/json")

    def test_task_create_without_description_sends_only_the_title(self):
        self.stub.route("POST", "/api/v1/projects/12/tasks", 201, {"data": TASK})
        self.run_cli("task", "create", "--title", "Only a title")
        self.assertEqual(json.loads(self.stub.requests[-1]["body"]), {"title": "Only a title"})

    def test_markdown_descriptions_survive_from_file_and_stdin(self):
        markdown = "## Context\r\n\nTabs\tand ünïcödé, `code`, and\n\n- a list\n  - nested\n\n```\nblock\n```\n"
        self.stub.route("POST", "/api/v1/projects/12/tasks", 201, {"data": TASK})

        path = os.path.join(self.tmp.name, "desc.md")
        with open(path, "wb") as handle:
            handle.write(markdown.encode("utf-8"))
        self.run_cli("task", "create", "--title", "T", "--description-file", path)
        self.assertEqual(json.loads(self.stub.requests[-1]["body"])["description"], markdown)

        self.run_cli("task", "create", "--title", "T", "--description-file", "-", stdin=markdown)
        self.assertEqual(json.loads(self.stub.requests[-1]["body"])["description"], markdown)

    def test_description_flag_and_file_are_exclusive(self):
        code, _out, err = self.run_cli("task", "create", "--title", "T", "--description", "a",
                                       "--description-file", "-")
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("not both", err)

    def test_task_create_json(self):
        self.stub.route("POST", "/api/v1/projects/12/tasks", 201, {"data": TASK})
        code, out, _err = self.run_cli("task", "create", "--title", "T", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["data"]["url"], TASK["url"])


class HeadersTest(CliTestCase):
    def setUp(self):
        super().setUp()
        self.write(os.path.join(self.repo, ".frontseat"), {"project": 12})

    def test_env_headers_reach_the_server_with_bearer_and_user_agent_intact(self):
        env = dict(self.env, FRONTSEAT_HEADERS="P-Access-Token-Id: abc\nP-Access-Token: xyz")
        code, _out, err = self.run_cli("whoami", env=env)
        self.assertEqual(code, 0, err)
        headers = self.stub.requests[-1]["headers"]
        self.assertEqual(headers["P-Access-Token-Id"], "abc")
        self.assertEqual(headers["P-Access-Token"], "xyz")
        self.assertEqual(headers["Authorization"], "Bearer " + TOKEN)
        self.assertEqual(headers["User-Agent"], "frontseat-cli/" + cli.VERSION)

    def test_user_config_headers_are_sent_and_env_wins_over_them(self):
        self.user_config({"headers": {"P-Access-Token-Id": "cfg-id"}})
        base_env = {"HOME": self.home, "FRONTSEAT_URL": self.stub.url, "FRONTSEAT_TOKEN": TOKEN}

        code, _out, err = self.run_cli("whoami", env=base_env)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.stub.requests[-1]["headers"]["P-Access-Token-Id"], "cfg-id")

        env = dict(base_env, FRONTSEAT_HEADERS="P-Access-Token-Id: env-id")
        code, _out, err = self.run_cli("whoami", env=env)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.stub.requests[-1]["headers"]["P-Access-Token-Id"], "env-id")

    def test_malformed_header_line_is_a_configuration_error(self):
        env = dict(self.env, FRONTSEAT_HEADERS="no-colon-here")
        code, _out, err = self.run_cli("whoami", env=env)
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("Invalid header line", err)
        self.assertEqual(self.stub.requests, [])

    def test_invalid_header_name_is_a_configuration_error(self):
        env = dict(self.env, FRONTSEAT_HEADERS="Bad Name: value")
        code, _out, err = self.run_cli("whoami", env=env)
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("Invalid header name", err)
        self.assertEqual(self.stub.requests, [])

    def test_crlf_in_a_header_value_is_a_configuration_error(self):
        env = dict(self.env, FRONTSEAT_HEADERS="X-Custom: ab\rcd")
        code, _out, err = self.run_cli("whoami", env=env)
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("carriage return", err)
        self.assertEqual(self.stub.requests, [])

    def test_reserved_header_name_is_refused_case_insensitively(self):
        env = dict(self.env, FRONTSEAT_HEADERS="authorization: Bearer evil")
        code, _out, err = self.run_cli("whoami", env=env)
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("manages itself", err)
        self.assertEqual(self.stub.requests, [])

    def test_non_string_header_value_in_user_config_is_an_error(self):
        self.user_config({"headers": {"X-Custom": 123}})
        env = {"HOME": self.home, "FRONTSEAT_URL": self.stub.url, "FRONTSEAT_TOKEN": TOKEN}
        code, _out, err = self.run_cli("whoami", env=env)
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("must be an object whose values are strings", err)

    def test_headers_in_project_file_is_an_error(self):
        self.write(os.path.join(self.repo, ".frontseat"), {"project": 1, "headers": {"X": "y"}})
        code, _out, err = self.run_cli("whoami")
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn('contains "headers"', err)
        self.assertEqual(self.stub.requests, [])

    def test_whoami_lists_header_names_but_never_values(self):
        env = dict(self.env, FRONTSEAT_HEADERS="P-Access-Token-Id: abc\nP-Access-Token: xyz")
        code, out, _err = self.run_cli("whoami", env=env)
        self.assertEqual(code, 0)
        self.assertIn("Headers:  P-Access-Token-Id, P-Access-Token  (from FRONTSEAT_HEADERS)", out)
        self.assertNotIn("abc", out)
        self.assertNotIn("xyz", out)

    def test_whoami_shows_none_without_headers_configured(self):
        code, out, _err = self.run_cli("whoami")
        self.assertEqual(code, 0)
        self.assertIn("Headers:  none", out)


class ErrorTest(CliTestCase):
    def setUp(self):
        super().setUp()
        self.write(os.path.join(self.repo, ".frontseat"), {"project": 12})

    def test_401_exits_3_with_the_api_message(self):
        self.stub.route("GET", "/api/v1/me", 401,
                        {"error": {"code": "unauthorized", "message": "Missing, invalid or expired API token."}})
        code, out, err = self.run_cli("whoami")
        self.assertEqual(code, cli.EXIT_AUTH)
        self.assertEqual(out, "")
        self.assertIn("error: Missing, invalid or expired API token.", err)
        self.assertIn("Account -> API tokens", err)
        self.assertIn("FRONTSEAT_TOKEN", err)

    def test_license_required_exits_4(self):
        message = "API access requires a FrontSeat license that includes the api_access feature."
        self.stub.route("GET", "/api/v1/projects", 403, {"error": {"code": "license_required", "message": message}})
        code, _out, err = self.run_cli("project", "list")
        self.assertEqual(code, cli.EXIT_LICENSE)
        self.assertIn("error: " + message, err)

    def test_unknown_project_exits_5_with_its_source(self):
        code, _out, err = self.run_cli("task", "list")
        self.assertEqual(code, cli.EXIT_NOT_FOUND)
        self.assertIn("Project 12", err)
        self.assertIn(".frontseat", err)
        self.assertIn("project list", err)

    def test_validation_errors_exit_1_with_fields(self):
        self.stub.route("POST", "/api/v1/projects/12/tasks", 422, {"error": {
            "code": "validation_failed", "message": "The request has invalid fields.",
            "fields": {"title": ["can't be blank"]}}})
        code, _out, err = self.run_cli("task", "create", "--title", "")
        self.assertEqual(code, cli.EXIT_API)
        self.assertIn("The request has invalid fields.", err)
        self.assertIn("title: can't be blank", err)

    def test_setup_required_exits_1(self):
        self.stub.route("GET", "/api/v1/me", 503,
                        {"error": {"code": "setup_required", "message": "This FrontSeat instance is not set up yet."}})
        code, _out, err = self.run_cli("whoami")
        self.assertEqual(code, cli.EXIT_API)
        self.assertIn("/setup", err)

    def test_server_errors_and_non_json_exit_1(self):
        self.stub.route("GET", "/api/v1/me", 500, {"error": {"code": "internal_error", "message": "Internal Server Error."}})
        code, _out, err = self.run_cli("whoami")
        self.assertEqual(code, cli.EXIT_API)
        self.assertIn("HTTP 500", err)

        self.stub.route("GET", "/api/v1/me", 502, "<html>Bad Gateway</html>")
        code, _out, err = self.run_cli("whoami")
        self.assertEqual(code, cli.EXIT_API)
        self.assertIn("Unexpected response", err)

    def test_redirects_are_not_followed(self):
        self.stub.route("GET", "/api/v1/me", 301, "", {"Location": "https://elsewhere.invalid/api/v1/me"})
        code, _out, err = self.run_cli("whoami")
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("redirects to https://elsewhere.invalid", err)
        self.assertEqual(len(self.stub.requests), 1)

    def test_redirect_hint_mentions_frontseat_headers(self):
        self.stub.route("GET", "/api/v1/me", 302, "", {"Location": "https://proxy.invalid/login"})
        code, _out, err = self.run_cli("whoami")
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("FRONTSEAT_HEADERS", err)
        self.assertIn("currently: none", err)

        env = dict(self.env, FRONTSEAT_HEADERS="P-Access-Token-Id: abc")
        code, _out, err = self.run_cli("whoami", env=env)
        self.assertEqual(code, cli.EXIT_CONFIG)
        self.assertIn("currently: from FRONTSEAT_HEADERS", err)

    def test_non_json_401_hint_mentions_frontseat_headers(self):
        self.stub.route("GET", "/api/v1/me", 401, "<html>login</html>")
        code, _out, err = self.run_cli("whoami")
        self.assertEqual(code, cli.EXIT_API)
        self.assertIn("Unexpected response", err)
        self.assertIn("FRONTSEAT_HEADERS", err)
        self.assertIn("currently: none", err)

    def test_connection_failure_exits_6(self):
        self.stub.close()
        code, _out, err = self.run_cli("whoami")
        self.assertEqual(code, cli.EXIT_CONNECTION)
        self.assertIn("Could not reach FrontSeat at %s/api/v1/me" % self.stub.url, err)
        self.assertIn("connection refused", err)
        self.assertNotIn("Errno", err)
        self.assertIn("from FRONTSEAT_URL", err)

    def test_unresolvable_host_exits_6(self):
        code, _out, err = self.run_cli("whoami", env=dict(self.env, FRONTSEAT_URL="http://frontseat.invalid"))
        self.assertEqual(code, cli.EXIT_CONNECTION)
        self.assertIn("http://frontseat.invalid/api/v1/me", err)
        self.assertIn("could not be resolved", err)

    def test_reasons_are_described_in_plain_words(self):
        import errno
        import http.client
        import socket

        self.assertEqual(cli.describe_reason(ConnectionRefusedError(61, "Connection refused")),
                         "connection refused (nothing is listening there)")
        self.assertEqual(cli.describe_reason(socket.gaierror(8, "nodename nor servname")),
                         "the host name could not be resolved")
        self.assertEqual(cli.describe_reason(http.client.RemoteDisconnected("closed")),
                         "the connection was closed by the server")
        self.assertEqual(cli.describe_reason(OSError(errno.EHOSTUNREACH, "No route to host")),
                         "host unreachable")
        self.assertEqual(cli.describe_reason("something odd"), "something odd")

    def test_create_timeout_exits_6_without_retrying(self):
        self.stub.route("POST", "/api/v1/projects/12/tasks", 201, {"data": TASK})
        self.stub.delay = 1.5
        original = cli.TIMEOUT_SECONDS
        cli.TIMEOUT_SECONDS = 0.5
        self.addCleanup(setattr, cli, "TIMEOUT_SECONDS", original)

        code, _out, err = self.run_cli("task", "create", "--title", "T")
        self.assertEqual(code, cli.EXIT_CONNECTION)
        self.assertIn("timed out", err)
        self.assertIn("may have been created", err)
        posts = [r for r in self.stub.requests if r["method"] == "POST"]
        self.assertEqual(len(posts), 1)


class ExecutableTest(CliTestCase):
    def test_runs_as_a_standalone_script(self):
        env = dict(os.environ, **self.env)
        env.pop("FRONTSEAT_PROJECT", None)
        result = subprocess.run([sys.executable, CLI_PATH, "whoami"], cwd=self.repo, env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ada", result.stdout)
        self.assertNotIn(TOKEN, result.stdout + result.stderr)

    def test_a_connection_error_is_the_only_output(self):
        # Nothing — import-time log noise from some Python builds included —
        # may precede the CLI's own message.
        self.stub.close()
        env = dict(os.environ, **self.env)
        result = subprocess.run([sys.executable, CLI_PATH, "whoami"], cwd=self.repo, env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, cli.EXIT_CONNECTION)
        self.assertEqual(result.stdout, "")
        lines = result.stderr.splitlines()
        self.assertEqual(len(lines), 2, result.stderr)
        self.assertTrue(lines[0].startswith("frontseat-cli: error: Could not reach FrontSeat at "))
        self.assertTrue(lines[1].startswith("hint: "))

    def test_help_and_version(self):
        for argv in (["--help"], ["task", "create", "--help"], ["task", "list", "--help"],
                     ["project", "list", "--help"], ["whoami", "--help"]):
            result = subprocess.run([sys.executable, CLI_PATH] + argv, capture_output=True,
                                    text=True, timeout=30)
            self.assertEqual(result.returncode, 0)
            self.assertIn("example", result.stdout)
            self.assertIn("exit codes", result.stdout)

        result = subprocess.run([sys.executable, CLI_PATH, "--version"], capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.stdout.strip(), "frontseat-cli " + cli.VERSION)


if __name__ == "__main__":
    unittest.main()
