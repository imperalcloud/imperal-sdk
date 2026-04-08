"""Extension Loader — loads and caches extension modules from /opt/extensions/.

Supports mtime-based auto-reload: if the extension's main.py changes,
the next load() call re-imports it. Extensions are cached by app_id.
"""
import importlib
import importlib.util
import logging
import os
import sys

log = logging.getLogger(__name__)


class ExtensionLoader:
    """Loads extensions from the extensions directory. Caches by app_id with mtime check."""

    def __init__(self, extensions_dir: str = "/opt/extensions"):
        self._extensions_dir = extensions_dir
        self._cache: dict = {}  # app_id -> {module, ext, mtime}

    def load(self, app_id: str):
        """Load or reload an extension by app_id. Returns the extension object.

        The extension must have a main.py with an Extension/ChatExtension instance.
        Auto-reloads when main.py mtime changes.
        """
        ext_dir = os.path.join(self._extensions_dir, app_id)
        main_path = os.path.join(ext_dir, "main.py")

        if not os.path.exists(main_path):
            raise FileNotFoundError(f"Extension '{app_id}' not found at {main_path}")

        current_mtime = os.path.getmtime(main_path)
        cached = self._cache.get(app_id)

        if cached and cached["mtime"] == current_mtime:
            return cached["ext"]

        # Load or reload
        log.info(f"Loading extension '{app_id}' from {main_path}")

        # Add extension dir to sys.path for relative imports
        if ext_dir not in sys.path:
            sys.path.insert(0, ext_dir)

        module_name = f"ext_{app_id.replace('-', '_')}"

        try:
            if module_name in sys.modules:
                # Reload
                module = importlib.reload(sys.modules[module_name])
            else:
                spec = importlib.util.spec_from_file_location(module_name, main_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

            # Find the extension instance
            ext = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if hasattr(attr, 'tools') and hasattr(attr, 'signals') and isinstance(attr.tools, dict):
                    ext = attr
                    break

            if ext is None:
                raise ImportError(f"No Extension instance found in {main_path}")

            self._cache[app_id] = {
                "module": module,
                "ext": ext,
                "mtime": current_mtime,
            }

            log.info(f"Loaded extension '{app_id}': {len(ext.tools)} tools, {len(getattr(ext, 'signals', {}))} signals")
            return ext

        except Exception as e:
            log.error(f"Failed to load extension '{app_id}': {e}")
            raise ImportError(f"Extension '{app_id}' load failed: {e}")
