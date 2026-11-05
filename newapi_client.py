from typing import Any, Dict, List, Optional, Tuple
import httpx


class NewAPIClient:
    """NewAPI API Client for querying and managing a NewAPI instance."""

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: int = 15,
        proxy: Optional[str] = None,
        quota_per_unit: int = 500000,
    ):
        self.base_url = self._normalize_url(base_url)
        self.token = token.strip()
        self.timeout = timeout
        self.proxy = proxy.strip() if proxy else None
        self.quota_per_unit = quota_per_unit or 500000

    @staticmethod
    def _normalize_url(url: str) -> str:
        url = url.strip()
        if not url:
            return ""
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "http://" + url
        url = url.rstrip("/")
        if url.endswith("/api"):
            url = url[:-4]
        return url

    def is_configured(self) -> bool:
        return bool(self.base_url and self.token)

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AstrBot-NewAPI-Plugin/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _create_client(self) -> httpx.AsyncClient:
        kwargs: Dict[str, Any] = {
            "timeout": self.timeout,
            "headers": self._get_headers(),
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
        return httpx.AsyncClient(**kwargs)

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.base_url:
            raise ValueError("未配置 NewAPI 站点地址，请在插件设置中填写。")

        url = f"{self.base_url}{endpoint}"
        async with self._create_client() as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                )
            except httpx.ConnectError as e:
                raise ConnectionError(f"连接 NewAPI 站点失败: {e}")
            except httpx.TimeoutException:
                raise TimeoutError(f"请求 NewAPI 超时（限时 {self.timeout} 秒）。")
            except Exception as e:
                raise RuntimeError(f"请求 NewAPI 出现异常: {e}")

            try:
                data = response.json()
            except Exception:
                if response.status_code != 200:
                    raise RuntimeError(
                        f"HTTP {response.status_code}: {response.text[:200]}"
                    )
                return {"success": True, "raw": response.text}

            if response.status_code >= 400:
                err_msg = ""
                if isinstance(data, dict):
                    err_msg = (
                        data.get("message")
                        or data.get("error", {}).get("message")
                        or str(data)
                    )
                else:
                    err_msg = str(data)
                raise RuntimeError(f"API 请求失败 [{response.status_code}]: {err_msg}")

            if (
                isinstance(data, dict)
                and not data.get("success", True)
                and "data" not in data
            ):
                err_msg = data.get("message", "未知业务错误")
                raise RuntimeError(f"业务请求失败: {err_msg}")

            return data

    def format_quota(self, quota: int) -> str:
        """Format quota into USD and token count."""
        per_unit = self.quota_per_unit if self.quota_per_unit > 0 else 500000
        usd = quota / per_unit
        return f"${usd:,.4f} ({quota:,} 点)"

    def usd_to_quota(self, usd: float) -> int:
        per_unit = self.quota_per_unit if self.quota_per_unit > 0 else 500000
        return int(round(usd * per_unit))

    # --- Site & Public API ---

    async def get_status(self) -> Dict[str, Any]:
        """GET /api/status - Query site status and update quota ratio."""
        res = await self._request("GET", "/api/status")
        data = res.get("data", res)
        if isinstance(data, dict) and "quota_per_unit" in data:
            try:
                self.quota_per_unit = int(data["quota_per_unit"])
            except (ValueError, TypeError):
                pass
        return data

    async def get_models(self) -> List[Any]:
        """GET /api/models - Query site supported models."""
        res = await self._request("GET", "/api/models")
        return res.get("data", [])

    async def get_performance_stats(self) -> Dict[str, Any]:
        """GET /api/performance/stats - Query NewAPI memory/disk/cache stats."""
        try:
            res = await self._request("GET", "/api/performance/stats")
            return res.get("data", res)
        except Exception:
            return {}

    # --- Self / Current User ---

    async def get_self(self) -> Dict[str, Any]:
        """GET /api/user/self - Query current authenticated user profile."""
        res = await self._request("GET", "/api/user/self")
        return res.get("data", {})

    async def get_self_subscriptions(self) -> List[Dict[str, Any]]:
        """GET /api/subscription/self - Query current user subscriptions."""
        try:
            res = await self._request("GET", "/api/subscription/self")
            data = res.get("data", {})
            if isinstance(data, dict):
                return data.get("subscriptions", []) or data.get(
                    "all_subscriptions", []
                )
            if isinstance(data, list):
                return data
        except Exception:
            pass
        return []

    async def get_user_subscriptions(self, user_id: int) -> List[Dict[str, Any]]:
        """GET /api/subscription/admin/users/:id/subscriptions - Query user subscriptions (Admin)."""
        try:
            res = await self._request(
                "GET", f"/api/subscription/admin/users/{user_id}/subscriptions"
            )
            data = res.get("data", [])
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("items", []) or data.get("subscriptions", [])
        except Exception:
            pass
        return []

    async def get_self_stat(
        self,
        start_ts: int = 0,
        end_ts: int = 0,
    ) -> Dict[str, Any]:
        """GET /api/log/self/stat - Query self quota consumption."""
        params: Dict[str, Any] = {"type": 2}
        if start_ts > 0:
            params["start_timestamp"] = start_ts
        if end_ts > 0:
            params["end_timestamp"] = end_ts
        res = await self._request("GET", "/api/log/self/stat", params=params)
        return res.get("data", {})

    async def redeem_code(self, key: str) -> Dict[str, Any]:
        """POST /api/user/topup - Redeem a code for the current user."""
        res = await self._request(
            "POST", "/api/user/topup", json_data={"key": key.strip()}
        )
        return res

    # --- Site Stats & Rankings ---

    async def get_site_stat(
        self,
        start_ts: int = 0,
        end_ts: int = 0,
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /api/log/stat - Query site consumption stat (Admin)."""
        params: Dict[str, Any] = {"type": 2}
        if start_ts > 0:
            params["start_timestamp"] = start_ts
        if end_ts > 0:
            params["end_timestamp"] = end_ts
        if username:
            params["username"] = username.strip()
        res = await self._request("GET", "/api/log/stat", params=params)
        return res.get("data", {})

    async def get_user_quota_dates(
        self,
        start_ts: int = 0,
        end_ts: int = 0,
    ) -> List[Dict[str, Any]]:
        """GET /api/data/users - Query quota grouped by user over time (Admin)."""
        params: Dict[str, Any] = {}
        if start_ts > 0:
            params["start_timestamp"] = start_ts
        if end_ts > 0:
            params["end_timestamp"] = end_ts
        res = await self._request("GET", "/api/data/users", params=params)
        return res.get("data", [])

    async def get_rankings(self, period: str = "week") -> Dict[str, Any]:
        """GET /api/rankings?period=today|week|month|year - Model & Vendor token ranking."""
        res = await self._request("GET", "/api/rankings", params={"period": period})
        return res.get("data", {})

    # --- User Management (Admin) ---

    async def get_all_users(
        self, p: int = 0, size: int = 100
    ) -> Tuple[List[Dict[str, Any]], int]:
        """GET /api/user/ - List all users with pagination."""
        res = await self._request("GET", "/api/user/", params={"p": p, "size": size})
        data = res.get("data", {})
        if isinstance(data, dict):
            items = data.get("items", [])
            total = data.get("total", len(items))
            return items, total
        if isinstance(data, list):
            return data, len(data)
        return [], 0

    async def search_users(self, keyword: str) -> List[Dict[str, Any]]:
        """GET /api/user/search?keyword=... - Search users."""
        res = await self._request(
            "GET", "/api/user/search", params={"keyword": keyword}
        )
        data = res.get("data", {})
        if isinstance(data, dict):
            return data.get("items", [])
        if isinstance(data, list):
            return data
        return []

    async def get_user(self, user_id: int) -> Dict[str, Any]:
        """GET /api/user/:id - Get specific user details."""
        res = await self._request("GET", f"/api/user/{user_id}")
        return res.get("data", {})

    async def create_user(
        self,
        username: str,
        password: str,
        display_name: Optional[str] = None,
        role: int = 1,
    ) -> Dict[str, Any]:
        """POST /api/user/ - Create a new user (Admin)."""
        payload: Dict[str, Any] = {
            "username": username.strip(),
            "password": password.strip(),
            "display_name": (display_name or username).strip(),
            "role": role,
        }
        res = await self._request("POST", "/api/user/", json_data=payload)
        return res

    async def manage_user_quota(
        self,
        user_id: int,
        mode: str,
        value_quota: int,
    ) -> Dict[str, Any]:
        """
        POST /api/user/manage - Adjust user quota.
        mode: "add" | "subtract" | "override"
        """
        payload = {
            "id": user_id,
            "action": "add_quota",
            "mode": mode,
            "value": value_quota,
        }
        res = await self._request("POST", "/api/user/manage", json_data=payload)
        return res

    async def manage_user_status(self, user_id: int, action: str) -> Dict[str, Any]:
        """
        POST /api/user/manage - Enable or disable user.
        action: "enable" | "disable"
        """
        payload = {
            "id": user_id,
            "action": action,
        }
        res = await self._request("POST", "/api/user/manage", json_data=payload)
        return res

    # --- Redemption Codes (Admin) ---

    async def create_redemption(
        self,
        name: str,
        count: int,
        quota: int,
        expired_time: int = -1,
    ) -> List[str]:
        """POST /api/redemption/ - Create batch redemption codes (Admin)."""
        payload = {
            "name": name.strip(),
            "count": count,
            "quota": quota,
            "expired_time": expired_time,
        }
        res = await self._request("POST", "/api/redemption/", json_data=payload)
        keys = res.get("data", [])
        if isinstance(keys, list):
            return [str(k) for k in keys]
        return []

    async def list_redemptions(
        self, p: int = 0, size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """GET /api/redemption/ - List redemption codes (Admin)."""
        res = await self._request(
            "GET", "/api/redemption/", params={"p": p, "size": size}
        )
        data = res.get("data", {})
        if isinstance(data, dict):
            return data.get("items", []), data.get("total", 0)
        if isinstance(data, list):
            return data, len(data)
        return [], 0

    async def search_redemptions(self, keyword: str) -> List[Dict[str, Any]]:
        """GET /api/redemption/search - Search redemption codes (Admin)."""
        res = await self._request(
            "GET", "/api/redemption/search", params={"keyword": keyword}
        )
        data = res.get("data", {})
        if isinstance(data, dict):
            return data.get("items", [])
        return []

    # --- Channels (Admin) ---

    async def list_channels(
        self, p: int = 0, size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """GET /api/channel/ - List channels (Admin)."""
        res = await self._request("GET", "/api/channel/", params={"p": p, "size": size})
        data = res.get("data", {})
        if isinstance(data, dict):
            return data.get("items", []), data.get("total", 0)
        if isinstance(data, list):
            return data, len(data)
        return [], 0

    async def test_channel(self, channel_id: Optional[int] = None) -> Any:
        """GET /api/channel/test or /api/channel/test/:id - Test channel."""
        endpoint = (
            f"/api/channel/test/{channel_id}" if channel_id else "/api/channel/test"
        )
        res = await self._request("GET", endpoint)
        return res.get("data", res)

    # --- Token (API Key) Management ---

    async def list_tokens(
        self, p: int = 0, size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """GET /api/token/ - List API keys."""
        res = await self._request("GET", "/api/token/", params={"p": p, "size": size})
        data = res.get("data", {})
        if isinstance(data, dict):
            return data.get("items", []), data.get("total", 0)
        if isinstance(data, list):
            return data, len(data)
        return [], 0

    async def add_token(
        self,
        name: str,
        remain_quota: int = 0,
        unlimited: bool = False,
    ) -> Dict[str, Any]:
        """POST /api/token/ - Create an API key."""
        payload = {
            "name": name.strip(),
            "remain_quota": remain_quota,
            "unlimited_quota": unlimited,
            "expired_time": -1,
        }
        res = await self._request("POST", "/api/token/", json_data=payload)
        return res.get("data", res)

    async def delete_token(self, token_id: int) -> Dict[str, Any]:
        """DELETE /api/token/:id - Delete an API key."""
        return await self._request("DELETE", f"/api/token/{token_id}")

    async def get_token_key(self, token_id: int) -> str:
        """POST /api/token/:id/key - Reveal full API key (sk-...)."""
        res = await self._request("POST", f"/api/token/{token_id}/key")
        data = res.get("data", {})
        if isinstance(data, dict):
            return data.get("key", "")
        return str(data)
