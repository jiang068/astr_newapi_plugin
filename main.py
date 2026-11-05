import datetime
import json
import os
import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil
from astrbot.api import AstrBotConfig, logger
from astrbot.api.all import *
from astrbot.api.event import AstrMessageEvent, MessageChain, MessageEventResult
from astrbot.api.event.filter import (
    EventMessageType,
    PermissionType,
    command,
    event_message_type,
    permission_type,
    regex,
)
from astrbot.api.message_components import Image, Plain
from astrbot.core.star.filter.command import GreedyStr
from astrbot.api.star import Context, Star, register

try:
    from .newapi_client import NewAPIClient
    from .renderer import DarkCardRenderer
except ImportError:
    from newapi_client import NewAPIClient
    from renderer import DarkCardRenderer


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
        self._load_cache()

    def _init_client(self) -> NewAPIClient:
        site_url = self.config.get("site_url", "")
        api_token = self.config.get("api_token", "")
        timeout = int(self.config.get("request_timeout", 15) or 15)
        proxy = self.config.get("proxy", "") or None
        quota_per_unit = int(self.config.get("quota_per_unit", 500000) or 500000)
        return NewAPIClient(
            base_url=site_url,
            token=api_token,
            timeout=timeout,
            proxy=proxy,
            quota_per_unit=quota_per_unit,
        )

    def _refresh_client(self) -> NewAPIClient:
        self.client = self._init_client()
        return self.client

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
            return "❌ 管理功能已被管理员在配置中禁用 (enable_admin=false)。"
        admin_only = bool(self.config.get("admin_only", True))
        if admin_only and not self._is_admin(event):
            sender_id = event.get_sender_id()
            return (
                f"❌ 权限不足：该指令仅限机器人管理员使用。\n"
                f"• 当前用户 ID: {sender_id}\n"
                f"• 提示：管理员可在后台配置或通过 /op {sender_id} 赋予管理员权限。"
            )
        return None

    def _get_plain_menu_text(self, is_adm: bool) -> str:
        admin_status = "开启" if self._is_admin_enabled() else "关闭"
        lines = [
            "📋 【NewAPI 站点服务菜单】",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📊 个人与查询指令：",
            "• /newapi my (或 /newapi 余额) - 查询用量/余额/订阅",
            "• /newapi bind <ID/用户名> - 绑定个人账号",
            "• /newapi unbind - 解绑个人账号",
            "• /newapi my_stat [today/week/month/all] - 个人消费统计",
            "• /newapi stat [today/week/month/all] - 全站消耗与速率",
            "• /newapi ranking [day/week/month/total] - 用户消耗排行榜",
            "• /newapi model_ranking [today/week/month] - 模型调用排行",
            "• /newapi status - 站点与服务器 CPU/内存状态",
            "• /newapi redeem <兑换码> - 充值卡 CDK 兑换",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"👑 管理功能状态: {admin_status}",
        ]
        if self._is_admin_enabled() and is_adm:
            lines.append("💡 管理员可输入 [/newapi admin] 查看完整管理菜单")
        return "\n".join(lines)

    def _get_plain_admin_menu_text(self) -> str:
        return "\n".join([
            "👑 【NewAPI 站点管理菜单】",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "👤 用户与额度管理：",
            "• /newapi user <ID/用户名> - 查用户详细状态与余额",
            "• /newapi create_user <账号> <密码> [昵称] - 创建普通用户",
            "• /newapi add_quota <用户> <美元> - 充值增加额度",
            "• /newapi sub_quota <用户> <美元> - 扣减指定额度",
            "• /newapi set_quota <用户> <美元> - 直接设置额度",
            "• /newapi enable_user <用户> - 解禁/启用账号",
            "• /newapi disable_user <用户> - 封禁/禁用账号",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "🎟️ 兑换码与渠道：",
            "• /newapi create_cdk <面额> [数量] [名称] - 批量生成兑换码",
            "• /newapi channels - 查看上游渠道配置与延迟",
            "• /newapi test_channel [渠道ID] - 测试渠道网络速度",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "🔑 令牌与数据安全：",
            "• /newapi token_list - 查看 API Key 列表",
            "• /newapi token_add <名称> [额度] - 创建新的 API Key",
            "• /newapi token_del <令牌ID> - 删除指定的 API Key",
            "• /newapi token_key <令牌ID> - 查看完整秘钥 (sk-...)",
            "• /newapi backup - 打包导出用户绑定与配置为 ZIP",
            "• /newapi restore [文件名] - 一键复原配置数据",
        ])

    # --- Helper Utilities ---

    def _get_time_bounds(self, period: str) -> Tuple[int, int, str]:
        now = datetime.datetime.now()
        end_ts = int(now.timestamp())
        period = (period or "day").lower().strip()

        if period in ["day", "today", "天", "日", "今日"]:
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
        elif period in ["total", "all", "总", "全部", "历史"]:
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
                if user and "username" in user:
                    return user_id, user.get("username", str(user_id))
            except Exception:
                pass
            return user_id, str(user_id)

        try:
            users = await client.search_users(identifier)
            for u in users:
                if str(u.get("username", "")).lower() == identifier.lower():
                    return int(u.get("id")), u.get("username")
            if users:
                first = users[0]
                return int(first.get("id")), first.get("username")
        except Exception:
            pass

        return None, None

    def _collect_hardware_metrics(self) -> Dict[str, Any]:
        """Collect local hardware CPU, Memory, and Disk stats using psutil."""
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            drive_root = (
                os.path.splitdrive(os.getcwd())[0] + "\\" if os.name == "nt" else "/"
            )
            disk = psutil.disk_usage(drive_root)
            return {
                "cpu_percent": cpu,
                "mem_percent": mem.percent,
                "mem_used_gb": round(mem.used / (1024**3), 1),
                "mem_total_gb": round(mem.total / (1024**3), 1),
                "disk_percent": disk.percent,
                "disk_used_gb": round(disk.used / (1024**3), 1),
                "disk_total_gb": round(disk.total / (1024**3), 1),
            }
        except Exception as e:
            logger.warning(f"[NewAPI] 获取硬件监控指标异常: {e}")
            return {
                "cpu_percent": 0.0,
                "mem_percent": 0.0,
                "mem_used_gb": 0.0,
                "mem_total_gb": 0.0,
                "disk_percent": 0.0,
                "disk_used_gb": 0.0,
                "disk_total_gb": 0.0,
            }

    # ==========================================
    # Master Command & Standalone Registrations
    # ==========================================

    @command("newapi", alias={"newapi_help", "newapi_menu", "newapimenu", "newapi菜单", "newapi帮助"})
    async def newapi_main(self, event: AstrMessageEvent, input: GreedyStr = GreedyStr("")):
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
        """显示 NewAPI 普通查询功能菜单 (PIL暗色图或纯文本)"""
        admin_status = "开启" if self._is_admin_enabled() else "关闭"
        is_adm = self._is_admin(event)

        sections = [
            (
                "📊 个人与查询指令",
                [
                    ("/newapi my [或 /newapi 余额]", "查询绑定账户余额、用量与订阅"),
                    ("/newapi bind <用户ID/名>", "绑定个人的 NewAPI 账号"),
                    ("/newapi unbind [或 /newapi 解绑]", "解绑当前绑定的 NewAPI 账号"),
                    ("/newapi my_stat [天/周/月/总]", "查询个人指定时间内的消费统计"),
                    ("/newapi stat [天/周/月/总]", "查询 NewAPI 全站总消耗与速率"),
                    ("/newapi ranking [天/周/月/总]", "查看全站用户消耗排行榜 Top 10"),
                    ("/newapi model_ranking [周期]", "查看热门模型与厂商调用占比排行"),
                    (
                        "/newapi status [或 /newapi 状态]",
                        "查看站点配置与 CPU/内存/磁盘状态",
                    ),
                    ("/newapi redeem <兑换码>", "使用充值卡 CDK 兑换额度"),
                ],
            )
        ]

        footer = f"管理功能状态: {admin_status}"
        if self._is_admin_enabled() and is_adm:
            footer += "  |  管理员可输入 [/newapi admin] 查看管理菜单"

        try:
            img_path = DarkCardRenderer.render_menu(
                title="NewAPI 站点服务菜单",
                subtitle="输入指令即可触发对应功能（支持中文与无空格缩写）",
                sections=sections,
                footer_note=footer,
            )
            if img_path and os.path.exists(img_path):
                return event.image_result(img_path)
        except Exception as e:
            logger.warning(f"[NewAPI] 暗色卡片菜单渲染异常，降级为纯文本回复: {e}")

        return event.plain_result(self._get_plain_menu_text(is_adm))

    async def admin_menu(self, event: AstrMessageEvent):
        """显示 NewAPI 管理员专用菜单 (PIL暗色图或纯文本)"""
        err = self._check_admin_permission(event)
        if err:
            return event.plain_result(err)

        sections = [
            (
                "👤 用户与额度管理",
                [
                    ("/newapi user <ID/用户名>", "查询指定用户的完整状态与余额"),
                    ("/newapi create_user <账号> <密码>", "创建新的普通用户账号"),
                    ("/newapi add_quota <用户> <美元>", "给用户充值增加额度 (如 5.0)"),
                    ("/newapi sub_quota <用户> <美元>", "扣减指定用户的额度"),
                    ("/newapi set_quota <用户> <美元>", "重置覆盖指定用户的额度"),
                    ("/newapi enable_user <用户>", "解禁/启用指定用户账号"),
                    ("/newapi disable_user <用户>", "封禁/禁用指定用户账号"),
                ],
            ),
            (
                "🎟️ 兑换码与渠道测速",
                [
                    (
                        "/newapi create_cdk <面额> [数量]",
                        "批量并发生成指定面额的兑换码",
                    ),
                    ("/newapi channels", "查看所有上游渠道配置与延迟"),
                    ("/newapi test_channel [渠道ID]", "测试渠道网络连接与响应速度"),
                ],
            ),
            (
                "🔑 API Key 秘钥管理",
                [
                    ("/newapi token_list", "查看当前账户拥有的 API Key 列表"),
                    (
                        "/newapi token_add <名称> [额度]",
                        "创建新的 API Key (留空为无限)",
                    ),
                    ("/newapi token_del <令牌ID>", "删除指定的 API Key"),
                    ("/newapi token_key <令牌ID>", "提取完整的 API Key 秘钥 (sk-...)"),
                ],
            ),
            (
                "💾 数据备份与恢复",
                [
                    (
                        "/newapi backup [或 /newapi 备份]",
                        "打包导出用户绑定与配置为 ZIP 压缩包",
                    ),
                    (
                        "/newapi restore [或 /newapi 恢复]",
                        "从最新或指定备份压缩包一键复原",
                    ),
                ],
            ),
        ]

        try:
            img_path = DarkCardRenderer.render_menu(
                title="👑 NewAPI 站点管理菜单",
                subtitle="仅限管理员调用（支持中文指令与无空格格式）",
                sections=sections,
                footer_note="提示：兑换码生成与数据备份支持直接复制与文件下载。",
            )
            if img_path and os.path.exists(img_path):
                return event.image_result(img_path)
        except Exception as e:
            logger.warning(f"[NewAPI] 管理菜单暗色卡片渲染异常，降级为纯文本回复: {e}")

        return event.plain_result(self._get_plain_admin_menu_text())

    async def bind_user(self, event: AstrMessageEvent, user_identifier: str = ""):
        """绑定个人的 NewAPI 用户 ID 或用户名"""
        user_identifier = user_identifier.strip()
        if not user_identifier:
            return event.plain_result(
                "使用方式: /newapi bind <用户ID或用户名>\n例如: /newapi bind 10 或 /newapi bind alice"
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
            f"• 绑定账号: {uname} (ID: {user_id})\n"
            f"• 提示: 您现在可发送 [/newapi my] 或 [/newapi 余额] 查询您的用量、余额与订阅信息。"
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

        target_user = None
        subscriptions = []

        if binding:
            uid = int(binding.get("user_id"))
            try:
                target_user = await client.get_user(uid)
            except Exception:
                pass
            try:
                subscriptions = await client.get_user_subscriptions(uid)
            except Exception:
                pass
        else:
            # Not bound: if admin or token user
            if self._is_admin(event):
                try:
                    target_user = await client.get_self()
                    subscriptions = await client.get_self_subscriptions()
                except Exception:
                    pass
            if not target_user:
                return event.plain_result(
                    "💡 您当前尚未绑定 NewAPI 账号。\n"
                    "请发送 [/newapi bind <用户ID或用户名>] 绑定您的账号，即可随时查询余额、用量与订阅！"
                )

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
        if subscriptions:
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
            f"• 用户名: {name_display}\n"
            f"• 用户 ID: {uid}  |  状态: {status_str}\n"
            f"• 所属分组: {group}\n"
            f"• 剩余余额: {client.format_quota(quota)}\n"
            f"• 累计消耗: {client.format_quota(used_quota)}\n"
            f"• 请求次数: {req_count:,} 次\n"
            f"• 订阅情况: {sub_desc}"
        )
        if not binding:
            msg += "\n──────────────────\n💡 提示: 发送 [/newapi bind <ID>] 可绑定专属用户。"
        return event.plain_result(msg)

    async def my_stat(self, event: AstrMessageEvent, period: str = "today"):
        """查询个人在指定周期内的消费统计 [today/week/month/all] (文本返回)"""
        client = self._refresh_client()
        if not client.is_configured():
            return event.plain_result(
                "❌ 尚未在插件设置中配置 NewAPI 站点地址或访问令牌。"
            )

        start_ts, end_ts, label = self._get_time_bounds(period)
        try:
            stat = await client.get_self_stat(start_ts, end_ts)
        except Exception as e:
            return event.plain_result(f"❌ 查询个人消耗统计失败: {e}")

        consumed_quota = stat.get("quota", 0)
        rpm = stat.get("rpm", 0)
        tpm = stat.get("tpm", 0)

        msg = (
            f"📈 【个人消费统计 - {label}】\n"
            f"• 消费金额: {client.format_quota(consumed_quota)}\n"
            f"• 当前速率: {rpm:,} RPM (请求/分)\n"
            f"• Token 速率: {tpm:,} TPM (Token/分)"
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
            try:
                stat = await client.get_self_stat(start_ts, end_ts)
                return event.plain_result(
                    f"⚠️ 当前令牌无全站统计权限，已为您显示个人统计 ({label}):\n"
                    f"• 消耗金额: {client.format_quota(stat.get('quota', 0))}\n"
                    f"• 当前速率: {stat.get('rpm', 0):,} RPM | {stat.get('tpm', 0):,} TPM"
                )
            except Exception:
                return event.plain_result(f"❌ 查询全站统计失败: {e}")

        consumed_quota = stat.get("quota", 0)
        rpm = stat.get("rpm", 0)
        tpm = stat.get("tpm", 0)

        msg = (
            f"🌐 【NewAPI 全站消耗统计 - {label}】\n"
            f"• 全站消耗: {client.format_quota(consumed_quota)}\n"
            f"• 请求速率: {rpm:,} RPM (请求/分)\n"
            f"• Token 速率: {tpm:,} TPM (Token/分)"
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
            formatted_rows: List[Tuple[int, str, str, str]] = []

            if period_key in ["total", "all", "总", "全部", "历史"]:
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
                    used = u.get("used_quota", 0)
                    req_cnt = u.get("request_count", 0)
                    extra = f"{req_cnt:,}次请求" if req_cnt else ""
                    formatted_rows.append(
                        (i, name_display, client.format_quota(used), extra)
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
                    extra = f"{tok_val:,} tokens" if tok_val else ""
                    formatted_rows.append(
                        (i, uname, client.format_quota(quota_val), extra)
                    )

            try:
                img_path = DarkCardRenderer.render_user_rankings(label, formatted_rows)
                if img_path and os.path.exists(img_path):
                    return event.image_result(img_path)
            except Exception as e:
                logger.warning(f"[NewAPI] 用户排行暗色卡片渲染异常，降级为纯文本回复: {e}")

            lines = [f"📊 【用户消耗排行榜 Top 10 - {label}】"]
            for rk, uname, q_str, extra in formatted_rows:
                extra_str = f" ({extra})" if extra else ""
                lines.append(f"#{rk} {uname}: {q_str}{extra_str}")
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
            "week": "week",
            "month": "month",
            "year": "year",
        }
        query_period = p_map.get(period.lower().strip(), "week")

        try:
            rankings = await client.get_rankings(query_period)
        except Exception as e:
            return event.plain_result(f"❌ 获取模型排行失败: {e}")

        models = rankings.get("models", [])
        vendors = rankings.get("vendors", [])

        if not models and not vendors:
            return event.plain_result(f"📊 该周期 ({query_period}) 暂无模型消耗数据。")

        try:
            img_path = DarkCardRenderer.render_model_rankings(query_period, models, vendors)
            if img_path and os.path.exists(img_path):
                return event.image_result(img_path)
        except Exception as e:
            logger.warning(f"[NewAPI] 模型排行暗色卡片渲染异常，降级为纯文本回复: {e}")

        lines = [f"🤖 【热门模型消耗排行 - {query_period}】"]
        for idx, m in enumerate(models[:10], 1):
            name = m.get("model_name", "未知")
            tok = m.get("token_count", 0)
            lines.append(f"• #{idx} {name}: {tok:,} Tokens")
        return event.plain_result("\n".join(lines))

    async def site_status(self, event: AstrMessageEvent):
        """查询 NewAPI 站点配置与服务器 CPU/内存/磁盘运行状态 (PIL暗色图或纯文本)"""
        client = self._refresh_client()
        if not client.base_url:
            return event.plain_result("❌ 尚未在插件设置中配置 NewAPI 站点地址。")

        try:
            status = await client.get_status()
            if isinstance(status, dict) and "quota_per_unit" in status:
                self._save_cache("quota_per_unit", status["quota_per_unit"])
                self._save_cache("system_name", status.get("system_name", "NewAPI"))
        except Exception as e:
            return event.plain_result(f"❌ 获取站点状态失败: {e}")

        # Collect hardware metrics
        sys_metrics = self._collect_hardware_metrics()

        # If NewAPI performance stats are available, merge disk or memory info if remote
        perf = await client.get_performance_stats()
        if perf and isinstance(perf, dict):
            disk_info = perf.get("disk_space_info", {})
            if isinstance(disk_info, dict) and disk_info.get("total", 0) > 0:
                tot_gb = round(disk_info["total"] / (1024**3), 1)
                used_gb = round(disk_info.get("used", 0) / (1024**3), 1)
                sys_metrics["disk_used_gb"] = used_gb
                sys_metrics["disk_total_gb"] = tot_gb
                sys_metrics["disk_percent"] = round(
                    disk_info.get("used_percent", 0.0), 1
                )

        try:
            img_path = DarkCardRenderer.render_status(status, sys_metrics)
            if img_path and os.path.exists(img_path):
                return event.image_result(img_path)
        except Exception as e:
            logger.warning(f"[NewAPI] 状态暗色卡片渲染异常，降级为纯文本回复: {e}")

        s_name = status.get("system_name", "NewAPI 站点")
        ver = status.get("version", "未知")
        return event.plain_result(
            f"🖥️ 【{s_name} 系统状态】\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• 站点版本: {ver}\n"
            f"• CPU 占用: {sys_metrics.get('cpu_percent', 0.0)}%\n"
            f"• 内存占用: {sys_metrics.get('mem_percent', 0.0)}% ({sys_metrics.get('mem_used_gb', 0.0)}GB / {sys_metrics.get('mem_total_gb', 0.0)}GB)\n"
            f"• 磁盘占用: {sys_metrics.get('disk_percent', 0.0)}% ({sys_metrics.get('disk_used_gb', 0.0)}GB / {sys_metrics.get('disk_total_gb', 0.0)}GB)"
        )

    async def redeem(self, event: AstrMessageEvent, cdk_key: str = ""):
        """使用兑换码为当前账号充值 (文本返回)"""
        cdk_key = cdk_key.strip()
        if not cdk_key:
            return event.plain_result("使用方式: /newapi redeem <兑换码CDK>")

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
            return event.plain_result("使用方式: /newapi user <用户名或用户ID>")

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
                "使用方式: /newapi create_user <用户名> <密码> [昵称]"
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
                "使用方式: /newapi add_quota <用户ID/用户名> <增加美元金额>"
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
                "使用方式: /newapi sub_quota <用户ID/用户名> <扣减美元金额>"
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
                "使用方式: /newapi set_quota <用户ID/用户名> <重置美元金额>"
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
            return event.plain_result("使用方式: /newapi enable_user <用户ID/用户名>")

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
            return event.plain_result("使用方式: /newapi disable_user <用户ID/用户名>")

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
                img_path = DarkCardRenderer.render_channels(channels, total)
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
        client = self._refresh_client()
        if not client.is_configured():
            return event.plain_result(
                "❌ 尚未在插件设置中配置 NewAPI 站点地址或访问令牌。"
            )

        try:
            tokens, total = await client.list_tokens(p=0, size=15)
            if not tokens:
                return event.plain_result("🔑 暂无已创建的 API Key。")

            lines = [f"🔑 【API Key 列表 (共 {total} 个)】"]
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

            lines.append("\n💡 输入 [/newapi token_key <ID>] 可查看完整秘钥。")
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
        if not name:
            return event.plain_result(
                "使用方式: /newapi token_add <名称> [额度美元(留空为无限)]"
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
                f"✅ API Key 创建成功！\n"
                f"• 令牌 ID: {tid}\n"
                f"• 令牌名称: {name}\n"
                f"• 初始额度: {quota_desc}\n"
            )
            if key:
                msg += f"• 秘钥 Key: {key}\n"
            else:
                msg += f"• 提示: 请使用 [/newapi token_key {tid}] 获取完整秘钥。"
            return event.plain_result(msg)
        except Exception as e:
            return event.plain_result(f"❌ 创建 API Key 失败: {e}")

    async def del_token_cmd(self, event: AstrMessageEvent, token_id: int = 0):
        """删除指定 API Key (文本返回)"""
        if token_id <= 0:
            return event.plain_result("使用方式: /newapi token_del <令牌ID>")

        client = self._refresh_client()
        if not client.is_configured():
            return event.plain_result(
                "❌ 尚未在插件设置中配置 NewAPI 站点地址或访问令牌。"
            )

        try:
            await client.delete_token(token_id)
            return event.plain_result(f"🗑️ 成功删除令牌 ID: {token_id}！")
        except Exception as e:
            return event.plain_result(f"❌ 删除 API Key 失败: {e}")

    async def get_token_key_cmd(self, event: AstrMessageEvent, token_id: int = 0):
        """获取完整的 API Key 秘钥 (sk-...) (文本返回)"""
        if token_id <= 0:
            return event.plain_result("使用方式: /newapi token_key <令牌ID>")

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

    @regex(r"^[!/／#]?newapi(?:\s*(?P<cmd>[^\s]+))?(?:\s+(?P<args>.*))?$")
    async def no_space_dispatcher(self, event: AstrMessageEvent):
        """
        兼容无空格格式的命令调用（例如 /newapi菜单 /newapi余额 /newapi绑定 123 /newapi排行 等）
        """
        msg = event.get_message_str().strip()
        m = re.match(
            r"^[!/／#]?newapi(?:\s*(?P<cmd>[^\s]+))?(?:\s+(?P<args>.*))?$",
            msg,
            re.IGNORECASE,
        )
        if not m:
            return

        cmd = (m.group("cmd") or "").lower().strip()
        raw_args = (m.group("args") or "").strip()

        if not cmd:
            return await self.menu(event)

        target = CMD_MAPPING.get(cmd)
        if not target:
            for k, v in CMD_MAPPING.items():
                if cmd == k:
                    target = v
                    break

        if not target:
            return await self.menu(event)

        return await self._dispatch_target(event, target, raw_args)
