"""
Database Schema Updates for Advanced Features
Adds tables for spam detection, image detection, gamification, case management, events, and CAPTCHA
"""

SCHEMA_UPDATES = """
-- Spam Detection Tables
CREATE TABLE IF NOT EXISTS spam_violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    violation_type TEXT NOT NULL,
    severity INTEGER NOT NULL,
    violation_count INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    channel_id INTEGER,
    message_content TEXT,
    active INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_spam_violations_user ON spam_violations(user_id, guild_id);
CREATE INDEX IF NOT EXISTS idx_spam_violations_timestamp ON spam_violations(timestamp);

-- Image Detection Tables
CREATE TABLE IF NOT EXISTS image_hashes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_value TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    attachment_url TEXT
);

CREATE INDEX IF NOT EXISTS idx_image_hashes_hash ON image_hashes(hash_value);
CREATE INDEX IF NOT EXISTS idx_image_hashes_user ON image_hashes(user_id);

CREATE TABLE IF NOT EXISTS image_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_value TEXT NOT NULL,
    reporter_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS image_blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_value TEXT NOT NULL UNIQUE,
    guild_id INTEGER NOT NULL,
    reason TEXT,
    blacklisted_at TEXT NOT NULL,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS image_whitelist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_value TEXT NOT NULL UNIQUE,
    guild_id INTEGER NOT NULL,
    whitelisted_at TEXT NOT NULL,
    active INTEGER DEFAULT 1
);

-- Gamification Tables (extend users table)
ALTER TABLE users ADD COLUMN IF NOT EXISTS streak_days INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS streak_last_updated TEXT;

-- Case Management Tables
CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_number INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    case_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence TEXT,
    duration INTEGER,
    created_at TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    notes TEXT,
    UNIQUE(guild_id, case_number)
);

CREATE INDEX IF NOT EXISTS idx_cases_user ON cases(user_id, guild_id);
CREATE INDEX IF NOT EXISTS idx_cases_number ON cases(guild_id, case_number);

CREATE TABLE IF NOT EXISTS case_appeals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    case_number INTEGER NOT NULL,
    appeal_reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    reviewed_by INTEGER,
    reviewed_at TEXT,
    decision TEXT
);

CREATE INDEX IF NOT EXISTS idx_appeals_user ON case_appeals(user_id, guild_id);
CREATE INDEX IF NOT EXISTS idx_appeals_status ON case_appeals(status);

-- Event Management Tables
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    creator_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    event_time TEXT NOT NULL,
    event_type TEXT DEFAULT 'general',
    created_at TEXT NOT NULL,
    status TEXT DEFAULT 'scheduled',
    reminder_sent INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_events_guild ON events(guild_id);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(event_time);

CREATE TABLE IF NOT EXISTS event_rsvps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    rsvp_time TEXT NOT NULL,
    UNIQUE(event_id, user_id),
    FOREIGN KEY (event_id) REFERENCES events(id)
);

CREATE INDEX IF NOT EXISTS idx_rsvps_event ON event_rsvps(event_id);
CREATE INDEX IF NOT EXISTS idx_rsvps_user ON event_rsvps(user_id);

-- CAPTCHA Verification Tables
CREATE TABLE IF NOT EXISTS captcha_verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    verified_at TEXT,
    status TEXT DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_captcha_user ON captcha_verifications(user_id, guild_id);
CREATE INDEX IF NOT EXISTS idx_captcha_status ON captcha_verifications(status);

-- Daily Statistics Table
CREATE TABLE IF NOT EXISTS daily_statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    total_messages INTEGER DEFAULT 0,
    new_users INTEGER DEFAULT 0,
    active_users INTEGER DEFAULT 0,
    spam_blocked INTEGER DEFAULT 0,
    images_blocked INTEGER DEFAULT 0,
    warnings_issued INTEGER DEFAULT 0,
    UNIQUE(guild_id, date)
);

CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_statistics(guild_id, date);

-- Project Showcase Tables
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
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
    user_id INTEGER NOT NULL,
    vote_type INTEGER NOT NULL, -- 1 for upvote
    UNIQUE(project_id, user_id)
);

-- Daily Challenges Tables
CREATE TABLE IF NOT EXISTS daily_challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    challenge_type TEXT NOT NULL, -- message, voice, help, etc.
    target_count INTEGER NOT NULL,
    xp_reward INTEGER NOT NULL,
    challenge_date TEXT NOT NULL, -- YYYY-MM-DD
    UNIQUE(guild_id, challenge_date)
);

CREATE TABLE IF NOT EXISTS user_challenges (
    user_id INTEGER NOT NULL,
    challenge_id INTEGER NOT NULL,
    progress INTEGER DEFAULT 0,
    completed INTEGER DEFAULT 0,
    completed_at TEXT,
    UNIQUE(user_id, challenge_id)
);

-- Voice Activity Tables
CREATE TABLE IF NOT EXISTS voice_stats (
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    total_minutes INTEGER DEFAULT 0,
    current_streak INTEGER DEFAULT 0,
    last_session_end TEXT,
    longest_streak INTEGER DEFAULT 0,
    UNIQUE(user_id, guild_id)
);

-- Virtual Coffee & Networking Tables
CREATE TABLE IF NOT EXISTS coffee_preferences (
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    interests TEXT, -- JSON array or comma-separated
    skills TEXT,
    looking_for TEXT,
    opt_in INTEGER DEFAULT 0,
    UNIQUE(user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS coffee_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user1_id INTEGER NOT NULL,
    user2_id INTEGER NOT NULL,
    week_of TEXT NOT NULL, -- YYYY-MM-DD start of week
    status TEXT DEFAULT 'pending', -- pending, completed, skipped
    channel_id INTEGER,
    created_at TEXT NOT NULL,
    user1_rating INTEGER,
    user2_rating INTEGER,
    UNIQUE(user1_id, week_of),
    UNIQUE(user2_id, week_of)
);

-- Humanity Score & Behavioral Fingerprinting
ALTER TABLE users ADD COLUMN humanity_score INTEGER DEFAULT 100;
ALTER TABLE users ADD COLUMN typing_timestamp TEXT;

-- Global Threat Intelligence (Cross-Server Intelligence)
CREATE TABLE IF NOT EXISTS global_threat_intel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id INTEGER NOT NULL, -- User ID or Domain
    target_type TEXT NOT NULL, -- 'user' or 'domain'
    reason TEXT,
    source TEXT, -- Which community or list it came from
    severity INTEGER DEFAULT 1,
    added_at TEXT NOT NULL,
    UNIQUE(target_id, target_type)
);

-- DM Spam Reporting (DM Spam Protection)
CREATE TABLE IF NOT EXISTS dm_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id INTEGER NOT NULL,
    reported_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    evidence TEXT,
    status TEXT DEFAULT 'pending', -- pending, verified, dismissed
    timestamp TEXT NOT NULL
);
"""
