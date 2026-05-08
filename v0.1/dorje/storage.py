"""Index storage — partitioned, slab-based, float16 vectors."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

import msgpack  # type: ignore[import-untyped]
import numpy as np

from dorje.types import CallRef, Chunk, ChunkMetadata, GraphNode, Triple

_PARTITIONS_DIR = "partitions"
_SCOPE_FILE = "scope.json"
_STATE_FILE = "state.json"
_CONTENT_VECTORS_FILE = "content_vectors.npy"
_METADATA_VECTORS_FILE = "metadata_vectors.npy"
_CHUNK_IDS_FILE = "chunk_ids.json"
_CHUNKS_FILE = "chunks.json"
_BM25_FILE = "bm25.msgpack"
_GRAPH_NODES_FILE = "graph/nodes.msgpack"
_GRAPH_TRIPLES_FILE = "graph/triples.msgpack"
_GRAPH_NODE_VECTORS_FILE = "graph/node_vectors.npy"
_GRAPH_VERB_VECTORS_FILE = "graph/verb_vectors.npy"
_GIT_COMMITS_FILE = "git/commits.json"
_GIT_VECTORS_FILE = "git/vectors.npy"

_VECTOR_DTYPE = np.float16


def _partition_key(relative_path: str) -> str:
    """Compute partition key from a relative file path.

    Partition key is the first path component (top-level directory),
    or '_root' for files directly in the index root.
    """
    assert relative_path, "relative_path must not be empty"
    parts = Path(relative_path).parts
    if len(parts) <= 1:
        return "_root"
    return parts[0]


def _partition_hash(key: str) -> str:
    """Stable hash for partition directory naming."""
    assert key, "partition key must not be empty"
    return sha256(key.encode("utf-8")).hexdigest()[:12]


class Scope:
    """Manages scope.json — what this index covers and where it delegates."""

    def __init__(self, index_path: Path) -> None:
        self._path = index_path / _SCOPE_FILE
        self.covers: str = "."
        self.delegates: list[str] = []

    def load(self) -> None:
        """Load scope from disk."""
        if not self._path.exists():
            return
        raw = self._path.read_text(encoding="utf-8")
        assert raw, f"Scope file is empty: {self._path}"
        data = json.loads(raw)
        assert isinstance(data, dict), "scope.json must be a JSON object"
        self.covers = str(data.get("covers", "."))
        delegates_raw = data.get("delegates", [])
        assert isinstance(delegates_raw, list), "scope.delegates must be a list"
        self.delegates = [str(d) for d in delegates_raw]

    def save(self) -> None:
        """Write scope to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"covers": self.covers, "delegates": self.delegates}
        self._path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def is_delegated(self, relative_path: str) -> bool:
        """Check if a path falls under a delegated subtree."""
        assert relative_path is not None, "relative_path must not be None"
        for delegate in self.delegates:
            if relative_path == delegate or relative_path.startswith(delegate + "/"):
                return True
        return False


class PartitionStore:
    """Storage for a single partition within the index."""

    def __init__(self, partition_path: Path) -> None:
        assert partition_path, "partition_path must not be empty"
        self._path = partition_path

    def _ensure_dirs(self) -> None:
        """Create partition directories."""
        self._path.mkdir(parents=True, exist_ok=True)
        (self._path / "graph").mkdir(exist_ok=True)
        (self._path / "git").mkdir(exist_ok=True)

    # -- Vectors --

    def write_vectors(
        self,
        chunk_ids: list[str],
        content_vectors: np.ndarray,
        metadata_vectors: np.ndarray,
    ) -> None:
        """Write content and metadata vectors to disk as float16."""
        assert len(chunk_ids) == content_vectors.shape[0], (
            f"chunk_ids length ({len(chunk_ids)}) != "
            f"content_vectors rows ({content_vectors.shape[0]})"
        )
        assert content_vectors.shape[0] == metadata_vectors.shape[0], (
            f"content_vectors rows ({content_vectors.shape[0]}) != "
            f"metadata_vectors rows ({metadata_vectors.shape[0]})"
        )

        self._ensure_dirs()

        np.save(
            str(self._path / _CONTENT_VECTORS_FILE),
            content_vectors.astype(_VECTOR_DTYPE),
        )
        np.save(
            str(self._path / _METADATA_VECTORS_FILE),
            metadata_vectors.astype(_VECTOR_DTYPE),
        )

        ids_path = self._path / _CHUNK_IDS_FILE
        ids_path.write_text(json.dumps(chunk_ids) + "\n", encoding="utf-8")

    def read_vectors(
        self,
        kind: str,
        slab_size: int | None = None,
    ) -> Iterator[tuple[list[str], np.ndarray]]:
        """Yield (ids, vectors) in slabs. kind is 'content' or 'metadata'.

        Vectors are loaded as float16 and upcast to float32 for compute.
        If slab_size is None, yields everything in one batch.
        """
        assert kind in ("content", "metadata"), f"kind must be 'content' or 'metadata', got {kind}"

        filename = _CONTENT_VECTORS_FILE if kind == "content" else _METADATA_VECTORS_FILE
        vec_path = self._path / filename
        ids_path = self._path / _CHUNK_IDS_FILE

        if not vec_path.exists() or not ids_path.exists():
            return

        ids_raw = ids_path.read_text(encoding="utf-8")
        all_ids: list[str] = json.loads(ids_raw)
        all_vectors = np.load(str(vec_path)).astype(np.float32)

        assert len(all_ids) == all_vectors.shape[0], (
            f"IDs count ({len(all_ids)}) != vectors rows ({all_vectors.shape[0]})"
        )

        if slab_size is None or slab_size >= len(all_ids):
            yield all_ids, all_vectors
            return

        total = len(all_ids)
        offset = 0
        max_iterations = (total // slab_size) + 2  # Safety bound
        for _ in range(max_iterations):
            if offset >= total:
                break
            end = min(offset + slab_size, total)
            yield all_ids[offset:end], all_vectors[offset:end]
            offset = end

    def has_vectors(self) -> bool:
        """Check if this partition has stored vectors."""
        return (self._path / _CONTENT_VECTORS_FILE).exists()

    # -- Chunks (metadata records) --

    def write_chunks(self, chunks: list[Chunk]) -> None:
        """Write chunk metadata to disk."""
        self._ensure_dirs()
        data = [_chunk_to_dict(c) for c in chunks]
        path = self._path / _CHUNKS_FILE
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def read_chunks(self) -> list[Chunk]:
        """Read chunk metadata from disk."""
        path = self._path / _CHUNKS_FILE
        if not path.exists():
            return []
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert isinstance(data, list), "chunks.json must be a JSON array"
        return [_dict_to_chunk(d) for d in data]

    # -- BM25 --

    def write_bm25(self, index_data: dict[str, Any]) -> None:
        """Write BM25 inverted index."""
        self._ensure_dirs()
        path = self._path / _BM25_FILE
        path.write_bytes(msgpack.packb(index_data, use_bin_type=True))

    def read_bm25(self) -> dict[str, Any] | None:
        """Read BM25 inverted index. Returns None if not present."""
        path = self._path / _BM25_FILE
        if not path.exists():
            return None
        return msgpack.unpackb(path.read_bytes(), raw=False)  # type: ignore[no-any-return]

    # -- Graph --

    def write_graph(
        self,
        nodes: list[GraphNode],
        triples: list[Triple],
    ) -> None:
        """Write graph nodes and triples."""
        self._ensure_dirs()

        nodes_data = [_graph_node_to_dict(n) for n in nodes]
        triples_data = [_triple_to_dict(t) for t in triples]

        nodes_path = self._path / _GRAPH_NODES_FILE
        triples_path = self._path / _GRAPH_TRIPLES_FILE

        nodes_path.write_bytes(msgpack.packb(nodes_data, use_bin_type=True))
        triples_path.write_bytes(msgpack.packb(triples_data, use_bin_type=True))

    def read_graph_nodes(self) -> list[GraphNode]:
        """Read graph nodes."""
        path = self._path / _GRAPH_NODES_FILE
        if not path.exists():
            return []
        data = msgpack.unpackb(path.read_bytes(), raw=False)
        assert isinstance(data, list), "graph nodes must be a list"
        return [_dict_to_graph_node(d) for d in data]

    def read_graph_triples(self) -> list[Triple]:
        """Read graph triples."""
        path = self._path / _GRAPH_TRIPLES_FILE
        if not path.exists():
            return []
        data = msgpack.unpackb(path.read_bytes(), raw=False)
        assert isinstance(data, list), "graph triples must be a list"
        return [_dict_to_triple(d) for d in data]

    def write_graph_vectors(
        self,
        kind: str,
        ids: list[str],
        vectors: np.ndarray,
    ) -> None:
        """Write graph node or verb vectors."""
        assert kind in ("node", "verb"), f"kind must be 'node' or 'verb', got {kind}"
        assert len(ids) == vectors.shape[0], "ids and vectors must have same length"

        self._ensure_dirs()
        filename = _GRAPH_NODE_VECTORS_FILE if kind == "node" else _GRAPH_VERB_VECTORS_FILE
        np.save(str(self._path / filename), vectors.astype(_VECTOR_DTYPE))

        ids_file = self._path / f"graph/{kind}_ids.json"
        ids_file.write_text(json.dumps(ids) + "\n", encoding="utf-8")

    def read_graph_vectors(
        self,
        kind: str,
        slab_size: int | None = None,
    ) -> Iterator[tuple[list[str], np.ndarray]]:
        """Yield graph vectors in slabs."""
        assert kind in ("node", "verb"), f"kind must be 'node' or 'verb', got {kind}"

        filename = _GRAPH_NODE_VECTORS_FILE if kind == "node" else _GRAPH_VERB_VECTORS_FILE
        vec_path = self._path / filename
        ids_path = self._path / f"graph/{kind}_ids.json"

        if not vec_path.exists() or not ids_path.exists():
            return

        all_ids: list[str] = json.loads(ids_path.read_text(encoding="utf-8"))
        all_vectors = np.load(str(vec_path)).astype(np.float32)

        assert len(all_ids) == all_vectors.shape[0]

        if slab_size is None or slab_size >= len(all_ids):
            yield all_ids, all_vectors
            return

        total = len(all_ids)
        offset = 0
        max_iterations = (total // slab_size) + 2
        for _ in range(max_iterations):
            if offset >= total:
                break
            end = min(offset + slab_size, total)
            yield all_ids[offset:end], all_vectors[offset:end]
            offset = end


class IndexStore:
    """Top-level index storage. Manages partitions and scope."""

    def __init__(self, index_path: Path) -> None:
        assert index_path, "index_path must not be empty"
        self._path = index_path
        self.scope = Scope(index_path)

    def initialize(self) -> None:
        """Create index directory structure and default scope."""
        self._path.mkdir(parents=True, exist_ok=True)
        (self._path / _PARTITIONS_DIR).mkdir(exist_ok=True)
        self.scope.covers = "."
        self.scope.delegates = []
        self.scope.save()

    def load(self) -> None:
        """Load index state from disk."""
        self.scope.load()

    def partition_for(self, relative_path: str) -> PartitionStore:
        """Get or create a partition store for a given file path."""
        key = _partition_key(relative_path)
        hashed = _partition_hash(key)
        partition_path = self._path / _PARTITIONS_DIR / hashed
        return PartitionStore(partition_path)

    def all_partitions(self) -> list[PartitionStore]:
        """List all existing partitions."""
        partitions_dir = self._path / _PARTITIONS_DIR
        if not partitions_dir.exists():
            return []
        result = []
        for child in sorted(partitions_dir.iterdir()):
            if child.is_dir():
                result.append(PartitionStore(child))
        return result

    def partition_keys(self) -> dict[str, str]:
        """Return mapping of partition key -> partition hash for all partitions."""
        mapping_file = self._path / _PARTITIONS_DIR / "_mapping.json"
        if not mapping_file.exists():
            return {}
        return json.loads(mapping_file.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def save_partition_mapping(self, mapping: dict[str, str]) -> None:
        """Save the partition key -> hash mapping."""
        partitions_dir = self._path / _PARTITIONS_DIR
        partitions_dir.mkdir(parents=True, exist_ok=True)
        mapping_file = partitions_dir / "_mapping.json"
        mapping_file.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")

    # -- Incremental state --

    def read_state(self) -> dict[str, Any]:
        """Read incremental indexing state."""
        path = self._path / _STATE_FILE
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def write_state(self, state: dict[str, Any]) -> None:
        """Write incremental indexing state."""
        self._path.mkdir(parents=True, exist_ok=True)
        path = self._path / _STATE_FILE
        path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    # -- Delegation tree --

    def enumerate_leaves(self, root: Path) -> list[Path]:
        """Walk the directory tree and find all leaf .dorje indexes."""
        assert root.is_absolute(), f"root must be absolute, got {root}"
        leaves: list[Path] = []
        self._collect_leaves(root, leaves, depth=0)
        return leaves

    def _collect_leaves(self, current: Path, leaves: list[Path], depth: int) -> None:
        """Recursively collect leaf indexes."""
        max_depth = 50
        assert depth < max_depth, f"Index tree exceeds max depth of {max_depth}"

        dorje_dir = current / ".dorje"
        if not dorje_dir.is_dir():
            return

        scope = Scope(dorje_dir)
        scope.load()

        if not scope.delegates:
            leaves.append(dorje_dir)
            return

        has_own_content = any(
            p.has_vectors() for p in IndexStore(dorje_dir).all_partitions()
        )
        if has_own_content:
            leaves.append(dorje_dir)

        for delegate in scope.delegates:
            child_path = current / delegate
            if child_path.is_dir():
                self._collect_leaves(child_path, leaves, depth + 1)


# -- Serialization helpers --


def _chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    """Serialize a Chunk to a JSON-compatible dict."""
    return {
        "id": chunk.id,
        "path": chunk.path,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "content": chunk.content,
        "chunk_type": chunk.chunk_type,
        "language": chunk.language,
        "metadata": asdict(chunk.metadata),
        "unit_id": chunk.unit_id,
        "pass_name": chunk.pass_name,
    }


def _dict_to_chunk(d: dict[str, Any]) -> Chunk:
    """Deserialize a Chunk from a dict."""
    meta_raw = d["metadata"]
    # Convert lists back to tuples for frozen dataclass
    for field_name in ("parameters", "decorators", "imports_used"):
        val = meta_raw.get(field_name)
        if isinstance(val, list):
            meta_raw[field_name] = tuple(val)
    # CallRef reconstruction
    calls_raw = meta_raw.get("calls_made")
    if isinstance(calls_raw, list):
        meta_raw["calls_made"] = tuple(
            CallRef(raw=c["raw"], resolved_unit_id=c.get("resolved_unit_id"))
            if isinstance(c, dict) else c
            for c in calls_raw
        )
    metadata = ChunkMetadata(**meta_raw)
    return Chunk(
        id=d["id"],
        path=d["path"],
        start_line=d["start_line"],
        end_line=d["end_line"],
        content=d["content"],
        chunk_type=d["chunk_type"],
        language=d.get("language"),
        metadata=metadata,
        unit_id=d.get("unit_id", ""),
        pass_name=d.get("pass_name", ""),
    )


def _graph_node_to_dict(node: GraphNode) -> dict[str, Any]:
    """Serialize a GraphNode."""
    return asdict(node)


def _dict_to_graph_node(d: dict[str, Any]) -> GraphNode:
    """Deserialize a GraphNode."""
    return GraphNode(
        id=d["id"],
        kind=d["kind"],
        label=d["label"],
        path=d.get("path"),
        line=d.get("line"),
        metadata=d.get("metadata", {}),
    )


def _triple_to_dict(triple: Triple) -> dict[str, Any]:
    """Serialize a Triple."""
    return asdict(triple)


def _dict_to_triple(d: dict[str, Any]) -> Triple:
    """Deserialize a Triple."""
    return Triple(
        subject=d["subject"],
        verb=d["verb"],
        object=d["object"],
        source=d["source"],
        bidirectional=d.get("bidirectional", False),
        metadata=d.get("metadata", {}),
    )
