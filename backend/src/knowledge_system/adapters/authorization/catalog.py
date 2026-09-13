"""Trusted in-process resource metadata used by the local authorization adapter."""

from collections.abc import Iterable, Sequence

from knowledge_system.application.ports.authorization import ResourceMetadata
from knowledge_system.domain.contracts import AuthorizedObjectId


class InMemoryResourceMetadataStore:
    """Deterministic local catalog; production uses a PostgreSQL-backed adapter."""

    def __init__(self, resources: Iterable[ResourceMetadata]) -> None:
        materialized = tuple(resources)
        catalog = {resource.object_id: resource for resource in materialized}
        if len(catalog) == 0:
            raise ValueError("resource catalog must not be empty")
        if len(catalog) != len(materialized):
            raise ValueError("resource object IDs must be unique")
        self._resources = catalog

    def get(self, object_id: AuthorizedObjectId) -> ResourceMetadata | None:
        return self._resources.get(object_id)

    def all_for_tenant(self, tenant_id: str) -> Sequence[ResourceMetadata]:
        return tuple(
            resource
            for resource in self._resources.values()
            if resource.tenant_id == tenant_id
        )
