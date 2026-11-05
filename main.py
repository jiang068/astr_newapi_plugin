import datetime
import json
import os
import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from astrbot.api import AstrBotConfig, logger
from astrbot.api.all import *
from astrbot.api.event import AstrMessageEvent, MessageChain, MessageEventResult
from astrbot.api.event.filter import (
    EventMessageType,
    PermissionType,
    command,
    event_message_type,
    permission_type,
)
from astrbot.api.message_components import Image, Plain
from astrbot.core.star.filter.command import GreedyStr
from astrbot.api.star import Context, Star, register

try:
    from .newapi_client import NewAPIClient
    from .renderer import DarkCardRenderer, format_bytes
except ImportError:
    from newapi_client import NewAPIClient
    from renderer import DarkCardRenderer, format_bytes


def get_plugin_data_dir() -> Path:
    """获取 AstrBot 官方指定的插件持久化数据目录 (data/plugin_data/astr_newapi_plugin)"""
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

        p = Path(get_astrbot_plugin_data_path()) / "astr_newapi_plugin"
        p.mkdir(parents=True, exist_ok=True)
        return p.resolve()
    except Exception:
        pass

    try:
        p = Path("data/plugin_data/astr_newapi_plugin").resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        pass

    p = Path(__file__).resolve().parent / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def migrate_legacy_data(target_dir: Path) -> None:
    """将历史遗留目录中的数据文件平滑迁移至 AstrBot 官方指定的 plugin_data 目录"""
    legacy_dirs = [
        Path(__file__).resolve().parent.parent,
        target_dir.parent / "astrbot_plugin_newapi",
    ]
    for legacy_dir in legacy_dirs:
        if not legacy_dir.exists() or legacy_dir.resolve() == target_dir.resolve():
            continue
        for fname in ["user_bindings.json", "cache.json", "config_backup.json"]:
            legacy_file = legacy_dir / fname
            target_file = target_dir / fname
            if legacy_file.exists() and not target_file.exists():
                try:
                    shutil.copy2(legacy_file, target_file)
                    logger.info(
                        f"[NewAPI] 已将历史数据 {fname} 自动迁移至官方目录: {target_file}"
                    )
                except Exception as e:
                    logger.warning(f"[NewAPI] 迁移历史数据 {fname} 失败: {e}")


# Command mapping for Chinese/English aliases and no-space inputs
CMD_MAPPING = {
    "menu": "menu",
    "help": "menu",
    "菜单": "menu",
    "帮助": "menu",
    "功能": "menu",
    "admin": "admin",
    "admin_menu": "admin",
    "管理": "admin",
    "管理菜单": "admin",
    "my": "my",
    "me": "my",
    "self": "my",
    "个人": "my",
    "个人信息": "my",
    "我的": "my",
    "余额": "my",
    "用量": "my",
    "订阅": "my",
    "bind": "bind",
    "绑定": "bind",
    "unbind": "unbind",
    "解绑": "unbind",
    "取消绑定": "unbind",
    "my_stat": "my_stat",
    "mystat": "my_stat",
    "个人统计": "my_stat",
    "我的统计": "my_stat",
    "我的消耗": "my_stat",
    "stat": "stat",
    "site_stat": "stat",
    "全站统计": "stat",
    "统计": "stat",
    "全站消耗": "stat",
    "ranking": "ranking",
    "rank": "ranking",
    "排行": "ranking",
    "排行榜": "ranking",
    "用户排行": "ranking",
    "消耗排行": "ranking",
    "model_ranking": "model_ranking",
    "models_ranking": "model_ranking",
    "模型排行": "model_ranking",
    "模型消耗": "model_ranking",
    "status": "status",
    "site_status": "status",
    "状态": "status",
    "系统状态": "status",
    "运行状态": "status",
    "redeem": "redeem",
    "topup": "redeem",
    "兑换": "redeem",
    "充值": "redeem",
    "user": "user",
    "user_info": "user",
    "查用户": "user",
    "用户详情": "user",
    "用户信息": "user",
    "create_user": "create_user",
    "new_user": "create_user",
    "创建用户": "create_user",
    "开户": "create_user",
    "create_cdk": "create_cdk",
    "cdk": "create_cdk",
    "生成兑换码": "create_cdk",
    "发卡": "create_cdk",
    "制卡": "create_cdk",
    "add_quota": "add_quota",
    "加额度": "add_quota",
    "增加额度": "add_quota",
    "充值用户": "add_quota",
    "sub_quota": "sub_quota",
    "扣额度": "sub_quota",
    "扣减额度": "sub_quota",
    "set_quota": "set_quota",
    "设额度": "set_quota",
    "设置额度": "set_quota",
    "重置额度": "set_quota",
    "enable_user": "enable_user",
    "解封": "enable_user",
    "解禁用户": "enable_user",
    "启用用户": "enable_user",
    "disable_user": "disable_user",
    "封号": "disable_user",
    "封禁用户": "disable_user",
    "禁用用户": "disable_user",
    "channels": "channels",
    "channel_list": "channels",
    "渠道": "channels",
    "渠道列表": "channels",
    "test_channel": "test_channel",
    "测速": "test_channel",
    "测试渠道": "test_channel",
    "token_list": "token_list",
    "tokens": "token_list",
    "令牌列表": "token_list",
    "查看令牌": "token_list",
    "token_add": "token_add",
    "创建令牌": "token_add",
    "添加令牌": "token_add",
    "token_del": "token_del",
    "删除令牌": "token_del",
    "token_key": "token_key",
    "查看秘钥": "token_key",
    "获取秘钥": "token_key",
    "backup": "backup",
    "备份": "backup",
    "export": "backup",
    "导出": "backup",
    "restore": "restore",
    "恢复": "restore",
    "还原": "restore",
}


@register(
    "astr_newapi_plugin",
    "Developer",
    "NewAPI 站点信息查询与管理插件，支持绑定账号查询用量/余额/订阅、全站统计、天/周/月/总消耗排行、用户管理、批量兑换码生成、数据备份与复原等功能。",
    "1.2.0",
)
class NewApiPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.context = context
        self.config = config
        self.data_dir = get_plugin_data_dir()
        migrate_legacy_data(self.data_dir)
        self.cache_file = self.data_dir / "cache.json"
        self.bindings_file = self.data_dir / "user_bindings.json"
        self.backups_dir = self.data_dir / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.client = self._init_client()
        cache = self._load_cache()
        self._site_name_cache = str(cache.get("system_name") or "").strip()
        self._site_name_base_url = self.client.base_url
        self._site_name_checked_at = 0.0

    def _init_client(self) -> NewAPIClient:
        site_url = self.config.get("site_url", "")
        api_token = self.config.get("api_token", "")
        api_user_id = self.config.get("api_user_id", "")
        timeout = int(self.config.get("request_timeout", 15) or 15)
        proxy = self.config.get("proxy", "") or None
        quota_per_unit = int(self.config.get("quota_per_unit", 500000) or 500000)
        return NewAPIClient(
            base_url=site_url,
            token=api_token,
            timeout=timeout,
            proxy=proxy,
            quota_per_unit=quota_per_unit,
            user_id=api_user_id,
        )

    def _refresh_client(self) -> NewAPIClient:
        self.client = self._init_client()
        return self.client

    async def _get_site_name(self, client: NewAPIClient) -> str:
        if self._site_name_base_url != client.base_url:
            self._site_name_cache = ""
            self._site_name_checked_at = 0.0
            self._site_name_base_url = client.base_url

        now = time.monotonic()
        if not client.base_url:
            return self._site_name_cache or "NewAPI"
        if not self._site_name_cache or now - self._site_name_checked_at >= 60:
            try:
                status = await client.get_status()
                site_name = status.get("system_name") if isinstance(status, dict) else None
                if site_name:
                    self._site_name_cache = str(site_name).strip()
                    self._save_cache("system_name", self._site_name_cache)
            except Exception as e:
                logger.debug("[NewAPI] 获取站点名称失败，使用缓存或域名: %s", e)
            self._site_name_checked_at = now

        return (
            self._site_name_cache
            or urlsplit(client.base_url).hostname
            or "NewAPI"
        )

    # --- Cache Management ---

    def _load_cache(self) -> Dict[str, Any]:
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        if "quota_per_unit" in data and self.client:
                            self.client.quota_per_unit = int(data["quota_per_unit"])
                        return data
        except Exception as e:
            logger.warning(f"[NewAPI] 读取缓存失败: {e}")
        return {}

    def _save_cache(self, key: str, value: Any) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            data = {}
            if self.cache_file.exists():
                try:
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            data[key] = value
            data["last_updated"] = int(time.time())
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[NewAPI] 写入缓存失败: {e}")

    # --- User Bindings Management ---

    def _load_bindings(self) -> Dict[str, Any]:
        try:
            if self.bindings_file.exists():
                with open(self.bindings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception as e:
            logger.warning(f"[NewAPI] 读取绑定配置失败: {e}")
        return {}

    def _save_binding(self, sender_id: str, user_id: int, username: str) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            bindings = self._load_bindings()
            bindings[str(sender_id)] = {
                "user_id": user_id,
                "username": username,
                "bind_time": int(time.time()),
            }
            with open(self.bindings_file, "w", encoding="utf-8") as f:
                json.dump(bindings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[NewAPI] 保存用户绑定失败: {e}")

    def _remove_binding(self, sender_id: str) -> bool:
        try:
            bindings = self._load_bindings()
            sid = str(sender_id)
            if sid in bindings:
                del bindings[sid]
                with open(self.bindings_file, "w", encoding="utf-8") as f:
                    json.dump(bindings, f, ensure_ascii=False, indent=2)
                return True
        except Exception as e:
            logger.warning(f"[NewAPI] 移除用户绑定失败: {e}")
        return False

    def _get_binding(self, sender_id: str) -> Optional[Dict[str, Any]]:
        bindings = self._load_bindings()
        return bindings.get(str(sender_id))

    # --- Permission & Security ---

    def _is_admin_enabled(self) -> bool:
        return bool(self.config.get("enable_admin", True))

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        if event.is_admin():
            return True
        sender_id = str(event.get_sender_id())
        try:
            bot_admins = self.context.get_config().get("admins_id", [])
            if sender_id in [str(a) for a in bot_admins]:
                return True
        except Exception:
            pass
        return False

    def _check_admin_permission(self, event: AstrMessageEvent) -> Optional[str]:
        """
        验证管理员权限。
        通过时返回 None；不通过时返回友好的中文提示字符串。
        严禁调用 event.stop_event()，确保用户知晓原因并能正常收到回复。
        """
        if not self._is_admin_enabled():
            return "❌ 管理功能已在插件设置中关闭。"
        admin_only = bool(self.config.get("admin_only", True))
        if admin_only and not self._is_admin(event):
            sender_id = event.get_sender_id()
            return (
            f"❌ 权限不足：该指令仅限机器人管理员使用。\n"
            f"• 当前用户编号：{sender_id}\n"
            f"• 管理员可在 AstrBot 管理面板中授予机器人管理员权限。"
            )
        return None

    def _get_plain_menu_text(self, is_adm: bool, site_name: str = "NewAPI") -> str:
        admin_status = "开启" if self._is_admin_enabled() else "关闭"
        lines = [
            f"📋 【{site_name} 服务菜单】",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📊 个人服务",
            "• /newapi 个人 - 查询已绑定账号的余额、用量和订阅",
            "• /newapi 绑定 <用户编号或用户名> - 绑定个人账号",
            "• /newapi 解绑 - 解除当前账号绑定",
            "• /newapi 我的统计 [今天/本周/本月/全部] - 查看个人消费统计",
            "• /newapi 全站统计 [今天/本周/本月/全部] - 查看全站消费和请求速率",
            "• /newapi 用户排行 [今天/本周/本月/总计] - 查看用户消费排行和图表",
            "• /newapi 模型排行 [今日/本周/本月/本年] - 查看模型与厂商排行图表",
            "• /newapi 状态 - 查看站点信息和远程资源数据",
            "• /newapi 兑换 <兑换码> - 使用兑换码充值",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"👑 管理功能：{admin_status}",
        ]
        if self._is_admin_enabled() and is_adm:
            lines.append("💡 管理员可发送 /newapi 管理 查看完整菜单")
        return "\n".join(lines)

    def _get_plain_admin_menu_text(self, site_name: str = "NewAPI") -> str:
        return "\n".join([
            f"👑 【{site_name} 管理菜单】",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "👤 用户和额度",
            "• /newapi 查用户 <用户编号或用户名> - 查看用户资料和余额",
            "• /newapi 创建用户 <账号> <密码> [昵称] - 创建普通用户",
            "• /newapi 加额度 <用户> <美元金额> - 增加用户额度",
            "• /newapi 扣额度 <用户> <美元金额> - 扣减用户额度",
            "• /newapi 设额度 <用户> <美元金额> - 设置用户额度",
            "• /newapi 解封 <用户> - 启用用户账号",
            "• /newapi 封号 <用户> - 禁用用户账号",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "🎟️ 兑换码和渠道",
            "• /newapi 生成兑换码 <美元面额> [数量] [名称] - 批量生成兑换码",
            "• /newapi 渠道列表 - 查看上游渠道和响应时间",
            "• /newapi 测试渠道 [渠道编号] - 测试渠道连接速度",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "🔑 访问令牌",
            "• /newapi 令牌列表 - 查看已创建的访问令牌",
            "• /newapi 创建令牌 <名称> [额度美元] - 创建访问令牌",
            "• /newapi 删除令牌 <编号> - 删除访问令牌",
            "• /newapi 查看秘钥 <编号> - 查看令牌完整密钥",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "💾 数据备份和恢复",
            "• /newapi 备份 - 导出绑定数据和配置文件",
            "• /newapi 恢复 [文件名] - 从备份文件恢复数据",
        ])

    # --- Helper Utilities ---

    def _get_time_bounds(self, period: str) -> Tuple[int, int, str]:
        now = datetime.datetime.now()
        end_ts = int(now.timestamp())
        period = (period or "day").lower().strip()

        if period in ["day", "today", "天", "日", "今日", "今天"]:
            start_of_day = datetime.datetime(now.year, now.month, now.day, 0, 0, 0)
            return int(start_of_day.timestamp()), end_ts, "今日"
        elif period in ["yesterday", "昨", "昨日"]:
            yesterday = now - datetime.timedelta(days=1)
            start_of_yesterday = datetime.datetime(
                yesterday.year, yesterday.month, yesterday.day, 0, 0, 0
            )
            end_of_yesterday = datetime.datetime(
                yesterday.year, yesterday.month, yesterday.day, 23, 59, 59
            )
            return (
                int(start_of_yesterday.timestamp()),
                int(end_of_yesterday.timestamp()),
                "昨日",
            )
        elif period in ["week", "周", "本周", "7d", "7天"]:
            start_of_week = now - datetime.timedelta(days=7)
            return int(start_of_week.timestamp()), end_ts, "近 7 天"
        elif period in ["month", "月", "本月", "30d", "30天"]:
            start_of_month = now - datetime.timedelta(days=30)
            return int(start_of_month.timestamp()), end_ts, "近 30 天"
        elif period in ["total", "all", "总", "总计", "全部", "历史"]:
            return 0, end_ts, "历史总计"
        else:
            start_of_day = datetime.datetime(now.year, now.month, now.day, 0, 0, 0)
            return int(start_of_day.timestamp()), end_ts, "今日"

    async def _resolve_user_id(
        self, identifier: str
    ) -> Tuple[Optional[int], Optional[str]]:
        identifier = str(identifier).strip()
        client = self._refresh_client()

        if identifier.isdigit():
            user_id = int(identifier)
            try:
                user = await client.get_user(user_id)
            except Exception as e:
                logger.warning("[NewAPI] 验证用户编号 %s 失败: %s", user_id, e)
                return None, None
            if not isinstance(user, dict) or not user.get("username"):
                return None, None
            return user_id, str(user["username"])

        try:
            users = await client.search_users(identifier)
            for u in users:
                if not isinstance(u, dict):
                    continue
                if str(u.get("username", "")).lower() == identifier.lower():
                    return int(u.get("id")), u.get("username")
            if users:
                first = next((user for user in users if isinstance(user, dict)), None)
                if not first:
                    return None, None
                return int(first.get("id")), first.get("username")
        except Exception:
            pass

        return None, None

    # ==========================================
    # Master Command & Standalone Registrations
    # ==========================================

    @command("newapi", alias={"newapi_help", "newapimenu", "newapi帮助"})
    async def newapi_main(self, event: AstrMessageEvent, input: GreedyStr):
        """NewAPI 站点信息查询与全能管理主入口指令"""
        content = str(input or "").strip()
        if not content:
            return await self.menu(event)

        parts = content.split(maxsplit=1)
        sub_cmd = parts[0].lower()
        raw_args = parts[1] if len(parts) > 1 else ""

        target = CMD_MAPPING.get(sub_cmd)
        if not target:
            for k, v in CMD_MAPPING.items():
                if sub_cmd == k:
                    target = v
                    break

        if not target:
            return await self.menu(event)

        return await self._dispatch_target(event, target, raw_args)

    @command("newapi_menu", alias={"newapi菜单"})
    async def cmd_menu(self, event: AstrMessageEvent):
        """显示 NewAPI 普通查询功能菜单"""
        return await self.menu(event)

    @command("newapi_my", alias={"newapi余额", "newapi我的", "newapi个人"})
    async def cmd_my(self, event: AstrMessageEvent):
        """查询个人绑定的 NewAPI 账户、用量、余额与订阅"""
        return await self.my_info(event)

    @command("newapi_bind", alias={"newapi绑定"})
    async def cmd_bind(self, event: AstrMessageEvent, user_identifier: str = ""):
        """绑定个人的 NewAPI 用户 ID 或用户名"""
        return await self.bind_user(event, user_identifier)

    @command("newapi_unbind", alias={"newapi解绑"})
    async def cmd_unbind(self, event: AstrMessageEvent):
        """解绑个人的 NewAPI 账号"""
        return await self.unbind_user(event)

    @command("newapi_stat", alias={"newapi统计", "newapi全站统计"})
    async def cmd_stat(self, event: AstrMessageEvent, period: str = "today"):
        """查询 NewAPI 全站消耗统计 [today/week/month/all]"""
        return await self.site_stat(event, period)

    @command("newapi_mystat", alias={"newapi个人统计"})
    async def cmd_mystat(self, event: AstrMessageEvent, period: str = "today"):
        """查询个人在指定周期内的消费统计 [today/week/month/all]"""
        return await self.my_stat(event, period)

    @command("newapi_ranking", alias={"newapi排行", "newapi排行榜"})
    async def cmd_ranking(self, event: AstrMessageEvent, period: str = "day"):
        """查询用户消耗排行榜 [day/week/month/total]"""
        return await self.user_ranking(event, period)

    @command("newapi_model_ranking", alias={"newapi模型排行"})
    async def cmd_model_ranking(self, event: AstrMessageEvent, period: str = "week"):
        """查询模型与厂商 Token 消耗排行 [today/week/month/year]"""
        return await self.model_ranking(event, period)

    @command("newapi_status", alias={"newapi状态", "newapi运行状态"})
    async def cmd_status(self, event: AstrMessageEvent):
        """查询 NewAPI 站点配置与服务器 CPU/内存/磁盘运行状态"""
        return await self.site_status(event)

    @command("newapi_redeem", alias={"newapi充值", "newapi兑换"})
    async def cmd_redeem(self, event: AstrMessageEvent, cdk_key: str = ""):
        """使用兑换码为当前账号充值"""
        return await self.redeem(event, cdk_key)

    @command("newapi_admin", alias={"newapi管理", "newapi管理菜单"})
    @permission_type(PermissionType.ADMIN)
    async def cmd_admin(self, event: AstrMessageEvent):
        """显示 NewAPI 管理员专用菜单"""
        return await self.admin_menu(event)

    @command("newapi_backup", alias={"newapi备份", "newapi导出"})
    @permission_type(PermissionType.ADMIN)
    async def cmd_backup(self, event: AstrMessageEvent):
        """管理员打包备份所有用户绑定与配置数据并导出"""
        return await self.backup_data_cmd(event)

    @command("newapi_restore", alias={"newapi恢复", "newapi还原"})
    @permission_type(PermissionType.ADMIN)
    async def cmd_restore(self, event: AstrMessageEvent, filename: str = ""):
        """管理员从备份压缩包解包复原数据"""
        return await self.restore_data_cmd(event, filename)

    # ==========================================
    # User / Query Commands
    # ==========================================

    async def menu(self, event: AstrMessageEvent):
        """显示中文个人功能菜单。"""
        admin_status = "开启" if self._is_admin_enabled() else "关闭"
        is_adm = self._is_admin(event)
        client = self._refresh_client()
        site_name = await self._get_site_name(client)

        sections = [
            (
                "📊 个人服务",
                [
                    ("/newapi 个人", "查看已绑定账号的余额、用量和订阅"),
                    ("/newapi 绑定 <用户编号或用户名>", "绑定你自己的 NewAPI 账号"),
                    ("/newapi 解绑", "解除当前账号绑定"),
                    ("/newapi 我的统计 [今天/本周/本月/全部]", "查看已绑定账号的消费统计"),
                    ("/newapi 全站统计 [今天/本周/本月/全部]", "查看全站消费和请求速率"),
                    ("/newapi 用户排行 [今天/本周/本月/总计]", "查看消费排行和占比图"),
                    ("/newapi 模型排行 [今日/本周/本月/本年]", "查看模型柱状图和厂商占比图"),
                    ("/newapi 状态", "查看站点版本和可用的远程资源数据"),
                    ("/newapi 兑换 <兑换码>", "使用兑换码充值"),
                ],
            )
        ]

        footer = f"管理功能：{admin_status}"
        if self._is_admin_enabled() and is_adm:
            footer += "  |  管理员可发送 /newapi 管理 查看管理菜单"

        try:
            img_path = DarkCardRenderer.render_menu(
                title=f"{site_name} 服务菜单",
                subtitle="选择下方中文指令即可使用",
                sections=sections,
                footer_note=footer,
            )
            if img_path and os.path.exists(img_path):
                return event.image_result(img_path)
        except Exception as e:
            logger.warning(f"[NewAPI] 暗色卡片菜单渲染异常，降级为纯文本回复: {e}")

        return event.plain_result(self._get_plain_menu_text(is_adm, site_name))

    async def admin_menu(self, event: AstrMessageEvent):
        """显示中文管理员菜单。"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        sections = [
            (
                "👤 用户和额度",
                [
                    ("/newapi 查用户 <用户编号或用户名>", "查看用户资料和余额"),
                    ("/newapi 创建用户 <账号> <密码>", "创建普通用户"),
                    ("/newapi 加额度 <用户> <美元金额>", "给用户增加额度"),
                    ("/newapi 扣额度 <用户> <美元金额>", "扣减用户额度"),
                    ("/newapi 设额度 <用户> <美元金额>", "设置用户额度"),
                    ("/newapi 解封 <用户>", "启用用户账号"),
                    ("/newapi 封号 <用户>", "禁用用户账号"),
                ],
            ),
            (
                "🎟️ 兑换码和渠道",
                [
                    ("/newapi 生成兑换码 <美元面额> [数量]", "批量生成兑换码"),
                    ("/newapi 渠道列表", "查看上游渠道和响应时间"),
                    ("/newapi 测试渠道 [渠道编号]", "测试渠道连接速度"),
                ],
            ),
            (
                "🔑 访问令牌",
                [
                    ("/newapi 令牌列表", "查看已创建的访问令牌"),
                    ("/newapi 创建令牌 <名称> [额度美元]", "创建访问令牌"),
                    ("/newapi 删除令牌 <编号>", "删除访问令牌"),
                    ("/newapi 查看秘钥 <编号>", "查看令牌完整密钥"),
                ],
            ),
            (
                "💾 数据备份和恢复",
                [
                    ("/newapi 备份", "导出绑定数据和配置文件"),
                    ("/newapi 恢复 [文件名]", "从备份文件恢复数据"),
                ],
            ),
        ]

        client = self._refresh_client()
        site_name = await self._get_site_name(client)
        try:
            img_path = DarkCardRenderer.render_menu(
                title=f"👑 {site_name} 管理菜单",
                subtitle="仅供机器人管理员使用",
                sections=sections,
                footer_note="提醒：创建、封禁、调额等操作会立即生效。",
            )
            if img_path and os.path.exists(img_path):
                return event.image_result(img_path)
        except Exception as e:
            logger.warning(f"[NewAPI] 管理菜单暗色卡片渲染异常，降级为纯文本回复: {e}")

        return event.plain_result(self._get_plain_admin_menu_text(site_name))

    async def bind_user(self, event: AstrMessageEvent, user_identifier: str = ""):
        """绑定个人的 NewAPI 用户 ID 或用户名"""
        user_identifier = user_identifier.strip()
        if not user_identifier:
            return event.plain_result(
                "用法：/newapi 绑定 <用户编号或用户名>\n例如：/newapi 绑定 10"
            )

        client = self._refresh_client()
        if not client.is_configured():
            return event.plain_result(
                "❌ 尚未在插件设置中配置 NewAPI 站点地址或访问令牌。"
            )

        user_id, uname = await self._resolve_user_id(user_identifier)
        if not user_id:
            return event.plain_result(
                f"❌ 未能找到匹配的用户 [{user_identifier}]，请检查后重试。"
            )

        sender_id = event.get_sender_id()
        self._save_binding(str(sender_id), user_id, uname or str(user_id))
        return event.plain_result(
            f"✅ 绑定成功！\n"
            f"• 绑定账号：{uname}（编号：{user_id}）\n"
            f"• 现在可发送 /newapi 个人 查询用量、余额与订阅信息。"
        )

    async def unbind_user(self, event: AstrMessageEvent):
        """解绑个人的 NewAPI 账号"""
        sender_id = event.get_sender_id()
        removed = self._remove_binding(str(sender_id))
        if removed:
            return event.plain_result("✅ 解绑成功！已解除与 NewAPI 账号的绑定。")
        else:
            return event.plain_result("💡 您当前尚未绑定任何 NewAPI 账号。")

    async def my_info(self, event: AstrMessageEvent):
        """查询个人绑定的 NewAPI 账户、用量、余额与订阅情况 (文本返回)"""
        client = self._refresh_client()
        if not client.is_configured():
            return event.plain_result(
                "❌ 尚未在插件设置中配置 NewAPI 站点地址或访问令牌。"
            )

        sender_id = str(event.get_sender_id())
        binding = self._get_binding(sender_id)
        if not isinstance(binding, dict):
            return event.plain_result(
                "💡 你还没有绑定 NewAPI 账号。\n"
                "请发送 /newapi 绑定 <用户编号或用户名>，绑定后即可查询余额、用量和订阅。"
            )

        try:
            uid = int(binding.get("user_id"))
        except (TypeError, ValueError):
            return event.plain_result(
                "❌ 绑定记录无效，请先发送 /newapi 解绑，再重新绑定账号。"
            )

        try:
            target_user = await client.get_user(uid)
        except Exception as e:
            logger.warning("[NewAPI] 查询绑定用户 %s 失败: %s", uid, e)
            return event.plain_result(f"❌ 查询绑定账号失败：{e}")
        if not isinstance(target_user, dict) or not target_user:
            return event.plain_result(
                "❌ 绑定的 NewAPI 账号不存在或当前访问令牌无权查询。\n"
                "请检查用户编号和访问令牌权限后重新绑定。"
            )

        try:
            subscriptions = await client.get_user_subscriptions(uid)
        except Exception as e:
            logger.warning("[NewAPI] 查询用户 %s 订阅失败: %s", uid, e)
            subscriptions = None

        uname = target_user.get("username", "未知")
        dname = target_user.get("display_name", uname)
        name_display = f"{uname} ({dname})" if dname and dname != uname else uname
        uid = target_user.get("id", "-")
        status_code = target_user.get("status", 1)
        status_str = "🟢正常" if status_code == 1 else "🔴封禁/禁用"
        group = target_user.get("group", "default")
        quota = target_user.get("quota", 0)
        used_quota = target_user.get("used_quota", 0)
        req_count = target_user.get("request_count", 0)

        # Parse subscriptions
        sub_desc = "暂无活跃订阅"
        if subscriptions is None:
            sub_desc = "暂不可获取"
        elif subscriptions:
            sub_lines = []
            for s in subscriptions:
                if isinstance(s, dict):
                    title = s.get("title") or s.get("plan_title") or "会员订阅"
                    expires = s.get("expires_at") or s.get("expired_time")
                    if expires and expires > 0:
                        exp_str = time.strftime("%Y-%m-%d", time.localtime(expires))
                        sub_lines.append(f"{title} (至 {exp_str})")
                    else:
                        sub_lines.append(f"{title}")
            if sub_lines:
                sub_desc = "、".join(sub_lines)

        msg = (
            f"👤 【NewAPI 账户与余额】\n"
            f"• 用户名：{name_display}\n"
            f"• 用户编号：{uid}  |  状态：{status_str}\n"
            f"• 所属分组：{group}\n"
            f"• 剩余额度：{client.format_quota(int(quota or 0))}\n"
            f"• 累计消费：{client.format_quota(int(used_quota or 0))}\n"
            f"• 请求次数：{int(req_count or 0):,} 次\n"
            f"• 订阅情况：{sub_desc}"
        )
        return event.plain_result(msg)

    async def my_stat(self, event: AstrMessageEvent, period: str = "today"):
        """查询个人在指定周期内的消费统计 [today/week/month/all] (文本返回)"""
        client = self._refresh_client()
        if not client.is_configured():
            return event.plain_result(
                "❌ 尚未在插件设置中配置 NewAPI 站点地址或访问令牌。"
            )

        binding = self._get_binding(str(event.get_sender_id()))
        if not isinstance(binding, dict):
            return event.plain_result(
                "💡 你还没有绑定 NewAPI 账号。\n"
                "请发送 /newapi 绑定 <用户编号或用户名>，再查询个人统计。"
            )

        username = str(binding.get("username") or "").strip()
        if not username:
            return event.plain_result(
                "❌ 绑定记录缺少用户名，请先发送 /newapi 解绑，再重新绑定账号。"
            )

        start_ts, end_ts, label = self._get_time_bounds(period)
        try:
            stat = await client.get_site_stat(
                start_ts, end_ts, username=username
            )
        except Exception as e:
            return event.plain_result(f"❌ 查询个人消耗统计失败: {e}")

        if not isinstance(stat, dict):
            return event.plain_result("❌ NewAPI 未返回个人统计数据，请稍后重试。")

        consumed_quota = stat.get("quota", 0)
        rpm = stat.get("rpm", 0)
        tpm = stat.get("tpm", 0)
        site_name = await self._get_site_name(client)

        msg = (
            f"📈 【{site_name} 个人消费统计 - {label}】\n"
            f"• 消费金额: {client.format_quota(consumed_quota)}\n"
            f"• 每分钟请求数：{rpm:,}\n"
            f"• 每分钟词元数：{tpm:,}"
        )
        return event.plain_result(msg)

    async def site_stat(self, event: AstrMessageEvent, period: str = "today"):
        """查询 NewAPI 全站消耗统计 [today/week/month/all] (文本返回)"""
        client = self._refresh_client()
        if not client.is_configured():
            return event.plain_result(
                "❌ 尚未在插件设置中配置 NewAPI 站点地址或访问令牌。"
            )

        start_ts, end_ts, label = self._get_time_bounds(period)
        try:
            stat = await client.get_site_stat(start_ts, end_ts)
        except Exception as e:
            return event.plain_result(f"❌ 查询全站统计失败: {e}")

        if not isinstance(stat, dict):
            return event.plain_result("❌ NewAPI 未返回全站统计数据，请稍后重试。")

        consumed_quota = stat.get("quota", 0)
        rpm = stat.get("rpm", 0)
        tpm = stat.get("tpm", 0)
        site_name = await self._get_site_name(client)

        msg = (
            f"🌐 【{site_name} 全站消费统计 - {label}】\n"
            f"• 全站消耗: {client.format_quota(consumed_quota)}\n"
            f"• 每分钟请求数：{rpm:,}\n"
            f"• 每分钟词元数：{tpm:,}"
        )
        return event.plain_result(msg)

    async def user_ranking(self, event: AstrMessageEvent, period: str = "day"):
        """查询用户消耗排行榜 [day/week/month/total] (PIL暗色图或纯文本)"""
        client = self._refresh_client()
        if not client.is_configured():
            return event.plain_result(
                "❌ 尚未在插件设置中配置 NewAPI 站点地址或访问令牌。"
            )

        period_key = (period or "day").lower().strip()
        start_ts, end_ts, label = self._get_time_bounds(period_key)

        try:
            formatted_rows: List[Tuple[int, str, str, str, int]] = []

            if period_key in ["total", "all", "总", "总计", "全部", "历史"]:
                users, _ = await client.get_all_users(p=0, size=100)
                if not users:
                    return event.plain_result("📊 暂无用户消耗数据。")

                valid_users = [
                    u
                    for u in users
                    if isinstance(u, dict) and u.get("used_quota", 0) > 0
                ]
                valid_users.sort(key=lambda x: x.get("used_quota", 0), reverse=True)
                top_users = valid_users[:10]

                if not top_users:
                    return event.plain_result(
                        f"📊 【用户消耗排行 - {label}】\n暂无任何消耗记录。"
                    )

                for i, u in enumerate(top_users, 1):
                    uname = u.get("username", "匿名")
                    dname = u.get("display_name", "")
                    name_display = (
                        f"{uname} ({dname})" if dname and dname != uname else uname
                    )
                    used = int(u.get("used_quota") or 0)
                    req_cnt = int(u.get("request_count") or 0)
                    extra = f"{req_cnt:,} 次请求" if req_cnt else ""
                    formatted_rows.append(
                        (i, name_display, client.format_quota(used), extra, used)
                    )

            else:
                data_list = await client.get_user_quota_dates(start_ts, end_ts)
                if not data_list:
                    return event.plain_result(
                        f"📊 【用户消耗排行 - {label}】\n该周期内暂无消耗数据。"
                    )

                aggregated: Dict[str, int] = {}
                token_aggregated: Dict[str, int] = {}
                for item in data_list:
                    if not isinstance(item, dict):
                        continue
                    uname = item.get("username") or "匿名用户"
                    quota_used = int(item.get("quota") or 0)
                    tokens = int(item.get("token_used") or 0)
                    aggregated[uname] = aggregated.get(uname, 0) + quota_used
                    token_aggregated[uname] = token_aggregated.get(uname, 0) + tokens

                sorted_users = sorted(
                    aggregated.items(), key=lambda x: x[1], reverse=True
                )
                top_users = sorted_users[:10]

                if not top_users or all(q <= 0 for _, q in top_users):
                    return event.plain_result(
                        f"📊 【用户消耗排行 - {label}】\n该周期内暂无消耗记录。"
                    )

                for i, (uname, quota_val) in enumerate(top_users, 1):
                    tok_val = token_aggregated.get(uname, 0)
                    extra = f"{tok_val:,} 个词元" if tok_val else ""
                    formatted_rows.append(
                        (
                            i,
                            uname,
                            client.format_quota(quota_val),
                            extra,
                            quota_val,
                        )
                    )

            site_name = urlsplit(client.base_url).hostname or "NewAPI"
            try:
                site_name = await self._get_site_name(client)
                img_path = DarkCardRenderer.render_user_rankings(
                    label, formatted_rows, site_name=site_name
                )
                if img_path and os.path.exists(img_path):
                    return event.image_result(img_path)
            except Exception as e:
                logger.warning(f"[NewAPI] 用户排行暗色卡片渲染异常，降级为纯文本回复: {e}")

            lines = [f"📊 【{site_name} 用户消费排行 前十 - {label}】"]
            for rk, uname, q_str, extra, _quota in formatted_rows:
                extra_str = f"（{extra}）" if extra else ""
                lines.append(f"第 {rk} 名  {uname}：{q_str}{extra_str}")
            return event.plain_result("\n".join(lines))

        except Exception as e:
            return event.plain_result(f"❌ 获取排行榜失败: {e}")

    async def model_ranking(self, event: AstrMessageEvent, period: str = "week"):
        """查询模型与厂商 Token 消耗排行 [today/week/month/year] (PIL暗色图或纯文本)"""
        client = self._refresh_client()
        if not client.is_configured():
            return event.plain_result(
                "❌ 尚未在插件设置中配置 NewAPI 站点地址或访问令牌。"
            )

        p_map = {
            "day": "today",
            "today": "today",
            "今日": "today",
            "今天": "today",
            "week": "week",
            "周": "week",
            "本周": "week",
            "month": "month",
            "月": "month",
            "本月": "month",
            "year": "year",
            "年": "year",
            "本年": "year",
        }
        period_key = str(period or "本周").lower().strip()
        query_period = p_map.get(period_key, "week")
        period_label = {
            "today": "今日",
            "week": "本周",
            "month": "本月",
            "year": "本年",
        }[query_period]

        try:
            rankings = await client.get_rankings(query_period)
        except Exception as e:
            return event.plain_result(f"❌ 获取模型排行失败: {e}")

        if not isinstance(rankings, dict):
            return event.plain_result("❌ NewAPI 返回的排行数据格式不正确。")
        models = rankings.get("models", [])
        vendors = rankings.get("vendors", [])
        models = models if isinstance(models, list) else []
        vendors = vendors if isinstance(vendors, list) else []

        if not models and not vendors:
            return event.plain_result(f"📊 {period_label} 暂无模型消费数据。")

        site_name = urlsplit(client.base_url).hostname or "NewAPI"
        try:
            site_name = await self._get_site_name(client)
            img_path = DarkCardRenderer.render_model_rankings(
                period_label, models, vendors, site_name=site_name
            )
            if img_path and os.path.exists(img_path):
                return event.image_result(img_path)
        except Exception as e:
            logger.warning(f"[NewAPI] 模型排行暗色卡片渲染异常，降级为纯文本回复: {e}")

        lines = [f"🤖 【{site_name} 模型消费排行 - {period_label}】"]
        models = [m for m in models if isinstance(m, dict)]
        for idx, m in enumerate(models[:10], 1):
            name = m.get("model_name", "未知")
            tok = int(m.get("total_tokens") or 0)
            share = m.get("share")
            try:
                share_ratio = float(share)
                share_label = f"{share_ratio:.2%}" if 0 <= share_ratio <= 1 else "占比暂不可获取"
            except (TypeError, ValueError):
                share_label = "占比暂不可获取"
            lines.append(f"第 {idx} 名  {name}：{tok:,} 个词元 · {share_label}")
        if vendors:
            lines.append("厂商词元占比：")
            for vendor in vendors[:5]:
                if not isinstance(vendor, dict):
                    continue
                vendor_name = str(vendor.get("vendor") or "其他")
                vendor_tokens = int(vendor.get("total_tokens") or 0)
                try:
                    vendor_share = float(vendor.get("share"))
                    vendor_share_label = (
                        f"{vendor_share:.2%}"
                        if 0 <= vendor_share <= 1
                        else "占比暂不可获取"
                    )
                except (TypeError, ValueError):
                    vendor_share_label = "占比暂不可获取"
                lines.append(
                    f"• {vendor_name}：{vendor_tokens:,} 个词元 · {vendor_share_label}"
                )
        return event.plain_result("\n".join(lines))

    async def site_status(self, event: AstrMessageEvent):
        """查询 NewAPI 站点配置与服务器 CPU/内存/磁盘运行状态 (PIL暗色图或纯文本)"""
        client = self._refresh_client()
        if not client.base_url:
            return event.plain_result("❌ 尚未在插件设置中配置 NewAPI 站点地址。")

        try:
            status = await client.get_status()
        except Exception as e:
            return event.plain_result(f"❌ 获取站点状态失败: {e}")
        if not isinstance(status, dict):
            return event.plain_result("❌ NewAPI 返回的站点状态格式不正确，请稍后重试。")
        if "quota_per_unit" in status:
            self._save_cache("quota_per_unit", status["quota_per_unit"])
        if status.get("system_name"):
            self._site_name_cache = str(status["system_name"]).strip()
            self._site_name_base_url = client.base_url
            self._site_name_checked_at = time.monotonic()
            self._save_cache("system_name", self._site_name_cache)

        # Only display values returned by NewAPI; unavailable values stay None.
        sys_metrics = {
            "cpu_percent": None,
            "mem_alloc_bytes": None,
            "mem_sys_bytes": None,
            "disk_percent": None,
            "disk_used_gb": None,
            "disk_total_gb": None,
        }
        try:
            perf = await client.get_performance_stats()
            logger.info(
                "[NewAPI] /api/performance/stats response: %s",
                json.dumps(perf, ensure_ascii=False),
            )
        except Exception as e:
            logger.error("[NewAPI] 获取远程性能数据失败: %s", e)
            perf = None

        if isinstance(perf, dict):
            memory_stats = perf.get("memory_stats")
            if isinstance(memory_stats, dict):
                for key in ("alloc", "sys"):
                    value = memory_stats.get(key)
                    if isinstance(value, (int, float)) and value >= 0:
                        sys_metrics[f"mem_{key}_bytes"] = value

            disk_info = perf.get("disk_space_info")
            if isinstance(disk_info, dict):
                total = disk_info.get("total")
                used = disk_info.get("used")
                percent = disk_info.get("used_percent")
                if isinstance(total, (int, float)) and total > 0:
                    sys_metrics["disk_total_gb"] = round(total / (1024**3), 1)
                    if isinstance(used, (int, float)) and used >= 0:
                        sys_metrics["disk_used_gb"] = round(used / (1024**3), 1)
                if isinstance(percent, (int, float)) and 0 <= percent <= 100:
                    sys_metrics["disk_percent"] = round(percent, 1)

        try:
            img_path = DarkCardRenderer.render_status(status, sys_metrics)
            if img_path and os.path.exists(img_path):
                return event.image_result(img_path)
        except Exception as e:
            logger.warning(f"[NewAPI] 状态暗色卡片渲染异常，降级为纯文本回复: {e}")

        s_name = status.get("system_name", "NewAPI 站点")
        ver = status.get("version", "未知")
        cpu_percent = sys_metrics["cpu_percent"]
        cpu_text = f"{cpu_percent:.1f}%" if cpu_percent is not None else "暂不可获取"
        mem_alloc = sys_metrics["mem_alloc_bytes"]
        mem_sys = sys_metrics["mem_sys_bytes"]
        alloc_text = format_bytes(mem_alloc)
        sys_text = format_bytes(mem_sys)
        memory_text = f"已分配 {alloc_text} / 进程持有 {sys_text}"
        disk_percent = sys_metrics["disk_percent"]
        disk_used = sys_metrics["disk_used_gb"]
        disk_total = sys_metrics["disk_total_gb"]
        disk_percent_text = (
            f"{disk_percent:.1f}%" if disk_percent is not None else "暂不可获取"
        )
        disk_used_text = (
            f"{disk_used:.1f}GB" if disk_used is not None else "暂不可获取"
        )
        disk_total_text = (
            f"{disk_total:.1f}GB" if disk_total is not None else "暂不可获取"
        )
        disk_text = f"{disk_percent_text} ({disk_used_text} / {disk_total_text})"
        return event.plain_result(
            f"🖥️ 【{s_name} 系统状态】\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• 站点版本: {ver}\n"
            f"• 处理器使用率：{cpu_text}\n"
            f"• 进程内存：{memory_text}\n"
            f"• 缓存所在磁盘：{disk_text}"
        )

    async def redeem(self, event: AstrMessageEvent, cdk_key: str = ""):
        """使用兑换码为当前账号充值 (文本返回)"""
        cdk_key = cdk_key.strip()
        if not cdk_key:
            return event.plain_result("用法：/newapi 兑换 <兑换码>")

        client = self._refresh_client()
        if not client.is_configured():
            return event.plain_result(
                "❌ 尚未在插件设置中配置 NewAPI 站点地址或访问令牌。"
            )

        try:
            res = await client.redeem_code(cdk_key)
            msg = res.get("message") or "充值成功！"
            return event.plain_result(f"🎉 {msg}")
        except Exception as e:
            return event.plain_result(f"❌ 兑换失败: {e}")

    # ==========================================
    # Admin / Management Commands
    # ==========================================

    async def get_user_info(self, event: AstrMessageEvent, username_or_id: str = ""):
        """管理员查询指定用户详细信息 (文本返回)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        if not username_or_id:
            return event.plain_result("用法：/newapi 查用户 <用户名或用户编号>")

        client = self._refresh_client()
        user_id, resolved_name = await self._resolve_user_id(username_or_id)
        if not user_id:
            return event.plain_result(f"❌ 未找到匹配的用户: {username_or_id}")

        try:
            user = await client.get_user(user_id)
        except Exception as e:
            return event.plain_result(f"❌ 获取用户信息失败: {e}")

        uname = user.get("username", "未知")
        dname = user.get("display_name", uname)
        uid = user.get("id", user_id)
        status_code = user.get("status", 1)
        status_str = "正常" if status_code == 1 else "已封禁/禁用"
        role_num = user.get("role", 1)
        role_str = "管理员" if role_num >= 10 else "普通用户"
        email = user.get("email", "未绑定")
        quota = user.get("quota", 0)
        used_quota = user.get("used_quota", 0)
        req_count = user.get("request_count", 0)
        group = user.get("group", "default")
        created_at = user.get("created_at", 0)
        created_str = (
            datetime.datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M:%S")
            if created_at
            else "未知"
        )

        msg = (
            f"👤 【用户详细信息】\n"
            f"• 用户 ID: {uid}\n"
            f"• 用户名: {uname} ({dname})\n"
            f"• 账户状态: {status_str}\n"
            f"• 角色权限: {role_str}\n"
            f"• 用户分组: {group}\n"
            f"• 绑定邮箱: {email}\n"
            f"• 剩余额度: {client.format_quota(quota)}\n"
            f"• 累计消耗: {client.format_quota(used_quota)}\n"
            f"• 请求次数: {req_count:,} 次\n"
            f"• 注册时间: {created_str}"
        )
        return event.plain_result(msg)

    async def create_user_cmd(
        self,
        event: AstrMessageEvent,
        username: str = "",
        password: str = "",
        display_name: str = "",
    ):
        """管理员创建新用户 (文本返回)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        if not username or not password:
            return event.plain_result(
                "用法：/newapi 创建用户 <用户名> <密码> [昵称]"
            )

        client = self._refresh_client()
        try:
            res = await client.create_user(
                username=username,
                password=password,
                display_name=display_name or username,
                role=1,
            )
            msg = res.get("message") or "用户创建成功！"
            return event.plain_result(
                f"✅ {msg}\n"
                f"• 用户名: {username}\n"
                f"• 初始密码: {password}\n"
                f"• 昵称: {display_name or username}"
            )
        except Exception as e:
            return event.plain_result(f"❌ 创建用户失败: {e}")

    async def create_cdk_cmd(
        self,
        event: AstrMessageEvent,
        quota_usd: float = 1.0,
        count: int = 1,
        name: str = "AstrBot生成",
    ):
        """管理员批量生成充值兑换码 (文本返回，方便复制)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        if quota_usd <= 0:
            return event.plain_result("❌ 兑换码面额必须大于 0 美元。")
        if count <= 0 or count > 100:
            return event.plain_result("❌ 兑换码生成数量必须在 1 ~ 100 之间。")

        client = self._refresh_client()
        quota_points = client.usd_to_quota(quota_usd)

        try:
            keys = await client.create_redemption(
                name=name or "AstrBot生成",
                count=count,
                quota=quota_points,
                expired_time=-1,
            )
            if not keys:
                return event.plain_result("❌ 兑换码创建失败，未能获取到生成的 CDK。")

            lines = [
                f"🎟️ 【成功生成 {len(keys)} 张兑换码】",
                f"• 面额: ${quota_usd:.2f} ({quota_points:,} 点)",
                f"• 标识名称: {name}",
                "• 兑换码列表:",
            ]
            for idx, key in enumerate(keys, 1):
                lines.append(f"{idx}. {key}")

            return event.plain_result("\n".join(lines))
        except Exception as e:
            return event.plain_result(f"❌ 创建兑换码失败: {e}")

    async def add_quota_cmd(
        self,
        event: AstrMessageEvent,
        user_identifier: str = "",
        quota_usd: float = 0.0,
    ):
        """管理员为指定用户增加额度 (文本返回)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        if not user_identifier or quota_usd <= 0:
            return event.plain_result(
                "用法：/newapi 加额度 <用户编号或用户名> <美元金额>"
            )

        client = self._refresh_client()
        user_id, uname = await self._resolve_user_id(user_identifier)
        if not user_id:
            return event.plain_result(f"❌ 未找到匹配的用户: {user_identifier}")

        quota_points = client.usd_to_quota(quota_usd)
        try:
            await client.manage_user_quota(
                user_id=user_id, mode="add", value_quota=quota_points
            )
            return event.plain_result(
                f"✅ 成功为用户 [{uname} (ID: {user_id})] 增加额度 ${quota_usd:.2f} ({quota_points:,} 点)！"
            )
        except Exception as e:
            return event.plain_result(f"❌ 增加额度失败: {e}")

    async def sub_quota_cmd(
        self,
        event: AstrMessageEvent,
        user_identifier: str = "",
        quota_usd: float = 0.0,
    ):
        """管理员扣减指定用户额度 (文本返回)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        if not user_identifier or quota_usd <= 0:
            return event.plain_result(
                "用法：/newapi 扣额度 <用户编号或用户名> <美元金额>"
            )

        client = self._refresh_client()
        user_id, uname = await self._resolve_user_id(user_identifier)
        if not user_id:
            return event.plain_result(f"❌ 未找到匹配的用户: {user_identifier}")

        quota_points = client.usd_to_quota(quota_usd)
        try:
            await client.manage_user_quota(
                user_id=user_id, mode="subtract", value_quota=quota_points
            )
            return event.plain_result(
                f"✅ 成功为用户 [{uname} (ID: {user_id})] 扣减额度 ${quota_usd:.2f} ({quota_points:,} 点)！"
            )
        except Exception as e:
            return event.plain_result(f"❌ 扣减额度失败: {e}")

    async def set_quota_cmd(
        self,
        event: AstrMessageEvent,
        user_identifier: str = "",
        quota_usd: float = 0.0,
    ):
        """管理员直接设置指定用户额度 (文本返回)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        if not user_identifier or quota_usd < 0:
            return event.plain_result(
                "用法：/newapi 设额度 <用户编号或用户名> <美元金额>"
            )

        client = self._refresh_client()
        user_id, uname = await self._resolve_user_id(user_identifier)
        if not user_id:
            return event.plain_result(f"❌ 未找到匹配的用户: {user_identifier}")

        quota_points = client.usd_to_quota(quota_usd)
        try:
            await client.manage_user_quota(
                user_id=user_id, mode="override", value_quota=quota_points
            )
            return event.plain_result(
                f"✅ 成功将用户 [{uname} (ID: {user_id})] 额度重设为 ${quota_usd:.2f} ({quota_points:,} 点)！"
            )
        except Exception as e:
            return event.plain_result(f"❌ 设置额度失败: {e}")

    async def enable_user_cmd(self, event: AstrMessageEvent, user_identifier: str = ""):
        """管理员解禁/启用用户 (文本返回)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        if not user_identifier:
            return event.plain_result("用法：/newapi 解封 <用户编号或用户名>")

        client = self._refresh_client()
        user_id, uname = await self._resolve_user_id(user_identifier)
        if not user_id:
            return event.plain_result(f"❌ 未找到匹配的用户: {user_identifier}")

        try:
            await client.manage_user_status(user_id=user_id, action="enable")
            return event.plain_result(
                f"✅ 成功启用/解禁用户 [{uname} (ID: {user_id})]！"
            )
        except Exception as e:
            return event.plain_result(f"❌ 启用用户失败: {e}")

    async def disable_user_cmd(
        self, event: AstrMessageEvent, user_identifier: str = ""
    ):
        """管理员封禁/禁用用户 (文本返回)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        if not user_identifier:
            return event.plain_result("用法：/newapi 封号 <用户编号或用户名>")

        client = self._refresh_client()
        user_id, uname = await self._resolve_user_id(user_identifier)
        if not user_id:
            return event.plain_result(f"❌ 未找到匹配的用户: {user_identifier}")

        try:
            await client.manage_user_status(user_id=user_id, action="disable")
            return event.plain_result(
                f"🚫 成功禁用/封禁用户 [{uname} (ID: {user_id})]！"
            )
        except Exception as e:
            return event.plain_result(f"❌ 禁用用户失败: {e}")

    async def list_channels_cmd(self, event: AstrMessageEvent):
        """管理员查看上游渠道列表 (PIL暗色图或纯文本)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        client = self._refresh_client()
        try:
            channels, total = await client.list_channels(p=0, size=15)
            if not channels:
                return event.plain_result("📡 暂无已配置的上游渠道。")

            try:
                site_name = await self._get_site_name(client)
                img_path = DarkCardRenderer.render_channels(
                    channels, total, site_name=site_name
                )
                if img_path and os.path.exists(img_path):
                    return event.image_result(img_path)
            except Exception as e:
                logger.warning(f"[NewAPI] 渠道暗色卡片渲染异常，降级为纯文本回复: {e}")

            lines = [f"📡 【上游渠道列表 (共 {total} 个)】"]
            for c in channels:
                cid = c.get("id", "-")
                cname = c.get("name", "未命名")
                cstatus = "🟢正常" if c.get("status") == 1 else "🔴禁用"
                resp_ms = c.get("response_time", 0)
                resp_str = f"{resp_ms}ms" if resp_ms else "-"
                lines.append(f"• ID:{cid} | {cname} [{cstatus}] 响应: {resp_str}")
            return event.plain_result("\n".join(lines))
        except Exception as e:
            return event.plain_result(f"❌ 获取渠道列表失败: {e}")

    async def test_channel_cmd(self, event: AstrMessageEvent, channel_id: int = 0):
        """管理员测试渠道连接与响应延迟 (文本返回)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        client = self._refresh_client()
        try:
            target_id = channel_id if channel_id > 0 else None
            res = await client.test_channel(target_id)

            if target_id:
                time_taken = res.get("time_taken", 0) if isinstance(res, dict) else 0
                return event.plain_result(
                    f"⚡ 渠道 [{target_id}] 测试成功，响应时间: {time_taken:.2f}s"
                )
            else:
                return event.plain_result("⚡ 渠道连通性测试完成，详情已在后台更新。")
        except Exception as e:
            return event.plain_result(f"❌ 渠道测试失败: {e}")

    async def list_tokens_cmd(self, event: AstrMessageEvent):
        """查看当前账号的 API Key 列表 (文本返回)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        client = self._refresh_client()
        if not client.is_configured():
            return event.plain_result(
                "❌ 尚未在插件设置中配置 NewAPI 站点地址或访问令牌。"
            )

        try:
            tokens, total = await client.list_tokens(p=0, size=15)
            if not tokens:
                return event.plain_result("🔑 暂无已创建的访问令牌。")

            lines = [f"🔑 【访问令牌列表（共 {total} 个）】"]
            for t in tokens:
                tid = t.get("id", "-")
                tname = t.get("name", "未命名")
                status = "启用" if t.get("status") == 1 else "禁用"
                unlimited = t.get("unlimited_quota", False)
                remain = (
                    "无限额度"
                    if unlimited
                    else client.format_quota(t.get("remain_quota", 0))
                )
                used = client.format_quota(t.get("used_quota", 0))
                lines.append(
                    f"• ID:{tid} | {tname} [{status}]\n  剩余: {remain} | 已用: {used}"
                )

            lines.append("\n💡 发送 /newapi 查看秘钥 <编号> 可查看完整密钥。")
            return event.plain_result("\n".join(lines))
        except Exception as e:
            return event.plain_result(f"❌ 获取令牌列表失败: {e}")

    async def add_token_cmd(
        self,
        event: AstrMessageEvent,
        name: str = "",
        quota_usd: float = 0.0,
    ):
        """创建新的 API Key (文本返回)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)
        if not name:
            return event.plain_result(
                "用法：/newapi 创建令牌 <名称> [额度美元；留空为无限额度]"
            )

        client = self._refresh_client()
        if not client.is_configured():
            return event.plain_result(
                "❌ 尚未在插件设置中配置 NewAPI 站点地址或访问令牌。"
            )

        unlimited = quota_usd <= 0
        quota_points = 0 if unlimited else client.usd_to_quota(quota_usd)

        try:
            token_obj = await client.add_token(
                name=name, remain_quota=quota_points, unlimited=unlimited
            )
            tid = token_obj.get("id", "-")
            key = token_obj.get("key", "")
            quota_desc = (
                "无限额度" if unlimited else f"${quota_usd:.2f} ({quota_points:,} 点)"
            )

            msg = (
                f"✅ 访问令牌创建成功！\n"
                f"• 令牌编号：{tid}\n"
                f"• 令牌名称：{name}\n"
                f"• 初始额度：{quota_desc}\n"
            )
            if key:
                msg += f"• 秘钥 Key: {key}\n"
            else:
                msg += f"• 请发送 /newapi 查看秘钥 {tid} 获取完整密钥。"
            return event.plain_result(msg)
        except Exception as e:
            return event.plain_result(f"❌ 创建访问令牌失败：{e}")

    async def del_token_cmd(self, event: AstrMessageEvent, token_id: int = 0):
        """删除指定 API Key (文本返回)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)
        if token_id <= 0:
            return event.plain_result("用法：/newapi 删除令牌 <令牌编号>")

        client = self._refresh_client()
        if not client.is_configured():
            return event.plain_result(
                "❌ 尚未在插件设置中配置 NewAPI 站点地址或访问令牌。"
            )

        try:
            await client.delete_token(token_id)
            return event.plain_result(f"🗑️ 成功删除令牌 ID: {token_id}！")
        except Exception as e:
            return event.plain_result(f"❌ 删除访问令牌失败：{e}")

    async def get_token_key_cmd(self, event: AstrMessageEvent, token_id: int = 0):
        """获取完整的 API Key 秘钥 (sk-...) (文本返回)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)
        if token_id <= 0:
            return event.plain_result("用法：/newapi 查看秘钥 <令牌编号>")

        client = self._refresh_client()
        if not client.is_configured():
            return event.plain_result(
                "❌ 尚未在插件设置中配置 NewAPI 站点地址或访问令牌。"
            )

        is_group = bool(event.get_group_id())
        try:
            key = await client.get_token_key(token_id)
            if not key:
                return event.plain_result(
                    f"❌ 未能获取到令牌 ID {token_id} 的完整秘钥。"
                )

            msg = f"🔑 令牌 [{token_id}] 秘钥:\n{key}"
            if is_group:
                msg += "\n⚠️ 注意：请妥善保管您的 API 秘钥，避免公开群聊中泄露。"
            return event.plain_result(msg)
        except Exception as e:
            return event.plain_result(f"❌ 获取令牌秘钥失败: {e}")

    # ==========================================
    # Backup & Restore Commands
    # ==========================================

    async def backup_data_cmd(self, event: AstrMessageEvent):
        """管理员打包备份所有用户绑定与配置数据并导出 (ZIP文件+文本返回)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        try:
            # 1. 写入最新的配置备份副本
            cfg_dict = dict(self.config) if self.config else {}
            cfg_backup_file = self.data_dir / "config_backup.json"
            with open(cfg_backup_file, "w", encoding="utf-8") as f:
                json.dump(cfg_dict, f, ensure_ascii=False, indent=2)

            # 2. 写入备份元数据清单
            now_dt = datetime.datetime.now()
            now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
            ts_str = now_dt.strftime("%Y%m%d_%H%M%S")

            manifest = {
                "plugin": "astr_newapi_plugin",
                "version": "1.2.0",
                "backup_time": int(now_dt.timestamp()),
                "backup_time_str": now_str,
                "files": [
                    "user_bindings.json",
                    "cache.json",
                    "config_backup.json",
                ],
                "restore_instructions": (
                    "解压本压缩包内所有文件至 AstrBot 插件数据目录 "
                    "(data/plugin_data/astr_newapi_plugin/) 覆盖相应 json 文件即可复原。"
                ),
            }
            manifest_file = self.data_dir / "backup_manifest.json"
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            # 3. 打包压缩
            zip_name = f"newapi_backup_{ts_str}.zip"
            zip_path = self.backups_dir / zip_name

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname in [
                    "user_bindings.json",
                    "cache.json",
                    "config_backup.json",
                    "backup_manifest.json",
                ]:
                    fpath = self.data_dir / fname
                    if fpath.exists():
                        zf.write(fpath, arcname=fname)

            file_size_kb = round(os.path.getsize(zip_path) / 1024, 2)
            bindings_count = len(self._load_bindings())

            msg = (
                f"📦 【NewAPI 插件数据备份成功】\n"
                f"• 备份文件名: {zip_name} ({file_size_kb} KB)\n"
                f"• 本地物理路径: {zip_path}\n"
                f"• 包含项目: 用户绑定关系 ({bindings_count} 人)、站点缓存、插件配置副本\n\n"
                f"💡 【数据迁移与复原方法】:\n"
                f"1. 将此压缩包直接复制或解压到目标 AstrBot 的插件数据目录：\n"
                f"   👉 data/plugin_data/astr_newapi_plugin/\n"
                f"2. 放入后重启 AstrBot 或在聊天框执行 [/newapi restore] 即可无缝复原！"
            )

            try:
                from astrbot.core.message.components import File, Plain

                return event.chain_result(
                    [Plain(msg), File(name=zip_name, file=str(zip_path))]
                )
            except Exception:
                return event.plain_result(msg)

        except Exception as e:
            logger.error(f"[NewAPI] 备份数据失败: {e}", exc_info=True)
            return event.plain_result(f"❌ 备份数据失败: {e}")

    async def restore_data_cmd(self, event: AstrMessageEvent, filename: str = ""):
        """管理员从备份压缩包解包复原数据 (文本返回)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        try:
            target_zip = None
            if filename.strip():
                candidate = self.backups_dir / filename.strip()
                if candidate.exists() and candidate.is_file():
                    target_zip = candidate

            if not target_zip:
                zip_files = sorted(
                    self.backups_dir.glob("*.zip"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if not zip_files:
                    return event.plain_result(
                        "❌ 未在备份目录中找到任何 .zip 备份文件。\n"
                        f"请将备份压缩包放置在: {self.backups_dir} 或运行 [/newapi backup] 创建新备份。"
                    )
                target_zip = zip_files[0]

            with zipfile.ZipFile(target_zip, "r") as zf:
                zf.extractall(self.data_dir)

            self._load_cache()
            bindings_count = len(self._load_bindings())

            return event.plain_result(
                f"✅ 【NewAPI 数据复原成功】\n"
                f"• 恢复源: {target_zip.name}\n"
                f"• 数据目标目录: {self.data_dir}\n"
                f"• 已恢复用户绑定: {bindings_count} 个用户\n"
                f"• 站点缓存与配置副本已同步载入生效！"
            )

        except Exception as e:
            logger.error(f"[NewAPI] 数据复原失败: {e}", exc_info=True)
            return event.plain_result(f"❌ 数据复原失败: {e}")

    # ==========================================
    # Regex Fallback for No-Space Commands
    # ==========================================

    async def _dispatch_target(
        self, event: AstrMessageEvent, target: str, raw_args: str = ""
    ):
        raw_args = (raw_args or "").strip()
        args_list = [a.strip() for a in raw_args.split() if a.strip()]

        if target == "menu":
            return await self.menu(event)
        elif target == "admin":
            return await self.admin_menu(event)
        elif target == "my":
            return await self.my_info(event)
        elif target == "bind":
            arg = args_list[0] if args_list else ""
            return await self.bind_user(event, arg)
        elif target == "unbind":
            return await self.unbind_user(event)
        elif target == "my_stat":
            arg = args_list[0] if args_list else "today"
            return await self.my_stat(event, arg)
        elif target == "stat":
            arg = args_list[0] if args_list else "today"
            return await self.site_stat(event, arg)
        elif target == "ranking":
            arg = args_list[0] if args_list else "day"
            return await self.user_ranking(event, arg)
        elif target == "model_ranking":
            arg = args_list[0] if args_list else "week"
            return await self.model_ranking(event, arg)
        elif target == "status":
            return await self.site_status(event)
        elif target == "redeem":
            arg = args_list[0] if args_list else ""
            return await self.redeem(event, arg)
        elif target == "user":
            arg = args_list[0] if args_list else ""
            return await self.get_user_info(event, arg)
        elif target == "create_user":
            u = args_list[0] if len(args_list) > 0 else ""
            p = args_list[1] if len(args_list) > 1 else ""
            d = args_list[2] if len(args_list) > 2 else ""
            return await self.create_user_cmd(event, u, p, d)
        elif target == "create_cdk":
            q = (
                float(args_list[0])
                if len(args_list) > 0 and args_list[0].replace(".", "", 1).isdigit()
                else 1.0
            )
            c = (
                int(args_list[1])
                if len(args_list) > 1 and args_list[1].isdigit()
                else 1
            )
            n = args_list[2] if len(args_list) > 2 else "AstrBot生成"
            return await self.create_cdk_cmd(event, q, c, n)
        elif target == "add_quota":
            u = args_list[0] if len(args_list) > 0 else ""
            q = (
                float(args_list[1])
                if len(args_list) > 1 and args_list[1].replace(".", "", 1).isdigit()
                else 0.0
            )
            return await self.add_quota_cmd(event, u, q)
        elif target == "sub_quota":
            u = args_list[0] if len(args_list) > 0 else ""
            q = (
                float(args_list[1])
                if len(args_list) > 1 and args_list[1].replace(".", "", 1).isdigit()
                else 0.0
            )
            return await self.sub_quota_cmd(event, u, q)
        elif target == "set_quota":
            u = args_list[0] if len(args_list) > 0 else ""
            q = (
                float(args_list[1])
                if len(args_list) > 1 and args_list[1].replace(".", "", 1).isdigit()
                else 0.0
            )
            return await self.set_quota_cmd(event, u, q)
        elif target == "enable_user":
            u = args_list[0] if args_list else ""
            return await self.enable_user_cmd(event, u)
        elif target == "disable_user":
            u = args_list[0] if args_list else ""
            return await self.disable_user_cmd(event, u)
        elif target == "channels":
            return await self.list_channels_cmd(event)
        elif target == "test_channel":
            cid = int(args_list[0]) if args_list and args_list[0].isdigit() else 0
            return await self.test_channel_cmd(event, cid)
        elif target == "token_list":
            return await self.list_tokens_cmd(event)
        elif target == "token_add":
            n = args_list[0] if len(args_list) > 0 else ""
            q = (
                float(args_list[1])
                if len(args_list) > 1 and args_list[1].replace(".", "", 1).isdigit()
                else 0.0
            )
            return await self.add_token_cmd(event, n, q)
        elif target == "token_del":
            tid = int(args_list[0]) if args_list and args_list[0].isdigit() else 0
            return await self.del_token_cmd(event, tid)
        elif target == "token_key":
            tid = int(args_list[0]) if args_list and args_list[0].isdigit() else 0
            return await self.get_token_key_cmd(event, tid)
        elif target == "backup":
            return await self.backup_data_cmd(event)
        elif target == "restore":
            arg = args_list[0] if args_list else ""
            return await self.restore_data_cmd(event, arg)
        else:
            return await self.menu(event)
