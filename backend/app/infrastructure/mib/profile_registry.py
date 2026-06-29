from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
from typing import Any


class MibProfileRegistry:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[4]
        self.mib_root = self.project_root / "mibs"
        self.profile_root = self.mib_root / "profiles"

    def list_profiles(self) -> list[dict[str, Any]]:
        return sorted(
            [self.public_profile(profile) for profile in self._load_profiles().values()],
            key=lambda item: item["id"],
        )

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        profiles = self._load_profiles()
        if profile_id not in profiles:
            raise ValueError(f"未知 MIB profile: {profile_id}")
        return deepcopy(profiles[profile_id])

    def get_provider_profiles(self, provider: str) -> list[dict[str, Any]]:
        return [
            self.public_profile(profile)
            for profile in self._load_profiles().values()
            if profile.get("provider") == provider
        ]

    def resolve_builtin_files(self, profile: dict[str, Any]) -> list[Path]:
        paths = []
        for relative_path in profile.get("builtin_files") or []:
            file_path = (self.mib_root / relative_path).resolve()
            if self.mib_root.resolve() not in file_path.parents:
                raise ValueError(f"MIB profile 引用了非法路径: {relative_path}")
            paths.append(file_path)
        return paths

    def _load_profiles(self) -> dict[str, dict[str, Any]]:
        profiles: dict[str, dict[str, Any]] = {}
        for file_path in sorted(self.profile_root.glob("*.json")):
            profile = json.loads(file_path.read_text(encoding="utf-8"))
            profile_id = str(profile.get("id") or "").strip()
            if not profile_id:
                raise ValueError(f"MIB profile 缺少 id: {file_path}")
            profiles[profile_id] = profile
        return profiles

    def public_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": profile.get("id"),
            "provider": profile.get("provider"),
            "display_name": profile.get("display_name") or profile.get("id"),
            "vendor": profile.get("vendor") or "unknown",
            "description": profile.get("description") or "",
            "protocols": profile.get("protocols") or [],
            "builtin_files": profile.get("builtin_files") or [],
            "oid_bindings": profile.get("oid_bindings") or {},
        }
