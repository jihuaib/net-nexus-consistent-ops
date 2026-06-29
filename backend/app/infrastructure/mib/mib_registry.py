from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import warnings

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL.*")

from pysmi.parser.smi import SmiV2Parser


MIB_FILE_EXTENSIONS = {".mib", ".txt", ".my", ""}


@dataclass(frozen=True)
class MibObject:
    object_name: str
    module_name: str
    oid: str
    macro: str
    syntax: str = ""
    max_access: str = ""
    status: str = ""
    description: str = ""
    file_path: str = ""
    value_map: dict[str, int] = field(default_factory=dict)
    base: bool = False


@dataclass(frozen=True)
class MibDeclaration:
    object_name: str
    module_name: str
    macro: str
    oid_expression: Any
    file_path: str
    syntax: str = ""
    max_access: str = ""
    status: str = ""
    description: str = ""
    value_map: dict[str, int] = field(default_factory=dict)


class MibRegistry:
    """MIB compiler facade backed by pysmi.

    pysmi handles SMIv2 parsing. NetNexus keeps only the runtime index needed
    by the UI and SNMP providers: OID tree, nearest-object translation and
    provider binding validation.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.compiled_files: list[str] = []
        self.loaded_files: list[str] = []
        self.failed_files: list[dict[str, Any]] = []
        self.modules: list[str] = []
        self.imports_by_module: dict[str, list[str]] = {}
        self.unresolved_objects: list[dict[str, Any]] = []
        self.oid_index: dict[str, MibObject] = {}
        self.symbol_index: dict[str, str] = {}
        self.module_symbol_index: dict[str, dict[str, str]] = {}
        self.child_index: dict[str, list[str]] = {}
        self._add_base_objects()
        self._rebuild_child_index()

    def compile_files(self, file_paths: list[str | Path]) -> dict[str, Any]:
        self.reset()
        self.compiled_files = [str(Path(item)) for item in file_paths if str(item).strip()]

        declarations: list[MibDeclaration] = []
        modules = set()
        parser = SmiV2Parser()

        for file_path in self.compiled_files:
            path = Path(file_path)
            if not self._is_mib_candidate(path):
                continue
            if not path.exists() or not path.is_file():
                self.failed_files.append(self._failed_file(path, "MIB 文件不存在或不可读取"))
                continue

            try:
                parsed_modules = parser.parse(path.read_text(encoding="utf-8", errors="ignore"))
            except Exception as exc:
                self.failed_files.append(self._failed_file(path, f"pysmi 解析失败: {exc}"))
                continue

            if not parsed_modules:
                self.failed_files.append(self._failed_file(path, "pysmi 未解析到 MIB 模块"))
                continue

            self.loaded_files.append(str(path))
            for module_ast in parsed_modules:
                module_name = str(module_ast[0])
                imports = module_ast[2] or {}
                module_declarations = module_ast[3] or []
                modules.add(module_name)
                self.imports_by_module[module_name] = sorted(imports.keys())
                declarations.extend(self._extract_declarations(module_name, str(path), module_declarations))

        self.modules = sorted(modules)
        self._resolve_declarations(declarations)
        self._rebuild_child_index()
        return self.get_summary()

    def get_summary(self) -> dict[str, Any]:
        return {
            "compiler": "pysmi",
            "requestedFiles": self.compiled_files,
            "expandedFileCount": len(self.loaded_files) + len(self.failed_files),
            "loadedFiles": [
                {"filePath": file_path, "fileName": Path(file_path).name, "status": "compiled"}
                for file_path in self.loaded_files
            ],
            "failedFiles": self.failed_files,
            "modules": self.modules,
            "baseModules": ["SNMPv2-SMI", "SNMPv2-TC"],
            "importsByModule": self.imports_by_module,
            "totalObjects": len(self.oid_index),
            "unresolvedObjects": self.unresolved_objects,
            "cacheHit": False,
            "oidTree": self.get_tree_children(),
        }

    def get_tree_children(self, parent_oid: str = "") -> list[dict[str, Any]]:
        parent = normalize_oid(parent_oid) if parent_oid else ""
        return [self._to_tree_node(oid) for oid in self.child_index.get(parent, [])]

    def build_tree(self) -> list[dict[str, Any]]:
        def attach(oid: str) -> dict[str, Any]:
            node = self._to_tree_node(oid)
            node["children"] = [attach(child_oid) for child_oid in self.child_index.get(oid, [])]
            return node

        return [attach(oid) for oid in self.child_index.get("", [])]

    def translate_oid(self, oid: str) -> dict[str, Any]:
        normalized = normalize_oid(oid)
        exact = self.oid_index.get(normalized)
        if exact:
            return {
                "oid": normalized,
                "matched": True,
                "exact": True,
                "object": self._object_to_dict(exact),
                "suffix": "",
                "moduleQualifiedName": self._qualified_name(exact),
            }

        parent_oid = self._find_nearest_parent_oid(normalized)
        if not parent_oid:
            return {
                "oid": normalized,
                "matched": False,
                "exact": False,
                "object": None,
                "suffix": "",
                "moduleQualifiedName": "",
            }

        obj = self.oid_index[parent_oid]
        suffix = normalized[len(parent_oid) :].lstrip(".")
        return {
            "oid": normalized,
            "matched": True,
            "exact": False,
            "object": self._object_to_dict(obj),
            "suffix": suffix,
            "moduleQualifiedName": self._qualified_name(obj),
        }

    def _extract_declarations(
        self,
        module_name: str,
        file_path: str,
        declarations: list[tuple[Any, ...]],
    ) -> list[MibDeclaration]:
        extracted: list[MibDeclaration] = []
        for declaration in declarations:
            if not declaration:
                continue
            clause_type = declaration[0]
            if clause_type == "valueDeclaration":
                extracted.append(
                    MibDeclaration(
                        object_name=declaration[1],
                        module_name=module_name,
                        macro="OBJECT IDENTIFIER",
                        oid_expression=declaration[2],
                        file_path=file_path,
                    )
                )
            elif clause_type == "objectTypeClause":
                syntax = declaration[2]
                extracted.append(
                    MibDeclaration(
                        object_name=declaration[1],
                        module_name=module_name,
                        macro="OBJECT-TYPE",
                        oid_expression=declaration[-1],
                        file_path=file_path,
                        syntax=format_syntax(syntax),
                        max_access=tag_value(declaration[4], "MaxAccessPart"),
                        status=tag_value(declaration[5], "Status"),
                        description=tag_value(declaration[6], "DESCRIPTION"),
                        value_map=extract_value_map(syntax),
                    )
                )
            elif clause_type == "notificationTypeClause":
                extracted.append(
                    MibDeclaration(
                        object_name=declaration[1],
                        module_name=module_name,
                        macro="NOTIFICATION-TYPE",
                        oid_expression=declaration[-1],
                        file_path=file_path,
                        status=as_text(declaration[3]),
                        description=tag_value(declaration[4], "DESCRIPTION"),
                    )
                )
            elif clause_type == "trapTypeClause":
                extracted.append(
                    MibDeclaration(
                        object_name=declaration[1],
                        module_name=module_name,
                        macro="TRAP-TYPE",
                        oid_expression=("trapTypeOid", declaration[2], declaration[-1]),
                        file_path=file_path,
                        description=tag_value(declaration[4], "DESCRIPTION"),
                    )
                )
            elif clause_type in {
                "moduleIdentityClause",
                "objectIdentityClause",
                "moduleComplianceClause",
                "objectGroupClause",
                "notificationGroupClause",
                "agentCapabilitiesClause",
            }:
                extracted.append(
                    MibDeclaration(
                        object_name=declaration[1],
                        module_name=module_name,
                        macro=clause_type_to_macro(clause_type),
                        oid_expression=declaration[-1],
                        file_path=file_path,
                        status=find_status(declaration),
                        description=find_description(declaration),
                    )
                )
        return extracted

    def _resolve_declarations(self, declarations: list[MibDeclaration]) -> None:
        pending = list(declarations)
        last_unresolved: dict[str, str] = {}
        progressed = True

        while pending and progressed:
            progressed = False
            next_pending: list[MibDeclaration] = []
            for declaration in pending:
                oid, missing_symbol = self._resolve_oid_expression(declaration.oid_expression)
                if not oid:
                    last_unresolved[self._declaration_key(declaration)] = missing_symbol or "unknown"
                    next_pending.append(declaration)
                    continue

                self._add_object(
                    MibObject(
                        object_name=declaration.object_name,
                        module_name=declaration.module_name,
                        oid=oid,
                        macro=declaration.macro,
                        syntax=declaration.syntax,
                        max_access=declaration.max_access,
                        status=declaration.status,
                        description=declaration.description,
                        file_path=declaration.file_path,
                        value_map=declaration.value_map,
                    )
                )
                progressed = True

            pending = next_pending

        self.unresolved_objects = [
            {
                "objectName": item.object_name,
                "moduleName": item.module_name,
                "oidExpression": format_oid_expression(item.oid_expression),
                "filePath": item.file_path,
                "fileName": Path(item.file_path).name,
                "missingSymbol": last_unresolved.get(self._declaration_key(item), ""),
            }
            for item in pending
        ]

    def _resolve_oid_expression(self, expression: Any) -> tuple[str | None, str | None]:
        if isinstance(expression, tuple) and expression and expression[0] == "trapTypeOid":
            enterprise_oid, missing = self._resolve_oid_expression(expression[1])
            if not enterprise_oid:
                return None, missing
            return normalize_oid(f"{enterprise_oid}.0.{expression[2]}"), None

        components = oid_components(expression)
        if not components:
            return None, "empty oid expression"

        arcs: list[str] = []
        for component in components:
            if isinstance(component, int):
                arcs.append(str(component))
                continue

            if isinstance(component, tuple) and len(component) >= 2:
                name, number = str(component[0]), component[1]
                known_oid = self.symbol_index.get(name)
                if not arcs and known_oid:
                    arcs = known_oid.lstrip(".").split(".")
                else:
                    arcs.append(str(number))
                continue

            token = str(component)
            if token.lstrip("-").isdigit():
                arcs.append(token)
                continue

            known_oid = self.symbol_index.get(token)
            if not known_oid:
                return None, token
            arcs = known_oid.lstrip(".").split(".")

        return normalize_oid(".".join(arcs)), None

    def _add_base_objects(self) -> None:
        for object_name, oid in [
            ("ccitt", ".0"),
            ("iso", ".1"),
            ("std", ".1.0"),
            ("iso8802", ".1.0.8802"),
            ("org", ".1.3"),
            ("dod", ".1.3.6"),
            ("internet", ".1.3.6.1"),
            ("directory", ".1.3.6.1.1"),
            ("mgmt", ".1.3.6.1.2"),
            ("mib-2", ".1.3.6.1.2.1"),
            ("system", ".1.3.6.1.2.1.1"),
            ("transmission", ".1.3.6.1.2.1.10"),
            ("experimental", ".1.3.6.1.3"),
            ("private", ".1.3.6.1.4"),
            ("enterprises", ".1.3.6.1.4.1"),
            ("zeroDotZero", ".0.0"),
        ]:
            self._add_object(
                MibObject(
                    object_name=object_name,
                    module_name="SNMPv2-SMI",
                    oid=oid,
                    macro="OBJECT IDENTIFIER",
                    base=True,
                )
            )

    def _add_object(self, obj: MibObject) -> None:
        normalized_oid = normalize_oid(obj.oid)
        normalized = MibObject(
            object_name=obj.object_name,
            module_name=obj.module_name,
            oid=normalized_oid,
            macro=obj.macro,
            syntax=obj.syntax,
            max_access=obj.max_access,
            status=obj.status,
            description=obj.description,
            file_path=obj.file_path,
            value_map=obj.value_map,
            base=obj.base,
        )
        self.oid_index[normalized_oid] = normalized
        self.symbol_index.setdefault(normalized.object_name, normalized_oid)
        self.module_symbol_index.setdefault(normalized.module_name, {})[normalized.object_name] = normalized_oid

    def _rebuild_child_index(self) -> None:
        self.child_index = {"": []}
        for oid in sorted(self.oid_index, key=oid_sort_key):
            parent_oid = self._find_nearest_parent_oid(oid, include_self=False)
            parent_key = parent_oid or ""
            self.child_index.setdefault(parent_key, []).append(oid)
            self.child_index.setdefault(oid, [])

    def _find_nearest_parent_oid(self, oid: str, include_self: bool = True) -> str | None:
        normalized = normalize_oid(oid)
        parts = normalized.lstrip(".").split(".")
        if not include_self and parts:
            parts = parts[:-1]
        while parts:
            candidate = "." + ".".join(parts)
            if candidate in self.oid_index:
                return candidate
            parts = parts[:-1]
        return None

    def _to_tree_node(self, oid: str) -> dict[str, Any]:
        obj = self.oid_index[oid]
        children = self.child_index.get(oid, [])
        parent_oid = self._find_nearest_parent_oid(oid, include_self=False)
        return {
            **self._object_to_dict(obj),
            "key": oid,
            "title": obj.object_name,
            "parentOid": parent_oid,
            "hasChildren": bool(children),
            "childCount": len(children),
            "queryMetadata": {
                "canWalk": obj.macro in {"OBJECT-TYPE", "OBJECT IDENTIFIER"},
                "canGet": obj.macro == "OBJECT-TYPE" and obj.max_access not in {"not-accessible", ""},
                "isNotification": obj.macro in {"NOTIFICATION-TYPE", "TRAP-TYPE"},
                "syntax": obj.syntax,
                "maxAccess": obj.max_access,
            },
        }

    def _object_to_dict(self, obj: MibObject) -> dict[str, Any]:
        return {
            "oid": obj.oid,
            "objectName": obj.object_name,
            "moduleName": obj.module_name,
            "moduleQualifiedName": self._qualified_name(obj),
            "macro": obj.macro,
            "syntax": obj.syntax,
            "maxAccess": obj.max_access,
            "status": obj.status,
            "description": obj.description,
            "filePath": obj.file_path,
            "fileName": Path(obj.file_path).name if obj.file_path else "",
            "valueMap": obj.value_map,
            "base": obj.base,
        }

    def _qualified_name(self, obj: MibObject) -> str:
        return f"{obj.module_name}::{obj.object_name}" if obj.module_name else obj.object_name

    def _failed_file(self, path: Path, message: str) -> dict[str, Any]:
        return {"filePath": str(path), "fileName": path.name, "msg": message}

    def _is_mib_candidate(self, path: Path) -> bool:
        return path.suffix.lower() in MIB_FILE_EXTENSIONS

    def _declaration_key(self, declaration: MibDeclaration) -> str:
        return f"{declaration.module_name}::{declaration.object_name}"


def oid_components(expression: Any) -> list[Any]:
    if isinstance(expression, tuple) and expression and expression[0] == "objectIdentifier":
        return list(expression[1] or [])
    if isinstance(expression, list):
        return expression
    return []


def format_oid_expression(expression: Any) -> str:
    if isinstance(expression, tuple) and expression and expression[0] == "trapTypeOid":
        return f"{format_oid_expression(expression[1])} 0 {expression[2]}"
    return " ".join(str(item) for item in oid_components(expression))


def tag_value(value: Any, tag: str) -> str:
    if isinstance(value, tuple) and value and value[0] == tag and len(value) > 1:
        return as_text(value[1])
    return ""


def find_status(declaration: tuple[Any, ...]) -> str:
    for item in declaration:
        if isinstance(item, tuple) and item and item[0] == "Status":
            return as_text(item[1])
        if isinstance(item, str) and item in {"current", "deprecated", "obsolete", "mandatory", "optional"}:
            return item
    return ""


def find_description(declaration: tuple[Any, ...]) -> str:
    for item in declaration:
        description = tag_value(item, "DESCRIPTION")
        if description:
            return description
    return ""


def format_syntax(value: Any) -> str:
    if not isinstance(value, tuple) or not value:
        return as_text(value)

    tag = value[0]
    if tag == "SimpleSyntax":
        base = as_text(value[1]) if len(value) > 1 else ""
        enum_values = extract_value_map(value)
        if enum_values:
            rendered = ", ".join(f"{name}({number})" for name, number in enum_values.items())
            return f"{base} {{ {rendered} }}"
        return base
    if tag == "conceptualTable":
        return f"SEQUENCE OF {format_syntax(value[1])}" if len(value) > 1 else "SEQUENCE OF"
    if tag == "row":
        return as_text(value[1]) if len(value) > 1 else "row"
    if tag == "Bits":
        return "BITS"
    if tag == "sequence":
        return "SEQUENCE"
    return compact_whitespace(" ".join(as_text(item) for item in value if item is not None))


def extract_value_map(value: Any) -> dict[str, int]:
    if isinstance(value, tuple):
        if value and value[0] == "enumSpec" and len(value) > 1:
            return {str(name): int(number) for name, number in value[1]}
        for item in value[1:]:
            nested = extract_value_map(item)
            if nested:
                return nested
    if isinstance(value, list):
        for item in value:
            nested = extract_value_map(item)
            if nested:
                return nested
    return {}


def clause_type_to_macro(value: str) -> str:
    mapping = {
        "moduleIdentityClause": "MODULE-IDENTITY",
        "objectIdentityClause": "OBJECT-IDENTITY",
        "moduleComplianceClause": "MODULE-COMPLIANCE",
        "objectGroupClause": "OBJECT-GROUP",
        "notificationGroupClause": "NOTIFICATION-GROUP",
        "agentCapabilitiesClause": "AGENT-CAPABILITIES",
    }
    return mapping.get(value, value).upper()


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, tuple):
        if len(value) == 2 and isinstance(value[0], str):
            return as_text(value[1])
        return compact_whitespace(" ".join(as_text(item) for item in value))
    if isinstance(value, list):
        return compact_whitespace(" ".join(as_text(item) for item in value))
    return compact_whitespace(str(value))


def compact_whitespace(value: str) -> str:
    return " ".join(str(value or "").split())


def normalize_oid(oid: str) -> str:
    stripped = str(oid or "").strip()
    if not stripped:
        return ""
    return "." + ".".join(part for part in stripped.lstrip(".").split(".") if part != "")


def oid_sort_key(oid: str) -> list[int]:
    key = []
    for part in normalize_oid(oid).lstrip(".").split("."):
        try:
            key.append(int(part))
        except ValueError:
            key.append(0)
    return key
