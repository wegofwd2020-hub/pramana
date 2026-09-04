"""Test that EntitlementRequiredError maps correctly to HTTP 403."""

from pramana.api.errors import _status_for
from pramana.exceptions import EntitlementRequiredError


def test_entitlement_required_is_a_domain_error():
    """EntitlementRequiredError stores context via base class."""
    err = EntitlementRequiredError("no entitlement", context={"course_id": "x"})
    assert err.context == {"course_id": "x"}


def test_entitlement_required_maps_to_403():
    """EntitlementRequiredError via subclass inheritance maps to HTTP 403."""
    assert _status_for(EntitlementRequiredError("x")) == 403
