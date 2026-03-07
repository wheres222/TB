"""
Gamification System - XP, leveling, streaks, challenges, voice rewards
"""
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, time
from typing import Dict, Optional
import math
import random
import asyncio

class GamificationSystem:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.xp_per_message = 10
        self.xp_cooldown = 60
        self.xp_bonus_streak = 5
        self.level_base = 100
        self.level_multiplier = 1.5
        self.role_rewards = {
            5: "Active Member", 10: "Regular", 20: "Veteran", 30: "Elite", 50: "Legend"
        }
        self.last_xp_gain = {}
        self.daily_streak_check.start()
        self.check_voice_activity.start()
    
    def calculate_level_xp(self, level: int) -> int:
        return int(self.level_base * (self.level_multiplier ** (level - 1)))
    
    def calculate_total_xp_for_level(self, level: int) -> int:
        total = 0
        for lvl in range(1, level):
            total += self.calculate_level_xp(lvl)
        return total
    
    def get_level_from_xp(self, xp: int) -> int:
        level = 1
        total_xp_needed = 0
        while total_xp_needed <= xp:
            total_xp_needed += self.calculate_level_xp(level)
            if total_xp_needed <= xp:
                level += 1
        return level
    
    async def award_xp(self, member: discord.Member, amount: int = None) -> Optional[int]:
        if amount is None: amount = self.xp_per_message
        user_id = member.id
        now = datetime.utcnow()
        if user_id in self.last_xp_gain and (now - self.last_xp_gain[user_id]).total_seconds() < self.xp_cooldown:
            return None
        self.last_xp_gain[user_id] = now
        
        cursor = await self.db.execute("SELECT xp, level, streak_days FROM users WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        if not result: return None
        current_xp, current_level, streak_days = result
        
        streak_bonus = (streak_days or 0) * self.xp_bonus_streak
        new_xp = current_xp + amount + streak_bonus
        new_level = self.get_level_from_xp(new_xp)
        
        await self.db.execute("UPDATE users SET xp = ?, level = ?, last_activity = ? WHERE user_id = ?", (new_xp, new_level, now.isoformat(), user_id))
        await self.db.commit()
        
        if new_level > current_level:
            await self.handle_level_up(member, new_level)
            return new_level
        return None
    
    async def handle_level_up(self, member: discord.Member, new_level: int):
        channel = discord.utils.get(member.guild.text_channels, name='level-ups')
        if channel:
            embed = discord.Embed(
                title="🎉 Level Up!",
                description=f"{member.mention} has reached **Level {new_level}**!",
                timestamp=datetime.utcnow()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)
        if new_level in self.role_rewards:
            await self.award_role_reward(member, new_level)
            
    async def award_role_reward(self, member: discord.Member, level: int):
        role_name = self.role_rewards.get(level)
        if not role_name: return
        role = discord.utils.get(member.guild.roles, name=role_name)
        if not role:
            colors = {5: discord.Color.green(), 10: discord.Color.blue(), 20: discord.Color.purple(), 30: discord.Color.orange(), 50: discord.Color.gold()}
            try:
                role = await member.guild.create_role(name=role_name, color=colors.get(level, discord.Color.default()))
            except: return
        try: await member.add_roles(role)
        except: pass

    async def update_streak(self, user_id: int):
        cursor = await self.db.execute("SELECT last_activity, streak_days, streak_last_updated FROM users WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        if not result: return
        last, streak, last_updated = result
        if not last: return
        last_date = datetime.fromisoformat(last).date()
        today = datetime.utcnow().date()
        
        if last_updated:
            if datetime.fromisoformat(last_updated).date() == today: return
            
        if last_date == today:
            new_streak = 1
            if last_updated:
                 if datetime.fromisoformat(last_updated).date() == today - timedelta(days=1):
                     new_streak = (streak or 0) + 1
            await self.db.execute("UPDATE users SET streak_days = ?, streak_last_updated = ? WHERE user_id = ?", (new_streak, datetime.utcnow().isoformat(), user_id))
            await self.db.commit()

    @tasks.loop(time=time(hour=0, minute=0))
    async def daily_streak_check(self):
        try:
            await self.db.execute("UPDATE users SET streak_days = 0 WHERE date(last_activity) < date('now', '-1 day') AND streak_days > 0")
            await self.db.commit()
            
            # Reset daily challenges logic implies new challenge will be generated on demand, no separate reset needed but we could clear progress if desired.
            # For this implementation, we rely on 'challenge_date' valid check.
        except: pass

    @daily_streak_check.before_loop
    async def before_streak_check(self):
        await self.bot.wait_until_ready()

    # --- Daily Challenges ---
    async def get_daily_challenge(self, guild_id):
        today = datetime.utcnow().date().isoformat()
        cursor = await self.db.execute("SELECT id, description, challenge_type, target_count, xp_reward FROM daily_challenges WHERE guild_id = ? AND challenge_date = ?", (guild_id, today))
        challenge = await cursor.fetchone()
        if challenge: return challenge
        
        types = [("message", "Send {n} messages", 10, 50), ("voice", "Spend {n} mins in voice", 15, 60), ("react", "React to {n} messages", 5, 30)]
        c_type, templ, target, reward = random.choice(types)
        await self.db.execute("INSERT INTO daily_challenges (guild_id, description, challenge_type, target_count, xp_reward, challenge_date) VALUES (?, ?, ?, ?, ?, ?)", (guild_id, templ.format(n=target), c_type, target, reward, today))
        await self.db.commit()
        
        # Get ID
        cursor = await self.db.execute("SELECT id, description, challenge_type, target_count, xp_reward FROM daily_challenges WHERE guild_id = ? AND challenge_date = ?", (guild_id, today))
        return await cursor.fetchone()

    async def update_challenge(self, user_id, guild_id, c_type, amount=1):
        chal = await self.get_daily_challenge(guild_id)
        if not chal: return
        cid, desc, stored_type, target, reward = chal
        if stored_type != c_type: return
        
        await self.db.execute("INSERT INTO user_challenges (user_id, challenge_id, progress) VALUES (?, ?, ?) ON CONFLICT(user_id, challenge_id) DO UPDATE SET progress = progress + ?", (user_id, cid, amount, amount))
        
        cursor = await self.db.execute("SELECT progress, completed FROM user_challenges WHERE user_id = ? AND challenge_id = ?", (user_id, cid))
        prog, completed = await cursor.fetchone()
        
        if not completed and prog >= target:
            await self.db.execute("UPDATE user_challenges SET completed = 1, completed_at = ? WHERE user_id = ? AND challenge_id = ?", (datetime.utcnow().isoformat(), user_id, cid))
            # Award reward
            member = self.bot.get_guild(guild_id).get_member(user_id)
            if member: await self.award_xp(member, reward)
        await self.db.commit()

    # --- Voice Rewards ---
    @tasks.loop(minutes=1)
    async def check_voice_activity(self):
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if member.bot: continue
                    xp = 5
                    if not member.voice.self_mute and not member.voice.mute: xp += 5 # Speaking bonus
                    await self.award_xp(member, xp)
                    await self.update_challenge(member.id, guild.id, 'voice', 1)
                    # Update stats
                    await self.db.execute("INSERT INTO voice_stats (user_id, guild_id, total_minutes) VALUES (?, ?, 1) ON CONFLICT(user_id, guild_id) DO UPDATE SET total_minutes = total_minutes + 1", (member.id, guild.id))
            await self.db.commit()
    
    @check_voice_activity.before_loop
    async def before_voice(self):
        await self.bot.wait_until_ready()

    async def get_leaderboard(self, guild_id, limit=10):
        cursor = await self.db.execute("SELECT user_id, xp, level, streak_days FROM users ORDER BY xp DESC LIMIT ?", (limit,))
        return await cursor.fetchall()

class GamificationCommands(commands.Cog):
    def __init__(self, bot, gamification):
        self.bot = bot
        self.gamification = gamification
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return
        await self.gamification.award_xp(message.author)
        await self.gamification.update_streak(message.author.id)
        await self.gamification.update_challenge(message.author.id, message.guild.id, 'message', 1)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot or not reaction.message.guild: return
        await self.gamification.update_challenge(user.id, reaction.message.guild.id, 'react', 1)

    @commands.command(name='daily_challenge')
    async def daily_challenge(self, ctx):
        chal = await self.gamification.get_daily_challenge(ctx.guild.id)
        cid, desc, ctype, target, reward = chal
        
        cursor = await self.gamification.db.execute("SELECT progress, completed FROM user_challenges WHERE user_id = ? AND challenge_id = ?", (ctx.author.id, cid))
        res = await cursor.fetchone()
        prog, completed = res if res else (0, 0)
        
        embed = discord.Embed(title="📅 Daily Challenge")
        embed.description = f"**{desc}**\nReward: {reward} XP"
        embed.add_field(name="Your Progress", value=f"{prog}/{target} {'✅' if completed else ''}")
        await ctx.send(embed=embed)

    @commands.command(name='voice_stats')
    async def voice_stats(self, ctx):
        cursor = await self.gamification.db.execute("SELECT total_minutes FROM voice_stats WHERE user_id = ? AND guild_id = ?", (ctx.author.id, ctx.guild.id))
        res = await cursor.fetchone()
        mins = res[0] if res else 0
        embed = discord.Embed(title="🎤 Voice Stats")
        embed.add_field(name="Total Time", value=f"{mins} minutes")
        await ctx.send(embed=embed)

    @commands.command(name='rank')
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        cursor = await self.gamification.db.execute("SELECT xp, level, streak_days FROM users WHERE user_id = ?", (member.id,))
        result = await cursor.fetchone()
        if not result: return await ctx.send("User not found.")
        xp, level, streak = result
        
        next_xp = self.gamification.calculate_total_xp_for_level(level + 1)
        curr_base = self.gamification.calculate_total_xp_for_level(level)
        prog = xp - curr_base
        needed = next_xp - curr_base
        pct = (prog / needed) * 100
        bar = "█" * int(pct/5) + "░" * (20 - int(pct/5))
        
        embed = discord.Embed(title=f"📊 Rank - {member.name}")
        embed.add_field(name="Level", value=str(level))
        embed.add_field(name="XP", value=f"{xp:,}")
        embed.add_field(name="Progress", value=f"{bar} {pct:.1f}%", inline=False)
        if streak: embed.add_field(name="Streak", value=f"{streak} days")
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name='leaderboard')
    async def leaderboard(self, ctx, limit: int = 10):
        lb = await self.gamification.get_leaderboard(ctx.guild.id, min(limit, 25))
        embed = discord.Embed(title="🏆 Leaderboard")
        entries = []
        for i, (uid, xp, lvl, streak) in enumerate(lb, 1):
            m = ctx.guild.get_member(uid)
            name = m.name if m else "Unknown"
            entries.append(f"{i}. {name} - Lvl {lvl} - {xp:,} XP {'🔥'+str(streak) if streak else ''}")
        embed.description = "\n".join(entries)
        await ctx.send(embed=embed)
        
    @commands.command(name='leaderboard_weekly')
    async def leaderboard_weekly(self, ctx, limit: int = 10):
        rows = await self.gamification.db.execute_fetchall("SELECT user_id, xp, level, streak_days FROM users WHERE date(last_activity) >= date('now', '-7 days') ORDER BY xp DESC LIMIT ?", (min(limit, 25),))
        embed = discord.Embed(title="🏆 Weekly Leaderboard")
        entries = []
        for i, (uid, xp, lvl, streak) in enumerate(rows, 1):
            m = ctx.guild.get_member(uid)
            entries.append(f"{i}. {m.name if m else 'Unknown'} - {xp:,} XP")
        embed.description = "\n".join(entries)
        await ctx.send(embed=embed)

    @commands.command(name='leaderboard_streak')
    async def leaderboard_streak(self, ctx, limit: int = 10):
        rows = await self.gamification.db.execute_fetchall("SELECT user_id, xp, level, streak_days FROM users WHERE streak_days > 0 ORDER BY streak_days DESC LIMIT ?", (min(limit, 25),))
        embed = discord.Embed(title="🔥 Streak Leaderboard")
        entries = []
        for i, (uid, xp, lvl, streak) in enumerate(rows, 1):
            m = ctx.guild.get_member(uid)
            entries.append(f"{i}. {m.name if m else 'Unknown'} - {streak} Days")
        embed.description = "\n".join(entries)
        await ctx.send(embed=embed)

def setup(bot, db):
    g = GamificationSystem(bot, db)
    bot.add_cog(GamificationCommands(bot, g))
    return g
