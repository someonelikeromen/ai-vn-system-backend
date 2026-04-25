"""SQLite 完整 Schema — 初始化脚本"""
from __future__ import annotations

import aiosqlite
from pathlib import Path
from loguru import logger


# ── Schema DDL（按依赖顺序） ──────────────────────────────────────────────────
SCHEMA_SQL = """
-- WAL 模式与并发安全（必须在每个连接初始化时执行）
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA cache_size   = -64000;

-- ═══════════════════════════════════════════════════════════════════════
-- 1. 项目与小说管理
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS novels (
    novel_id          TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    ip_type           TEXT NOT NULL DEFAULT 'original',   -- 'original' | 'fanfiction'
    world_type        TEXT NOT NULL DEFAULT 'single_world', -- 'single_world' | 'multi_world'
    current_world_key TEXT,
    default_style_stack JSON DEFAULT '[]',
    attr_schema_id    TEXT DEFAULT 'standard_10d',        -- 属性体系ID
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    archived          INTEGER DEFAULT 0                   -- BOOLEAN
);

CREATE TABLE IF NOT EXISTS protagonist_state (
    novel_id            TEXT PRIMARY KEY REFERENCES novels(novel_id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    points              INTEGER DEFAULT 0,
    tier                INTEGER DEFAULT 0,
    tier_sub            TEXT DEFAULT 'M',
    attributes          JSON DEFAULT '{"STR":1.0,"DUR":1.0,"VIT":1.0,"REC":1.0,"AGI":1.0,"REF":1.0,"PER":1.0,"MEN":1.0,"SOL":1.0,"CHA":1.0}',
    energy_pools        JSON DEFAULT '{}',
    status_effects      JSON DEFAULT '[]',
    world_key           TEXT,
    world_locked_until  TEXT,
    psyche_model_json   JSON,
    knowledge_scope     JSON DEFAULT '[]',
    -- AI 生成的角色档案字段
    gender              TEXT DEFAULT '',
    age                 TEXT DEFAULT '',
    identity            TEXT DEFAULT '',
    height              TEXT DEFAULT '',
    weight              TEXT DEFAULT '',
    alignment           TEXT DEFAULT '',
    appearance          TEXT DEFAULT '',
    clothing            TEXT DEFAULT '',
    background          TEXT DEFAULT '',
    personality         JSON DEFAULT '[]',
    flaws               JSON DEFAULT '[]',
    desires             JSON DEFAULT '[]',
    fears               JSON DEFAULT '[]',
    quirks              JSON DEFAULT '[]',
    traits              JSON DEFAULT '[]',
    updated_at          TEXT
);

CREATE TABLE IF NOT EXISTS medals (
    novel_id    TEXT REFERENCES novels(novel_id) ON DELETE CASCADE,
    stars       INTEGER,
    count       INTEGER DEFAULT 0,
    PRIMARY KEY (novel_id, stars)
);

-- ═══════════════════════════════════════════════════════════════════════
-- 2. 兑换与物品系统
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS item_catalog (
    item_key          TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    source_world      TEXT,
    item_type         TEXT NOT NULL,
    base_tier         INTEGER DEFAULT 0,
    base_tier_sub     TEXT DEFAULT 'M',
    base_price        INTEGER DEFAULT 0,
    required_medals   JSON DEFAULT '[]',
    growth_difficulty TEXT DEFAULT 'N/A',
    target_tier       INTEGER,
    target_tier_sub   TEXT,
    payload_template  JSON NOT NULL DEFAULT '{}',
    eval_report       TEXT,
    is_limited        INTEGER DEFAULT 0,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS owned_items (
    id                TEXT PRIMARY KEY,
    novel_id          TEXT NOT NULL REFERENCES novels(novel_id) ON DELETE CASCADE,
    item_key          TEXT NOT NULL,
    item_name         TEXT NOT NULL DEFAULT '',
    item_type         TEXT NOT NULL,
    source_world      TEXT DEFAULT '',
    tier              INTEGER DEFAULT 0,
    tier_sub          TEXT DEFAULT 'M',
    final_tier        INTEGER DEFAULT 0,
    final_sub         TEXT DEFAULT 'M',
    price_paid        INTEGER DEFAULT 0,
    acquired_at_chapter TEXT,
    description       TEXT DEFAULT '',
    is_equipped       INTEGER DEFAULT 1,
    can_unequip       INTEGER DEFAULT 1,
    payload           JSON NOT NULL DEFAULT '{}',
    is_active         INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS exchange_log (
    id                TEXT PRIMARY KEY,
    novel_id          TEXT NOT NULL REFERENCES novels(novel_id),
    chapter_id        TEXT,
    action            TEXT NOT NULL,
    item_key          TEXT,
    points_delta      INTEGER DEFAULT 0,
    medals_delta      JSON DEFAULT '[]',
    eval_token_hash   TEXT,
    growth_snapshot   JSON,
    timestamp         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rollback_manifests (
    id            TEXT PRIMARY KEY,
    novel_id      TEXT NOT NULL REFERENCES novels(novel_id) ON DELETE CASCADE,
    chapter_id    TEXT NOT NULL,
    instructions  JSON NOT NULL DEFAULT '[]',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rollback_chapter ON rollback_manifests(novel_id, chapter_id);

-- ═══════════════════════════════════════════════════════════════════════
-- 3. 通用成长系统（替代旧 proficiency_xp）
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS growth_records (
    id            TEXT PRIMARY KEY,
    novel_id      TEXT NOT NULL REFERENCES novels(novel_id) ON DELETE CASCADE,
    owned_id      TEXT NOT NULL REFERENCES owned_items(id) ON DELETE CASCADE,
    item_type     TEXT NOT NULL,
    growth_key    TEXT NOT NULL,
    sub_key       TEXT,
    current_xp    INTEGER DEFAULT 0,
    level_index   INTEGER DEFAULT 0,
    use_count     INTEGER DEFAULT 0,
    last_event_at TEXT,
    version       INTEGER DEFAULT 0,
    UNIQUE(novel_id, owned_id, growth_key, sub_key)
);

CREATE TABLE IF NOT EXISTS growth_event_records (
    event_id    TEXT PRIMARY KEY,
    novel_id    TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    chapter_id  TEXT,
    xp_grants   JSON NOT NULL DEFAULT '[]',
    settled_at  TEXT NOT NULL
);

-- ═══════════════════════════════════════════════════════════════════════
-- 4. Decay System（反刷积分衰减）
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS kill_records (
    novel_id            TEXT NOT NULL REFERENCES novels(novel_id) ON DELETE CASCADE,
    enemy_category      TEXT NOT NULL,
    enemy_tier          INTEGER NOT NULL,
    enemy_tier_sub      TEXT NOT NULL,
    kill_count          INTEGER DEFAULT 0,
    defeat_count        INTEGER DEFAULT 0,
    points_decay_stage  INTEGER DEFAULT 0,
    medal_decay_stage   INTEGER DEFAULT 0,
    PRIMARY KEY (novel_id, enemy_category)
);

-- ═══════════════════════════════════════════════════════════════════════
-- 5. 三套存储同步状态
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS node_sync_status (
    novel_id        TEXT NOT NULL,
    node_id         TEXT NOT NULL,
    sqlite_written  INTEGER DEFAULT 0,
    graph_written   INTEGER DEFAULT 0,
    vector_written  INTEGER DEFAULT 0,
    retry_count     INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    synced_at       TEXT,
    PRIMARY KEY (novel_id, node_id)
);

-- ═══════════════════════════════════════════════════════════════════════
-- 6. 章节与叙事系统
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS chapters (
    id              TEXT PRIMARY KEY,
    novel_id        TEXT NOT NULL REFERENCES novels(novel_id) ON DELETE CASCADE,
    chapter_num     INTEGER NOT NULL,
    title           TEXT,
    world_key       TEXT,
    arc_label       TEXT DEFAULT '',
    raw_content     TEXT DEFAULT '',
    summary         TEXT DEFAULT '',
    synopsis_node_id TEXT,
    created_at      TEXT NOT NULL,
    finalized       INTEGER DEFAULT 0,
    UNIQUE(novel_id, chapter_num)
);

CREATE TABLE IF NOT EXISTS narrative_hooks (
    id                    TEXT PRIMARY KEY,
    novel_id              TEXT NOT NULL REFERENCES novels(novel_id) ON DELETE CASCADE,
    description           TEXT NOT NULL,
    seeded_at_chapter     TEXT,
    status                TEXT DEFAULT 'active',
    resolved_at_chapter   TEXT,
    urgency               TEXT DEFAULT 'low',
    related_node_ids      JSON DEFAULT '[]',
    graph_node_id         TEXT
);

CREATE TABLE IF NOT EXISTS achievements (
    id              TEXT PRIMARY KEY,
    novel_id        TEXT NOT NULL REFERENCES novels(novel_id) ON DELETE CASCADE,
    achievement_key TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    unlocked_at     TEXT NOT NULL,
    chapter_id      TEXT,
    reward_type     TEXT,
    reward_value    JSON,
    UNIQUE(novel_id, achievement_key)
);

-- ═══════════════════════════════════════════════════════════════════════
-- 7. 世界管理
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS world_archives (
    id              TEXT PRIMARY KEY,
    novel_id        TEXT NOT NULL REFERENCES novels(novel_id) ON DELETE CASCADE,
    world_key       TEXT NOT NULL,
    world_name      TEXT NOT NULL DEFAULT '',
    current_snapshot JSON DEFAULT '{}',
    identity        JSON,
    time_flow_ratio TEXT DEFAULT '1:1',     -- 格式："主世界:目标世界"，如"2:1"
    time_flow_type  TEXT DEFAULT 'ratio',   -- ratio|fixed_interval|frozen|hybrid
    peak_tier       INTEGER DEFAULT 0,      -- 该世界最强存在的星级（WorldTraverse定价用）
    peak_tier_sub   TEXT DEFAULT 'M',       -- 对应子档
    catalog_json    TEXT,
    entered_at      TEXT,
    last_active_at  TEXT,
    UNIQUE(novel_id, world_key)
);


-- ═══════════════════════════════════════════════════════════════════════
-- 8. NPC 档案
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS npc_profiles (
    id              TEXT PRIMARY KEY,
    novel_id        TEXT NOT NULL REFERENCES novels(novel_id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    world_key       TEXT,
    npc_type        TEXT DEFAULT 'human',    -- human|monster|spirit|mech|companion
    trait_lock      JSON DEFAULT '[]',       -- 稳定特质（漂移检测用）
    knowledge_scope JSON DEFAULT '[]',       -- 该NPC的已知信息边界
    capability_cap  JSON DEFAULT '{}',       -- 能力上限（感知/战力等）
    psyche_model    JSON,
    -- Companion 专用字段（npc_type='companion' 时有效）
    initial_affinity INTEGER DEFAULT 50,    -- 好感度 0-100
    loyalty_type    TEXT DEFAULT '中性',    -- 忠诚类型：无条件/利益/情感/理念/中性
    companion_slot  INTEGER,                -- 同伴栏槽位（1-起）
    graph_node_id   TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(novel_id, name)
);


-- ═══════════════════════════════════════════════════════════════════════
-- 9. 对话历史
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    novel_id        TEXT NOT NULL REFERENCES novels(novel_id) ON DELETE CASCADE,
    role            TEXT NOT NULL,           -- 'user' | 'assistant'
    raw_content     TEXT NOT NULL DEFAULT '',
    display_content TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    chapter_id      TEXT,
    message_order   INTEGER NOT NULL,
    UNIQUE(novel_id, message_order)
);
CREATE INDEX IF NOT EXISTS idx_messages_novel ON messages(novel_id, message_order);

-- ═══════════════════════════════════════════════════════════════════════
-- 10. 回合快照（用于最近3次对话回退）
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS turn_snapshots (
    id                  TEXT PRIMARY KEY,
    novel_id            TEXT NOT NULL REFERENCES novels(novel_id) ON DELETE CASCADE,
    user_message_order  INTEGER NOT NULL,   -- 对应 user 消息的 message_order（该轮起点）
    protagonist_json    TEXT NOT NULL,      -- 回合开始前的完整 protagonist_state JSON
    grants_json         TEXT NOT NULL DEFAULT '[]', -- 本轮产生的 grants 列表
    medals_json         TEXT NOT NULL DEFAULT '[]', -- 快照时的凭证状态 [{stars, count}]
    growth_json         TEXT NOT NULL DEFAULT '[]', -- 快照时的成长记录 [{owned_id, growth_key, sub_key, current_xp, level_index, version, use_count}]
    created_at          TEXT NOT NULL,
    UNIQUE(novel_id, user_message_order)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_novel ON turn_snapshots(novel_id, created_at DESC);
"""


async def init_db(db_path: str) -> None:
    """初始化数据库（建表 + WAL 模式设置）"""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(str(path)) as db:
        # 逐条执行 SCHEMA（aiosqlite 不支持 executescript 的完整 WAL 设置）
        for stmt in _split_statements(SCHEMA_SQL):
            if stmt.strip():
                await db.execute(stmt)
        await db.commit()

    logger.info(f"数据库初始化完成: {path}")


def _split_statements(sql: str) -> list[str]:
    """将多条 SQL 以分号分割（忽略注释行）"""
    stmts: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        # 跳过纯注释行
        if stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmts.append("\n".join(buf))
            buf = []
    if buf:
        stmts.append("\n".join(buf))
    return stmts
