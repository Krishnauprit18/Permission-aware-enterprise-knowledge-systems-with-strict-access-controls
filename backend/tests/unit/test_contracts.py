"""Unit tests for framework-independent security contracts."""

import pytest

from knowledge_system.domain.contracts import AuthorizationDecision


@pytest.mark.unit
@pytest.mark.security
def test_external_sharing_requires_view_authorization() -> None:
    with pytest.raises(ValueError, match="view authorization"):
        AuthorizationDecision(allowed=False, can_share_externally=True)


@pytest.mark.unit
@pytest.mark.security
def test_view_authorization_does_not_imply_external_sharing() -> None:
    decision = AuthorizationDecision(allowed=True)
    assert decision.can_share_externally is False
