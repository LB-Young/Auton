from datetime import datetime

from auton.genome.contracts import Asset, Catalog
from auton.genome.repository import error


class MemoryPolicy:
    def visible(
        self,
        catalog: Catalog,
        asset: Asset,
        now: datetime,
        seen: frozenset[str] = frozenset(),
        memo: dict[str, bool] | None = None,
    ) -> bool:
        memo = {} if memo is None else memo
        if len(seen) > 32:
            return False
        if asset.id in memo:
            return memo[asset.id]
        current = catalog.records.get(asset.id)
        if current is None or current.status != "active" or asset.id in seen:
            return False
        if (asset.expires_at and asset.expires_at <= now) or (
            current.asset.expires_at and current.asset.expires_at <= now
        ):
            return False
        for parent in set(asset.parents) | set(current.asset.parents):
            record = catalog.records.get(parent)
            if record is None or not self.visible(
                catalog, record.asset, now, seen | {asset.id}, memo
            ):
                return False
        memo[asset.id] = True
        return True

    def publishable(self, catalog: Catalog, asset: Asset, now: datetime) -> None:
        if asset.expires_at and asset.expires_at <= now:
            raise error("asset_expired", "Expired memory cannot be promoted")
        if asset.id in asset.parents:
            raise error("asset_cycle", "An asset cannot derive from itself")
        current = catalog.records.get(asset.id)
        if current and current.status == "revoked":
            raise error("asset_revoked", "Revoked identities cannot be resurrected")
        for parent in asset.parents:
            record = catalog.records.get(parent)
            if record is None or not self.visible(catalog, record.asset, now):
                raise error("parent_unavailable", "An asset source is missing, revoked or expired")
            # A previously published descendant cannot become a source of its ancestor.
            pending = [parent]
            seen = set()
            while pending:
                identity = pending.pop()
                if identity == asset.id:
                    raise error("asset_cycle", "Asset dependency cycle")
                if identity not in seen:
                    seen.add(identity)
                    if len(seen) > 32:
                        raise error(
                            "asset_lineage_limit",
                            "Asset source graph exceeds the current review limit",
                        )
                    pending.extend(catalog.records[identity].asset.parents)
        for identity, record in catalog.records.items():
            if (
                identity != asset.id
                and record.status == "active"
                and self.visible(catalog, record.asset, now)
                and record.asset.kind == asset.kind
                and record.asset.name.casefold() == asset.name.casefold()
            ):
                raise error("asset_name_conflict", "An active asset already uses this name")


class MemoryPolicyFactory:
    def create(self) -> MemoryPolicy:
        return MemoryPolicy()
