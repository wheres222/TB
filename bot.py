"""
============================================================================
TENBOT - Ultra Discord Bot for Business Communities
============================================================================
All-in-one bot for professional Discord communities with:
- Advanced spam detection (image fingerprinting, trust-aware)
- Multi-dimensional trust scoring
- Case management system
- Gamification and reputation
- Comprehensive moderation tools

Author: TENBOT Development Team
Version: 2.0.0
License: MIT
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands

# Voice receive/transcription dependencies are optional; disable VC summarizer if missing
try:
    from discord.ext import voice_recv as vr
except ImportError:  # pragma: no cover - optional dependency
    vr = None

try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover - optional dependency
    WhisperModel = None

import asyncio
import aiohttp
import io
import os
import tempfile
import wave
from datetime import datetime, timedelta
from typing import Optional

# Import configuration
import config

# Import database
from database import Database, get_db
from database import database as database_module
from legacy_features.integration import load_phase2_legacy_modules

# Import modules
from modules import (
    get_spam_detector, get_image_detector, get_trust_system,
    get_reputation_system, get_analytics_system, get_enhanced_gamification
)

# Import utilities
from utils import (
    format_timespan, create_progress_bar, create_embed,
    send_dm, is_moderator, truncate_string
)

# Determine whether voice summarizer features can run
STT_PROVIDER = (getattr(config, "STT_PROVIDER", "local") or "local").lower()
DEEPGRAM_ENABLED = bool(getattr(config, "DEEPGRAM_API_KEY", ""))
LOCAL_STT_AVAILABLE = WhisperModel is not None

# Voice receive is always required; transcription can be local or deepgram.
VC_SUPPORTED = vr is not None and (LOCAL_STT_AVAILABLE or DEEPGRAM_ENABLED)

# Cache local whisper model so we don't re-initialize on every stop.
_WHISPER_MODEL: Optional[WhisperModel] = None


def get_whisper_model() -> Optional[WhisperModel]:
    global _WHISPER_MODEL
    if WhisperModel is None:
        return None
    if _WHISPER_MODEL is None:
        _WHISPER_MODEL = WhisperModel(
            config.VC_TRANSCRIPTION_MODEL,
            compute_type=config.VC_TRANSCRIPTION_COMPUTE_TYPE
        )
    return _WHISPER_MODEL


def build_vc_channel_overwrites(guild: discord.Guild) -> dict:
    """Build VC control channel permissions with privacy defaults."""
    private_mode = getattr(config, "VC_CONTROL_CHANNEL_PRIVATE", True)
    allowed_role_names = set(getattr(config, "VC_CONTROL_ALLOWED_ROLE_NAMES", []))

    if not private_mode:
        return {
            guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False, send_messages=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_messages=True,
            embed_links=True,
            read_message_history=True,
        ),
    }

    # Allow configured roles (or fallback to mod roles)
    if not allowed_role_names:
        allowed_role_names = set(getattr(config, "MOD_ROLE_NAMES", []))

    matched_roles = 0
    for role in guild.roles:
        has_admin_perms = role.permissions.administrator or role.permissions.manage_guild
        if role.name in allowed_role_names or has_admin_perms:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )
            matched_roles += 1

    # Ensure at least owner can access even if no role names match.
    if matched_roles == 0 and guild.owner:
        overwrites[guild.owner] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
        )

    return overwrites


def build_vc_status_embed(session: dict) -> discord.Embed:
    is_active = bool(session.get("active"))
    status_text = "🟢 Currently Listening" if is_active else "⚪ Currently Idle"
    description = (
        "Click the buttons below to manage the AI summarization for the current voice call."
    )
    embed = discord.Embed(
        title="🎧 Voice Channel Summarizer",
        description=description,
        color=discord.Color.green() if is_active else discord.Color.dark_gray()
    )
    embed.add_field(name="Current Status", value=status_text, inline=False)
    return embed


async def generate_vc_summary(messages: list[str], transcript_lines: list[str]) -> discord.Embed:
    combined_lines = [*transcript_lines, *messages]
    combined_lines = combined_lines[-400:]
    if not combined_lines:
        return discord.Embed(
            title=" Voice Call Summary",
            description="No messages captured from participants during this session.",
            color=discord.Color.blue()
        )

    conversation = "\n".join(combined_lines)
    prompt = (
        "Summarize the key topics and decisions from this Discord voice call in 5-7 bullets. "
        "Be concise and accurate.\n\n"
        f"{conversation}"
    )

    if config.ENABLE_AI_SUMMARIES:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {config.GROQ_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": config.AI_SUMMARY_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.4,
                        "max_tokens": 350
                    }
                ) as response:
                    data = await response.json()
                    summary = data["choices"][0]["message"]["content"]

            return discord.Embed(
                title=" Voice Call Summary",
                description=summary,
                color=discord.Color.blue()
            )
        except Exception as e:
            return discord.Embed(
                title=" Voice Call Summary",
                description=f"AI summary failed: {e}",
                color=discord.Color.red()
            )

    fallback = "\n".join(f"• {line}" for line in combined_lines[-10:])
    return discord.Embed(
        title=" Voice Call Summary (Fallback)",
        description=fallback,
        color=discord.Color.blue()
    )


async def delete_message_later(message: discord.Message, delay_seconds: int):
    if delay_seconds <= 0:
        return

    await asyncio.sleep(delay_seconds)
    try:
        await message.delete()
    except (discord.NotFound, discord.Forbidden):
        pass
    except Exception:
        pass


if VC_SUPPORTED:
    class VCAudioSink(vr.AudioSink):
        def __init__(self):
            super().__init__()
            self.buffers: dict[int, io.BytesIO] = {}

        def write(self, user: Optional[discord.User], data: vr.VoiceData):
            if user is None:
                return

            buffer = self.buffers.setdefault(user.id, io.BytesIO())
            buffer.write(data.pcm)


def pcm_to_wav_bytes(raw_audio: bytes) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(48000)
        wav_file.writeframes(raw_audio)
    return output.getvalue()


async def transcribe_with_deepgram(wav_bytes: bytes) -> list[str]:
    api_key = getattr(config, "DEEPGRAM_API_KEY", "")
    if not api_key:
        return []

    model = getattr(config, "DEEPGRAM_MODEL", "nova-2") or "nova-2"
    url = (
        f"https://api.deepgram.com/v1/listen?model={model}&smart_format=true"
        "&punctuate=true&utterances=true&diarize=true"
    )

    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "audio/wav",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=wav_bytes, timeout=90) as response:
            if response.status >= 400:
                error_text = await response.text()
                raise RuntimeError(f"Deepgram error {response.status}: {error_text[:240]}")

            data = await response.json()

    results = data.get("results", {}) if isinstance(data, dict) else {}
    utterances = results.get("utterances", [])

    lines: list[str] = []
    if isinstance(utterances, list) and utterances:
        for utterance in utterances:
            text = str((utterance or {}).get("transcript", "")).strip()
            if text:
                lines.append(text)
        return lines

    channels = results.get("channels", [])
    if channels:
        alt = (channels[0].get("alternatives") or [{}])[0]
        text = str(alt.get("transcript", "")).strip()
        if text:
            lines.append(text)

    return lines


async def transcribe_audio_buffers(
    buffers: dict[int, io.BytesIO],
    guild: Optional[discord.Guild] = None,
) -> list[str]:
    if not buffers or not VC_SUPPORTED:
        return []

    provider = (getattr(config, "STT_PROVIDER", "local") or "local").lower()
    transcript_lines: list[str] = []

    # Auto-fallbacks for reliability
    use_deepgram = provider == "deepgram" and DEEPGRAM_ENABLED
    use_local = provider == "local" and LOCAL_STT_AVAILABLE

    if not use_deepgram and not use_local:
        if DEEPGRAM_ENABLED:
            use_deepgram = True
        elif LOCAL_STT_AVAILABLE:
            use_local = True
        else:
            return []

    local_model = get_whisper_model() if use_local else None

    for user_id, buffer in buffers.items():
        raw_audio = buffer.getvalue()
        if not raw_audio:
            continue

        member = guild.get_member(user_id) if guild else None
        speaker = member.display_name if member else f"User {user_id}"

        wav_bytes = pcm_to_wav_bytes(raw_audio)

        try:
            if use_deepgram:
                texts = await transcribe_with_deepgram(wav_bytes)
                for text in texts:
                    transcript_lines.append(f"{speaker}: {text}")
                continue

            if not local_model:
                continue

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                temp_wav.write(wav_bytes)
                temp_path = temp_wav.name

            try:
                segments, _ = local_model.transcribe(temp_path, beam_size=5)
                for segment in segments:
                    text = segment.text.strip()
                    if text:
                        transcript_lines.append(f"{speaker}: {text}")
            finally:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        except Exception as e:
            transcript_lines.append(f"{speaker}: [transcription failed: {e}]")

    return transcript_lines


class VCSummaryControlView(discord.ui.View):
    def __init__(self, bot_instance: "TenBot"):
        super().__init__(timeout=None)
        self.bot_instance = bot_instance

    @discord.ui.button(
        label="Start Listening",
        style=discord.ButtonStyle.success,
        custom_id="vc_summary:start"
    )
    async def start_listening(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.bot_instance.start_vc_session(interaction)

    @discord.ui.button(
        label="Stop Listening",
        style=discord.ButtonStyle.danger,
        custom_id="vc_summary:stop"
    )
    async def stop_listening(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.bot_instance.stop_vc_session(interaction)


# ============================================================================
# BOT SETUP
# ============================================================================

class TenBot(commands.Bot):
    """
    Main bot class with custom initialization.
    """

    def __init__(self):
        # Set up intents (what events bot can see)
        intents = discord.Intents.all()

        # Initialize bot
        super().__init__(
            command_prefix=config.BOT_PREFIX,
            intents=intents,
            help_command=None  # We'll create our own
        )

        # Initialize modules (will be set in setup_hook)
        self.db: Optional[Database] = None
        self.spam_detector = None
        self.image_detector = None
        self.trust_system = None
        self.reputation_system = None
        self.analytics_system = None
        self.enhanced_gamification = None
        self.legacy_phase2_modules = {}
        self.vc_sessions = {}

    async def setup_hook(self):
        """
        Called when bot is setting up.
        Initialize database and modules here.
        """
        print("🚀 Setting up TENBOT...")

        # Initialize database
        self.db = Database()
        await self.db.initialize()
        database_module.db = self.db

        # Initialize modules
        self.spam_detector = get_spam_detector()
        self.image_detector = await get_image_detector()
        self.trust_system = get_trust_system()
        self.reputation_system = get_reputation_system()
        self.analytics_system = get_analytics_system()
        self.enhanced_gamification = get_enhanced_gamification()

        print("✅ All modules initialized!")

        # Load command cogs
        print("📦 Loading command cogs...")

        # Load moderation commands
        try:
            from commands.mod_commands import ModerationCommands
            await self.add_cog(ModerationCommands(self), override=True)
            print("  ✅ ModerationCommands loaded")
        except Exception as e:
            print(f"   Failed to load ModerationCommands: {e}")
            import traceback
            traceback.print_exc()

        self.add_view(VCSummaryControlView(self))

        # Load admin commands
        try:
            from commands.admin_commands import AdminCommands
            await self.add_cog(AdminCommands(self), override=True)
            print("  ✅ AdminCommands loaded")
        except Exception as e:
            print(f"   Failed to load AdminCommands: {e}")
            import traceback
            traceback.print_exc()

        # Load analytics commands
        try:
            from commands.analytics_commands import AnalyticsReputationCommands
            await self.add_cog(AnalyticsReputationCommands(self), override=True)
            print("  ✅ AnalyticsReputationCommands loaded")
        except Exception as e:
            print(f"   Failed to load AnalyticsReputationCommands: {e}")
            import traceback
            traceback.print_exc()

        # Load gamification commands
        try:
            from commands.gamification_commands import GamificationCommands
            await self.add_cog(GamificationCommands(self), override=True)
            print("  ✅ GamificationCommands loaded")
        except Exception as e:
            print(f"   Failed to load GamificationCommands: {e}")
            import traceback
            traceback.print_exc()

        # Load compatible legacy phase-2 modules
        try:
            print("🧩 Loading legacy phase-2 modules...")
            self.legacy_phase2_modules = await load_phase2_legacy_modules(
                self,
                self.db.db,
            )
            print(f"✅ Loaded {len(self.legacy_phase2_modules)} legacy phase-2 module(s)")
        except Exception as e:
            print(f" Failed loading legacy phase-2 modules: {e}")
            import traceback
            traceback.print_exc()
        print("✅ Finished loading command cogs!")

        # Sync slash commands
        try:
            synced = await self.tree.sync()
            print(f"✅ Synced {len(synced)} slash commands globally!")
        except Exception as e:
            print(f" Failed to sync commands: {e}")
            import traceback
            traceback.print_exc()

    async def ensure_vc_control_channel(self, guild: discord.Guild) -> discord.TextChannel:
        desired_overwrites = build_vc_channel_overwrites(guild)
        existing = discord.utils.get(guild.text_channels, name="vc-summarizer")
        if existing:
            try:
                await existing.edit(overwrites=desired_overwrites, reason="Apply VC privacy policy")
            except Exception:
                pass
            return existing

        return await guild.create_text_channel(
            "vc-summarizer",
            overwrites=desired_overwrites,
            reason="Voice summarizer control channel"
        )

    async def ensure_vc_control_message(self, guild: discord.Guild) -> discord.Message:
        channel = await self.ensure_vc_control_channel(guild)
        session = self.vc_sessions.get(guild.id, {})
        message_id = session.get("control_message_id")

        embed = build_vc_status_embed(session)
        view = VCSummaryControlView(self)

        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed, view=view)
                return message
            except discord.NotFound:
                pass

        message = await channel.send(embed=embed, view=view)
        self.vc_sessions[guild.id] = {**session, "control_message_id": message.id}
        return message

    async def start_vc_session(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(" Use this in a server.", ephemeral=True)
            return

        if not VC_SUPPORTED:
            await interaction.response.send_message(
                " Voice summarizer unavailable. Install discord-ext-voice-recv and configure either local faster-whisper or Deepgram API.",
                ephemeral=True
            )
            return

        voice_state = interaction.user.voice
        if not voice_state or not voice_state.channel:
            await interaction.response.send_message(
                " Join a voice channel first.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        channel = voice_state.channel
        session = self.vc_sessions.get(guild.id, {})

        if session.get("active"):
            await interaction.followup.send("✅ Already listening.", ephemeral=True)
            return

        voice_client = discord.utils.get(self.voice_clients, guild=guild)
        if voice_client and voice_client.channel != channel:
            await voice_client.move_to(channel)
        elif not voice_client:
            await channel.connect()

        voice_client = discord.utils.get(self.voice_clients, guild=guild)
        sink = VCAudioSink() if VC_SUPPORTED else None
        if voice_client and sink:
            voice_client.listen(sink)

        session.update({
            "active": True,
            "voice_channel_id": channel.id,
            "started_at": datetime.utcnow().isoformat(),
            "messages": [],
            "transcript_lines": [],
            "audio_sink": sink,
            "started_by": interaction.user.id
        })
        self.vc_sessions[guild.id] = session

        await self.ensure_vc_control_message(guild)
        await interaction.followup.send("✅ Started listening.", ephemeral=True)

    async def stop_vc_session(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(" Use this in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        session = self.vc_sessions.get(guild.id, {})

        if not session.get("active"):
            await interaction.followup.send("✅ Already idle.", ephemeral=True)
            return

        voice_client = discord.utils.get(self.voice_clients, guild=guild)
        sink = session.get("audio_sink")
        if voice_client:
            await voice_client.disconnect(force=True)

        transcript_lines = []
        if config.VC_TRANSCRIPTION_ENABLED and sink and VC_SUPPORTED:
            transcript_lines = await transcribe_audio_buffers(sink.buffers, guild)

        # Build summary before clearing session buffers.
        summary = await generate_vc_summary(
            session.get("messages", []),
            transcript_lines
        )

        auto_delete_minutes = max(0, int(getattr(config, "VC_SUMMARY_AUTO_DELETE_MINUTES", 0)))
        if auto_delete_minutes > 0:
            summary.set_footer(text=f"Auto-deletes in {auto_delete_minutes} minute(s)")

        # Clear sensitive session data immediately after summary generation.
        session.update({
            "active": False,
            "messages": [],
            "transcript_lines": [],
            "audio_sink": None,
            "stopped_at": datetime.utcnow().isoformat(),
        })
        self.vc_sessions[guild.id] = session
        await self.ensure_vc_control_message(guild)

        control_channel = await self.ensure_vc_control_channel(guild)
        summary_message = await control_channel.send(embed=summary)

        if auto_delete_minutes > 0:
            asyncio.create_task(delete_message_later(summary_message, auto_delete_minutes * 60))

        await interaction.followup.send("✅ Stopped listening and posted summary.", ephemeral=True)

    async def on_ready(self):
        """
        Called when bot is fully ready and connected.
        """
        print("=" * 60)
        print(f"✅ {self.user.name} is online!")
        print(f"📊 Connected to {len(self.guilds)} server(s)")
        print(f"👥 Monitoring {sum(g.member_count for g in self.guilds)} users")
        print("=" * 60)

        # Start background tasks
        if not backup_database.is_running():
            backup_database.start()

        if not cleanup_old_data.is_running():
            cleanup_old_data.start()

        if not update_reputation_scores.is_running():
            update_reputation_scores.start()

        if not update_trust_scores.is_running():
            update_trust_scores.start()

        if not check_daily_streaks.is_running():
            check_daily_streaks.start()

        for guild in self.guilds:
            try:
                await self.ensure_vc_control_message(guild)
            except Exception as e:
                print(f" Failed to set VC control message in {guild.name}: {e}")

    async def close(self):
        """
        Cleanup when bot shuts down.
        """
        print("🛑 Shutting down...")

        if self.db:
            await self.db.close()

        if self.image_detector:
            close_result = self.image_detector.close()
            if asyncio.iscoroutine(close_result):
                await close_result

        await super().close()


# ============================================================================
# INITIALIZE BOT
# ============================================================================

bot = TenBot()


# ============================================================================
# BACKGROUND TASKS
# ============================================================================

@tasks.loop(hours=1)
async def backup_database():
    """Backup database every hour."""
    try:
        db = await get_db()
        await db.backup()
        print(f"💾 Database backed up at {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f" Backup failed: {e}")


@tasks.loop(hours=24)
async def cleanup_old_data():
    """Clean up old data daily."""
    try:
        db = await get_db()

        # Clean message history older than 30 days
        await db.cleanup_old_messages(days=30)

        # Vacuum database to reclaim space
        await db.execute("VACUUM")

        print(f"🧹 Database cleanup completed at {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f" Cleanup failed: {e}")


@tasks.loop(hours=6)
async def update_reputation_scores():
    """Recalculate reputation scores periodically."""
    try:
        db = await get_db()

        # Get all active users (posted in last 30 days)
        active_users = await db.fetch_all(
            """
            SELECT DISTINCT user_id
            FROM message_history
            WHERE created_at >= datetime('now', '-30 days')
            """, ()
        )

        if not active_users:
            return

        # Recalculate reputation for active users
        for row in active_users:
            user_id = row['user_id']

            # Get member object (need for reputation calculation)
            for guild in bot.guilds:
                try:
                    member = await guild.fetch_member(int(user_id))
                    if member:
                        await bot.reputation_system.calculate_reputation(member)
                        break
                except:
                    continue

        print(f" Updated reputation for {len(active_users)} active users")
    except Exception as e:
        print(f" Reputation update failed: {e}")


@tasks.loop(hours=12)
async def update_trust_scores():
    """Recalculate trust scores periodically."""
    try:
        db = await get_db()

        # Get all users active in last 7 days
        active_users = await db.fetch_all(
            """
            SELECT DISTINCT user_id
            FROM message_history
            WHERE created_at >= datetime('now', '-7 days')
            """, ()
        )

        if not active_users:
            return

        # Recalculate trust
        for row in active_users:
            user_id = row['user_id']

            for guild in bot.guilds:
                try:
                    member = await guild.fetch_member(int(user_id))
                    if member:
                        await bot.trust_system.calculate_trust_score(member)
                        break
                except:
                    continue

        print(f"🔒 Updated trust scores for {len(active_users)} active users")
    except Exception as e:
        print(f" Trust update failed: {e}")


@tasks.loop(hours=1)
async def check_daily_streaks():
    """Check and update daily streaks for all users."""
    try:
        db = await get_db()

        # Get all users with active streaks
        users_with_streaks = await db.fetch_all(
            """
            SELECT user_id, last_active_date
            FROM gamification
            WHERE current_streak_days > 0
            """, ()
        )

        for row in users_with_streaks:
            user_id = row['user_id']
            last_active = row['last_active_date']

            if last_active:
                last_date = datetime.fromisoformat(last_active).date()
                today = datetime.now().date()
                days_diff = (today - last_date).days

                # Streak broken (missed a day)
                if days_diff > 1:
                    await db.execute(
                        """
                        UPDATE gamification
                        SET current_streak_days = 0
                        WHERE user_id = ?
                        """,
                        (user_id,)
                    )
                    print(f"💔 Streak broken for user {user_id}")

        print(f"🔥 Checked streaks for {len(users_with_streaks)} users")
    except Exception as e:
        print(f" Streak check failed: {e}")


# ============================================================================
# EVENT HANDLERS
# ============================================================================

@bot.event
async def on_member_join(member: discord.Member):
    """
    Handle new member joining.
    """
    if member.bot:
        return

    db = await get_db()
    user_id = str(member.id)

    # Create user record
    await db.create_user(user_id, member.name, member.display_name)

    # Update join date
    await db.update_user(user_id, joined_server=member.joined_at)

    # Calculate initial trust score
    await bot.trust_system.calculate_trust_score(member)

    # Log to database
    await db.log_action(
        action_type='member_join',
        actor_id=user_id,
        guild_id=str(member.guild.id),
        details={'username': member.name}
    )

    print(f"👋 {member.name} joined the server")


@bot.event
async def on_message(message: discord.Message):
    """
    Main message handler - spam detection, XP, etc.
    """
    # Ignore bots
    if message.author.bot:
        return

    # Ignore DMs
    if not message.guild:
        return

    db = await get_db()
    user_id = str(message.author.id)

    # Ensure user exists in database
    user_data = await db.get_user(user_id)
    if not user_data:
        await db.create_user(user_id, message.author.name, message.author.display_name)

    session = bot.vc_sessions.get(message.guild.id)
    if session and session.get("active") and getattr(config, "VC_CAPTURE_TEXT_MESSAGES", False):
        voice_channel_id = session.get("voice_channel_id")
        if voice_channel_id:
            voice_channel = message.guild.get_channel(voice_channel_id)
            if voice_channel and message.author in voice_channel.members and message.content.strip():
                session.setdefault("messages", []).append(
                    f"{message.author.display_name}: {message.content.strip()}"
                )
                session["messages"] = session["messages"][-300:]

    # ====== SPAM DETECTION ======
    is_spam, spam_type, reason = await bot.spam_detector.check_message(message)

    if is_spam:
        await handle_spam(message, spam_type, reason)
        return  # Don't process spammy messages further

    # ====== IMAGE DETECTION ======
    if message.attachments and config.FEATURES['image_detection']:
        spam_images = await bot.image_detector.check_multiple_images(
            message.attachments,
            user_id,
            str(message.channel.id),
            str(message.id)
        )

        for filename, is_spam_img, img_reason in spam_images:
            if is_spam_img:
                await handle_image_spam(message, filename, img_reason)
                return  # Delete message with spam image

    # ====== UPDATE USER STATS ======
    await db.increment_user_stat(user_id, 'total_messages', 1)

    # Update channel activity
    await db.execute(
        """
        INSERT INTO channel_activity (user_id, channel_id, message_count, last_message_at)
        VALUES (?, ?, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, channel_id) DO UPDATE SET
            message_count = message_count + 1,
            last_message_at = CURRENT_TIMESTAMP
        """,
        (user_id, str(message.channel.id))
    )

    # ====== GAMIFICATION ======
    if config.FEATURES['gamification']:
        # Award XP
        await handle_xp_gain(message.author, message.guild, 'message')

        # Check gamification milestones if supported by current module version.
        if hasattr(bot.enhanced_gamification, 'check_milestones'):
            try:
                await bot.enhanced_gamification.check_milestones(user_id)
            except Exception as e:
                print(f" check_milestones failed for {user_id}: {e}")

    # Process commands
    await bot.process_commands(message)


@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
    """
    Track reactions for reputation/gamification.
    """
    if user.bot:
        return

    db = await get_db()

    # Increment reaction counter for giver
    await db.increment_user_stat(str(user.id), 'total_reactions_given', 1)

    # Increment for receiver (if not bot)
    if reaction.message.author and not reaction.message.author.bot:
        await db.increment_user_stat(
            str(reaction.message.author.id),
            'total_reactions_received',
            1
        )

        # Award XP to message author
        if config.FEATURES['gamification']:
            await handle_xp_gain(
                reaction.message.author,
                reaction.message.guild,
                'reaction',
                config.XP_PER_REACTION_RECEIVED
            )


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState
):
    """
    Track voice channel participation.
    """
    if member.bot:
        return

    db = await get_db()
    user_id = str(member.id)

    # User joined voice channel
    if before.channel is None and after.channel is not None:
        await db.execute(
            """
            INSERT INTO voice_sessions (user_id, channel_id, joined_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (user_id, str(after.channel.id))
        )

    # User left voice channel
    elif before.channel is not None and after.channel is None:
        # Calculate session duration
        session = await db.fetch_one(
            """
            SELECT joined_at FROM voice_sessions
            WHERE user_id = ? AND left_at IS NULL
            ORDER BY joined_at DESC LIMIT 1
            """,
            (user_id,)
        )

        if session:
            joined_at = datetime.fromisoformat(session['joined_at'])
            duration_minutes = (datetime.now() - joined_at).total_seconds() / 60

            # Update session
            await db.execute(
                """
                UPDATE voice_sessions
                SET left_at = CURRENT_TIMESTAMP, duration_minutes = ?
                WHERE user_id = ? AND left_at IS NULL
                """,
                (duration_minutes, user_id)
            )

            # Update total voice time
            await db.increment_user_stat(user_id, 'total_voice_minutes', int(duration_minutes))

            # Award voice XP (if session > 5 minutes)
            if config.FEATURES['gamification'] and duration_minutes >= 5:
                xp_amount = int(duration_minutes) * config.XP_PER_VOICE_MINUTE
                await handle_xp_gain(member, member.guild, 'voice', xp_amount)

                # Refresh milestones if supported by current module version.
                if hasattr(bot.enhanced_gamification, 'check_milestones'):
                    try:
                        await bot.enhanced_gamification.check_milestones(user_id)
                    except Exception as e:
                        print(f" check_milestones failed for {user_id}: {e}")


# ============================================================================
# BADGE & ACHIEVEMENT CHECKING
# ============================================================================

async def check_and_award_badges(user: discord.Member, guild: discord.Guild):
    """
    Check and award badges based on user activity patterns.

    Args:
        user: Discord Member
        guild: Discord Guild
    """
    db = await get_db()
    user_id = str(user.id)

    # Get user stats
    user_data = await db.get_user(user_id)
    if not user_data:
        return

    gamif_data = await db.fetch_one(
        "SELECT * FROM gamification WHERE user_id = ?",
        (user_id,)
    )
    if not gamif_data:
        return

    badges_to_award = []

    # Check for message milestones
    messages = user_data.get('total_messages', 0)
    if messages >= 100 and not await has_badge(user_id, 'century_club'):
        badges_to_award.append('century_club')
    if messages >= 500 and not await has_badge(user_id, 'message_master'):
        badges_to_award.append('message_master')
    if messages >= 1000 and not await has_badge(user_id, 'chatterbox'):
        badges_to_award.append('chatterbox')

    # Check for streak badges
    streak = gamif_data.get('current_streak_days', 0)
    if streak >= 7 and not await has_badge(user_id, 'week_warrior'):
        badges_to_award.append('week_warrior')
    if streak >= 30 and not await has_badge(user_id, 'monthly_legend'):
        badges_to_award.append('monthly_legend')
    if streak >= 100 and not await has_badge(user_id, 'unstoppable'):
        badges_to_award.append('unstoppable')

    # Check for voice badges
    voice_hours = user_data.get('total_voice_minutes', 0) / 60
    if voice_hours >= 10 and not await has_badge(user_id, 'voice_champion'):
        badges_to_award.append('voice_champion')
    if voice_hours >= 50 and not await has_badge(user_id, 'voice_legend'):
        badges_to_award.append('voice_legend')

    # Check for reaction badges
    reactions_given = user_data.get('total_reactions_given', 0)
    if reactions_given >= 100 and not await has_badge(user_id, 'super_supporter'):
        badges_to_award.append('super_supporter')
    if reactions_given >= 500 and not await has_badge(user_id, 'reaction_royalty'):
        badges_to_award.append('reaction_royalty')

    # Check for time-based badges
    current_hour = datetime.now().hour
    if current_hour < 6 and not await has_badge(user_id, 'early_bird'):
        badges_to_award.append('early_bird')
    if current_hour >= 22 and not await has_badge(user_id, 'night_owl'):
        badges_to_award.append('night_owl')

    # Award badges
    for badge_key in badges_to_award:
        try:
            await bot.enhanced_gamification.award_badge(user_id, badge_key)
            print(f" Awarded badge '{badge_key}' to {user.name}")

            # Optionally notify user
            badge = bot.enhanced_gamification.BADGES.get(badge_key)
            if badge:
                await send_badge_notification(user, guild, badge)
        except Exception as e:
            print(f"⚠  Error awarding badge: {e}")


async def has_badge(user_id: str, badge_key: str) -> bool:
    """Check if user already has a badge."""
    db = await get_db()
    result = await db.fetch_value(
        "SELECT COUNT(*) FROM user_badges WHERE user_id = ? AND badge_key = ?",
        (user_id, badge_key)
    )
    return result > 0


async def send_badge_notification(
    user: discord.Member,
    guild: discord.Guild,
    badge: dict
):
    """Send notification when user earns a badge."""
    rarity_colors = {
        'common': discord.Color.light_grey(),
        'uncommon': discord.Color.green(),
        'rare': discord.Color.blue(),
        'epic': discord.Color.purple(),
        'legendary': discord.Color.gold()
    }

    embed = create_embed(
        title=" New Badge Earned!",
        description=f"{user.mention} earned the **{badge['name']}** badge!\n\n"
                   f"*{badge['description']}*",
        color=rarity_colors.get(badge['rarity'], discord.Color.blue())
    )
    embed.add_field(name="Rarity", value=badge['rarity'].title())
    embed.set_thumbnail(url=user.display_avatar.url)

    # Find badges channel or use general
    channel = discord.utils.get(guild.channels, name='badges')
    if not channel:
        channel = discord.utils.get(guild.channels, name='general')

    if channel:
        try:
            await channel.send(embed=embed)
        except:
            pass  # Silently fail if can't send


# ============================================================================
# SPAM HANDLING
# ============================================================================

async def handle_spam(
    message: discord.Message,
    spam_type: str,
    reason: str
):
    """
    Handle detected spam message.

    Args:
        message: Spam message
        spam_type: Type of spam detected
        reason: Detailed reason
    """
    db = await get_db()
    user_id = str(message.author.id)

    # Delete the message
    try:
        await message.delete()
        print(f"🗑  Deleted spam from {message.author.name}: {reason}")
    except discord.Forbidden:
        print(f"⚠  Cannot delete message (missing permissions)")
        return

    # Mark message as spam in database
    await db.execute(
        "UPDATE message_history SET is_spam = 1 WHERE message_id = ?",
        (str(message.id),)
    )

    # Get current warning count
    warning_count = await db.get_warning_count(user_id, active_only=True)
    new_warning_count = warning_count + 1

    # Determine severity and action
    if spam_type in ['scam', 'link_spam']:
        severity = 'high'
    elif spam_type in ['mention_spam', 'cross_channel']:
        severity = 'medium'
    else:
        severity = 'low'

    # Calculate timeout duration
    timeout_duration = config.TIMEOUT_DURATIONS.get(new_warning_count)

    # Create case
    case_id = await db.create_case(
        case_type='warning',
        user_id=user_id,
        reason=f"Spam detected: {reason}",
        created_by='system',
        action_taken=f"Warning #{new_warning_count}" + (f", timeout {format_timespan(timeout_duration)}" if timeout_duration else ""),
        channel_id=str(message.channel.id),
        message_id=str(message.id)
    )

    # Add warning
    await db.add_warning(
        user_id=user_id,
        reason=reason,
        issued_by='system',
        warning_type=spam_type,
        severity=severity,
        action_taken='timeout' if timeout_duration else 'warning_only',
        timeout_duration=timeout_duration,
        message_id=str(message.id),
        channel_id=str(message.channel.id),
        case_id=case_id
    )

    # Apply timeout if needed
    if timeout_duration and new_warning_count < config.AUTO_BAN_THRESHOLD:
        try:
            await message.author.timeout(
                timedelta(seconds=timeout_duration),
                reason=f"Spam warning #{new_warning_count}: {reason}"
            )
        except discord.Forbidden:
            print(f"⚠  Cannot timeout {message.author.name} (missing permissions)")

    # Auto-ban if threshold reached
    elif new_warning_count >= config.AUTO_BAN_THRESHOLD:
        try:
            await message.author.ban(reason=f"Auto-ban: {new_warning_count} warnings")
            await db.update_user(user_id, is_banned=True)
        except discord.Forbidden:
            print(f"⚠  Cannot ban {message.author.name} (missing permissions)")

    # Send DM to user
    embed = create_embed(
        title="⚠ Spam Warning",
        description=f"Your message was removed for violating spam rules.",
        color=discord.Color.red()
    )
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Warning", value=f"#{new_warning_count} of {config.AUTO_BAN_THRESHOLD}", inline=True)

    if timeout_duration:
        embed.add_field(name="Timeout", value=format_timespan(timeout_duration), inline=True)

    if new_warning_count >= config.AUTO_BAN_THRESHOLD - 1:
        embed.add_field(
            name="⚠ Important",
            value="Next violation will result in automatic ban!",
            inline=False
        )

    await send_dm(message.author, embed)

    # Recalculate trust score (warnings affect trust)
    await bot.trust_system.calculate_trust_score(message.author)


async def handle_image_spam(message: discord.Message, filename: str, reason: str):
    """
    Handle spam image detection.
    """
    # Delete message
    try:
        await message.delete()
        print(f"🖼  Deleted spam image from {message.author.name}: {reason}")
    except:
        pass

    # Warn user
    embed = create_embed(
        title="🖼 Spam Image Detected",
        description=f"Your image was removed.",
        color=discord.Color.red()
    )
    embed.add_field(name="Image", value=filename, inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)

    await send_dm(message.author, embed)


# ============================================================================
# GAMIFICATION
# ============================================================================

async def handle_xp_gain(
    user: discord.Member,
    guild: discord.Guild,
    source: str,
    xp_amount: int = None
):
    """
    Award XP to user and handle level ups.

    Args:
        user: Discord Member
        guild: Discord Guild
        source: XP source ('message', 'reaction', 'voice')
        xp_amount: XP to award (uses config defaults if None)
    """
    db = await get_db()
    user_id = str(user.id)

    # Determine XP amount
    if xp_amount is None:
        if source == 'message':
            xp_amount = config.XP_PER_MESSAGE
        elif source == 'reaction':
            xp_amount = config.XP_PER_REACTION_RECEIVED
        elif source == 'voice':
            xp_amount = config.XP_PER_VOICE_MINUTE
        else:
            xp_amount = 0

    # Check cooldown for messages
    if source == 'message':
        gamification = await db.fetch_one(
            "SELECT last_xp_message_time FROM gamification WHERE user_id = ?",
            (user_id,)
        )

        if gamification and gamification['last_xp_message_time']:
            last_time = datetime.fromisoformat(gamification['last_xp_message_time'])
            if (datetime.now() - last_time).total_seconds() < config.XP_COOLDOWN:
                return  # Still on cooldown

        # Update cooldown
        await db.execute(
            "UPDATE gamification SET last_xp_message_time = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user_id,)
        )

    # Add XP
    result = await db.add_xp(user_id, xp_amount, source)

    # Handle level up
    if result['leveled_up']:
        await handle_level_up(user, guild, result['old_level'], result['new_level'])

    # Refresh milestones if supported by current module version.
    if hasattr(bot.enhanced_gamification, 'check_milestones'):
        try:
            await bot.enhanced_gamification.check_milestones(user_id)
        except Exception as e:
            print(f" check_milestones failed for {user_id}: {e}")

    # Check for badges based on activity
    await check_and_award_badges(user, guild)


async def handle_level_up(
    user: discord.Member,
    guild: discord.Guild,
    old_level: int,
    new_level: int
):
    """
    Handle user leveling up.

    Args:
        user: Discord Member
        guild: Discord Guild
        old_level: Previous level
        new_level: New level
    """
    print(f"🎉 {user.name} leveled up: {old_level} → {new_level}")

    # Check for level role rewards
    if new_level in config.LEVEL_ROLES:
        role_name = config.LEVEL_ROLES[new_level]
        role = discord.utils.get(guild.roles, name=role_name)

        if role:
            try:
                await user.add_roles(role)
            except discord.Forbidden:
                print(f"⚠  Cannot assign role {role_name} (missing permissions)")

    # Send level up message
    embed = create_embed(
        title="🎉 Level Up!",
        description=f"{user.mention} reached **Level {new_level}**!",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=user.display_avatar.url)

    # Find level-up channel or use general
    channel = discord.utils.get(guild.channels, name='level-ups')
    if not channel:
        channel = discord.utils.get(guild.channels, name='general')

    if channel:
        try:
            await channel.send(embed=embed)
        except:
            pass


# ============================================================================
# SLASH COMMANDS - USER COMMANDS
# ============================================================================

@bot.tree.command(name="stats")
@app_commands.describe(user="User to check stats for")
async def stats_command(interaction: discord.Interaction, user: discord.Member = None):
    """
    View detailed user statistics.
    """
    target = user or interaction.user
    db = await get_db()
    user_id = str(target.id)

    # Get user profile
    profile = await db.get_user_profile(user_id)

    if not profile:
        await interaction.response.send_message(
            " User not found in database.",
            ephemeral=True
        )
        return

    # Create embed
    embed = create_embed(
        title=f"📊 Stats - {target.display_name}",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=target.display_avatar.url)

    # Basic stats
    embed.add_field(
        name=" Messages",
        value=f"{profile.get('total_messages', 0):,}",
        inline=True
    )

    embed.add_field(
        name=" Reactions",
        value=f"{profile.get('total_reactions_received', 0):,}",
        inline=True
    )

    embed.add_field(
        name="🎤 Voice Time",
        value=f"{profile.get('total_voice_minutes', 0):.0f}m",
        inline=True
    )

    # Gamification
    if config.FEATURES['gamification'] and profile.get('total_xp'):
        embed.add_field(
            name=" Level",
            value=str(profile.get('current_level', 1)),
            inline=True
        )

        embed.add_field(
            name="💎 XP",
            value=f"{profile.get('total_xp', 0):,}",
            inline=True
        )

        embed.add_field(
            name="🔥 Streak",
            value=f"{profile.get('current_streak_days', 0)} days",
            inline=True
        )

    # Trust & Reputation
    if config.FEATURES['trust_system']:
        trust_score = profile.get('trust_score', 0)
        trust_tier = profile.get('trust_tier', 'new')

        embed.add_field(
            name="🛡 Trust Score",
            value=f"{trust_score:.1f}/100 ({trust_tier})",
            inline=True
        )

    # Warnings
    warnings = profile.get('active_warnings', 0)
    if warnings > 0:
        embed.add_field(
            name="⚠ Warnings",
            value=str(warnings),
            inline=True
        )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rank")
async def rank_command(interaction: discord.Interaction, user: discord.Member = None):
    """
    Check your rank and XP progress.
    """
    if not config.FEATURES['gamification']:
        await interaction.response.send_message(
            " Gamification is disabled.",
            ephemeral=True
        )
        return

    target = user or interaction.user
    db = await get_db()
    user_id = str(target.id)

    # Get gamification data
    data = await db.fetch_one(
        "SELECT * FROM gamification WHERE user_id = ?",
        (user_id,)
    )

    if not data:
        await interaction.response.send_message(
            " No data found.",
            ephemeral=True
        )
        return

    # Calculate progress to next level
    current_level = data['current_level']
    total_xp = data['total_xp']
    xp_for_next = (current_level + 1) * config.XP_PER_LEVEL
    xp_current_level = current_level * config.XP_PER_LEVEL
    xp_progress = total_xp - xp_current_level
    xp_needed = xp_for_next - xp_current_level

    progress_bar = create_progress_bar(xp_progress, xp_needed)

    # Create embed
    embed = create_embed(
        title=f"📊 Rank - {target.display_name}",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=target.display_avatar.url)

    embed.add_field(
        name="Level",
        value=f" {current_level}",
        inline=True
    )

    embed.add_field(
        name="Total XP",
        value=f"{total_xp:,}",
        inline=True
    )

    embed.add_field(
        name="Streak",
        value=f"🔥 {data['current_streak_days']}d",
        inline=True
    )

    embed.add_field(
        name=f"Progress to Level {current_level + 1}",
        value=f"{progress_bar}\n{xp_progress}/{xp_needed} XP",
        inline=False
    )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="leaderboard")
async def leaderboard_command(interaction: discord.Interaction):
    """
    View server leaderboard.
    """
    if not config.FEATURES['gamification']:
        await interaction.response.send_message(
            " Gamification is disabled.",
            ephemeral=True
        )
        return

    db = await get_db()
    top_users = await db.get_leaderboard(limit=10)

    embed = create_embed(
        title=" Leaderboard",
        description="Top 10 members by XP",
        color=discord.Color.gold()
    )

    for i, user_data in enumerate(top_users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."

        embed.add_field(
            name=f"{medal} {user_data.get('display_name', 'Unknown')}",
            value=f"Level {user_data.get('current_level', 1)} • {user_data.get('total_xp', 0):,} XP",
            inline=False
        )

    await interaction.response.send_message(embed=embed)


# ============================================================================
# SLASH COMMANDS - MOD COMMANDS
# ============================================================================

@bot.tree.command(name="investigate")
@app_commands.describe(user="User to investigate")
@app_commands.checks.has_permissions(moderate_members=True)
async def investigate_command(interaction: discord.Interaction, user: discord.Member):
    """
    Get comprehensive user investigation report (MOD ONLY).
    """
    await interaction.response.defer(ephemeral=True)

    db = await get_db()
    user_id = str(user.id)

    # Get all user data
    profile = await db.get_user_profile(user_id)
    warnings = await db.get_user_warnings(user_id, active_only=False)
    cases = await db.get_user_cases(user_id)
    trust_data = await bot.trust_system.get_trust_score(user_id)

    if not profile:
        await interaction.followup.send(" User not found.", ephemeral=True)
        return

    # Create detailed embed
    embed = create_embed(
        title=f" Investigation - {user.display_name}",
        description=f"User ID: {user_id}",
        color=discord.Color.orange()
    )

    # Trust info
    if trust_data:
        trust_score = trust_data.get('overall_score', 0)
        trust_tier = trust_data.get('trust_tier', 'unknown')

        if trust_score >= 80:
            status = "🟢 Highly Trusted"
        elif trust_score >= 60:
            status = "🟡 Trusted"
        elif trust_score >= 40:
            status = "🟠 Regular"
        else:
            status = "🔴 Low Trust"

        embed.add_field(
            name="Trust Status",
            value=f"{status}\nScore: {trust_score:.1f}/100\nTier: {trust_tier}",
            inline=True
        )

    # Activity
    embed.add_field(
        name="Activity",
        value=f"Messages: {profile.get('total_messages', 0):,}\nVoice: {profile.get('total_voice_minutes', 0):.0f}m",
        inline=True
    )

    # Warnings
    active_warnings = len([w for w in warnings if not w.get('expires_at') or datetime.fromisoformat(w['expires_at']) > datetime.now()])
    embed.add_field(
        name="Warnings",
        value=f"Active: {active_warnings}\nTotal: {len(warnings)}",
        inline=True
    )

    # Recent cases
    if cases:
        recent_cases = cases[:3]
        case_text = "\n".join(
            f"#{c['case_id']}: {c['case_type']} - {truncate_string(c['reason'], 50)}"
            for c in recent_cases
        )
        embed.add_field(
            name="Recent Cases",
            value=case_text or "None",
            inline=False
        )

    # Account info
    created_days = (datetime.now(user.created_at.tzinfo) - user.created_at).days
    joined_days = (datetime.now(user.joined_at.tzinfo) - user.joined_at).days if user.joined_at else 0

    embed.add_field(
        name="Account Age",
        value=f"{created_days} days",
        inline=True
    )

    embed.add_field(
        name="Server Age",
        value=f"{joined_days} days",
        inline=True
    )

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="trust")
@app_commands.describe(user="User to check trust score")
async def trust_command(interaction: discord.Interaction, user: discord.Member = None):
    """
    Check trust score for a user.
    """
    target = user or interaction.user
    await interaction.response.defer()

    # Calculate/update trust score
    trust_data = await bot.trust_system.calculate_trust_score(target)

    embed = create_embed(
        title=f"🛡 Trust Score - {target.display_name}",
        color=discord.Color.blue()
    )

    # Overall score
    overall = trust_data['overall_score']
    tier = trust_data['trust_tier']

    embed.add_field(
        name="Overall Score",
        value=f"{overall:.1f}/100",
        inline=True
    )

    embed.add_field(
        name="Trust Tier",
        value=tier.title(),
        inline=True
    )

    # Component breakdown (for mods only)
    if is_moderator(interaction.user):
        components = f"""
        Account Age: {trust_data['account_age']:.1f}
        Server Age: {trust_data['server_age']:.1f}
        Message Count: {trust_data['message_count']:.1f}
        Message Quality: {trust_data['message_quality']:.1f}
        Consistency: {trust_data['consistency']:.1f}
        Warnings: {trust_data['warning_penalty']:.1f}
        Reputation: {trust_data['reputation']:.1f}
        """
        embed.add_field(
            name="Component Breakdown",
            value=f"```{components}```",
            inline=False
        )

    await interaction.followup.send(embed=embed)


# ============================================================================
# IMAGE COMMANDS
# ============================================================================

@bot.tree.command(name="report_image")
@app_commands.describe(
    message_id="ID of message containing spam image",
    reason="Why you're reporting this image"
)
async def report_image_command(
    interaction: discord.Interaction,
    message_id: str,
    reason: str
):
    """
    Report an image as spam.
    """
    await interaction.response.defer(ephemeral=True)

    result = await bot.image_detector.report_image(
        message_id=message_id,
        reported_by=str(interaction.user.id),
        report_reason=reason,
        channel_id=str(interaction.channel.id)
    )

    if not result['success']:
        await interaction.followup.send(
            f" {result['reason']}",
            ephemeral=True
        )
        return

    embed = create_embed(
        title="✅ Image Reported",
        description="Thank you for helping keep the community safe!",
        color=discord.Color.green()
    )

    embed.add_field(
        name="Report Count",
        value=f"{result['report_count']}/{result['threshold']}",
        inline=True
    )

    if result['auto_blocked']:
        embed.add_field(
            name="Status",
            value="🚫 Auto-blocked (threshold reached)",
            inline=True
        )
        embed.color = discord.Color.red()

    await interaction.followup.send(embed=embed, ephemeral=True)


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@investigate_command.error
@trust_command.error
async def mod_command_error(interaction: discord.Interaction, error):
    """Handle errors for mod commands."""
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            " You need Moderate Members permission to use this command!",
            ephemeral=True
        )


# ============================================================================
# MAIN
# ============================================================================

def main():
    """
    Main entry point.
    """
    # Validate config
    errors = config.validate_config()
    if errors:
        print("⚠  Configuration Errors:")
        for error in errors:
            print(f"    {error}")
        return

    # Show startup info
    print("=" * 60)
    print("🚀 STARTING TENBOT")
    print("=" * 60)
    print(f"Features Enabled:")
    for feature, enabled in config.FEATURES.items():
        status = "✅" if enabled else ""
        print(f"  {status} {feature}")
    print("=" * 60)

    # Run bot
    try:
        bot.run(config.BOT_TOKEN)
    except discord.LoginFailure:
        print(" Invalid bot token!")
        print("   Please set BOT_TOKEN in your .env file")
    except Exception as e:
        print(f" Error starting bot: {e}")


if __name__ == "__main__":
    main()

