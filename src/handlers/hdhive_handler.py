import re
import json
import logging
import httpx
import os
from typing import Optional, Dict, Any, List, Tuple
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
        self.next_action_unlock = cfg.get("next_action_unlock", "")
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
        
        # 编译正则表达式（性能优化）
        self._hash_pattern = re.compile(r"https?://hdhive\.com/resource/([0-9a-f]{32})")
        self._token_pattern = re.compile(r"token=([^;]+)")
        self._pts_pattern = re.compile(r"需要使用\s*(\d+)\s*积分")
        self._url_pattern = re.compile(r"https?://\S+")
        
        # 从文件读取cookie
        self.cookie = self._load_cookie_from_file()

    def _load_cookie_from_file(self) -> str:
        """从文件加载cookie"""
        try:
            # 创建目录（如果不存在）
            os.makedirs(os.path.dirname(COOKIE_FILE_PATH), exist_ok=True)
            
            if os.path.exists(COOKIE_FILE_PATH):
                with open(COOKIE_FILE_PATH, 'r', encoding='utf-8') as f:
                    cookie = f.read().strip()
                    if cookie:
                        logger.info(f"从文件加载cookie成功")
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
            logger.info(f"cookie已保存到文件: {COOKIE_FILE_PATH}")
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
        match = self._hash_pattern.search(url)
        return match.group(1) if match else None

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

    async def _re_login(self, resource_hash: str) -> bool:
        """重新登录HDHive并更新Cookie中的Token"""
        if not self.username or not self.password:
            logger.error("HDHive自动登录失败：未配置用户名或密码")
            return False

        login_url = f"https://hdhive.com/login?redirect=/resource/{resource_hash}"
        login_headers = {
            "content-type": "text/plain;charset=UTF-8",
            "user-agent": self.user_agent,
            "next-action": self.login_next_action
        }
        login_data = json.dumps([{"username": self.username, "password": self.password}])

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    login_url,
                    headers=login_headers,
                    content=login_data,
                    follow_redirects=False
                )

            if response.status_code not in (200, 302):
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
                    break

            if not new_token:
                logger.error(f"HDHive登录失败：未从响应中提取到Token")
                return False

            # 更新cookie并保存到文件
            self.cookie = f"token={new_token}"
            self._save_cookie_to_file(self.cookie)
            
            logger.info(f"HDHive自动登录成功，已更新Token")
            return True

        except Exception as e:
            logger.error(f"HDHive登录异常：{str(e)}", exc_info=True)
            return False

    async def _do_first_action(self, client: httpx.AsyncClient, url: str, headers1: Dict[str, str], 
                             h: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """执行第一个action请求"""
        try:
            response = await client.post(url, headers=headers1, content=json.dumps([h]))
            response.raise_for_status()  # 检查HTTP状态码
            logger.debug(f"action1响应：{response.text[:500]}...")  # 限制日志长度
            return self._find_json_object(response.text), response.text
        except httpx.HTTPError as e:
            logger.error(f"action1请求失败：{str(e)}")
            return None, str(e)

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

    async def _handle_action1_response(self, client: httpx.AsyncClient, url: str, 
                                     headers1: Dict[str, str], h: str, 
                                     obj1: Dict[str, Any], r1_text: str) -> Optional[str]:
        """处理action1的响应"""
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            if not obj1:
                logger.error(f"action1响应无法解析JSON")
                return None

            # 情况1：直接拿到data_str
            if "response" in obj1 and isinstance(obj1.get("response"), dict):
                data_str = obj1.get("response", {}).get("data")
                if data_str:
                    return data_str
                else:
                    logger.warning("action1响应有response，但无data字段")

            # 情况2：响应包含错误
            elif "error" in obj1 and isinstance(obj1.get("error"), dict):
                err = obj1.get("error", {})
                code = err.get("code")
                msg = err.get("message", "")
                logger.warning(f"action1错误：code={code}，msg={msg}")

                # 子情况2.1：登录过期 → 登录后重试
                if msg == "登录已过期":
                    login_success = await self._re_login(h)
                    if not login_success:
                        return None
                    
                    # 更新Cookie后重试
                    headers1 = self._build_headers(self.next_action_first)
                    obj1, r1_text = await self._do_first_action(client, url, headers1, h)
                    retry_count += 1
                    continue

                # 子情况2.2：需要积分解锁
                elif code == "400404" and "需要使用" in msg and "积分解锁" in msg:
                    return await self._handle_unlock(client, url, headers1, h, msg)

                # 其他错误
                else:
                    logger.error(f"action1未处理的错误：code={code}，msg={msg}")
                    return None

            # 既无response也无error
            else:
                logger.error(f"action1响应格式异常")
                return None

        logger.error(f"action1重试次数过多({max_retries}次)")
        return None

    async def _handle_unlock(self, client: httpx.AsyncClient, url: str, headers1: Dict[str, str], 
                           h: str, error_msg: str) -> Optional[str]:
        """处理资源解锁"""
        # 提取所需积分
        match = self._pts_pattern.search(error_msg)
        pts = int(match.group(1)) if (match and match.group(1).isdigit()) else 0

        # 判断是否满足解锁阈值
        if pts >= self.unlock_threshold:
            logger.error(f"解锁所需积分{pts}≥阈值{self.unlock_threshold}，无法解锁")
            return None

        # 执行解锁请求
        logger.info(f"开始解锁资源，所需积分：{pts}")
        headers_unlock = self._build_headers(self.next_action_unlock)
        try:
            response = await client.post(
                url, headers=headers_unlock, content=json.dumps([h])
            )
            response.raise_for_status()
            
            obj_unlock = self._find_json_object(response.text, "response")
            logger.debug(f"解锁响应：{response.text[:500]}...")

            # 解锁成功后重试action1
            if obj_unlock and obj_unlock.get("response", {}).get("success"):
                logger.info("资源解锁成功，重试action1")
                self.pts = pts
                obj1, r1_text = await self._do_first_action(client, url, headers1, h)
                return obj1.get("response", {}).get("data") if obj1 else None
            else:
                logger.error(f"解锁失败：{response.text}")
                return None
        except httpx.HTTPError as e:
            logger.error(f"解锁请求失败：{str(e)}")
            return None

    async def _get_final_url(self, client: httpx.AsyncClient, url: str, data_str: str) -> Optional[str]:
        """获取最终的资源URL"""
        headers2 = self._build_headers(self.next_action_second)
        
        try:
            response = await client.post(
                url, headers=headers2, content=json.dumps([data_str])
            )
            response.raise_for_status()
            
            obj2 = self._find_json_object(response.text)
            logger.debug(f"action2响应：{response.text[:500]}...")

            if not obj2:
                logger.error("action2响应无法解析JSON")
                return None

            # 提取最终URL和访问密码
            url_field = obj2.get("url")
            access_code = obj2.get("access_code")
            
            if not url_field:
                logger.error("action2响应无url字段")
                return None

            # 提取有效HTTP链接
            match = self._url_pattern.search(url_field)
            final_url = match.group(0) if match else None
            
            if not final_url:
                logger.error(f"未从url字段提取到有效链接：{url_field}")
                return None

            # 拼接访问密码
            if access_code and "password=" not in final_url:
                separator = "&" if "?" in final_url else "?"
                final_url = f"{final_url}{separator}password={access_code}"
                if not final_url.endswith("#"):
                    final_url = f"{final_url}#"

            logger.info(f"解析成功，最终URL：{final_url[:100]}...")
            return final_url

        except httpx.HTTPError as e:
            logger.error(f"action2请求失败：{str(e)}")
            return None

    async def resolve_url(self, url: str) -> Optional[str]:
        """解析HDHive链接"""
        h = self._extract_hash(url)
        if not h:
            logger.error(f"无效的HDHive链接：{url}")
            return None
        
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                headers1 = self._build_headers(self.next_action_first)
                
                # 第一次执行action1
                obj1, r1_text = await self._do_first_action(client, url, headers1, h)
                
                # 处理action1响应
                data_str = await self._handle_action1_response(client, url, headers1, h, obj1, r1_text)
                if not data_str:
                    return None
                
                # 执行action2获取最终URL
                return await self._get_final_url(client, url, data_str)

        except Exception as e:
            logger.error(f"HDHive解析失败: {str(e)}", exc_info=True)
            return None

    async def rewrite_text(self, text: Optional[str]) -> Optional[str]:
        """重写文本中的HDHive链接"""
        if not text:
            return text
        
        urls = self._hash_pattern.findall(text)
        if not urls:
            return text.replace("直达链接", "解锁失败")
        
        replaced = text
        for u in urls:
            full_url = f"https://hdhive.com/resource/{u}"
            new_url = await self.resolve_url(full_url)
            if new_url:
                replaced = replaced.replace(full_url, new_url)
        
        # 替换文本中的"直达链接"为积分信息
        pts_text = str(self.pts) if self.pts else "0"
        replaced = replaced.replace("直达链接", f"{pts_text}积分解锁")
        self.pts = 0
        
        return replaced
