"""Apply ERNow's background to Streamlit's HTML shell before React loads.

Installed when the app first runs; subsequent requests (including reloads)
receive the styled shell. A server's very first cold-start request precedes
app execution and is still controlled by Streamlit Community Cloud.
"""

from pathlib import Path
from threading import Lock
import logging

from streamlit import file_util

_lock = Lock()
_installed = False
_PREPAINT = b"""
<style id="ernow-startup-theme">
html,body,#root,[data-testid="stApp"],[data-testid="stAppViewContainer"],
[data-testid="stHeader"]{background:#F8F4E6!important;color-scheme:light}
[data-testid="stAppSkeleton"],[data-testid="stSkeleton"]{display:none!important}
</style>
"""


def install_startup_theme():
    """Transform only the app shell, without changing Streamlit on disk."""
    global _installed
    with _lock:
        if _installed:
            return
        # Newer Streamlit releases replaced Tornado with another server.
        # An optional appearance fix must never prevent the app from starting.
        try:
            from streamlit.web.server.routes import StaticFileHandler
        except ImportError:
            logging.getLogger(__name__).warning(
                "Startup styling unavailable: install the pinned Streamlit version."
            )
            return
        index_path = str(Path(file_util.get_static_dir()) / "index.html")
        original = Path(index_path).read_bytes()
        if b"<head>" not in original:
            logging.getLogger(__name__).warning("Unrecognized Streamlit HTML shell")
            return
        themed = original.replace(b"<head>", b"<head>" + _PREPAINT, 1)
        original_content = StaticFileHandler.get_content
        original_size = StaticFileHandler.get_content_size

        def get_content(cls, abspath, start=None, end=None):
            if abspath == index_path:
                yield themed[start:end]
            else:
                yield from original_content(abspath, start, end)

        def get_content_size(self):
            if self.absolute_path == index_path:
                return len(themed)
            return original_size(self)

        StaticFileHandler.get_content = classmethod(get_content)
        StaticFileHandler.get_content_size = get_content_size
        # An initial request may have cached the unstyled shell's ETag.
        StaticFileHandler._static_hashes.pop(index_path, None)
        _installed = True
