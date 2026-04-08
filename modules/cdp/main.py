"""CDP — Chrome DevTools Protocol interaction stubs.

Provides a per-worker driver registry so that the orchestrator can
associate a browser driver with each worker_id. Business logic
implementation delegates to the registered driver for page interaction.
"""

import threading

_registry_lock = threading.Lock()
_driver_registry: dict[str, object] = {}


def register_driver(worker_id: str, driver: object) -> None:
    """Register a browser driver instance for the given worker."""
    with _registry_lock:
        _driver_registry[worker_id] = driver


def unregister_driver(worker_id: str) -> None:
    """Remove the driver entry for the given worker."""
    with _registry_lock:
        _driver_registry.pop(worker_id, None)


def detect_page_state() -> str:
    """Detect the current page state via the registered driver.

    Note: The spec interface does not include a worker_id parameter for CDP
    functions; this implementation retrieves the sole registered driver.
    In a single-driver-per-process deployment this is correct behaviour.

    Returns:
        The detected page state as a string.

    Raises:
        RuntimeError: if no driver has been registered via register_driver().
    """
    with _registry_lock:
        driver = next(iter(_driver_registry.values()), None)
    if driver is None:
        raise RuntimeError("No driver registered; call register_driver() first.")
    return driver.detect_page_state()


def fill_card(card_info) -> None:
    """Fill card form fields via the registered driver.

    Args:
        card_info: CardInfo instance with card number, expiry, and CVV.

    Raises:
        RuntimeError: if no driver has been registered via register_driver().
    """
    with _registry_lock:
        driver = next(iter(_driver_registry.values()), None)
    if driver is None:
        raise RuntimeError("No driver registered; call register_driver() first.")
    driver.fill_card(card_info)


def fill_billing(billing_profile) -> None:
    """Fill billing form fields via the registered driver.

    Args:
        billing_profile: BillingProfile instance with address and contact info.

    Raises:
        RuntimeError: if no driver has been registered via register_driver().
    """
    with _registry_lock:
        driver = next(iter(_driver_registry.values()), None)
    if driver is None:
        raise RuntimeError("No driver registered; call register_driver() first.")
    driver.fill_billing(billing_profile)


def clear_card_fields() -> None:
    """Clear card form fields via the registered driver.

    Raises:
        RuntimeError: if no driver has been registered via register_driver().
    """
    with _registry_lock:
        driver = next(iter(_driver_registry.values()), None)
    if driver is None:
        raise RuntimeError("No driver registered; call register_driver() first.")
    driver.clear_card_fields()
