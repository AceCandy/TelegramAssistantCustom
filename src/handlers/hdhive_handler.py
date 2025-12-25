import re
import json
import logging
import httpx
import os
import time
import uuid
from urllib.parse import quote
from typing import Optional, Dict, Any, Tuple
from functools import lru_cache

logger = logging.getLogger(__name__)

# Cookie文件路径
COOKIE_FILE_PATH = "/app/config/hdhive.json"

class HDHiveResolver:
    """HDHive资源链接解析器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        cfg = config.get("hdhive", {})
        
        # 配置参数
        self.next_action_first = cfg.get("next_action_first", "")
        self.next_action_second = cfg.get("next_action_second", "")
        self.login_next_action = cfg.get("login_next_action", "")
        self.username = cfg.get("username", "")
        self.password = cfg.get("password", "")
        self.unlock_threshold = cfg.get("unlock_threshold", 20)
        self.user_agent = cfg.get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        )
        
        # 状态变量
        self.pts = 0
        self.unlock_failed = False
        
        # 编译正则表达式（性能优化）
        self._resource_pattern = re.compile(r"https?://hdhive\.com/resource/(?:(\d+)/)?([0-9a-f]{32})")
        self._token_pattern = re.compile(r"token=([^;]+)")
        self._pts_pattern = re.compile(r"需要使用\s*(\d+)\s*积分")
        self._url_pattern = re.compile(r"https?://\S+")
        
        # 从文件读取cookie
        self.cookie = self._load_cookie_from_file()

    # 日志显示映射
    STEP_MAP = {
        "resolve_url": "🔗 解析链接",
        "_re_login": "🔐 自动登录",
        "_action1_get_query": "🔍 获取查询参数",
        "_go_api_get_data_str": "📡 获取数据",
        "_go_api_unlock": "🔓 解锁资源",
        "_get_final_url": "🏁 获取最终链接",
        "rewrite_text": "📝 重写文本",
    }

    IO_MAP = {
        "input": "📥 输入",
        "output": "📤 输出",
    }

    def _load_cookie_from_file(self) -> str:
        """从文件加载cookie"""
        try:
            # 创建目录（如果不存在）
            os.makedirs(os.path.dirname(COOKIE_FILE_PATH), exist_ok=True)
            
            if os.path.exists(COOKIE_FILE_PATH):
                with open(COOKIE_FILE_PATH, 'r', encoding='utf-8') as f:
                    cookie = f.read().strip()
                    if cookie:
                        logger.debug("从文件加载cookie成功")
                        return cookie
        except Exception as e:
            logger.error(f"加载cookie文件失败: {str(e)}")
        
        logger.info("未找到有效的cookie文件，使用空cookie")
        return ""

    def _save_cookie_to_file(self, cookie: str) -> bool:
        """将cookie保存到文件"""
        try:
            # 创建目录（如果不存在）
            os.makedirs(os.path.dirname(COOKIE_FILE_PATH), exist_ok=True)
            
            with open(COOKIE_FILE_PATH, 'w', encoding='utf-8') as f:
                f.write(cookie)
            logger.debug(f"cookie已保存到文件: {COOKIE_FILE_PATH}")
            return True
        except Exception as e:
            logger.error(f"保存cookie文件失败: {str(e)}")
            return False

    @staticmethod
    @lru_cache(maxsize=4)
    def _compile_regex(pattern: str) -> re.Pattern:
        """编译正则表达式并缓存"""
        return re.compile(pattern)

    def _extract_hash(self, url: str) -> Optional[str]:
        """提取资源哈希值"""
        match = self._resource_pattern.search(url)
        return match.group(2) if match else None

    def _extract_resource_path(self, url: str) -> Optional[str]:
        match = self._resource_pattern.search(url)
        if not match:
            return None
        resource_id = match.group(1)
        resource_hash = match.group(2)
        if resource_id:
            return f"/resource/{resource_id}/{resource_hash}"
        return f"/resource/{resource_hash}"

    def _find_json_object(self, text: str, key_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """从文本中查找JSON对象"""
        lines = text.splitlines()
        candidates = []
        
        for line in lines:
            if ":{" in line or ":[{" in line:
                try:
                    # 分割后清理并解析JSON
                    payload = line.split(":", 1)[1].strip().strip('"').strip("'")
                    obj = json.loads(payload)
                    candidates.append(obj)
                except (json.JSONDecodeError, IndexError):
                    continue
        
        # 如果有key提示，优先返回包含该key的对象
        if key_hint:
            for obj in candidates:
                if key_hint in obj:
                    return obj
        
        # 返回最后一个候选对象（通常是最相关的）
        return candidates[-1] if candidates else None

    async def _re_login(self, resource_url: str) -> bool:
        """重新登录HDHive并更新Cookie中的Token"""
        self._log_step("_re_login", "input", {"resource_url": resource_url})
        if not self.username or not self.password:
            self._log_step("_re_login", "output", {"status": "missing_credentials"})
            logger.error("HDHive自动登录失败：未配置用户名或密码")
            return False

        redirect_path = self._extract_resource_path(resource_url)
        if not redirect_path:
            self._log_step("_re_login", "output", {"status": "invalid_resource_path"})
            logger.error("HDHive自动登录失败：无法从链接中提取资源路径")
            return False

        login_url = f"https://hdhive.com/login?redirect={redirect_path}"
        login_headers = {
            "content-type": "text/plain;charset=UTF-8",
            "user-agent": self.user_agent,
            "next-action": self.login_next_action
        }
        login_data = json.dumps([{"username": self.username, "password": self.password}])

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await self._send(
                    client,
                    method="POST",
                    url=login_url,
                    headers=login_headers,
                    content=login_data,
                    follow_redirects=False,
                    context={"step": "_re_login", "phase": "login"},
                )

            if response.status_code not in (200, 302):
                self._log_step("_re_login", "output", {"status": "http_error", "http_status": response.status_code})
                logger.error(f"HDHive登录失败：状态码{response.status_code}")
                return False

            # 兼容新旧版httpx的headers获取方式
            set_cookie_list = (response.headers.get_list("Set-Cookie") 
                              if hasattr(response.headers, "get_list") 
                              else response.headers.getlist("Set-Cookie"))
            
            new_token = None
            for cookie in set_cookie_list:
                match = self._token_pattern.search(cookie)
                if match:
                    new_token = match.group(1)
                if new_token:
                    break

            if not new_token:
                self._log_step("_re_login", "output", {"status": "missing_token"})
                logger.error(f"HDHive登录失败：未从响应中提取到Token")
                return False

            # 更新cookie并保存到文件
            self.cookie = f"token={new_token}"
            self._save_cookie_to_file(self.cookie)
            
            logger.info(f"HDHive自动登录成功，已更新Token")
            self._log_step("_re_login", "output", {"status": "ok"})
            return True

        except Exception as e:
            self._log_step("_re_login", "output", {"status": "exception", "error": str(e)})
            logger.error(f"HDHive登录异常：{str(e)}", exc_info=True)
            return False

    def _build_headers(self, next_action: str) -> Dict[str, str]:
        """构建请求头"""
        headers = {
            "content-type": "text/plain;charset=UTF-8",
            "user-agent": self.user_agent,
            "next-action": next_action
        }
        # 每次构建请求头时都重新从文件加载最新的cookie
        self.cookie = self._load_cookie_from_file()
        if self.cookie:
            headers["cookie"] = self.cookie
        return headers

    def _build_api_headers(self) -> Dict[str, str]:
        headers = {
            "accept": "application/json, text/plain, */*",
            "user-agent": self.user_agent,
        }
        self.cookie = self._load_cookie_from_file()
        if self.cookie:
            headers["cookie"] = self.cookie
        return headers

    def _build_api_json_headers(self) -> Dict[str, str]:
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "user-agent": self.user_agent,
        }
        self.cookie = self._load_cookie_from_file()
        if self.cookie:
            headers["cookie"] = self.cookie
        return headers

    def _redact_cookie(self, cookie: str) -> str:
        if not cookie:
            return cookie
        cookie = re.sub(r"(token=)[^;]+", r"\1***", cookie)
        cookie = re.sub(r"(csrf_access_token=)[^;]+", r"\1***", cookie)
        return cookie

    def _sanitize_headers(self, headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        if not headers:
            return {}
        sanitized: Dict[str, str] = {}
        for k, v in headers.items():
            lk = k.lower()
            if lk == "cookie":
                sanitized[k] = self._redact_cookie(v)
            elif lk in ("authorization", "proxy-authorization"):
                sanitized[k] = "***"
            else:
                sanitized[k] = v
        return sanitized

    def _safe_text(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8", errors="replace")
            except Exception:
                return repr(value)
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    def _log_http_event(self, payload: Dict[str, Any]) -> None:
        logger.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str))

    def _preview_text(self, value: Optional[str], limit: int = 500) -> Optional[str]:
        if value is None:
            return None
        if len(value) <= limit:
            return value
        return value[:limit] + "…"

    def _log_step(self, step: str, io: str, payload: Optional[Dict[str, Any]] = None) -> None:
        step_display = self.STEP_MAP.get(step, step)
        io_display = self.IO_MAP.get(io, io)
        
        # 构建单行日志信息
        log_parts = [f"[{step_display}]"]
        
        if payload:
            # 提取关键信息
            url = payload.get("resource_url") or payload.get("url")
            if url:
                log_parts.append(f"url:{url}")
                
            # 提取参数（排除url）
            params = {k: v for k, v in payload.items() if k not in ("resource_url", "url", "status", "error", "query", "data_str", "final_url")}
            if params:
                log_parts.append(f"参数:{json.dumps(params, ensure_ascii=False)}")
                
            # 提取出参/结果
            results = {}
            for k in ("status", "error", "query", "data_str", "final_url", "pts", "requires_unlock"):
                if k in payload:
                    results[k] = payload[k]
            if results:
                log_parts.append(f"出参:{json.dumps(results, ensure_ascii=False)}")
        
        msg = " ".join(log_parts)
        
        event_payload: Dict[str, Any] = {
            "event": "hdhive_step",
            "step": step,
            "step_display": step_display,
            "io": io,
            "io_display": io_display,
            "msg": msg,
        }
        if payload:
            event_payload.update(payload)
        self._log_http_event(event_payload)

    async def _send(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        content: Optional[Any] = None,
        json_body: Optional[Any] = None,
        follow_redirects: Optional[bool] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        rid = uuid.uuid4().hex[:12]
        start = time.monotonic()
        body_text = self._safe_text(content) if content is not None else self._safe_text(json_body)
        req_payload = {
            "event": "third_party_http_request",
            "rid": rid,
            "method": method,
            "url": url,
            "headers": self._sanitize_headers(headers),
            "body": body_text,
            "body_length": len(body_text) if body_text is not None else 0,
            "body_preview": self._preview_text(body_text),
        }
        if context:
            req_payload["context"] = context
        self._log_http_event(req_payload)

        try:
            request_kwargs: Dict[str, Any] = {
                "method": method,
                "url": url,
                "headers": headers,
                "content": content,
                "json": json_body,
            }
            if follow_redirects is not None:
                request_kwargs["follow_redirects"] = follow_redirects
            response = await client.request(**request_kwargs)
        except Exception as e:
            self._log_http_event(
                {
                    "event": "third_party_http_error",
                    "rid": rid,
                    "method": method,
                    "url": url,
                    "error": str(e),
                }
            )
            raise

        elapsed_ms = int((time.monotonic() - start) * 1000)
        resp_headers: Dict[str, str] = {}
        for k, v in response.headers.items():
            if k.lower() == "set-cookie":
                resp_headers[k] = self._redact_cookie(v)
            else:
                resp_headers[k] = v

        resp_text = response.text
        self._log_http_event(
            {
                "event": "third_party_http_response",
                "rid": rid,
                "method": method,
                "url": url,
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
                "headers": resp_headers,
                "body": resp_text,
                "body_length": len(resp_text) if resp_text is not None else 0,
                "body_preview": self._preview_text(resp_text),
                "context": context or {},
            }
        )
        return response

    def _build_action1_payload(self, resource_hash: str) -> str:
        payload_obj = {"slug": resource_hash, "utctimestamp": int(time.time())}
        return json.dumps([json.dumps(payload_obj, separators=(",", ":"))], separators=(",", ":"))

    def _extract_indexed_value(self, text: str, index: int) -> Optional[Any]:
        pattern = self._compile_regex(rf"(?:^|\n){index}:(.*?)(?=\n\d+:|$)")
        match = pattern.search(text)
        if not match:
            return None
        raw = match.group(1).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip().strip('"')

    async def _action1_get_query(self, client: httpx.AsyncClient, resource_url: str, resource_hash: str) -> Optional[str]:
        self._log_step(
            "_action1_get_query",
            "input",
            {"resource_url": resource_url, "resource_hash": resource_hash},
        )
        payload = self._build_action1_payload(resource_hash)
        for _ in range(2):
            headers1 = self._build_headers(self.next_action_first)
            response = await self._send(
                client,
                method="POST",
                url=resource_url,
                headers=headers1,
                content=payload,
                context={"step": "_action1_get_query", "phase": "action1"},
            )
            if response.status_code == 401 or "请先登录" in response.text or "登录已过期" in response.text:
                self._log_step("_action1_get_query", "output", {"status": "need_relogin"})
                if not await self._re_login(resource_url):
                    self._log_step("_action1_get_query", "output", {"status": "relogin_failed"})
                    return None
                continue
            response.raise_for_status()
            query = self._extract_indexed_value(response.text, 1)
            query_str = query if isinstance(query, str) and query else None
            self._log_step(
                "_action1_get_query",
                "output",
                {"query": self._preview_text(query_str), "query_length": len(query_str) if query_str else 0},
            )
            return query_str
        return None

    async def _go_api_get_data_str(self, client: httpx.AsyncClient, resource_url: str, resource_hash: str, query: str) -> Tuple[Optional[str], bool, int]:
        self._log_step(
            "_go_api_get_data_str",
            "input",
            {"resource_url": resource_url, "resource_hash": resource_hash, "query": self._preview_text(query), "query_length": len(query) if query else 0},
        )
        url = f"https://hdhive.com/go-api/customer/resources/{resource_hash}/url?query={quote(query, safe='')}"
        for _ in range(2):
            headers = self._build_api_headers()
            response = await self._send(
                client,
                method="GET",
                url=url,
                headers=headers,
                context={"step": "_go_api_get_data_str", "phase": "go_api_url"},
            )
            if response.status_code == 401:
                self._log_step("_go_api_get_data_str", "output", {"status": "need_relogin", "http_status": response.status_code})
                if not await self._re_login(resource_url):
                    self._log_step("_go_api_get_data_str", "output", {"status": "relogin_failed"})
                    return None, False, 0
                continue
            if response.status_code not in (200, 400):
                response.raise_for_status()
            try:
                obj = response.json()
            except Exception:
                self._log_step("_go_api_get_data_str", "output", {"status": "invalid_json", "http_status": response.status_code})
                logger.error("go-api响应无法解析为JSON")
                return None, False, 0

            if isinstance(obj, dict):
                code = obj.get("code")
                msg = obj.get("message", "") or ""
                if code == 401 or msg == "请先登录":
                    self._log_step("_go_api_get_data_str", "output", {"status": "need_relogin", "code": code, "message": msg})
                    if not await self._re_login(resource_url):
                        self._log_step("_go_api_get_data_str", "output", {"status": "relogin_failed"})
                        return None, False, 0
                    continue
                if code == "400404" and "需要使用" in msg and "积分解锁" in msg:
                    match = self._pts_pattern.search(msg)
                    pts = int(match.group(1)) if (match and match.group(1).isdigit()) else 0
                    self._log_step(
                        "_go_api_get_data_str",
                        "output",
                        {"requires_unlock": True, "pts": pts, "code": code, "message": msg},
                    )
                    return None, True, pts
                if obj.get("success") is True and obj.get("data"):
                    data_str = str(obj.get("data"))
                    self._log_step(
                        "_go_api_get_data_str",
                        "output",
                        {"requires_unlock": False, "data_str": self._preview_text(data_str), "data_str_length": len(data_str)},
                    )
                    return data_str, False, 0
            self._log_step("_go_api_get_data_str", "output", {"requires_unlock": False, "status": "no_data"})
            return None, False, 0
        return None, False, 0

    async def _go_api_unlock(self, client: httpx.AsyncClient, resource_url: str, resource_hash: str, query: str) -> Optional[str]:
        self._log_step(
            "_go_api_unlock",
            "input",
            {"resource_url": resource_url, "resource_hash": resource_hash, "query": self._preview_text(query), "query_length": len(query) if query else 0},
        )
        url = f"https://hdhive.com/go-api/customer/resources/{resource_hash}/unlock"
        payload = {"data": query}
        for _ in range(2):
            headers = self._build_api_json_headers()
            response = await self._send(
                client,
                method="POST",
                url=url,
                headers=headers,
                json_body=payload,
                context={"step": "_go_api_unlock", "phase": "go_api_unlock"},
            )
            if response.status_code == 401:
                self._log_step("_go_api_unlock", "output", {"status": "need_relogin"})
                if not await self._re_login(resource_url):
                    self._log_step("_go_api_unlock", "output", {"status": "relogin_failed"})
                    return None
                continue
            if response.status_code not in (200, 400):
                response.raise_for_status()
            try:
                obj = response.json()
            except Exception:
                self._log_step("_go_api_unlock", "output", {"status": "invalid_json", "http_status": response.status_code})
                logger.error("go-api unlock响应无法解析为JSON")
                return None

            if isinstance(obj, dict):
                code = obj.get("code")
                msg = obj.get("message", "") or ""
                if code == 401 or msg == "请先登录":
                    self._log_step("_go_api_unlock", "output", {"status": "need_relogin", "code": code, "message": msg})
                    if not await self._re_login(resource_url):
                        self._log_step("_go_api_unlock", "output", {"status": "relogin_failed"})
                        return None
                    continue
                if obj.get("success") is True and obj.get("data"):
                    data = str(obj.get("data"))
                    self._log_step(
                        "_go_api_unlock",
                        "output",
                        {"status": "unlock_success", "unlock_data": self._preview_text(data), "unlock_data_length": len(data)},
                    )
                    return data
            self._log_step("_go_api_unlock", "output", {"status": "unlock_failed"})
            return None
        return None

    async def _get_final_url(self, client: httpx.AsyncClient, url: str, data_str: str) -> Optional[str]:
        """获取最终的资源URL"""
        self._log_step(
            "_get_final_url",
            "input",
            {"resource_url": url, "data_str": self._preview_text(data_str), "data_str_length": len(data_str) if data_str else 0},
        )
        headers2 = self._build_headers(self.next_action_second)
        
        try:
            response = await self._send(
                client,
                method="POST",
                url=url,
                headers=headers2,
                content=json.dumps([data_str]),
                context={"step": "_get_final_url", "phase": "action2"},
            )
            response.raise_for_status()
            
            obj2 = self._find_json_object(response.text)
            logger.debug(f"action2响应：{response.text[:500]}...")

            if not obj2:
                self._log_step("_get_final_url", "output", {"status": "invalid_json"})
                logger.error("action2响应无法解析JSON")
                return None

            # 提取最终URL和访问密码
            url_field = obj2.get("url")
            access_code = obj2.get("access_code")
            
            if not url_field:
                self._log_step("_get_final_url", "output", {"status": "missing_url_field"})
                logger.error("action2响应无url字段")
                return None

            # 提取有效HTTP链接
            match = self._url_pattern.search(url_field)
            final_url = match.group(0) if match else None
            
            if not final_url:
                self._log_step("_get_final_url", "output", {"status": "no_http_url", "url_field_preview": self._preview_text(str(url_field))})
                logger.error(f"未从url字段提取到有效链接：{url_field}")
                return None

            # 拼接访问密码
            if access_code and "password=" not in final_url:
                separator = "&" if "?" in final_url else "?"
                final_url = f"{final_url}{separator}password={access_code}"
                if not final_url.endswith("#"):
                    final_url = f"{final_url}#"

            logger.info(f"解析成功，最终URL：{final_url[:100]}...")
            self._log_step("_get_final_url", "output", {"final_url": self._preview_text(final_url, 300), "final_url_length": len(final_url)})
            return final_url

        except httpx.HTTPError as e:
            self._log_step("_get_final_url", "output", {"status": "http_error", "error": str(e)})
            logger.error(f"action2请求失败：{str(e)}")
            return None

    async def resolve_url(self, url: str) -> Optional[str]:
        """解析HDHive链接"""
        self._log_step("resolve_url", "input", {"url": url})
        self.pts = 0
        self.unlock_failed = False
        h = self._extract_hash(url)
        if not h:
            self._log_step("resolve_url", "output", {"status": "invalid_url", "url": url})
            logger.error(f"无效的HDHive链接：{url}")
            return None
        self._log_step("resolve_url", "output", {"resource_hash": h})
        
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                max_attempts = 3
                for _ in range(max_attempts):
                    query = await self._action1_get_query(client, url, h)
                    if not query:
                        self._log_step("resolve_url", "output", {"status": "action1_failed"})
                        return None

                    data_str, requires_unlock, pts = await self._go_api_get_data_str(client, url, h, query)
                    if requires_unlock:
                        self.pts = pts
                        if pts >= self.unlock_threshold:
                            self._log_step(
                                "resolve_url",
                                "output",
                                {"status": "unlock_blocked", "pts": pts, "unlock_threshold": self.unlock_threshold},
                            )
                            logger.error(f"解锁所需积分{pts}≥阈值{self.unlock_threshold}，无法解锁")
                            self.unlock_failed = True
                            return None
                        unlock_data = await self._go_api_unlock(client, url, h, query)
                        if not unlock_data:
                            self._log_step("resolve_url", "output", {"status": "unlock_failed", "pts": pts})
                            self.unlock_failed = True
                            return None
                        
                        # 解锁成功后，需要重新走一遍流程获取最新的query和data_str
                        # 因为解锁后，服务器状态变了，原来的query可能失效或需要更新
                        logger.info(f"解锁成功，重新获取资源数据...")
                        continue

                    if not data_str:
                        self._log_step("resolve_url", "output", {"status": "go_api_no_data"})
                        return None

                    final_url = await self._get_final_url(client, url, data_str)
                    self._log_step("resolve_url", "output", {"status": "ok", "final_url": self._preview_text(final_url, 300) if final_url else None})
                    return final_url
                return None

        except Exception as e:
            self._log_step("resolve_url", "output", {"status": "exception", "error": str(e)})
            logger.error(f"HDHive解析失败: {str(e)}", exc_info=True)
            return None

    async def rewrite_text(self, text: Optional[str]) -> Optional[str]:
        """重写文本中的HDHive链接"""
        self._log_step("rewrite_text", "input", {"text_length": len(text) if text else 0})
        if not text:
            self._log_step("rewrite_text", "output", {"status": "empty"})
            return text
        
        matches = list(self._resource_pattern.finditer(text))
        if not matches:
            self._log_step("rewrite_text", "output", {"status": "no_match"})
            return text.replace("直达链接", "解锁失败")
        
        replaced = text
        for m in matches:
            full_url = m.group(0)
            self._log_step("rewrite_text", "input", {"url": full_url})
            new_url = await self.resolve_url(full_url)
            self._log_step("rewrite_text", "output", {"url": full_url, "new_url": self._preview_text(new_url, 300) if new_url else None})
            if new_url:
                replaced = replaced.replace(full_url, new_url)
        
        # 替换文本中的"直达链接"为积分信息
        if self.unlock_failed and self.pts:
            replaced = replaced.replace("直达链接", f"解锁失败，需要{self.pts}积分")
        else:
            pts_text = str(self.pts) if self.pts else "0"
            replaced = replaced.replace("直达链接", f"{pts_text}积分解锁")
        self._log_step(
            "rewrite_text",
            "output",
            {"status": "ok", "matches": len(matches), "pts": self.pts, "unlock_failed": self.unlock_failed},
        )
        self.pts = 0
        self.unlock_failed = False
        
        return replaced
