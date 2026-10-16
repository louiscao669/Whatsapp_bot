"""Runtime defaults and redacted logging shared by the bot and platform."""

import logging
import os
import sys
from importlib.util import module_from_spec, spec_from_file_location

from .log_redaction import install_log_redaction
from .repo_paths import REPO_ROOT


def load_config_defaults():
    config_path = REPO_ROOT / "config.py"
    if not config_path.exists():
        return

    spec = spec_from_file_location("eten_runtime_config", config_path)
    if not spec or not spec.loader:
        return

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    for key, value in getattr(module, "CONFIG_DEFAULTS", {}).items():
        os.environ.setdefault(key, str(value))


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
    # Client IPs, participant ids and deep-link tokens must not reach the
    # journal: it is outside every data path the protocol describes, so
    # nothing exports it, prunes it or destroys it with the rest of the
    # identifiers. Attached to the root handlers, which is what the WSGI
    # access log propagates to.
    install_log_redaction()
