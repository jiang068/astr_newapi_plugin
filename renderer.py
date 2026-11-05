import os
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

# Cached fonts by font size
_FONT_CACHE: Dict[int, ImageFont.FreeTypeFont] = {}
_FONT_PATH: Optional[str] = None


def _find_system_font() -> Optional[str]:
    global _FONT_PATH

    if _FONT_PATH is not None:
        return _FONT_PATH

    candidates = [
        # Linux：优先使用 Noto CJK
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",

        # Windows
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyh.ttf",
        "C:/Windows/Fonts/simsun.ttc",
    ]

    for path in candidates:
        if os.path.isfile(path):
            _FONT_PATH = path
            print(f"[NewAPI Renderer] Selected font: {path}")
            return path

    _FONT_PATH = ""
    print("[NewAPI Renderer] ERROR: No CJK font found")
    return None


def _get_font(size: int = 15):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]

    font_path = _find_system_font()

    if font_path:
        try:
            # Noto CJK TTC 字体集合：
            # index=2 对应简体中文 SC
            if "NotoSansCJK-Regular.ttc" in font_path:
                font = ImageFont.truetype(
                    font_path,
                    size,
                    index=2
                )
            else:
                font = ImageFont.truetype(font_path, size)

            print(
                f"[NewAPI Renderer] Loaded: "
                f"{font.getname()}, size={size}"
            )

            _FONT_CACHE[size] = font
            return font

        except Exception as e:
            print(f"[NewAPI Renderer] Font error: {e}")

    raise RuntimeError(
        "No usable Chinese font available for NewAPI renderer"
    )


def _get_temp_path() -> str:
    # Cleanup old temp files occasionally
    temp_dir = tempfile.gettempdir()
    return os.path.join(temp_dir, f"newapi_{uuid.uuid4().hex[:10]}.png")


def _draw_progress_bar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    height: int,
    percent: float,
    fill_color: str = "#89b4fa",
    bg_color: str = "#313244",
) -> None:
    percent = max(0.0, min(100.0, percent))
    draw.rounded_rectangle([(x, y), (x + width, y + height)], radius=4, fill=bg_color)
    bar_w = int(width * (percent / 100.0))
    if bar_w > 4:
        draw.rounded_rectangle(
            [(x, y), (x + bar_w, y + height)], radius=4, fill=fill_color
        )


class DarkCardRenderer:
    """Lightweight, compact dark theme image renderer using Pillow."""

    BG_COLOR = "#181825"
    CARD_BG = "#1e1e2e"
    BORDER_COLOR = "#313244"
    TEXT_PRIMARY = "#cdd6f4"
    TEXT_SECONDARY = "#a6adc8"
    TEXT_MUTED = "#6c7086"
    ACCENT_BLUE = "#89b4fa"
    ACCENT_GREEN = "#a6e3a1"
    ACCENT_YELLOW = "#f9e2af"
    ACCENT_PEACH = "#fab387"
    ACCENT_RED = "#f38ba8"

    @classmethod
    def render_menu(
        cls,
        title: str,
        subtitle: str,
        sections: List[Tuple[str, List[Tuple[str, str]]]],
        footer_note: Optional[str] = None,
    ) -> str:
        """Render a compact, elegant command menu."""
        width = 720
        padding = 24
        header_h = 75
        sec_header_h = 32
        item_h = 28

        total_items = sum(len(items) for _, items in sections)
        content_h = (
            header_h
            + len(sections) * (sec_header_h + 12)
            + total_items * item_h
            + (40 if footer_note else 20)
            + 30
        )
        height = max(350, content_h)

        img = Image.new("RGB", (width, height), color=cls.BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Draw outer container card
        draw.rounded_rectangle(
            [(padding, padding), (width - padding, height - padding)],
            radius=12,
            fill=cls.CARD_BG,
            outline=cls.BORDER_COLOR,
            width=1,
        )

        font_title = _get_font(22)
        font_sub = _get_font(13)
        font_sec = _get_font(15)
        font_cmd = _get_font(13)
        font_desc = _get_font(13)
        font_footer = _get_font(12)

        # Header
        top_y = padding + 18
        # Accent icon pill
        draw.rounded_rectangle(
            [(padding + 20, top_y), (padding + 26, top_y + 26)],
            radius=3,
            fill=cls.ACCENT_BLUE,
        )
        draw.text(
            (padding + 36, top_y - 2),
            title,
            fill=cls.TEXT_PRIMARY,
            font=font_title,
        )
        draw.text(
            (padding + 36, top_y + 28),
            subtitle,
            fill=cls.TEXT_SECONDARY,
            font=font_sub,
        )

        curr_y = top_y + 60
        draw.line(
            [(padding + 20, curr_y), (width - padding - 20, curr_y)],
            fill=cls.BORDER_COLOR,
            width=1,
        )
        curr_y += 14

        # Sections
        for sec_title, items in sections:
            # Section header badge
            draw.rounded_rectangle(
                [(padding + 20, curr_y), (padding + 20 + 130, curr_y + 24)],
                radius=6,
                fill=cls.BORDER_COLOR,
            )
            draw.text(
                (padding + 30, curr_y + 3),
                sec_title,
                fill=cls.ACCENT_BLUE,
                font=font_sec,
            )
            curr_y += 32

            for cmd, desc in items:
                # Command
                draw.text(
                    (padding + 24, curr_y),
                    cmd,
                    fill=cls.ACCENT_GREEN,
                    font=font_cmd,
                )
                # Description
                draw.text(
                    (padding + 230, curr_y),
                    desc,
                    fill=cls.TEXT_SECONDARY,
                    font=font_desc,
                )
                curr_y += item_h

            curr_y += 8

        # Footer
        if footer_note:
            draw.line(
                [(padding + 20, curr_y), (width - padding - 20, curr_y)],
                fill=cls.BORDER_COLOR,
                width=1,
            )
            curr_y += 10
            draw.text(
                (padding + 24, curr_y),
                footer_note,
                fill=cls.TEXT_MUTED,
                font=font_footer,
            )

        file_path = _get_temp_path()
        img.save(file_path, format="PNG")
        img.close()
        return file_path

    @classmethod
    def render_user_rankings(
        cls,
        period_label: str,
        rows: List[
            Tuple[int, str, str, str]
        ],  # (rank, name, quota_formatted, extra_info)
    ) -> str:
        """Render Top 10 user rankings card."""
        width = 720
        padding = 24
        header_h = 70
        row_h = 38
        height = padding * 2 + header_h + len(rows) * row_h + 30

        img = Image.new("RGB", (width, height), color=cls.BG_COLOR)
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle(
            [(padding, padding), (width - padding, height - padding)],
            radius=12,
            fill=cls.CARD_BG,
            outline=cls.BORDER_COLOR,
            width=1,
        )

        font_title = _get_font(20)
        font_sub = _get_font(13)
        font_rank = _get_font(15)
        font_name = _get_font(14)
        font_val = _get_font(13)

        top_y = padding + 18
        draw.rounded_rectangle(
            [(padding + 20, top_y), (padding + 26, top_y + 24)],
            radius=3,
            fill=cls.ACCENT_YELLOW,
        )
        draw.text(
            (padding + 36, top_y - 2),
            f"🏆 全站用户消耗排行 - {period_label} Top {len(rows)}",
            fill=cls.TEXT_PRIMARY,
            font=font_title,
        )
        draw.text(
            (padding + 36, top_y + 26),
            "按实际模型调用消耗金额统计",
            fill=cls.TEXT_SECONDARY,
            font=font_sub,
        )

        curr_y = top_y + 55
        draw.line(
            [(padding + 20, curr_y), (width - padding - 20, curr_y)],
            fill=cls.BORDER_COLOR,
            width=1,
        )
        curr_y += 12

        medals_color = {1: cls.ACCENT_YELLOW, 2: "#bac2de", 3: cls.ACCENT_PEACH}

        for rank, name, quota_str, extra in rows:
            bg_col = "#232338" if rank % 2 == 0 else cls.CARD_BG
            draw.rounded_rectangle(
                [
                    (padding + 16, curr_y - 2),
                    (width - padding - 16, curr_y + row_h - 6),
                ],
                radius=6,
                fill=bg_col,
            )

            # Rank badge
            rank_color = medals_color.get(rank, cls.TEXT_MUTED)
            rank_badge_text = f"#{rank}"
            draw.text(
                (padding + 28, curr_y + 6),
                rank_badge_text,
                fill=rank_color,
                font=font_rank,
            )

            # Username
            draw.text(
                (padding + 85, curr_y + 7),
                name[:24],
                fill=cls.TEXT_PRIMARY,
                font=font_name,
            )

            # Extra info if any
            if extra:
                draw.text(
                    (padding + 270, curr_y + 8),
                    extra,
                    fill=cls.TEXT_MUTED,
                    font=font_sub,
                )

            # Quota formatted (right aligned)
            val_bbox = draw.textbbox((0, 0), quota_str, font=font_val)
            val_w = val_bbox[2] - val_bbox[0]
            draw.text(
                (width - padding - 30 - val_w, curr_y + 7),
                quota_str,
                fill=cls.ACCENT_GREEN,
                font=font_val,
            )

            curr_y += row_h

        file_path = _get_temp_path()
        img.save(file_path, format="PNG")
        img.close()
        return file_path

    @classmethod
    def render_model_rankings(
        cls,
        period_label: str,
        models: List[Dict[str, Any]],
        vendors: List[Dict[str, Any]],
    ) -> str:
        """Render model token consumption rankings card."""
        width = 720
        padding = 24
        header_h = 70
        row_h = 32
        model_count = min(len(models), 10)
        vendor_count = min(len(vendors), 5)
        height = (
            padding * 2
            + header_h
            + model_count * row_h
            + (vendor_count * 28 + 40 if vendor_count else 0)
            + 35
        )

        img = Image.new("RGB", (width, height), color=cls.BG_COLOR)
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle(
            [(padding, padding), (width - padding, height - padding)],
            radius=12,
            fill=cls.CARD_BG,
            outline=cls.BORDER_COLOR,
            width=1,
        )

        font_title = _get_font(20)
        font_sub = _get_font(13)
        font_item = _get_font(13)

        top_y = padding + 18
        draw.rounded_rectangle(
            [(padding + 20, top_y), (padding + 26, top_y + 24)],
            radius=3,
            fill=cls.ACCENT_BLUE,
        )
        draw.text(
            (padding + 36, top_y - 2),
            f"🤖 模型消耗排行 - {period_label} Top {model_count}",
            fill=cls.TEXT_PRIMARY,
            font=font_title,
        )
        draw.text(
            (padding + 36, top_y + 26),
            "各模型与厂商 Token 调用量及占比",
            fill=cls.TEXT_SECONDARY,
            font=font_sub,
        )

        curr_y = top_y + 55
        draw.line(
            [(padding + 20, curr_y), (width - padding - 20, curr_y)],
            fill=cls.BORDER_COLOR,
            width=1,
        )
        curr_y += 12

        for i, m in enumerate(models[:model_count], 1):
            mname = m.get("model_name", "未知")
            vendor = m.get("vendor", "")
            tokens = m.get("total_tokens", 0)
            share = m.get("share", 0.0)

            draw.text(
                (padding + 24, curr_y),
                f"{i}.",
                fill=cls.ACCENT_YELLOW if i <= 3 else cls.TEXT_MUTED,
                font=font_item,
            )
            model_display = f"{mname} [{vendor}]" if vendor else mname
            draw.text(
                (padding + 52, curr_y),
                model_display[:30],
                fill=cls.TEXT_PRIMARY,
                font=font_item,
            )

            tok_str = f"{tokens:,} Tokens ({share:.1f}%)"
            bbox = draw.textbbox((0, 0), tok_str, font=font_item)
            w = bbox[2] - bbox[0]
            draw.text(
                (width - padding - 26 - w, curr_y),
                tok_str,
                fill=cls.ACCENT_GREEN,
                font=font_item,
            )

            curr_y += row_h

        if vendor_count:
            curr_y += 10
            draw.line(
                [(padding + 20, curr_y), (width - padding - 20, curr_y)],
                fill=cls.BORDER_COLOR,
                width=1,
            )
            curr_y += 12
            draw.text(
                (padding + 24, curr_y),
                "🏢 厂商调用份额占比:",
                fill=cls.ACCENT_PEACH,
                font=font_sub,
            )
            curr_y += 24

            for v in vendors[:vendor_count]:
                vname = v.get("vendor", "其他")
                tokens = v.get("total_tokens", 0)
                share = v.get("share", 0.0)
                draw.text(
                    (padding + 30, curr_y),
                    f"• {vname}",
                    fill=cls.TEXT_SECONDARY,
                    font=font_item,
                )
                v_str = f"{tokens:,} Tokens ({share:.1f}%)"
                bbox = draw.textbbox((0, 0), v_str, font=font_item)
                w = bbox[2] - bbox[0]
                draw.text(
                    (width - padding - 26 - w, curr_y),
                    v_str,
                    fill=cls.TEXT_PRIMARY,
                    font=font_item,
                )
                curr_y += 24

        file_path = _get_temp_path()
        img.save(file_path, format="PNG")
        img.close()
        return file_path

    @classmethod
    def render_status(
        cls,
        site_info: Dict[str, Any],
        sys_metrics: Dict[str, Any],
    ) -> str:
        """Render system status card with CPU, memory, and disk usage bars."""
        width = 720
        padding = 24
        height = 490

        img = Image.new("RGB", (width, height), color=cls.BG_COLOR)
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle(
            [(padding, padding), (width - padding, height - padding)],
            radius=12,
            fill=cls.CARD_BG,
            outline=cls.BORDER_COLOR,
            width=1,
        )

        font_title = _get_font(20)
        font_sub = _get_font(13)
        font_sec = _get_font(14)
        font_label = _get_font(13)
        font_val = _get_font(13)

        top_y = padding + 18
        draw.rounded_rectangle(
            [(padding + 20, top_y), (padding + 26, top_y + 24)],
            radius=3,
            fill=cls.ACCENT_GREEN,
        )
        sys_name = site_info.get("system_name", "NewAPI")
        version = site_info.get("version", "未知")
        draw.text(
            (padding + 36, top_y - 2),
            f"⚡ {sys_name} 站点与系统运行状态",
            fill=cls.TEXT_PRIMARY,
            font=font_title,
        )
        draw.text(
            (padding + 36, top_y + 26),
            f"版本: {version}  |  状态正常运行中",
            fill=cls.TEXT_SECONDARY,
            font=font_sub,
        )

        curr_y = top_y + 55
        draw.line(
            [(padding + 20, curr_y), (width - padding - 20, curr_y)],
            fill=cls.BORDER_COLOR,
            width=1,
        )
        curr_y += 14

        # Section: Hardware Metrics (CPU, Memory, Disk)
        draw.text(
            (padding + 24, curr_y),
            "🖥️ 硬件资源负载",
            fill=cls.ACCENT_BLUE,
            font=font_sec,
        )
        curr_y += 28

        # 1. CPU Usage
        cpu_pct = float(sys_metrics.get("cpu_percent", 0.0))
        draw.text(
            (padding + 28, curr_y),
            "CPU 使用率:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        draw.text(
            (padding + 120, curr_y),
            f"{cpu_pct:.1f}%",
            fill=cls.TEXT_PRIMARY,
            font=font_val,
        )
        cpu_bar_color = cls.ACCENT_RED if cpu_pct > 85 else cls.ACCENT_BLUE
        _draw_progress_bar(
            draw, padding + 220, curr_y + 3, 400, 14, cpu_pct, fill_color=cpu_bar_color
        )
        curr_y += 32

        # 2. Memory Usage
        mem_pct = float(sys_metrics.get("mem_percent", 0.0))
        mem_used_gb = float(sys_metrics.get("mem_used_gb", 0.0))
        mem_total_gb = float(sys_metrics.get("mem_total_gb", 0.0))
        draw.text(
            (padding + 28, curr_y),
            "内存使用率:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        draw.text(
            (padding + 120, curr_y),
            f"{mem_pct:.1f}% ({mem_used_gb:.1f}G/{mem_total_gb:.1f}G)",
            fill=cls.TEXT_PRIMARY,
            font=font_val,
        )
        mem_bar_color = cls.ACCENT_RED if mem_pct > 85 else cls.ACCENT_GREEN
        _draw_progress_bar(
            draw, padding + 280, curr_y + 3, 340, 14, mem_pct, fill_color=mem_bar_color
        )
        curr_y += 32

        # 3. Disk Usage
        disk_pct = float(sys_metrics.get("disk_percent", 0.0))
        disk_used_gb = float(sys_metrics.get("disk_used_gb", 0.0))
        disk_total_gb = float(sys_metrics.get("disk_total_gb", 0.0))
        draw.text(
            (padding + 28, curr_y),
            "硬盘使用率:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        draw.text(
            (padding + 120, curr_y),
            f"{disk_pct:.1f}% ({disk_used_gb:.1f}G/{disk_total_gb:.1f}G)",
            fill=cls.TEXT_PRIMARY,
            font=font_val,
        )
        disk_bar_color = cls.ACCENT_RED if disk_pct > 85 else cls.ACCENT_PEACH
        _draw_progress_bar(
            draw,
            padding + 280,
            curr_y + 3,
            340,
            14,
            disk_pct,
            fill_color=disk_bar_color,
        )
        curr_y += 36

        draw.line(
            [(padding + 20, curr_y), (width - padding - 20, curr_y)],
            fill=cls.BORDER_COLOR,
            width=1,
        )
        curr_y += 14

        # Section: Site & Environment
        draw.text(
            (padding + 24, curr_y),
            "🌐 站点服务参数",
            fill=cls.ACCENT_BLUE,
            font=font_sec,
        )
        curr_y += 28

        quota_unit = site_info.get("quota_per_unit", 500000)
        start_time = site_info.get("start_time", 0)
        uptime_str = (
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time))
            if start_time
            else "未知"
        )

        draw.text(
            (padding + 28, curr_y),
            "• 额度换算比例:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        draw.text(
            (padding + 150, curr_y),
            f"1 USD = {quota_unit:,} 点",
            fill=cls.ACCENT_GREEN,
            font=font_val,
        )
        draw.text(
            (padding + 380, curr_y),
            "• 站点启动时间:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        draw.text(
            (padding + 490, curr_y), uptime_str, fill=cls.TEXT_PRIMARY, font=font_val
        )
        curr_y += 28

        email_v = "🟢开启" if site_info.get("email_verification") else "🔴关闭"
        github_o = "🟢开启" if site_info.get("github_oauth") else "🔴关闭"
        wechat_l = "🟢开启" if site_info.get("wechat_login") else "🔴关闭"
        turnstile = "🟢开启" if site_info.get("turnstile_check") else "🔴关闭"

        draw.text(
            (padding + 28, curr_y),
            "• 邮箱验证注册:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        draw.text(
            (padding + 150, curr_y), email_v, fill=cls.TEXT_PRIMARY, font=font_val
        )
        draw.text(
            (padding + 380, curr_y),
            "• 微信快捷登录:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        draw.text(
            (padding + 490, curr_y), wechat_l, fill=cls.TEXT_PRIMARY, font=font_val
        )
        curr_y += 28

        draw.text(
            (padding + 28, curr_y),
            "• GitHub 授权:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        draw.text(
            (padding + 150, curr_y), github_o, fill=cls.TEXT_PRIMARY, font=font_val
        )
        draw.text(
            (padding + 380, curr_y),
            "• 人机安全验证:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        draw.text(
            (padding + 490, curr_y), turnstile, fill=cls.TEXT_PRIMARY, font=font_val
        )

        file_path = _get_temp_path()
        img.save(file_path, format="PNG")
        img.close()
        return file_path

    @classmethod
    def render_channels(
        cls,
        channels: List[Dict[str, Any]],
        total: int,
    ) -> str:
        """Render upstream channels list card."""
        width = 720
        padding = 24
        header_h = 70
        row_h = 36
        height = padding * 2 + header_h + len(channels) * row_h + 30

        img = Image.new("RGB", (width, height), color=cls.BG_COLOR)
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle(
            [(padding, padding), (width - padding, height - padding)],
            radius=12,
            fill=cls.CARD_BG,
            outline=cls.BORDER_COLOR,
            width=1,
        )

        font_title = _get_font(20)
        font_sub = _get_font(13)
        font_item = _get_font(13)

        top_y = padding + 18
        draw.rounded_rectangle(
            [(padding + 20, top_y), (padding + 26, top_y + 24)],
            radius=3,
            fill=cls.ACCENT_GREEN,
        )
        draw.text(
            (padding + 36, top_y - 2),
            f"📡 上游渠道配置 (前 {len(channels)} / 共 {total} 个)",
            fill=cls.TEXT_PRIMARY,
            font=font_title,
        )
        draw.text(
            (padding + 36, top_y + 26),
            "显示渠道 ID、名称、状态与平均响应延迟",
            fill=cls.TEXT_SECONDARY,
            font=font_sub,
        )

        curr_y = top_y + 55
        draw.line(
            [(padding + 20, curr_y), (width - padding - 20, curr_y)],
            fill=cls.BORDER_COLOR,
            width=1,
        )
        curr_y += 12

        for i, c in enumerate(channels, 1):
            cid = c.get("id", "-")
            cname = c.get("name", "未命名")
            status = "🟢 启用" if c.get("status") == 1 else "🔴 停用"
            resp_time = c.get("response_time", 0)
            resp_str = f"{resp_time}ms" if resp_time > 0 else "-"
            weight = c.get("weight", 0)
            priority = c.get("priority", 0)

            bg_col = "#232338" if i % 2 == 0 else cls.CARD_BG
            draw.rounded_rectangle(
                [
                    (padding + 16, curr_y - 2),
                    (width - padding - 16, curr_y + row_h - 6),
                ],
                radius=6,
                fill=bg_col,
            )

            # Channel ID & name
            draw.text(
                (padding + 26, curr_y + 6),
                f"[{cid}] {cname[:22]}",
                fill=cls.TEXT_PRIMARY,
                font=font_item,
            )

            # Status
            draw.text(
                (padding + 280, curr_y + 6),
                status,
                fill=cls.TEXT_SECONDARY,
                font=font_item,
            )

            # Weight & Priority
            draw.text(
                (padding + 380, curr_y + 6),
                f"权重:{weight} 优先:{priority}",
                fill=cls.TEXT_MUTED,
                font=font_item,
            )

            # Latency (right aligned)
            lat_display = f"延迟: {resp_str}"
            bbox = draw.textbbox((0, 0), lat_display, font=font_item)
            w = bbox[2] - bbox[0]
            draw.text(
                (width - padding - 26 - w, curr_y + 6),
                lat_display,
                fill=cls.ACCENT_GREEN
                if resp_time and resp_time < 1000
                else cls.ACCENT_YELLOW,
                font=font_item,
            )

            curr_y += row_h

        file_path = _get_temp_path()
        img.save(file_path, format="PNG")
        img.close()
        return file_path
