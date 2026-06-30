from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from math import log, sqrt
from pathlib import Path
import json
import re
from typing import Any
from uuid import uuid4

try:
    from rank_bm25 import BM25Okapi
except Exception:  # pragma: no cover - dependency fallback for constrained installs
    BM25Okapi = None


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KNOWLEDGE_FILE = PROJECT_ROOT / ".netnexus" / "knowledge_documents.json"
DEFAULT_BUILTIN_DIR = PROJECT_ROOT / "knowledge"
MAX_CHUNK_CHARS = 900
CHUNK_OVERLAP_CHARS = 120
SEARCH_LIMIT = 5
TITLE_WEIGHT = 2.0
TAG_WEIGHT = 2.0
SOURCE_WEIGHT = 1.0
EXACT_PHRASE_BOOST = 1.2


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    title: str
    heading: str
    source: str
    tags: list[str]
    content: str
    tokens: list[str]
    title_tokens: list[str]
    tag_tokens: list[str]
    source_tokens: list[str]
    readonly: bool


class KnowledgeBaseService:
    def __init__(
        self,
        *,
        storage_file: Path | None = None,
        builtin_dir: Path | None = None,
    ) -> None:
        self._storage_file = storage_file or DEFAULT_KNOWLEDGE_FILE
        self._builtin_dir = builtin_dir or DEFAULT_BUILTIN_DIR

    def list_documents(self) -> dict[str, Any]:
        documents = self._all_documents()
        return {
            "items": [public_document(document) for document in documents],
            "summary": {
                "total": len(documents),
                "builtin": len([item for item in documents if item.get("readonly")]),
                "custom": len([item for item in documents if not item.get("readonly")]),
            },
        }

    def upsert_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        title = clean_text(payload.get("title"))
        content = clean_text(payload.get("content"))
        if not title:
            raise ValueError("知识文档标题不能为空")
        if not content:
            raise ValueError("知识文档内容不能为空")

        documents = self._read_custom_documents()
        document_id = clean_identifier(payload.get("id")) or f"kb_{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        existing = next((item for item in documents if item.get("id") == document_id), None)
        next_document = {
            "id": document_id,
            "title": title,
            "content": content,
            "source": clean_text(payload.get("source")) or "operator",
            "tags": normalize_tags(payload.get("tags")),
            "created_at": existing.get("created_at") if existing else now,
            "updated_at": now,
            "readonly": False,
        }
        documents = [item for item in documents if item.get("id") != document_id]
        documents.append(next_document)
        self._write_custom_documents(documents)
        return {"document": public_document(next_document)}

    def delete_document(self, document_id: str) -> dict[str, Any]:
        normalized_id = clean_identifier(document_id)
        documents = self._read_custom_documents()
        next_documents = [item for item in documents if item.get("id") != normalized_id]
        if len(next_documents) == len(documents):
            if any(item.get("id") == normalized_id for item in self._builtin_documents()):
                raise ValueError("内置知识文档不能删除")
            raise ValueError(f"知识文档不存在: {document_id}")
        self._write_custom_documents(next_documents)
        return {"deleted": True, "id": normalized_id}

    def search(self, query: str, *, limit: int = SEARCH_LIMIT) -> dict[str, Any]:
        normalized_query = " ".join(str(query or "").split())
        chunks = self._chunks()
        scored = score_chunks(normalized_query, chunks)
        limit = max(1, min(int(limit or SEARCH_LIMIT), 20))
        return {
            "query": normalized_query,
            "items": [public_search_result(item) for item in scored[:limit]],
            "summary": {
                "backend": retrieval_backend_name(),
                "documents": len(self._all_documents()),
                "chunks": len(chunks),
                "returned": min(len(scored), limit),
            },
        }

    def retrieve_for_diagnosis(
        self,
        *,
        question: str,
        facts: list[dict[str, Any]],
        question_context: dict[str, Any],
        context_constraints: dict[str, Any],
        limit: int = 4,
    ) -> dict[str, Any]:
        query = build_retrieval_query(
            question=question,
            facts=facts,
            question_context=question_context,
            context_constraints=context_constraints,
        )
        result = self.search(query, limit=limit)
        return {
            "enabled": True,
            "query": query,
            "items": result["items"],
            "summary": result["summary"],
            "instructions": [
                "knowledge_context 是检索到的外部知识，只能辅助解释、排障步骤和建议",
                "实时 facts、topology、question_context 和 context_constraints 的优先级高于知识库内容",
                "不能因为知识库模板存在某类故障，就推断当前环境也发生该故障",
            ],
        }

    def _all_documents(self) -> list[dict[str, Any]]:
        return [*self._builtin_documents(), *self._read_custom_documents()]

    def _builtin_documents(self) -> list[dict[str, Any]]:
        if not self._builtin_dir.exists():
            return []
        documents = []
        for path in sorted(self._builtin_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            title = first_markdown_title(content) or path.stem.replace("_", " ")
            documents.append(
                {
                    "id": f"builtin_{path.stem}",
                    "title": title,
                    "content": content,
                    "source": display_path(path),
                    "tags": ["builtin", "runbook"],
                    "created_at": None,
                    "updated_at": None,
                    "readonly": True,
                }
            )
        return documents

    def _read_custom_documents(self) -> list[dict[str, Any]]:
        if not self._storage_file.exists():
            return []
        try:
            raw = json.loads(self._storage_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        items = raw.get("items") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []
        return [normalize_document(item) for item in items if isinstance(item, dict)]

    def _write_custom_documents(self, documents: list[dict[str, Any]]) -> None:
        self._storage_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"items": [normalize_document(item) for item in documents]}
        self._storage_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _chunks(self) -> list[KnowledgeChunk]:
        chunks = []
        for document in self._all_documents():
            for index, section in enumerate(split_into_chunks(document.get("content") or ""), start=1):
                content = section["content"]
                heading = section["heading"] or document.get("title") or document["id"]
                chunk_id = f"{document['id']}#chunk-{index}"
                title_tokens = tokenize(document.get("title") or "")
                tag_tokens = tokenize(" ".join(document.get("tags") or []))
                source_tokens = tokenize(document.get("source") or "")
                tokens = weighted_tokens(
                    [
                        tokenize(content),
                        tokenize(heading),
                        repeat_tokens(title_tokens, TITLE_WEIGHT),
                        repeat_tokens(tag_tokens, TAG_WEIGHT),
                        repeat_tokens(source_tokens, SOURCE_WEIGHT),
                    ]
                )
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=chunk_id,
                        document_id=document["id"],
                        title=document.get("title") or document["id"],
                        heading=heading,
                        source=document.get("source") or "",
                        tags=list(document.get("tags") or []),
                        content=content,
                        tokens=tokens,
                        title_tokens=title_tokens,
                        tag_tokens=tag_tokens,
                        source_tokens=source_tokens,
                        readonly=bool(document.get("readonly")),
                    )
                )
        return chunks


def empty_knowledge_context() -> dict[str, Any]:
    return {
        "enabled": False,
        "query": "",
        "items": [],
        "summary": {"documents": 0, "chunks": 0, "returned": 0},
        "instructions": [],
    }


def build_retrieval_query(
    *,
    question: str,
    facts: list[dict[str, Any]],
    question_context: dict[str, Any],
    context_constraints: dict[str, Any],
) -> str:
    parts = [question]
    for fact in facts:
        parts.extend(
            str(fact.get(key) or "")
            for key in ["fact_type", "device_id", "object", "value", "source", "severity"]
        )
        parts.extend(flatten_text_values(fact.get("context") or {}))
    parts.extend(str(item) for item in context_constraints.get("evidence", []) or [])
    parts.extend(flatten_text_values(question_context))
    return " ".join(part for part in parts if part).strip()


def score_chunks(query: str, chunks: list[KnowledgeChunk]) -> list[dict[str, Any]]:
    query_tokens = expand_query_tokens(tokenize(query))
    if not query_tokens or not chunks:
        return []

    if BM25Okapi is not None:
        return score_chunks_with_bm25(query, query_tokens, chunks)
    return score_chunks_with_fallback(query, query_tokens, chunks)


def score_chunks_with_bm25(
    query: str,
    query_tokens: list[str],
    chunks: list[KnowledgeChunk],
) -> list[dict[str, Any]]:
    bm25 = BM25Okapi([chunk.tokens for chunk in chunks])
    raw_scores = bm25.get_scores(query_tokens)
    scored = []
    query_counter = Counter(query_tokens)
    for chunk, raw_score in zip(chunks, raw_scores):
        matched_terms = matched_query_terms(query_counter, chunk)
        if not matched_terms:
            continue
        lexical_score = lexical_overlap_score(query_counter, chunk)
        base_score = max(float(raw_score), 0.0) + lexical_score
        boost = metadata_boost(query_tokens, query, chunk)
        final_score = round(base_score * boost, 6)
        scored.append(
            {
                "chunk": chunk,
                "score": final_score,
                "raw_score": round(base_score, 6),
                "bm25_score": round(float(raw_score), 6),
                "lexical_score": round(lexical_score, 6),
                "boost": round(boost, 4),
                "matched_terms": matched_terms,
                "backend": "rank_bm25.BM25Okapi",
            }
        )
    scored.sort(key=lambda item: (-item["score"], item["chunk"].title, item["chunk"].chunk_id))
    return scored


def score_chunks_with_fallback(
    query: str,
    query_tokens: list[str],
    chunks: list[KnowledgeChunk],
) -> list[dict[str, Any]]:
    query_counter = Counter(query_tokens)
    document_frequency = Counter()
    for chunk in chunks:
        document_frequency.update(set(chunk.tokens))

    scored = []
    chunk_count = len(chunks)
    for chunk in chunks:
        token_counter = Counter(chunk.tokens)
        score = 0.0
        for token, query_count in query_counter.items():
            frequency = token_counter.get(token, 0)
            if not frequency:
                continue
            idf = log((chunk_count + 1) / (document_frequency[token] + 1)) + 1
            score += (1 + log(frequency)) * idf * query_count
        if score <= 0:
            continue
        score = score / sqrt(max(len(chunk.tokens), 1))
        boost = metadata_boost(query_tokens, query, chunk)
        scored.append(
            {
                "chunk": chunk,
                "score": round(score * boost, 6),
                "raw_score": round(score, 6),
                "bm25_score": None,
                "lexical_score": round(score, 6),
                "boost": round(boost, 4),
                "matched_terms": matched_query_terms(query_counter, chunk),
                "backend": "fallback_tf_idf",
            }
        )
    scored.sort(key=lambda item: (-item["score"], item["chunk"].title, item["chunk"].chunk_id))
    return scored


def matched_query_terms(query_counter: Counter[str], chunk: KnowledgeChunk) -> list[str]:
    chunk_terms = set(chunk.tokens)
    return sorted(
        {token for token in query_counter if token in chunk_terms},
        key=lambda item: (-query_counter[item], item),
    )[:12]


def lexical_overlap_score(query_counter: Counter[str], chunk: KnowledgeChunk) -> float:
    token_counter = Counter(chunk.tokens)
    score = 0.0
    for token, query_count in query_counter.items():
        frequency = token_counter.get(token, 0)
        if frequency:
            score += min(frequency, 3) * query_count
    return score / sqrt(max(len(chunk.tokens), 1))


def metadata_boost(query_tokens: list[str], query: str, chunk: KnowledgeChunk) -> float:
    query_set = set(query_tokens)
    boost = 1.0
    if query_set.intersection(chunk.title_tokens):
        boost += 0.14
    if query_set.intersection(chunk.tag_tokens):
        boost += 0.1
    if query_set.intersection(chunk.source_tokens):
        boost += 0.06
    if exact_phrase_match(query, chunk):
        boost += EXACT_PHRASE_BOOST
    return boost


def exact_phrase_match(query: str, chunk: KnowledgeChunk) -> bool:
    normalized_query = normalize_phrase(query)
    if not normalized_query or len(normalized_query) < 4:
        return False
    haystack = normalize_phrase(" ".join([chunk.title, chunk.heading, chunk.content]))
    phrases = [normalize_phrase(item) for item in query_phrases(query)]
    return any(phrase and len(phrase) >= 4 and phrase in haystack for phrase in phrases) or normalized_query in haystack


def query_phrases(query: str) -> list[str]:
    phrases = []
    for part in re.split(r"[,;，；。?？\n]+", query or ""):
        normalized = " ".join(part.split())
        if normalized:
            phrases.append(normalized)
    return phrases


def normalize_phrase(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def public_search_result(scored_item: dict[str, Any]) -> dict[str, Any]:
    chunk: KnowledgeChunk = scored_item["chunk"]
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "title": chunk.title,
        "heading": chunk.heading,
        "source": chunk.source,
        "tags": chunk.tags,
        "score": scored_item["score"],
        "raw_score": scored_item.get("raw_score"),
        "bm25_score": scored_item.get("bm25_score"),
        "lexical_score": scored_item.get("lexical_score"),
        "boost": scored_item.get("boost"),
        "retrieval_backend": scored_item.get("backend"),
        "matched_terms": scored_item["matched_terms"],
        "content": chunk.content,
        "readonly": chunk.readonly,
    }


def public_document(document: dict[str, Any]) -> dict[str, Any]:
    content = document.get("content") or ""
    return {
        "id": document.get("id"),
        "title": document.get("title"),
        "source": document.get("source") or "",
        "tags": list(document.get("tags") or []),
        "content": content,
        "content_length": len(content),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
        "readonly": bool(document.get("readonly")),
    }


def normalize_document(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": clean_identifier(item.get("id")) or f"kb_{uuid4().hex[:12]}",
        "title": clean_text(item.get("title")) or "未命名知识",
        "content": clean_text(item.get("content")),
        "source": clean_text(item.get("source")) or "operator",
        "tags": normalize_tags(item.get("tags")),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "readonly": bool(item.get("readonly")),
    }


def split_into_chunks(content: str, max_chars: int = MAX_CHUNK_CHARS) -> list[dict[str, str]]:
    sections = markdown_sections(content)
    chunks: list[dict[str, str]] = []
    for section in sections:
        chunks.extend(split_section_into_chunks(section, max_chars=max_chars))
    return chunks


def markdown_sections(content: str) -> list[dict[str, str]]:
    sections = []
    current_heading = ""
    current_lines = []
    for line in (content or "").splitlines():
        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading_match:
            if current_lines:
                sections.append({"heading": current_heading, "content": "\n".join(current_lines).strip()})
            current_heading = heading_match.group(2).strip()
            current_lines = [line]
            continue
        current_lines.append(line)
    if current_lines:
        sections.append({"heading": current_heading, "content": "\n".join(current_lines).strip()})
    return [section for section in sections if section["content"]] or [{"heading": "", "content": (content or "").strip()}]


def split_section_into_chunks(section: dict[str, str], max_chars: int = MAX_CHUNK_CHARS) -> list[dict[str, str]]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", section.get("content") or "") if paragraph.strip()]
    chunks: list[dict[str, str]] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append({"heading": section.get("heading") or "", "content": current})
            overlap = current[-CHUNK_OVERLAP_CHARS:] if CHUNK_OVERLAP_CHARS > 0 else ""
            current = f"{overlap}\n\n{paragraph}".strip() if overlap else paragraph
        else:
            current = f"{current}\n\n{paragraph}".strip() if current else paragraph
    if current:
        chunks.append({"heading": section.get("heading") or "", "content": current})
    return chunks


def tokenize(text: str) -> list[str]:
    tokens = []
    for match in re.finditer(r"[A-Za-z0-9_./:-]+|[\u4e00-\u9fff]+", text or ""):
        value = match.group(0).lower()
        if re.match(r"^[\u4e00-\u9fff]+$", value):
            tokens.extend(value)
            tokens.extend(value[index : index + 2] for index in range(max(len(value) - 1, 0)))
        else:
            tokens.append(value)
    return [token for token in tokens if token.strip()]


def expand_query_tokens(tokens: list[str]) -> list[str]:
    return list(dict.fromkeys(tokens))


def flatten_text_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            parts.append(str(key))
            parts.extend(flatten_text_values(item))
        return parts
    if isinstance(value, (list, tuple, set)):
        parts = []
        for item in value:
            parts.extend(flatten_text_values(item))
        return parts
    if isinstance(value, bool):
        return [str(value).lower()]
    return [str(value)]


def weighted_tokens(token_groups: list[list[str]]) -> list[str]:
    tokens = []
    for group in token_groups:
        tokens.extend(group)
    return tokens


def repeat_tokens(tokens: list[str], weight: float) -> list[str]:
    repeat = max(1, int(round(weight)))
    return [token for token in tokens for _ in range(repeat)]


def retrieval_backend_name() -> str:
    return "rank_bm25.BM25Okapi" if BM25Okapi is not None else "fallback_tf_idf"


def first_markdown_title(content: str) -> str | None:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def clean_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def clean_identifier(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "").strip())


def normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.replace(",", "\n").replace(";", "\n").splitlines()
    elif isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = [value]
    tags = [clean_text(item) for item in raw_items if clean_text(item)]
    return list(dict.fromkeys(tags))[:20]
