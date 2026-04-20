"""Worker task factory for ``integration.runtime.start()``.

Handles BitBrowser lifecycle and runs purchase cycles from ``task_source``.
``ENABLE_PRODUCTION_TASK_FN`` is enforced by the caller, not this module.
"""
import importlib
import logging
import threading
import uuid
from typing import Any, Callable, Optional

from modules.cdp import main as cdp
from modules.cdp.driver import _get_current_ip_best_effort, maxmind_lookup_zip
from modules.cdp.fingerprint import BitBrowserSession, get_bitbrowser_client

_log = logging.getLogger(__name__)  # pylint: disable=invalid-name

# P1-5: Task-level abort registry.
_abort_lock: threading.Lock = threading.Lock()
_abort_flags: "dict[str, threading.Event]" = {}


def abort_task(worker_id: str) -> None:
    """Request an abort for the task of *worker_id*. Idempotent and thread-safe."""
    try:
        with _abort_lock:
            flag = _abort_flags.setdefault(worker_id, threading.Event())
        flag.set()
    except Exception as exc:  # pylint: disable=broad-except
        _log.warning("worker=%s abort_task=error: %s", worker_id, exc)


def is_task_aborted(worker_id: str) -> bool:
    """Return ``True`` if an abort has been requested for *worker_id*."""
    with _abort_lock:
        flag = _abort_flags.get(worker_id)
    return flag is not None and flag.is_set()


def _register_abort(worker_id: str) -> None:
    with _abort_lock:
        if worker_id not in _abort_flags:
            _abort_flags[worker_id] = threading.Event()


def _clear_abort(worker_id: str) -> None:
    with _abort_lock:
        _abort_flags.pop(worker_id, None)


def make_task_fn(task_source: Optional[Callable[[str], Any]] = None) -> Callable[[str], None]:
    """Return a task_fn for ``runtime.start()``.

    Args:
        task_source: Optional ``(worker_id) -> WorkerTask | None`` callable.
            When ``None``, only the browser lifecycle is exercised.
    Returns:
        Callable ``(worker_id: str) -> None``.
    """

    def task_fn(worker_id: str) -> None:
        """Execute one browser lifecycle cycle for *worker_id*."""
        _register_abort(worker_id)
        try:
            if is_task_aborted(worker_id):
                return

            bb_client = get_bitbrowser_client()
            if bb_client is None:
                raise RuntimeError(
                    f"BitBrowser client unavailable for worker {worker_id}. "
                    "Set BITBROWSER_API_KEY and ensure the endpoint is reachable."
                )

            with BitBrowserSession(bb_client) as (profile_id, webdriver_url):
                selenium_driver = _build_remote_driver(webdriver_url)
                try:
                    # Wrap in GivexDriver and register with CDP registry (F-03)
                    from modules.cdp.driver import GivexDriver  # noqa: PLC0415
                    givex_driver = GivexDriver(selenium_driver)
                    cdp.register_driver(worker_id, givex_driver)

                    # Register browser process PID when available (F-03)
                    pid = _get_browser_pid(selenium_driver)
                    if pid is not None:
                        cdp._register_pid(worker_id, pid)  # pylint: disable=protected-access

                    # Register BitBrowser profile id (F-04)
                    cdp.register_browser_profile(worker_id, profile_id)

                    # Guard: verify driver exposes add_cdp_listener (U-06)
                    from integration.runtime import probe_cdp_listener_support  # noqa: PLC0415
                    probe_cdp_listener_support(selenium_driver)

                    # Resolve proxy IP → zip code via MaxMind (F-07).
                    # The proxy IP is extracted from the PROXY_SERVER env var or
                    # the driver's proxy attribute — no external HTTP calls.
                    zip_code: Optional[str] = None
                    try:
                        detected_ip = _get_current_ip_best_effort()
                        if detected_ip:
                            zip_code = maxmind_lookup_zip(detected_ip)
                    except Exception as exc:  # pylint: disable=broad-except
                        _log.debug(
                            "worker=%s zip derivation error: %s", worker_id, exc
                        )

                    if zip_code:
                        _log.info(
                            "worker=%s zip_selection=zip_match zip=%s",
                            worker_id,
                            zip_code,
                        )
                    else:
                        _log.info(
                            "worker=%s zip_selection=round_robin "
                            "(MaxMind zip unavailable)",
                            worker_id,
                        )

                    # Run purchase cycle when a task source is wired (F-02/F-07).
                    # A CycleContext is created once per cycle so that billing is
                    # locked for the entire cycle (P5: billing fixed across card retries).
                    if task_source is not None:
                        task = task_source(worker_id)
                        if task is not None:
                            from modules.common.types import CycleContext  # noqa: PLC0415
                            ctx = CycleContext(
                                cycle_id=uuid.uuid4().hex,
                                worker_id=worker_id,
                                zip_code=zip_code,
                            )
                            orchestrator_module = importlib.import_module(
                                "integration.orchestrator"
                            )
                            run_cycle = orchestrator_module.run_cycle
                            run_cycle(
                                task,
                                zip_code=zip_code,
                                worker_id=worker_id,
                                ctx=ctx,
                                abort_check=lambda: is_task_aborted(worker_id),
                            )
                    else:
                        _log.debug(
                            "worker=%s profile=%s driver registered; "
                            "no task_source wired — purchase cycle skipped.",
                            worker_id,
                            profile_id,
                        )
                finally:
                    # Always unregister the driver to prevent registry leaks (GAP-CDP-01)
                    cdp.unregister_driver(worker_id)
        finally:
            _clear_abort(worker_id)

    return task_fn


def _build_remote_driver(webdriver_url: str):
    """Build a Selenium Remote WebDriver against *webdriver_url*.

    Raises:
        RuntimeError: if selenium is not installed.
    """
    try:
        remote_module = importlib.import_module("selenium.webdriver")
        capabilities_module = importlib.import_module(
            "selenium.webdriver.common.desired_capabilities"
        )
        Remote = remote_module.Remote
        DesiredCapabilities = capabilities_module.DesiredCapabilities
        capabilities = dict(DesiredCapabilities.CHROME)
        return Remote(
            command_executor=webdriver_url,
            desired_capabilities=capabilities,
        )
    except ImportError as exc:
        raise RuntimeError(
            "selenium is not installed; cannot build Remote driver. "
            "Install selenium-wire==5.1.0 for production use."
        ) from exc


def _get_browser_pid(driver) -> Optional[int]:
    """Try to read the browser process PID from *driver*.

    Returns ``None`` if the PID cannot be determined (e.g. plain Remote
    driver, non-seleniumwire driver, or driver not yet connected).
    """
    try:
        pid = getattr(driver, "browser_pid", None)
        if pid is not None:
            return int(pid)
        service = getattr(driver, "service", None)
        if service is not None:
            proc = getattr(service, "process", None)
            if proc is not None:
                return int(proc.pid)
    except (AttributeError, TypeError, ValueError):  # pylint: disable=broad-except
        _log.debug("_get_browser_pid: could not read PID", exc_info=True)
    return None
