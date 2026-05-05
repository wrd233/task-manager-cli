import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


APP_DIR_ENV = "TM_APP_DIR"
GRAPH_ENV = "TM_LOGSEQ_GRAPH"
DB_ENV = "TM_DATABASE_PATH"
PROVIDER_ENV = "TM_PROVIDER"
PROVIDER_BASE_URL_ENV = "TM_PROVIDER_BASE_URL"
PROVIDER_API_KEY_ENV = "TM_PROVIDER_API_KEY"
PROVIDER_MODEL_ENV = "TM_PROVIDER_MODEL"


def default_app_dir() -> Path:
    return Path(os.environ.get(APP_DIR_ENV, Path.home() / ".task-manager-cli")).expanduser()


def default_config_path() -> Path:
    return default_app_dir() / "config.json"


def default_logseq_graph() -> Optional[str]:
    env = os.environ.get(GRAPH_ENV)
    if env:
        return str(Path(env).expanduser())
    candidate = Path("/Users/wangrundong/logseq/Logseq_File")
    return str(candidate) if candidate.exists() else None


def load_local_env(path: Optional[Path] = None) -> Dict[str, str]:
    search = []
    if path:
        search.append(Path(path).expanduser())
    search.extend([Path.cwd() / ".env.local", Path.cwd() / ".env"])
    data: Dict[str, str] = {}
    for candidate in search:
        if not candidate.exists():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip().strip("\"'")
    return data


def _env_or_local(key: str, local_env: Dict[str, str], default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(key) or local_env.get(key) or default


@dataclass
class Settings:
    app_dir: Path = field(default_factory=default_app_dir)
    database_path: Path = field(default_factory=lambda: default_app_dir() / "task_manager.sqlite3")
    logseq_graph_path: Optional[Path] = None
    sensitive_patterns: List[str] = field(default_factory=list)
    ignored_embed_uuids: List[str] = field(default_factory=list)
    default_redact: bool = True
    write_mode: str = "disabled"
    write_backup_dir: Optional[Path] = None
    write_require_confirm: bool = True
    allowed_write_operations: List[str] = field(default_factory=lambda: ["append_child_block", "append_page_section", "create_page"])
    provider_name: str = "mock"
    provider_base_url: Optional[str] = None
    provider_api_key: Optional[str] = None
    provider_model: Optional[str] = None
    provider_timeout: int = 30
    provider_max_tokens: int = 1200
    provider_prompt_version: str = "clarify-v1"

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Settings":
        path = Path(config_path or default_config_path()).expanduser()
        data = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        local_env = load_local_env()
        app_dir = Path(data.get("app_dir") or default_app_dir()).expanduser()
        db_path = Path(os.environ.get(DB_ENV) or data.get("database_path") or app_dir / "task_manager.sqlite3").expanduser()
        graph = os.environ.get(GRAPH_ENV) or data.get("logseq_graph_path") or default_logseq_graph()
        return cls(
            app_dir=app_dir,
            database_path=db_path,
            logseq_graph_path=Path(graph).expanduser() if graph else None,
            sensitive_patterns=list(data.get("sensitive_patterns", [])),
            ignored_embed_uuids=list(data.get("ignored_embed_uuids", [])),
            default_redact=bool(data.get("default_redact", True)),
            write_mode=data.get("write_mode", "disabled"),
            write_backup_dir=Path(data["write_backup_dir"]).expanduser() if data.get("write_backup_dir") else app_dir / "backups",
            write_require_confirm=bool(data.get("write_require_confirm", True)),
            allowed_write_operations=list(data.get("allowed_write_operations", ["append_child_block", "append_page_section", "create_page"])),
            provider_name=str(_env_or_local(PROVIDER_ENV, local_env, data.get("provider_name") or "mock")),
            provider_base_url=_env_or_local(PROVIDER_BASE_URL_ENV, local_env, data.get("provider_base_url")),
            provider_api_key=_env_or_local(PROVIDER_API_KEY_ENV, local_env, data.get("provider_api_key")),
            provider_model=_env_or_local(PROVIDER_MODEL_ENV, local_env, data.get("provider_model")),
            provider_timeout=int(data.get("provider_timeout", 30)),
            provider_max_tokens=int(data.get("provider_max_tokens", 1200)),
            provider_prompt_version=str(data.get("provider_prompt_version", "clarify-v1")),
        )

    def save(self, config_path: Optional[Path] = None) -> Path:
        self.app_dir.mkdir(parents=True, exist_ok=True)
        path = Path(config_path or default_config_path()).expanduser()
        data = {
            "app_dir": str(self.app_dir),
            "database_path": str(self.database_path),
            "logseq_graph_path": str(self.logseq_graph_path) if self.logseq_graph_path else None,
            "sensitive_patterns": self.sensitive_patterns,
            "ignored_embed_uuids": self.ignored_embed_uuids,
            "default_redact": self.default_redact,
            "write_mode": self.write_mode,
            "write_backup_dir": str(self.write_backup_dir) if self.write_backup_dir else None,
            "write_require_confirm": self.write_require_confirm,
            "allowed_write_operations": self.allowed_write_operations,
            "provider_name": self.provider_name,
            "provider_base_url": self.provider_base_url,
            "provider_model": self.provider_model,
            "provider_timeout": self.provider_timeout,
            "provider_max_tokens": self.provider_max_tokens,
            "provider_prompt_version": self.provider_prompt_version,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def init_settings(graph_path: Optional[str] = None, database_path: Optional[str] = None) -> Settings:
    settings = Settings.load()
    if graph_path:
        settings.logseq_graph_path = Path(graph_path).expanduser()
    if database_path:
        settings.database_path = Path(database_path).expanduser()
    settings.app_dir.mkdir(parents=True, exist_ok=True)
    settings.save()
    return settings
