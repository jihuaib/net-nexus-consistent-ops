from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from .mib_registry import MIB_FILE_EXTENSIONS, MibRegistry
from .profile_registry import MibProfileRegistry


class MibService:
    def __init__(self, profile_registry: MibProfileRegistry | None = None) -> None:
        self.profile_registry = profile_registry or MibProfileRegistry()
        self.workspace_root = self.profile_registry.mib_root / "workspace"
        self._registries: dict[str, MibRegistry] = {}
        self._summaries: dict[str, dict[str, Any]] = {}

    def list_profiles(self) -> dict[str, Any]:
        return {"items": self.profile_registry.list_profiles()}

    def compile_profile(
        self,
        profile_id: str,
        uploaded_files: list[dict[str, str]] | None = None,
        include_tree: bool = True,
    ) -> dict[str, Any]:
        profile = self.profile_registry.get_profile(profile_id)
        self._write_uploaded_files(profile_id, uploaded_files or [])
        file_paths = self._profile_files(profile)
        registry = MibRegistry()
        summary = registry.compile_files(file_paths)
        result = self._decorate_summary(profile, summary)
        if include_tree:
            result["tree"] = registry.build_tree()
        self._registries[profile_id] = registry
        self._summaries[profile_id] = result
        return result

    def get_status(self, profile_id: str) -> dict[str, Any]:
        if profile_id not in self._summaries:
            return self.compile_profile(profile_id, include_tree=False)
        return self._summaries[profile_id]

    def get_tree(self, profile_id: str, parent_oid: str = "", full: bool = False) -> dict[str, Any]:
        registry = self._get_or_compile_registry(profile_id)
        profile = self.profile_registry.get_profile(profile_id)
        return {
            "profile": self.profile_registry.public_profile(profile),
            "parentOid": parent_oid or "",
            "items": registry.build_tree() if full else registry.get_tree_children(parent_oid),
        }

    def translate_oid(self, profile_id: str, oid: str) -> dict[str, Any]:
        registry = self._get_or_compile_registry(profile_id)
        profile = self.profile_registry.get_profile(profile_id)
        return {
            "profile": self.profile_registry.public_profile(profile),
            "translation": registry.translate_oid(oid),
        }

    def _get_or_compile_registry(self, profile_id: str) -> MibRegistry:
        if profile_id not in self._registries:
            self.compile_profile(profile_id, include_tree=False)
        return self._registries[profile_id]

    def _decorate_summary(self, profile: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
        public_profile = self.profile_registry.public_profile(profile)
        return {
            "profile": public_profile,
            "compiledAt": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "oidBindings": public_profile["oid_bindings"],
            "uploadedFiles": self._uploaded_file_names(public_profile["id"]),
        }

    def _profile_files(self, profile: dict[str, Any]) -> list[Path]:
        return [
            *self.profile_registry.resolve_builtin_files(profile),
            *sorted(self._upload_dir(profile["id"]).glob("*")),
        ]

    def _write_uploaded_files(self, profile_id: str, uploaded_files: list[dict[str, str]]) -> None:
        if not uploaded_files:
            return
        upload_dir = self._upload_dir(profile_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        for item in uploaded_files:
            raw_name = item.get("file_name") or item.get("fileName") or ""
            content = item.get("content") or ""
            file_name = safe_mib_file_name(raw_name)
            (upload_dir / file_name).write_text(content, encoding="utf-8")

    def _uploaded_file_names(self, profile_id: str) -> list[str]:
        upload_dir = self._upload_dir(profile_id)
        if not upload_dir.exists():
            return []
        return sorted(path.name for path in upload_dir.iterdir() if path.is_file())

    def _upload_dir(self, profile_id: str) -> Path:
        return self.workspace_root / safe_profile_id(profile_id) / "uploads"


def safe_profile_id(profile_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(profile_id or "").strip()) or "default"


def safe_mib_file_name(file_name: str) -> str:
    name = Path(file_name).name.strip()
    if not name:
        raise ValueError("上传 MIB 文件名不能为空")
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    suffix = Path(name).suffix.lower()
    if suffix not in MIB_FILE_EXTENSIONS:
        raise ValueError(f"不支持的 MIB 文件扩展名: {suffix}")
    return name
