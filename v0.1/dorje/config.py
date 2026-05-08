"""Configuration loading, saving, and validation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

_ENV_EMBEDDER_AUTH_KEY = "DORJE_EMBEDDER_AUTH_KEY"
_ENV_LLM_AUTH_KEY = "DORJE_LLM_AUTH_KEY"
_ENV_FILE_NAMES = (".env",)
_MAX_ENV_FILE_LINES = 500

_MAX_WORKERS_MULTIPLIER = 2
_MIN_WORKERS = 1
_DEFAULT_MAX_TOKENS = 8192
_DEFAULT_MIN_TOKENS_PER_CHUNK = 128
_DEFAULT_MAX_PARAGRAPHS_PER_CHUNK = 10
_DEFAULT_STRIDE_TOKENS = 256
_DEFAULT_BATCH_SIZE = 64
_DEFAULT_DIMENSION = 2048
_DEFAULT_TOP_K = 20
_DEFAULT_INDEX_DIR = ".dorje"
_CONFIG_FILENAME = "config.json"
_PACKS_FILENAME = "packs.json"
_GLOBAL_CONFIG_DIR = Path.home() / ".dorje"
_GLOBAL_CONFIG_FILE = _GLOBAL_CONFIG_DIR / _CONFIG_FILENAME


@dataclass(frozen=True, slots=True)
class EmbedderConfig:
    """Configuration for the embedding endpoint."""

    endpoint: str = ""
    model: str = ""
    auth_key: str | None = None
    dimension: int = 0
    batch_size: int = _DEFAULT_BATCH_SIZE

    def validate(self) -> None:
        """Validate embedder configuration."""
        assert self.endpoint, "embedder.endpoint must not be empty"
        assert self.model, "embedder.model must not be empty"
        assert self.dimension > 0, f"embedder.dimension must be > 0, got {self.dimension}"
        assert self.batch_size > 0, f"embedder.batch_size must be > 0, got {self.batch_size}"


@dataclass(frozen=True, slots=True)
class LLMConfig:
    """Configuration for the LLM endpoint (optional enrichment)."""

    endpoint: str = ""
    model: str = ""
    auth_key: str | None = None
    enabled: bool = False

    def validate(self) -> None:
        """Validate LLM configuration."""
        if self.enabled:
            assert self.endpoint, "llm.endpoint must not be empty when enabled"
            assert self.model, "llm.model must not be empty when enabled"


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    """Configuration for the chunking pipeline."""

    max_tokens: int = _DEFAULT_MAX_TOKENS
    min_tokens_per_chunk: int = _DEFAULT_MIN_TOKENS_PER_CHUNK
    max_paragraphs_per_chunk: int = _DEFAULT_MAX_PARAGRAPHS_PER_CHUNK
    stride_tokens: int = _DEFAULT_STRIDE_TOKENS

    def validate(self) -> None:
        """Validate chunking configuration."""
        assert self.max_tokens > 0, f"chunking.max_tokens must be > 0, got {self.max_tokens}"
        assert (
            self.min_tokens_per_chunk > 0
        ), f"chunking.min_tokens_per_chunk must be > 0, got {self.min_tokens_per_chunk}"
        assert (
            self.max_paragraphs_per_chunk > 0
        ), f"chunking.max_paragraphs_per_chunk must be > 0, got {self.max_paragraphs_per_chunk}"
        assert (
            self.stride_tokens > 0
        ), f"chunking.stride_tokens must be > 0, got {self.stride_tokens}"
        assert self.stride_tokens < self.max_tokens, (
            f"chunking.stride_tokens ({self.stride_tokens}) must be < "
            f"chunking.max_tokens ({self.max_tokens})"
        )


@dataclass(frozen=True, slots=True)
class SearchConfig:
    """Configuration for search behavior."""

    slab_size: int | None = None  # None = load all vectors at once
    top_k: int = _DEFAULT_TOP_K

    def validate(self) -> None:
        """Validate search configuration."""
        assert self.top_k > 0, f"search.top_k must be > 0, got {self.top_k}"
        if self.slab_size is not None:
            assert self.slab_size > 0, f"search.slab_size must be > 0, got {self.slab_size}"


@dataclass(frozen=True, slots=True)
class ConcurrencyConfig:
    """Configuration for worker pool sizing."""

    workers: int | None = None  # None = auto-detect

    def validate(self) -> None:
        """Validate concurrency configuration."""
        if self.workers is not None:
            assert self.workers > 0, f"concurrency.workers must be > 0, got {self.workers}"

    def effective_workers(self) -> int:
        """Return the actual worker count to use."""
        if self.workers is not None:
            return self.workers
        cpu_count = os.cpu_count() or 2
        return max(cpu_count - 2, _MIN_WORKERS) * _MAX_WORKERS_MULTIPLIER


@dataclass(frozen=True, slots=True)
class Config:
    """Top-level Dorje configuration."""

    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    concurrency: ConcurrencyConfig = field(default_factory=ConcurrencyConfig)

    def validate(self) -> None:
        """Validate all configuration sections."""
        self.embedder.validate()
        self.llm.validate()
        self.chunking.validate()
        self.search.validate()
        self.concurrency.validate()


def _dict_to_embedder(d: dict[str, object]) -> EmbedderConfig:
    """Parse embedder config from dict. Unknown keys are ignored."""
    return EmbedderConfig(
        endpoint=str(d.get("endpoint", EmbedderConfig.endpoint)),
        model=str(d.get("model", EmbedderConfig.model)),
        auth_key=str(d["auth_key"]) if d.get("auth_key") else None,
        dimension=int(d.get("dimension", EmbedderConfig.dimension)),  # type: ignore[arg-type]
        batch_size=int(d.get("batch_size", EmbedderConfig.batch_size)),  # type: ignore[arg-type]
    )


def _dict_to_llm(d: dict[str, object]) -> LLMConfig:
    """Parse LLM config from dict."""
    return LLMConfig(
        endpoint=str(d.get("endpoint", LLMConfig.endpoint)),
        model=str(d.get("model", LLMConfig.model)),
        auth_key=str(d["auth_key"]) if d.get("auth_key") else None,
        enabled=bool(d.get("enabled", LLMConfig.enabled)),
    )


def _dict_to_chunking(d: dict[str, object]) -> ChunkingConfig:
    """Parse chunking config from dict."""
    return ChunkingConfig(
        max_tokens=int(d.get("max_tokens", ChunkingConfig.max_tokens)),  # type: ignore[arg-type]
        min_tokens_per_chunk=int(
            d.get("min_tokens_per_chunk", ChunkingConfig.min_tokens_per_chunk)  # type: ignore[arg-type]
        ),
        max_paragraphs_per_chunk=int(
            d.get("max_paragraphs_per_chunk", ChunkingConfig.max_paragraphs_per_chunk)  # type: ignore[arg-type]
        ),
        stride_tokens=int(d.get("stride_tokens", ChunkingConfig.stride_tokens)),  # type: ignore[arg-type]
    )


def _dict_to_search(d: dict[str, object]) -> SearchConfig:
    """Parse search config from dict."""
    slab_raw = d.get("slab_size")
    slab_size = int(slab_raw) if slab_raw is not None else None  # type: ignore[arg-type]
    return SearchConfig(
        slab_size=slab_size,
        top_k=int(d.get("top_k", SearchConfig.top_k)),  # type: ignore[arg-type]
    )


def _dict_to_concurrency(d: dict[str, object]) -> ConcurrencyConfig:
    """Parse concurrency config from dict."""
    workers_raw = d.get("workers")
    workers = int(workers_raw) if workers_raw is not None else None  # type: ignore[arg-type]
    return ConcurrencyConfig(workers=workers)


def _load_env_file() -> dict[str, str]:
    """Load key=value pairs from .env file in ~/.dorje/ directory.

    Returns a dict of env vars. Does not mutate os.environ.
    Ignores comments (#) and blank lines.
    """
    env_vars: dict[str, str] = {}

    for name in _ENV_FILE_NAMES:
        env_path = _GLOBAL_CONFIG_DIR / name
        if not env_path.is_file():
            continue

        raw = env_path.read_text(encoding="utf-8")
        lines = raw.splitlines()
        assert len(lines) <= _MAX_ENV_FILE_LINES, (
            f".env file exceeds {_MAX_ENV_FILE_LINES} lines"
        )

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            eq_idx = stripped.find("=")
            if eq_idx <= 0:
                continue
            key = stripped[:eq_idx].strip()
            value = stripped[eq_idx + 1:].strip()
            # Strip surrounding quotes if present
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            env_vars[key] = value

    return env_vars


def _resolve_auth_key(env_var_name: str, env_file_vars: dict[str, str]) -> str | None:
    """Resolve an auth key: os.environ takes priority, then .env file."""
    value = os.environ.get(env_var_name)
    if value:
        return value
    value = env_file_vars.get(env_var_name)
    if value:
        return value
    return None


def load_config(index_path: Path | None = None) -> Config:
    """Load config from ~/.dorje/config.json. Fails if file doesn't exist.

    Auth keys are resolved from environment variables (DORJE_EMBEDDER_AUTH_KEY,
    DORJE_LLM_AUTH_KEY), not from config.json. Place them in ~/.dorje/.env
    or export them in your shell.

    The config is always global at ~/.dorje/config.json.
    The index_path argument is ignored — kept for API compatibility.
    """
    config_file = _GLOBAL_CONFIG_FILE

    assert config_file.exists(), (
        f"Config file not found: {config_file}\n"
        f"Run 'dorje --generate-config' first."
    )

    raw = config_file.read_text(encoding="utf-8")
    assert raw, f"Config file is empty: {config_file}"

    data = json.loads(raw)
    assert isinstance(data, dict), f"Config must be a JSON object, got {type(data).__name__}"

    # Load auth keys from env / .env file
    env_file_vars = _load_env_file()
    embedder_auth = _resolve_auth_key(_ENV_EMBEDDER_AUTH_KEY, env_file_vars)
    llm_auth = _resolve_auth_key(_ENV_LLM_AUTH_KEY, env_file_vars)

    # Apply model pack if specified
    pack_name = data.get("pack")
    pack_data: dict[str, object] = {}
    if pack_name:
        pack_data = _load_pack(str(pack_name))

    # Merge: pack provides base, config.json overrides
    embedder_raw = data.get("embedder", {})
    llm_raw = data.get("llm", {})
    pack_embedder = pack_data.get("embedder", {})
    pack_llm = pack_data.get("llm", {})

    assert isinstance(pack_embedder, dict), "pack embedder must be a dict"
    assert isinstance(pack_llm, dict), "pack llm must be a dict"
    assert isinstance(embedder_raw, dict), "embedder config must be a dict"
    assert isinstance(llm_raw, dict), "llm config must be a dict"

    merged_embedder = {**pack_embedder, **{k: v for k, v in embedder_raw.items() if v}}
    merged_llm = {**pack_llm, **{k: v for k, v in llm_raw.items() if v}}

    # Inject resolved auth keys
    merged_embedder["auth_key"] = embedder_auth
    merged_llm["auth_key"] = llm_auth

    config = Config(
        embedder=_dict_to_embedder(merged_embedder),
        llm=_dict_to_llm(merged_llm),
        chunking=_dict_to_chunking(data.get("chunking", {})),
        search=_dict_to_search(data.get("search", {})),
        concurrency=_dict_to_concurrency(data.get("concurrency", {})),
    )
    config.validate()
    return config


def generate_config(force: bool = False) -> Path:
    """Generate a default config.json at ~/.dorje/config.json.

    Also generates a .env template and packs.json if they don't exist.

    Args:
        force: If True, overwrite existing config. If False, fail if config exists.

    Returns:
        Path to the generated config file.
    """
    config_file = _GLOBAL_CONFIG_FILE

    if config_file.exists() and not force:
        assert False, (
            f"Config already exists at {config_file}. "
            f"Use --generate-config-force-overwrite to replace it."
        )

    _GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    config = Config()
    save_config(config)

    # Generate .env template if missing
    env_file = _GLOBAL_CONFIG_DIR / ".env"
    if not env_file.exists():
        env_file.write_text(
            "# Dorje auth keys — do NOT commit this file\n"
            "DORJE_EMBEDDER_AUTH_KEY=\n"
            "DORJE_LLM_AUTH_KEY=\n",
            encoding="utf-8",
        )

    # Generate packs.json if missing
    packs_file = _GLOBAL_CONFIG_DIR / _PACKS_FILENAME
    if not packs_file.exists():
        _generate_default_packs(packs_file)

    return config_file


def save_config(config: Config, pack_name: str | None = None) -> None:
    """Save config to ~/.dorje/config.json.

    Auth keys are NOT written — they belong in ~/.dorje/.env.
    """
    config_file = _GLOBAL_CONFIG_FILE
    _GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    data: dict[str, object] = {}

    if pack_name:
        data["pack"] = pack_name

    data["embedder"] = {
        "endpoint": config.embedder.endpoint,
        "model": config.embedder.model,
        "dimension": config.embedder.dimension,
        "batch_size": config.embedder.batch_size,
    }
    data["llm"] = {
        "endpoint": config.llm.endpoint,
        "model": config.llm.model,
        "enabled": config.llm.enabled,
    }
    data["chunking"] = {
        "max_tokens": config.chunking.max_tokens,
        "min_tokens_per_chunk": config.chunking.min_tokens_per_chunk,
        "max_paragraphs_per_chunk": config.chunking.max_paragraphs_per_chunk,
        "stride_tokens": config.chunking.stride_tokens,
    }
    data["search"] = {
        "slab_size": config.search.slab_size,
        "top_k": config.search.top_k,
    }
    data["concurrency"] = {
        "workers": config.concurrency.workers,
    }

    config_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


_PACKS_FILE = _GLOBAL_CONFIG_DIR / _PACKS_FILENAME
_MAX_PACKS = 50


def _load_pack(pack_name: str) -> dict[str, object]:
    """Load a named model pack from ~/.dorje/packs.json.

    Returns the pack's dict with 'embedder' and 'llm' keys.
    """
    assert pack_name, "pack name must not be empty"

    packs_file = _PACKS_FILE
    assert packs_file.exists(), (
        f"Packs file not found: {packs_file}\n"
        f"Run 'dorje --generate-config' to create it."
    )

    raw = packs_file.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert isinstance(data, dict), "packs.json must be a JSON object"
    assert len(data) <= _MAX_PACKS, f"packs.json exceeds {_MAX_PACKS} packs"

    assert pack_name in data, (
        f"Unknown pack '{pack_name}'. "
        f"Available: {', '.join(sorted(data.keys()))}"
    )

    pack = data[pack_name]
    assert isinstance(pack, dict), f"pack '{pack_name}' must be a JSON object"
    return pack


def list_packs() -> dict[str, dict[str, object]]:
    """List all available model packs from ~/.dorje/packs.json."""
    packs_file = _PACKS_FILE
    if not packs_file.exists():
        return {}

    raw = packs_file.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert isinstance(data, dict), "packs.json must be a JSON object"
    return data


def set_pack(pack_name: str) -> None:
    """Set the active model pack in config.json.

    Loads the pack to validate it exists, then updates config.json
    with the pack name. Existing overrides in config.json are preserved.
    """
    # Validate the pack exists
    pack_data = _load_pack(pack_name)

    config_file = _GLOBAL_CONFIG_FILE
    assert config_file.exists(), (
        f"Config file not found: {config_file}\n"
        f"Run 'dorje --generate-config' first."
    )

    raw = config_file.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert isinstance(data, dict), "config.json must be a JSON object"

    data["pack"] = pack_name
    config_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _generate_default_packs(packs_file: Path) -> None:
    """Generate a template packs.json with common provider configurations."""
    packs = {
        "openai": {
            "embedder": {
                "endpoint": "https://api.openai.com/v1",
                "model": "text-embedding-3-small",
                "dimension": 1536,
            },
            "llm": {
                "endpoint": "https://api.openai.com/v1",
                "model": "gpt-4.1-mini",
                "enabled": True,
            },
        },
        "groq": {
            "embedder": {
                "endpoint": "",
                "model": "",
                "dimension": 0,
            },
            "llm": {
                "endpoint": "https://api.groq.com/openai/v1",
                "model": "llama-3.3-70b-versatile",
                "enabled": True,
            },
        },
        "local": {
            "embedder": {
                "endpoint": "",
                "model": "",
                "dimension": 0,
            },
            "llm": {
                "endpoint": "",
                "model": "",
                "enabled": False,
            },
        },
    }
    packs_file.write_text(json.dumps(packs, indent=2) + "\n", encoding="utf-8")


def find_index_path(start: Path) -> Path:
    """Find the nearest .dorje directory walking up from start."""
    assert start.is_absolute(), f"start must be an absolute path, got {start}"

    current = start
    max_depth = 100  # Safety bound
    for _ in range(max_depth):
        candidate = current / _DEFAULT_INDEX_DIR
        if candidate.is_dir():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    return start / _DEFAULT_INDEX_DIR
