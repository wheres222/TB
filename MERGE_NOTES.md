# TENBOT Merge Notes

## Which folder is newer?
- Newer runtime base: `TENBOT-main/TENBOT-main`
- Reason: its core files were modified more recently (notably on **February 22, 2026**) than the older Python monolith inside `TENBOT/reputation-bot-master/reputation-bot-master` (mostly **January 28 to February 1, 2026**).

## Feature comparison (code-level)
- Old monolith (`reputation-bot-master`): more standalone feature modules and command breadth (about 69 text commands).
- New structured project (`TENBOT-main/TENBOT-main`): cleaner modular architecture, slash-command cogs, upgraded database layer, plus voice-call summarization/transcription support (about 48 slash commands detected).

## What was merged into this folder?
- Base runtime copied from newer project.
- Legacy-only modules copied into `legacy_features/`:
  - `account_monitoring.py`
  - `advanced_networking.py`
  - `business_features.py`
  - `captcha_verification.py`
  - `case_management.py`
  - `channel_analytics.py`
  - `dm_protection.py`
  - `enhanced_achievements.py`
  - `event_manager.py`
  - `gamification.py`
  - `humanity_fingerprinting.py`
  - `INTEGRATION_GUIDE.py`
  - `invite_detection.py`
  - `marketplace.py`
  - `message_logger.py`
  - `schema_updates.py`
  - `test_modules.py`
  - `threat_intelligence.py`
  - `topic_detection.py`
  - `user_management.py`
  - `welcome_system.py`
- Legacy marketplace assets copied to `legacy_features/Martkeplace_images/`.

## Important compatibility note
- Phase 2 now auto-loads only schema-compatible legacy modules.
- Remaining legacy files are still preserved-only and require adapter work before enablement in the new runtime.

## Phase 2 status
- Implemented phase 2 integration in `legacy_features/integration.py`.
- `bot.py` now loads schema-compatible legacy modules during startup.
- Loaded modules are exposed on `bot.legacy_phase2_modules`.

### Phase 2 modules wired
- `captcha_verification`
- `dm_protection`
- `threat_intelligence`
- `advanced_networking`
- `event_manager`
- `topic_detection`
- `humanity_fingerprinting`

### Runtime toggles
- Global switch: `LEGACY_PHASE2_ENABLED`
- Per-module switches:
  - `LEGACY_CAPTCHA_VERIFICATION`
  - `LEGACY_DM_PROTECTION`
  - `LEGACY_THREAT_INTELLIGENCE`
  - `LEGACY_ADVANCED_NETWORKING`
  - `LEGACY_EVENT_MANAGER`
  - `LEGACY_TOPIC_DETECTION`
  - `LEGACY_HUMANITY_FINGERPRINTING`
