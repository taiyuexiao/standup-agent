import os
import sys
from pathlib import Path

from highagent.collectors.kimi_code import KimiCodeCollector


def default_root(platform: str = None, environ=None, home: Path = None) -> Path:
    """Kimi 桌面端（Kimi Work 模式）内嵌 kimi-code 内核的数据根；仅 macOS 路径有实据。"""
    platform = platform or sys.platform
    environ = os.environ if environ is None else environ
    home = home or Path.home()
    suffix = Path("daimon-share/daimon/runtime/kimi-code/home")
    if platform == "win32":
        base = environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(base) / "kimi-desktop" / suffix
    if platform == "darwin":
        return home / "Library" / "Application Support" / "kimi-desktop" / suffix
    return home / ".config" / "kimi-desktop" / suffix


class KimiWorkCollector(KimiCodeCollector):
    """Kimi 桌面端 Kimi Work 模式：内核同 Kimi Code（wire.jsonl 同构），差异：
    - 会话目录 conv-*/ctitle-*；ctitle-* 是标题生成旁路，过滤
    - 排除 origin.kind == system_trigger 的触发噪声
    - 剔除 user 内容里的 <attachment>...</attachment> 块
    daimon/agents/.../conversations.sqlite 与 memory/transcripts/ 是 wire.jsonl 的
    派生/索引数据，不作为采集源（会重复）。
    """

    name = "kimi_work"
    noise_origins = KimiCodeCollector.noise_origins | {"system_trigger"}
    skip_session_prefixes = ("ctitle-",)
    strip_attachments = True
    strip_meta_prefix = True  # 桌面端 user 消息正文也带 <meta .../> 前缀

    def __init__(self, root: Path = None):
        super().__init__(root or default_root())
