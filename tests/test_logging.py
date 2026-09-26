import logging

from mingati.utils.logging import setup_logging


def test_last_error_is_tracked() -> None:
    tracker = setup_logging("INFO")

    logging.getLogger("mingati.test").warning("not an error")
    assert tracker.last_error is None

    logging.getLogger("mingati.test").error("provider %s down", "steam")
    assert tracker.last_error is not None
    assert tracker.last_error.message == "provider steam down"
    assert tracker.last_error.logger == "mingati.test"


def test_discord_library_never_logs_debug_payloads() -> None:
    setup_logging("DEBUG")

    assert logging.getLogger("discord").level == logging.INFO
