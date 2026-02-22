import json
import unittest

import httpx

from src.handlers.hdhive_handler import HDHiveResolver


class TestHDHiveResolver(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_url_direct_page_with_login_and_unlock(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_file = Path(temp_dir) / "hdhive_cookie.json"
            resource_url = "https://hdhive.com/resource/123/0123456789abcdef0123456789abcdef"
            go_unlock_url = (
                "https://hdhive.com/go-api/customer/resources/"
                "0123456789abcdef0123456789abcdef/unlock"
            )

            state = {
                "resource_calls": 0,
                "login_calls": 0,
                "unlock_calls": 0,
            }

            def handler(request: httpx.Request) -> httpx.Response:
                path = request.url.path

                if path.startswith("/resource/"):
                    state["resource_calls"] += 1
                    cookie = request.headers.get("cookie", "")

                    # server-action 登录请求
                    if request.method == "POST" and request.headers.get("next-action") == "login-action":
                        state["login_calls"] += 1
                        return httpx.Response(
                            303,
                            text="ok",
                            headers={
                                "set-cookie": "session=abc; Path=/; HttpOnly",
                                "content-type": "text/plain;charset=UTF-8",
                            },
                        )

                    # server-action 加解密
                    if request.method == "POST" and request.headers.get("next-action") == "enc-action":
                        return httpx.Response(
                            200,
                            text='1:"encrypted-query"',
                            headers={"content-type": "text/plain;charset=UTF-8"},
                        )
                    if request.method == "POST" and request.headers.get("next-action") == "dec-action":
                        payload = request.content.decode("utf-8")
                        if "encrypted-lock" in payload:
                            return httpx.Response(
                                200,
                                text='1:{"url":"https://115cdn.example.com/file/abc123","unlock_points":5}',
                                headers={"content-type": "text/plain;charset=UTF-8"},
                            )
                        return httpx.Response(
                            200,
                            text='1:{"url":"https://115cdn.example.com/file/abc123","unlock_points":0}',
                            headers={"content-type": "text/plain;charset=UTF-8"},
                        )

                    # 第一次无cookie，要求登录
                    if "session=abc" not in cookie:
                        return httpx.Response(
                            200,
                            text="请先登录",
                            headers={"content-type": "text/html; charset=utf-8"},
                        )

                    # 登录后第一次访问还需要积分解锁
                    if state["resource_calls"] == 2:
                        html = '<html><body>需要使用 5 积分解锁 unlockData="unlock-secret"</body></html>'
                        return httpx.Response(
                            200,
                            text=html,
                            headers={"content-type": "text/html; charset=utf-8"},
                        )

                    # 解锁后返回115链接
                    html = '<html><body><a href="https://115cdn.example.com/file/abc123">download</a></body></html>'
                    return httpx.Response(
                        200,
                        text=html,
                        headers={"content-type": "text/html; charset=utf-8"},
                    )

                if path == "/login" and request.method == "POST":
                    state["login_calls"] += 1
                    return httpx.Response(
                        200,
                        text="ok",
                        headers={
                            "set-cookie": "session=abc; Path=/; HttpOnly",
                            "content-type": "application/json",
                        },
                    )

                if request.url == httpx.URL(go_unlock_url) and request.method == "POST":
                    state["unlock_calls"] += 1
                    payload = json.loads(request.content.decode("utf-8"))
                    if payload.get("data") not in ("unlock-secret", "encrypted-query"):
                        return httpx.Response(400, json={"success": False, "message": "bad data"})
                    return httpx.Response(200, json={"success": True, "data": "ok"})

                go_url = (
                    "https://hdhive.com/go-api/customer/resources/"
                    "0123456789abcdef0123456789abcdef/url"
                )
                if str(request.url).startswith(go_url) and request.method == "GET":
                    if state["unlock_calls"] == 0:
                        return httpx.Response(
                            400,
                            json={
                                "success": False,
                                "data": "encrypted-lock",
                                "message": "需要使用 5 积分解锁",
                                "code": "400404",
                            },
                        )
                    return httpx.Response(
                        200,
                        json={"success": True, "data": "encrypted-unlocked", "message": "success", "code": "200"},
                    )

                return httpx.Response(404, text=f"unexpected: {request.method} {request.url}")

            resolver = HDHiveResolver(
                {
                    "hdhive": {
                        "username": "demo",
                        "password": "pass",
                        "unlock_threshold": 20,
                        "cookie_file_path": str(cookie_file),
                        "server_action_login": "login-action",
                        "server_action_encrypt": "enc-action",
                        "server_action_decrypt": "dec-action",
                    }
                }
            )

            transport = httpx.MockTransport(handler)

            def create_client() -> httpx.AsyncClient:
                return httpx.AsyncClient(transport=transport, timeout=20)

            resolver._create_client = create_client  # type: ignore[assignment]

            final_url = await resolver.resolve_url(resource_url)

            self.assertEqual(final_url, "https://115cdn.example.com/file/abc123")
            self.assertEqual(state["login_calls"], 1)
            self.assertEqual(state["unlock_calls"], 1)

            # cookie应被持久化，下一次不需要重新登录
            persisted = json.loads(cookie_file.read_text("utf-8"))
            self.assertEqual(persisted["cookies"].get("session"), "abc")

            final_url_2 = await resolver.resolve_url(resource_url)
            self.assertEqual(final_url_2, "https://115cdn.example.com/file/abc123")
            self.assertEqual(state["login_calls"], 1)

    async def test_rewrite_text_supports_new_hdhive_tld_and_uppercase(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_file = Path(temp_dir) / "hdhive_cookie.json"
            resolver = HDHiveResolver(
                {
                    "hdhive": {
                        "unlock_threshold": 20,
                        "cookie_file_path": str(cookie_file),
                    }
                }
            )
            resource_url = "HTTPS://WWW.HDHIVE.CC/resource/115/0123456789abcdef0123456789abcdef"
            state = {"calls": 0}

            async def fake_resolve(url: str):
                state["calls"] += 1
                self.assertEqual(url, resource_url)
                return "https://115cdn.example.com/file/new-domain"

            resolver.resolve_url = fake_resolve  # type: ignore[assignment]

            rewritten = await resolver.rewrite_text(f"测试链接：{resource_url}")

            self.assertIn("https://115cdn.example.com/file/new-domain", rewritten)
            self.assertEqual(state["calls"], 1)

    async def test_resolve_url_refreshes_stale_server_actions(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_file = Path(temp_dir) / "hdhive_cookie.json"
            resource_hash = "0123456789abcdef0123456789abcdef"
            resource_url = f"https://hdhive.com/resource/115/{resource_hash}"
            go_url = f"https://hdhive.com/go-api/customer/resources/{resource_hash}/url"

            stale_ids = {
                "login": "old-login-action",
                "encrypt": "old-enc-action",
                "decrypt": "old-dec-action",
            }
            current_ids = {
                "login": "60117d32a5f428137a3759c2470ea04fd5bc035e45",
                "encrypt": "4009ae744a7d94ccc9b0f0ff4e3f5bc55d39a111ad",
                "decrypt": "40c9c3d9fd41a3ddb01539b93b112ebf0dd6e5f98f",
            }

            page_html = (
                "<html><head>"
                "<script src='/_next/static/chunks/chunk-encrypt.js'></script>"
                "<script src='/_next/static/chunks/chunk-login.js'></script>"
                "</head><body>resource page</body></html>"
            )
            encrypt_chunk = (
                f'(0,t.createServerReference)("{current_ids["encrypt"]}",t.callServer,void 0,t.findSourceMapURL,"encrypte");'
                f'(0,t.createServerReference)("{current_ids["decrypt"]}",t.callServer,void 0,t.findSourceMapURL,"decrypt");'
            )
            login_chunk = (
                f'(0,t.createServerReference)("{current_ids["login"]}",t.callServer,void 0,t.findSourceMapURL,"login");'
            )

            state = {
                "old_encrypt_calls": 0,
                "new_encrypt_calls": 0,
                "discover_chunk_calls": 0,
            }

            def handler(request: httpx.Request) -> httpx.Response:
                path = request.url.path
                next_action = request.headers.get("next-action", "")

                if path.startswith("/resource/") and request.method == "GET":
                    return httpx.Response(
                        200,
                        text=page_html,
                        headers={"content-type": "text/html; charset=utf-8"},
                    )

                if path == "/login" and request.method == "GET":
                    return httpx.Response(
                        200,
                        text=page_html,
                        headers={"content-type": "text/html; charset=utf-8"},
                    )

                if path == "/_next/static/chunks/chunk-encrypt.js":
                    state["discover_chunk_calls"] += 1
                    return httpx.Response(
                        200,
                        text=encrypt_chunk,
                        headers={"content-type": "application/javascript"},
                    )

                if path == "/_next/static/chunks/chunk-login.js":
                    state["discover_chunk_calls"] += 1
                    return httpx.Response(
                        200,
                        text=login_chunk,
                        headers={"content-type": "application/javascript"},
                    )

                if path.startswith("/resource/") and request.method == "POST":
                    if next_action == stale_ids["encrypt"]:
                        state["old_encrypt_calls"] += 1
                        return httpx.Response(
                            404,
                            text="Server action not found.",
                            headers={
                                "content-type": "text/plain",
                                "x-nextjs-action-not-found": "1",
                            },
                        )
                    if next_action == current_ids["encrypt"]:
                        state["new_encrypt_calls"] += 1
                        return httpx.Response(
                            200,
                            text='1:"encrypted-query"',
                            headers={"content-type": "text/plain;charset=UTF-8"},
                        )
                    if next_action == current_ids["decrypt"]:
                        return httpx.Response(
                            200,
                            text='1:{"url":"https://115cdn.example.com/file/auto","unlock_points":0}',
                            headers={"content-type": "text/plain;charset=UTF-8"},
                        )

                if str(request.url).startswith(go_url) and request.method == "GET":
                    if request.url.params.get("query") != "encrypted-query":
                        return httpx.Response(400, json={"success": False, "message": "bad query"})
                    return httpx.Response(
                        200,
                        json={"success": True, "data": "encrypted-data", "message": "success", "code": "200"},
                    )

                return httpx.Response(404, text=f"unexpected: {request.method} {request.url}")

            resolver = HDHiveResolver(
                {
                    "hdhive": {
                        "username": "demo",
                        "password": "pass",
                        "unlock_threshold": 20,
                        "cookie_file_path": str(cookie_file),
                        "server_action_login": stale_ids["login"],
                        "server_action_encrypt": stale_ids["encrypt"],
                        "server_action_decrypt": stale_ids["decrypt"],
                    }
                }
            )

            transport = httpx.MockTransport(handler)

            def create_client() -> httpx.AsyncClient:
                return httpx.AsyncClient(transport=transport, timeout=20)

            resolver._create_client = create_client  # type: ignore[assignment]

            final_url = await resolver.resolve_url(resource_url)

            self.assertEqual(final_url, "https://115cdn.example.com/file/auto")
            self.assertEqual(state["old_encrypt_calls"], 1)
            self.assertGreaterEqual(state["new_encrypt_calls"], 1)
            self.assertGreaterEqual(state["discover_chunk_calls"], 1)

    async def test_resolve_url_server_action_encrypt_decrypt_flow(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_file = Path(temp_dir) / "hdhive_cookie.json"
            resource_hash = "0123456789abcdef0123456789abcdef"
            resource_url = f"https://hdhive.com/resource/115/{resource_hash}"
            go_url = f"https://hdhive.com/go-api/customer/resources/{resource_hash}/url"

            state = {
                "encrypt_calls": 0,
                "decrypt_calls": 0,
                "go_url_calls": 0,
                "login_calls": 0,
            }

            def handler(request: httpx.Request) -> httpx.Response:
                path = request.url.path
                next_action = request.headers.get("next-action", "")

                if path == "/login" and request.method == "POST":
                    state["login_calls"] += 1
                    return httpx.Response(
                        303,
                        text="ok",
                        headers={
                            "set-cookie": "token=abc; Path=/; HttpOnly",
                            "content-type": "text/plain;charset=UTF-8",
                        },
                    )

                if path.startswith("/resource/") and request.method == "GET":
                    # 页面不提供直链，强制走go-api路径
                    return httpx.Response(
                        200,
                        text="<html><body>resource page</body></html>",
                        headers={"content-type": "text/html; charset=utf-8"},
                    )

                if path.startswith("/resource/") and request.method == "POST":
                    if next_action == "enc-action":
                        state["encrypt_calls"] += 1
                        return httpx.Response(
                            200,
                            text='1:"encrypted-query"',
                            headers={"content-type": "text/plain;charset=UTF-8"},
                        )

                    if next_action == "dec-action":
                        state["decrypt_calls"] += 1
                        return httpx.Response(
                            200,
                            text='1:{"url":"https://115cdn.example.com/file/xyz?password=abc","access_code":"","unlock_points":0}',
                            headers={"content-type": "text/plain;charset=UTF-8"},
                        )

                if str(request.url).startswith(go_url) and request.method == "GET":
                    state["go_url_calls"] += 1
                    query = request.url.params.get("query")
                    if query != "encrypted-query":
                        return httpx.Response(400, json={"success": False, "message": "bad query", "code": "400"})
                    return httpx.Response(
                        200,
                        json={"success": True, "data": "encrypted-data", "message": "success", "code": "200"},
                    )

                return httpx.Response(404, text=f"unexpected: {request.method} {request.url}")

            resolver = HDHiveResolver(
                {
                    "hdhive": {
                        "username": "demo",
                        "password": "pass",
                        "unlock_threshold": 20,
                        "cookie_file_path": str(cookie_file),
                        "server_action_login": "login-action",
                        "server_action_encrypt": "enc-action",
                        "server_action_decrypt": "dec-action",
                    }
                }
            )

            transport = httpx.MockTransport(handler)

            def create_client() -> httpx.AsyncClient:
                return httpx.AsyncClient(transport=transport, timeout=20)

            resolver._create_client = create_client  # type: ignore[assignment]

            final_url = await resolver.resolve_url(resource_url)

            self.assertEqual(final_url, "https://115cdn.example.com/file/xyz?password=abc")
            self.assertGreaterEqual(state["encrypt_calls"], 1)
            self.assertGreaterEqual(state["decrypt_calls"], 1)
            self.assertEqual(state["go_url_calls"], 1)


if __name__ == "__main__":
    unittest.main()
