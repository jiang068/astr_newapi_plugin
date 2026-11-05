import os
import tempfile
import time
import uuid
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

# Cached fonts by font size
_FONT_CACHE: Dict[int, ImageFont.FreeTypeFont] = {}
_FONT_PATH: Optional[str] = None


_EMOJI_FONT_PATH = Path(__file__).resolve().parent / "NotoEmoji-Variable.ttf"
_EMOJI_FONT_CACHE: Dict[int, Optional[ImageFont.FreeTypeFont]] = {}
_EMOJI_FONT_WARNING_REPORTED = False

_EMOJI_CHARS = set(
    "🏆🤖🏢⚡🖥🌐🟢🔴📡"
)

def _get_emoji_font(size: int):
    global _EMOJI_FONT_WARNING_REPORTED
    if size not in _EMOJI_FONT_CACHE:
        try:
            if not _EMOJI_FONT_PATH.is_file():
                raise FileNotFoundError(f"Emoji font not found: {_EMOJI_FONT_PATH}")
            _EMOJI_FONT_CACHE[size] = ImageFont.truetype(str(_EMOJI_FONT_PATH), size)
        except (OSError, ValueError) as e:
            _EMOJI_FONT_CACHE[size] = None
            if not _EMOJI_FONT_WARNING_REPORTED:
                print(
                    "[NewAPI Renderer] Emoji font unavailable; "
                    f"using CJK fallback: {e}"
                )
                _EMOJI_FONT_WARNING_REPORTED = True
    return _EMOJI_FONT_CACHE[size]


def _draw_text(draw, xy, text, **kwargs):
    """
    Draw mixed Chinese/English/Emoji text.
    Chinese and English use the original font.
    Emoji use monochrome Noto Emoji.
    """
    text = str(text)
    base_font = kwargs.pop("font")

    x, y = xy

    base_ascent = base_font.getmetrics()[0]

    def is_emoji(ch: str) -> bool:
        return ch in _EMOJI_CHARS or unicodedata.category(ch) == "So"

    # Keep variation selectors, skin-tone modifiers, and ZWJ sequences with
    # their base emoji so the emoji font can draw a complete glyph cluster.
    clusters: List[str] = []
    for ch in text:
        if clusters and (
            ch in ("\ufe0e", "\ufe0f", "\u200d")
            or clusters[-1].endswith("\u200d")
            or unicodedata.combining(ch)
            or 0x1F3FB <= ord(ch) <= 0x1F3FF
        ):
            clusters[-1] += ch
        else:
            clusters.append(ch)

    run = ""

    def draw_run(value: str, font: ImageFont.FreeTypeFont) -> None:
        nonlocal x
        if value:
            draw.text((x, y), value, font=font, **kwargs)
            x += draw.textlength(value, font=font)

    for cluster in clusters:
        if is_emoji(cluster[0]):
            draw_run(run, base_font)
            run = ""
            emoji_font = _get_emoji_font(base_font.size)
            if emoji_font is not None:
                emoji_ascent = emoji_font.getmetrics()[0]
                draw.text(
                    (x, y + base_ascent - emoji_ascent),
                    cluster,
                    font=emoji_font,
                    **kwargs,
                )
                x += draw.textlength(cluster, font=emoji_font)
            else:
                draw_run(cluster, base_font)
        else:
            run += cluster

    draw_run(run, base_font)

def _find_system_font() -> Optional[str]:
    global _FONT_PATH

    if _FONT_PATH is not None:
        return _FONT_PATH

    candidates = [
        # Linux：优先使用 Noto CJK
        str(Path(__file__).resolve().parent / "NotoSansCJKsc-Regular.otf"),
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",

        # Windows
        "C:/Windows/Fonts/NotoSansCJKsc-Regular.otf",
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


def format_bytes(value: Optional[float]) -> str:
    """Format a byte count without rounding small values down to zero MB."""
    if value is None:
        return "暂不可获取"
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f} {unit}"
        amount /= 1024


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


def _share_label(value: Any) -> str:
    """Format NewAPI's share ratio (0.2534) as a human percentage."""
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return "占比暂不可获取"
    if not 0 <= ratio <= 1:
        return "占比暂不可获取"
    return f"{ratio:.2%}"


def _int_or_zero(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _fit_text(draw, value: str, font, max_width: int) -> str:
    """Trim a label by rendered width so it never collides with its neighbor."""
    value = str(value)
    if draw.textlength(value, font=font) <= max_width:
        return value
    while value and draw.textlength(value + "…", font=font) > max_width:
        value = value[:-1]
    return value + "…" if value else "…"


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
        width = 820
        padding = 24
        header_h = 75
        sec_header_h = 32
        item_h = 42

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
        _draw_text(draw,
            (padding + 36, top_y - 2),
            title,
            fill=cls.TEXT_PRIMARY,
            font=font_title,
        )
        _draw_text(draw,
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
            section_width = min(
                250, int(draw.textlength(sec_title, font=font_sec)) + 22
            )
            draw.rounded_rectangle(
                [(padding + 20, curr_y), (padding + 20 + section_width, curr_y + 24)],
                radius=6,
                fill=cls.BORDER_COLOR,
            )
            _draw_text(draw,
                (padding + 30, curr_y + 3),
                sec_title,
                fill=cls.ACCENT_BLUE,
                font=font_sec,
            )
            curr_y += 32

            for cmd, desc in items:
                # Put descriptions on their own line to keep long Chinese
                # commands from colliding with the explanatory text.
                _draw_text(draw,
                    (padding + 24, curr_y),
                    cmd,
                    fill=cls.ACCENT_GREEN,
                    font=font_cmd,
                )
                _draw_text(draw,
                    (padding + 42, curr_y + 18),
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
            _draw_text(draw,
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
        rows: List[Tuple[int, str, str, str, int]],
        site_name: str = "NewAPI",
    ) -> str:
        """Render a user consumption list with relative amount bars."""
        width = 760
        padding = 24
        header_h = 70
        row_h = 58
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
        _draw_text(draw,
            (padding + 36, top_y - 2),
            f"🏆 {site_name} 用户消费排行 · {period_label}",
            fill=cls.TEXT_PRIMARY,
            font=font_title,
        )
        _draw_text(draw,
            (padding + 36, top_y + 26),
            "按实际调用金额排序，条形长度表示相对金额",
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
        max_quota = max((max(0, row[4]) for row in rows), default=0)

        for rank, name, quota_str, extra, raw_quota in rows:
            bg_col = "#232338" if rank % 2 == 0 else cls.CARD_BG
            draw.rounded_rectangle(
                [
                    (padding + 16, curr_y - 2),
                    (width - padding - 16, curr_y + row_h - 4),
                ],
                radius=6,
                fill=bg_col,
            )

            # Rank badge
            rank_color = medals_color.get(rank, cls.TEXT_MUTED)
            _draw_text(draw,
                (padding + 28, curr_y + 6),
                f"第 {rank} 名",
                fill=rank_color,
                font=font_rank,
            )

            # Username
            value_width = int(draw.textlength(quota_str, font=font_val))
            name_x = padding + 98
            name_max_width = width - padding - 36 - value_width - name_x
            _draw_text(draw,
                (name_x, curr_y + 6),
                _fit_text(draw, name, font_name, name_max_width),
                fill=cls.TEXT_PRIMARY,
                font=font_name,
            )

            val_bbox = draw.textbbox((0, 0), quota_str, font=font_val)
            val_w = val_bbox[2] - val_bbox[0]
            _draw_text(draw,
                (width - padding - 30 - val_w, curr_y + 6),
                quota_str,
                fill=cls.ACCENT_GREEN,
                font=font_val,
            )

            if extra:
                _draw_text(draw,
                    (name_x, curr_y + 31),
                    extra,
                    fill=cls.TEXT_MUTED,
                    font=font_sub,
                )
            bar_x = padding + 290
            bar_width = width - padding - 30 - bar_x
            bar_percent = (max(0, raw_quota) / max_quota * 100) if max_quota else 0
            _draw_progress_bar(
                draw,
                bar_x,
                curr_y + 34,
                bar_width,
                8,
                bar_percent,
                fill_color=cls.ACCENT_BLUE,
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
        site_name: str = "NewAPI",
    ) -> str:
        """Render model bars and a vendor share pie chart."""
        width = 800
        padding = 24
        header_h = 75
        row_h = 48
        model_count = min(len(models), 10)
        vendor_entries = []
        if len(vendors) <= 5:
            vendor_entries = list(vendors)
        else:
            vendor_entries = list(vendors[:4])
            remainder = vendors[4:]
            vendor_entries.append(
                {
                    "vendor": "其他",
                    "total_tokens": sum(
                        _int_or_zero(row.get("total_tokens"))
                        for row in remainder
                        if isinstance(row, dict)
                    ),
                }
            )
        chart_h = 170 if vendor_entries else 0
        height = padding * 2 + header_h + model_count * row_h + chart_h + 35

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
        font_small = _get_font(12)

        top_y = padding + 18
        draw.rounded_rectangle(
            [(padding + 20, top_y), (padding + 26, top_y + 24)],
            radius=3,
            fill=cls.ACCENT_BLUE,
        )
        _draw_text(draw,
            (padding + 36, top_y - 2),
            f"🤖 {site_name} 模型调用排行 · {period_label}",
            fill=cls.TEXT_PRIMARY,
            font=font_title,
        )
        _draw_text(draw,
            (padding + 36, top_y + 26),
            "模型条形图按词元数比较；百分比保留两位小数",
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

        max_tokens = max(
            (
                _int_or_zero(m.get("total_tokens"))
                for m in models[:model_count]
                if isinstance(m, dict)
            ),
            default=0,
        )
        for i, m in enumerate(models[:model_count], 1):
            if not isinstance(m, dict):
                continue
            mname = str(m.get("model_name") or "未知模型")
            vendor = str(m.get("vendor") or "")
            tokens = _int_or_zero(m.get("total_tokens"))
            share = _share_label(m.get("share"))
            model_display = f"{mname}（{vendor}）" if vendor else mname
            _draw_text(draw,
                (padding + 24, curr_y + 2),
                f"第 {i} 名",
                fill=cls.ACCENT_YELLOW if i <= 3 else cls.TEXT_MUTED,
                font=font_item,
            )
            _draw_text(draw,
                (padding + 90, curr_y + 2),
                _fit_text(draw, model_display, font_item, 350),
                fill=cls.TEXT_PRIMARY,
                font=font_item,
            )
            stat_text = f"{tokens:,} 个词元  ·  {share}"
            stat_width = int(draw.textlength(stat_text, font=font_item))
            _draw_text(draw,
                (width - padding - 26 - stat_width, curr_y + 2),
                stat_text,
                fill=cls.ACCENT_GREEN,
                font=font_item,
            )
            bar_x = padding + 90
            bar_width = width - padding - 32 - bar_x
            _draw_progress_bar(
                draw,
                bar_x,
                curr_y + 25,
                bar_width,
                8,
                (tokens / max_tokens * 100) if max_tokens else 0,
                fill_color=cls.ACCENT_BLUE,
            )
            curr_y += row_h

        if vendor_entries:
            curr_y += 10
            draw.line(
                [(padding + 20, curr_y), (width - padding - 20, curr_y)],
                fill=cls.BORDER_COLOR,
                width=1,
            )
            curr_y += 12
            _draw_text(draw,
                (padding + 24, curr_y),
                "🏢 厂商词元占比",
                fill=cls.ACCENT_PEACH,
                font=font_sub,
            )
            curr_y += 28
            valid_vendors = []
            for v in vendor_entries:
                if not isinstance(v, dict):
                    continue
                tokens = _int_or_zero(v.get("total_tokens"))
                valid_vendors.append((str(v.get("vendor") or "其他"), tokens, v.get("share")))
            vendor_total = sum(item[1] for item in valid_vendors)

            pie_x, pie_y, pie_size = padding + 28, curr_y, 118
            colors = [
                cls.ACCENT_BLUE,
                cls.ACCENT_GREEN,
                cls.ACCENT_YELLOW,
                cls.ACCENT_PEACH,
                cls.ACCENT_RED,
            ]
            if vendor_total:
                start_angle = -90.0
                for i, (_, tokens, _) in enumerate(valid_vendors):
                    extent = tokens / vendor_total * 360
                    if extent > 0:
                        draw.pieslice(
                            (pie_x, pie_y, pie_x + pie_size, pie_y + pie_size),
                            start=start_angle,
                            end=start_angle + extent,
                            fill=colors[i % len(colors)],
                            outline=cls.CARD_BG,
                        )
                    start_angle += extent
            else:
                draw.ellipse(
                    (pie_x, pie_y, pie_x + pie_size, pie_y + pie_size),
                    fill=cls.BORDER_COLOR,
                )
                _draw_text(draw,
                    (pie_x + 23, pie_y + 50),
                    "暂无数据",
                    fill=cls.TEXT_SECONDARY,
                    font=font_small,
                )

            legend_x = pie_x + pie_size + 28
            legend_width = width - padding - 38 - legend_x
            for i, (vname, tokens, share_value) in enumerate(valid_vendors):
                legend_y = curr_y + i * 25
                draw.rounded_rectangle(
                    (legend_x, legend_y + 3, legend_x + 10, legend_y + 13),
                    radius=3,
                    fill=colors[i % len(colors)],
                )
                label = _fit_text(draw, vname, font_item, max(80, legend_width - 220))
                _draw_text(draw,
                    (legend_x + 18, legend_y),
                    label,
                    fill=cls.TEXT_SECONDARY,
                    font=font_item,
                )
                share = _share_label(share_value)
                if vname == "其他" and share == "占比暂不可获取" and vendor_total:
                    share = _share_label(tokens / vendor_total)
                value = f"{tokens:,} 个词元 · {share}"
                value_w = int(draw.textlength(value, font=font_small))
                _draw_text(draw,
                    (width - padding - 34 - value_w, legend_y + 1),
                    value,
                    fill=cls.TEXT_PRIMARY,
                    font=font_small,
                )

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
        _draw_text(draw,
            (padding + 36, top_y - 2),
            f"⚡ {sys_name} 站点与系统运行状态",
            fill=cls.TEXT_PRIMARY,
            font=font_title,
        )
        _draw_text(draw,
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
        _draw_text(draw,
            (padding + 24, curr_y),
            "🖥️ NewAPI 远程资源",
            fill=cls.ACCENT_BLUE,
            font=font_sec,
        )
        curr_y += 28

        # 1. CPU Usage (not returned by /api/performance/stats)
        cpu_pct = sys_metrics.get("cpu_percent")
        _draw_text(draw,
            (padding + 28, curr_y),
            "CPU 使用率:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        cpu_text = (
            f"{cpu_pct:.1f}%"
            if isinstance(cpu_pct, (int, float))
            else "暂不可获取"
        )
        _draw_text(draw,
            (padding + 120, curr_y),
            cpu_text,
            fill=cls.TEXT_PRIMARY,
            font=font_val,
        )
        if isinstance(cpu_pct, (int, float)):
            cpu_bar_color = cls.ACCENT_RED if cpu_pct > 85 else cls.ACCENT_BLUE
            _draw_progress_bar(
                draw, padding + 220, curr_y + 3, 400, 14, cpu_pct, fill_color=cpu_bar_color
            )
        curr_y += 32

        # 2. NewAPI process memory (alloc/sys), not whole-server RAM.
        mem_alloc = sys_metrics.get("mem_alloc_bytes")
        mem_sys = sys_metrics.get("mem_sys_bytes")
        _draw_text(draw,
            (padding + 28, curr_y),
            "进程内存:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        alloc_text = format_bytes(mem_alloc)
        sys_text = format_bytes(mem_sys)
        mem_text = f"已分配 {alloc_text} / 进程持有 {sys_text}"
        _draw_text(draw,
            (padding + 120, curr_y),
            mem_text,
            fill=cls.TEXT_PRIMARY,
            font=font_val,
        )
        curr_y += 32

        # 3. Disk Usage
        disk_pct = sys_metrics.get("disk_percent")
        disk_used_gb = sys_metrics.get("disk_used_gb")
        disk_total_gb = sys_metrics.get("disk_total_gb")
        _draw_text(draw,
            (padding + 28, curr_y),
            "缓存所在盘:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        _draw_text(draw,
            (padding + 120, curr_y),
            (
                f"{disk_pct:.1f}%" if isinstance(disk_pct, (int, float)) else "暂不可获取"
            )
            + f" ({disk_used_gb if disk_used_gb is not None else '暂不可获取'}G/"
            + f"{disk_total_gb if disk_total_gb is not None else '暂不可获取'}G)",
            fill=cls.TEXT_PRIMARY,
            font=font_val,
        )
        if isinstance(disk_pct, (int, float)):
            disk_bar_color = cls.ACCENT_RED if disk_pct > 85 else cls.ACCENT_PEACH
            _draw_progress_bar(
                draw,
                padding + 400,
                curr_y + 3,
                220,
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
        _draw_text(draw,
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

        _draw_text(draw,
            (padding + 28, curr_y),
            "• 额度换算比例:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        _draw_text(draw,
            (padding + 150, curr_y),
            f"1 USD = {quota_unit:,} 点",
            fill=cls.ACCENT_GREEN,
            font=font_val,
        )
        _draw_text(draw,
            (padding + 380, curr_y),
            "• 站点启动时间:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        _draw_text(draw,
            (padding + 490, curr_y), uptime_str, fill=cls.TEXT_PRIMARY, font=font_val
        )
        curr_y += 28

        email_v = "🟢开启" if site_info.get("email_verification") else "🔴关闭"
        github_o = "🟢开启" if site_info.get("github_oauth") else "🔴关闭"
        wechat_l = "🟢开启" if site_info.get("wechat_login") else "🔴关闭"
        turnstile = "🟢开启" if site_info.get("turnstile_check") else "🔴关闭"

        _draw_text(draw,
            (padding + 28, curr_y),
            "• 邮箱验证注册:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        _draw_text(draw,
            (padding + 150, curr_y), email_v, fill=cls.TEXT_PRIMARY, font=font_val
        )
        _draw_text(draw,
            (padding + 380, curr_y),
            "• 微信快捷登录:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        _draw_text(draw,
            (padding + 490, curr_y), wechat_l, fill=cls.TEXT_PRIMARY, font=font_val
        )
        curr_y += 28

        _draw_text(draw,
            (padding + 28, curr_y),
            "• GitHub 授权:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        _draw_text(draw,
            (padding + 150, curr_y), github_o, fill=cls.TEXT_PRIMARY, font=font_val
        )
        _draw_text(draw,
            (padding + 380, curr_y),
            "• 人机安全验证:",
            fill=cls.TEXT_SECONDARY,
            font=font_label,
        )
        _draw_text(draw,
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
        site_name: str = "NewAPI",
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
        _draw_text(draw,
            (padding + 36, top_y - 2),
            f"📡 {site_name} 上游渠道配置（前 {len(channels)} / 共 {total} 个）",
            fill=cls.TEXT_PRIMARY,
            font=font_title,
        )
        _draw_text(draw,
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
            _draw_text(draw,
                (padding + 26, curr_y + 6),
                f"[{cid}] {cname[:22]}",
                fill=cls.TEXT_PRIMARY,
                font=font_item,
            )

            # Status
            _draw_text(draw,
                (padding + 280, curr_y + 6),
                status,
                fill=cls.TEXT_SECONDARY,
                font=font_item,
            )

            # Weight & Priority
            _draw_text(draw,
                (padding + 380, curr_y + 6),
                f"权重:{weight} 优先:{priority}",
                fill=cls.TEXT_MUTED,
                font=font_item,
            )

            # Latency (right aligned)
            lat_display = f"延迟: {resp_str}"
            bbox = draw.textbbox((0, 0), lat_display, font=font_item)
            w = bbox[2] - bbox[0]
            _draw_text(draw,
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
