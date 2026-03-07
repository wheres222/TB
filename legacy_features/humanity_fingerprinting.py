"""
Behavioral Fingerprinting & Humanity Score System
Feature 1 from beg.txt: Posting patterns, timing, length distributions.
"""

import discord
from discord.ext import commands
from datetime import datetime, timedelta
import math
from collections import defaultdict, deque

class HumanityFingerprinting:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        # Cache for typing timestamps {user_id: timestamp}
        self.typing_starts = {}
        # Message length history per user to detect bot-like consistency
        self.message_lengths = defaultdict(lambda: deque(maxlen=20))

    async def update_humanity_score(self, user_id, guild_id, penalty=None, bonus=None):
        """Update the 0-100 humanity score in the database"""
        cursor = await self.db.execute("SELECT humanity_score FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row: return
        
        current_score = row[0]
        if penalty: current_score = max(0, current_score - penalty)
        if bonus: current_score = min(100, current_score + bonus)
        
        await self.db.execute("UPDATE users SET humanity_score = ? WHERE user_id = ?", (current_score, user_id))
        await self.db.commit()
        return current_score

    async def analyze_message_pattern(self, message):
        """Analyze message for bot-like patterns"""
        if message.author.bot: return
        
        user_id = message.author.id
        content = message.content
        length = len(content)
        now = datetime.utcnow()

        # 1. Typing vs Timestamp Gap (Detects instant-paste bots)
        if user_id in self.typing_starts:
            start_time = self.typing_starts[user_id]
            typing_duration = (now - start_time).total_seconds()
            # If message is long but sent instantly after typing started (or no typing indicator)
            if length > 100 and typing_duration < 1.0:
                await self.update_humanity_score(user_id, message.guild.id, penalty=10)
                # print(f"⚠️ {message.author.name} humanity score -10 (Instant long message)")

        # 2. Message Length Distribution (Entropy)
        # If all messages have nearly identical lengths, it's often a bot pattern
        self.message_lengths[user_id].append(length)
        if len(self.message_lengths[user_id]) >= 10:
            lengths = list(self.message_lengths[user_id])
            avg = sum(lengths) / len(lengths)
            variance = sum((x - avg) ** 2 for x in lengths) / len(lengths)
            if variance < 2.0 and avg > 20: # Very consistent length
                await self.update_humanity_score(user_id, message.guild.id, penalty=5)
                # print(f"⚠️ {message.author.name} humanity score -5 (Repetitive length)")

        # 3. Clean recovery
        # Slowly regain humanity through normal chat (1 point per 5 normal messages)
        await self.update_humanity_score(user_id, message.guild.id, bonus=1)

    async def handle_typing(self, channel, user, when):
        """Track when users start typing"""
        if user.bot: return
        self.typing_starts[user.id] = datetime.utcnow()

class HumanityCommands(commands.Cog):
    def __init__(self, bot, fingerprinting):
        self.bot = bot
        self.fingerprinting = fingerprinting

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot: return
        await self.fingerprinting.analyze_message_pattern(message)

    @commands.Cog.listener()
    async def on_typing(self, channel, user, when):
        await self.fingerprinting.handle_typing(channel, user, when)

    @commands.command(name='humanity')
    @commands.has_permissions(moderate_members=True)
    async def humanity_stats(self, ctx, member: discord.Member = None):
        """Check a user's humanity/bot score"""
        member = member or ctx.author
        cursor = await self.fingerprinting.db.execute("SELECT humanity_score FROM users WHERE user_id = ?", (member.id,))
        row = await cursor.fetchone()
        
        if not row:
            return await ctx.send("User not tracked.")
            
        score = row[0]
        status = "Human ✅" if score > 80 else "Probation ⚠️" if score > 50 else "Suspicious 🤖"
        
        embed = discord.Embed(title=f"👤 Humanity Profile: {member.name}")
        embed.add_field(name="Score", value=f"**{score}/100**")
        embed.add_field(name="Status", value=status)
        embed.set_footer(text="Lower scores trigger stricter auto-mod filters.")
        await ctx.send(embed=embed)

def setup(bot, db):
    fp = HumanityFingerprinting(bot, db)
    bot.add_cog(HumanityCommands(bot, fp))
    return fp
