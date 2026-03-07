"""
Phase 2 legacy integration loader.

Loads selected legacy Cogs into the modern TENBOT runtime with:
- Guarded dynamic imports (avoid module name collisions)
- Schema bootstrap for legacy-only tables/columns
- Per-module feature flags
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import util as importlib_util
from pathlib import Path
from typing import Any, Dict

import config


@dataclass(frozen=True)
class LegacyModuleSpec:
    key: str
    file_name: str
    system_class: str
    cog_class: str


LEGACY_PHASE2_MODULES = (
    LegacyModuleSpec(
        key="captcha_verification",
        file_name="captcha_verification.py",
        system_class="CaptchaVerification",
        cog_class="CaptchaCommands",
    ),
    LegacyModuleSpec(
        key="dm_protection",
        file_name="dm_protection.py",
        system_class="DMProtection",
        cog_class="DMProtectionCommands",
    ),
    LegacyModuleSpec(
        key="threat_intelligence",
        file_name="threat_intelligence.py",
        system_class="ThreatIntelligence",
        cog_class="ThreatIntelCommands",
    ),
    LegacyModuleSpec(
        key="advanced_networking",
        file_name="advanced_networking.py",
        system_class="AdvancedNetworking",
        cog_class="AdvancedNetworkingCommands",
    ),
    LegacyModuleSpec(
        key="event_manager",
        file_name="event_manager.py",
        system_class="EventManager",
        cog_class="EventCommands",
    ),
    LegacyModuleSpec(
        key="topic_detection",
        file_name="topic_detection.py",
        system_class="TopicDetection",
        cog_class="TopicDetectionCommands",
    ),
    LegacyModuleSpec(
        key="humanity_fingerprinting",
        file_name="humanity_fingerprinting.py",
        system_class="HumanityFingerprinting",
        cog_class="HumanityCommands",
    ),
)


LEGACY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS captcha_verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    verified_at TEXT,
    status TEXT DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_captcha_user ON captcha_verifications(user_id, guild_id);
CREATE INDEX IF NOT EXISTS idx_captcha_status ON captcha_verifications(status);

CREATE TABLE IF NOT EXISTS dm_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id TEXT NOT NULL,
    reported_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    evidence TEXT,
    status TEXT DEFAULT 'pending',
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dm_reports_status ON dm_reports(status);
CREATE INDEX IF NOT EXISTS idx_dm_reports_reported ON dm_reports(reported_id);

CREATE TABLE IF NOT EXISTS global_threat_intel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    reason TEXT,
    source TEXT,
    severity INTEGER DEFAULT 1,
    added_at TEXT NOT NULL,
    UNIQUE(target_id, target_type)
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    link TEXT,
    category TEXT,
    image_url TEXT,
    upvotes INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    active INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_projects_category ON projects(category);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);

CREATE TABLE IF NOT EXISTS project_votes (
    project_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    vote_type INTEGER NOT NULL,
    UNIQUE(project_id, user_id)
);

CREATE TABLE IF NOT EXISTS coffee_preferences (
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    interests TEXT,
    skills TEXT,
    looking_for TEXT,
    opt_in INTEGER DEFAULT 0,
    UNIQUE(user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS coffee_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user1_id TEXT NOT NULL,
    user2_id TEXT NOT NULL,
    week_of TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    channel_id TEXT,
    created_at TEXT NOT NULL,
    user1_rating INTEGER,
    user2_rating INTEGER,
    UNIQUE(user1_id, week_of),
    UNIQUE(user2_id, week_of)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    creator_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    event_time TEXT NOT NULL,
    event_type TEXT DEFAULT 'general',
    created_at TEXT NOT NULL,
    status TEXT DEFAULT 'scheduled',
    reminder_sent INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS event_rsvps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    rsvp_time TEXT NOT NULL,
    UNIQUE(event_id, user_id)
);
"""


def _is_enabled(module_key: str) -> bool:
    module_toggles = getattr(config, "LEGACY_PHASE2_MODULES", {})
    return bool(module_toggles.get(module_key, True))


def _load_module_from_file(module_key: str, file_path: Path) -> Any:
    module_name = f"tenbot_legacy_{module_key}"
    spec = importlib_util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {file_path}")

    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _ensure_column(db_connection: Any, table_name: str, column_name: str, definition: str) -> None:
    cursor = await db_connection.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1] for row in await cursor.fetchall()}

    if column_name not in columns:
        await db_connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )


async def ensure_phase2_legacy_schema(db_connection: Any) -> None:
    """
    Ensure legacy phase-2 tables and columns exist in the current database.
    """
    await db_connection.executescript(LEGACY_SCHEMA_SQL)
    await _ensure_column(db_connection, "users", "humanity_score", "INTEGER DEFAULT 100")
    await _ensure_column(db_connection, "users", "typing_timestamp", "TEXT")
    await db_connection.commit()


async def load_phase2_legacy_modules(bot: Any, db_connection: Any) -> Dict[str, Any]:
    """
    Load selected legacy modules as Cogs into the running bot.

    Returns:
        Dict of {module_key: system_instance}
    """
    if not getattr(config, "LEGACY_PHASE2_ENABLED", False):
        print("  - Legacy phase 2 is disabled by config")
        return {}

    await ensure_phase2_legacy_schema(db_connection)

    loaded: Dict[str, Any] = {}
    base_dir = Path(__file__).resolve().parent

    for module_spec in LEGACY_PHASE2_MODULES:
        if not _is_enabled(module_spec.key):
            print(f"  - Skipping legacy module: {module_spec.key} (disabled)")
            continue

        module_path = base_dir / module_spec.file_name
        if not module_path.exists():
            print(f"  - Skipping legacy module: {module_spec.key} (file missing)")
            continue

        try:
            module = _load_module_from_file(module_spec.key, module_path)
            system_cls = getattr(module, module_spec.system_class)
            cog_cls = getattr(module, module_spec.cog_class)

            system_instance = system_cls(bot, db_connection)
            cog_instance = cog_cls(bot, system_instance)
            await bot.add_cog(cog_instance)

            loaded[module_spec.key] = system_instance
            print(f"  - Loaded legacy module: {module_spec.key}")
        except Exception as exc:
            print(f"  - Failed to load legacy module {module_spec.key}: {exc}")

    return loaded

