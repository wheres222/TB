"""
Enhanced Achievement System Module
Expanded achievements for diverse participation types
"""

import discord
from discord.ext import commands
from datetime import datetime, time
from typing import Dict, List, Optional

class EnhancedAchievements:
    """
    Manages diverse achievement types beyond message count
    
    Achievement Categories:
    - Time-based (Early Bird, Night Owl)
    - Social (Helpful Member, Conversation Starter)
    - Contribution (Resource Sharer, Thread Creator)
    - Streak-based (Consistency awards)
    - Milestone (First post, 1000th message)
    - Special (Community Champion, Top Contributor)
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        
        # Define all achievements
        self.achievements = self._define_achievements()
        
        # Track achievements channel
        self.achievement_channel_name = "achievements"
    
    def _define_achievements(self) -> Dict[str, Dict]:
        """
        Define all available achievements
        
        Returns:
            Dictionary of achievement definitions
        """
        return {
            # Time-based achievements
            "early_bird": {
                "name": "🌅 Early Bird",
                "description": "Send your first message of the day 30 times",
                "requirement": 30,
                "xp_reward": 500,
                "category": "time"
            },
            "night_owl": {
                "name": "🦉 Night Owl",
                "description": "Be active after midnight 20 times",
                "requirement": 20,
                "xp_reward": 400,
                "category": "time"
            },
            "weekend_warrior": {
                "name": "🎮 Weekend Warrior",
                "description": "Be active every weekend for a month",
                "requirement": 4,  # 4 weekends
                "xp_reward": 600,
                "category": "time"
            },
            
            # Social achievements
            "helpful_member": {
                "name": "🤝 Helpful Member",
                "description": "Receive 50 thank you reactions (👍, ❤️, 🙏)",
                "requirement": 50,
                "xp_reward": 800,
                "category": "social"
            },
            "conversation_starter": {
                "name": "💬 Conversation Starter",
                "description": "Start threads that get 20+ replies (10 times)",
                "requirement": 10,
                "xp_reward": 700,
                "category": "social"
            },
            "community_connector": {
                "name": "🌐 Community Connector",
                "description": "Help 10 new members get started",
                "requirement": 10,
                "xp_reward": 600,
                "category": "social"
            },
            
            # Contribution achievements
            "resource_sharer": {
                "name": "📚 Resource Sharer",
                "description": "Share 100 helpful links or resources",
                "requirement": 100,
                "xp_reward": 1000,
                "category": "contribution"
            },
            "question_answerer": {
                "name": "❓ Question Answerer",
                "description": "Answer 50 questions in help channels",
                "requirement": 50,
                "xp_reward": 900,
                "category": "contribution"
            },
            "thread_master": {
                "name": "🧵 Thread Master",
                "description": "Create 25 discussion threads",
                "requirement": 25,
                "xp_reward": 500,
                "category": "contribution"
            },
            
            # Streak achievements
            "consistent_contributor": {
                "name": "📅 Consistent Contributor",
                "description": "Maintain a 30-day activity streak",
                "requirement": 30,
                "xp_reward": 1500,
                "category": "streak"
            },
            "dedicated_member": {
                "name": "⭐ Dedicated Member",
                "description": "Maintain a 100-day activity streak",
                "requirement": 100,
                "xp_reward": 5000,
                "category": "streak"
            },
            
            # Milestone achievements
            "first_steps": {
                "name": "👶 First Steps",
                "description": "Send your first message in the server",
                "requirement": 1,
                "xp_reward": 100,
                "category": "milestone"
            },
            "century_club": {
                "name": "💯 Century Club",
                "description": "Send 100 messages",
                "requirement": 100,
                "xp_reward": 500,
                "category": "milestone"
            },
            "thousand_words": {
                "name": "📝 Thousand Words",
                "description": "Send 1,000 messages",
                "requirement": 1000,
                "xp_reward": 2000,
                "category": "milestone"
            },
            "ten_thousand_legend": {
                "name": "👑 Ten Thousand Legend",
                "description": "Send 10,000 messages",
                "requirement": 10000,
                "xp_reward": 10000,
                "category": "milestone"
            },
            
            # Voice achievements
            "voice_veteran": {
                "name": "🎤 Voice Veteran",
                "description": "Spend 50 hours in voice channels",
                "requirement": 3000,  # Minutes
                "xp_reward": 2000,
                "category": "voice"
            },
            
            # Special achievements
            "community_champion": {
                "name": "🏆 Community Champion",
                "description": "Reach the top of the monthly leaderboard",
                "requirement": 1,
                "xp_reward": 3000,
                "category": "special"
            },
            "founding_member": {
                "name": "🌟 Founding Member",
                "description": "Be among the first 100 members",
                "requirement": 1,
                "xp_reward": 1000,
                "category": "special"
            },
        }
    
    async def check_achievement(self, user_id: int, guild_id: int, achievement_id: str) -> bool:
        """
        Check if user has already earned an achievement
        
        Args:
            user_id: User to check
            guild_id: Guild context
            achievement_id: Achievement to check
            
        Returns:
            True if already earned
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT 1 FROM user_achievements
                WHERE user_id = ? AND guild_id = ? AND achievement_id = ?
                """,
                (user_id, guild_id, achievement_id)
            )
            result = await cursor.fetchone()
            return result is not None
            
        except Exception as e:
            print(f"✗ Error checking achievement: {e}")
            return False
    
    async def award_achievement(self, member: discord.Member, achievement_id: str):
        """
        Award achievement to user
        
        Args:
            member: Member to award
            achievement_id: Achievement to award
        """
        # Check if achievement exists
        if achievement_id not in self.achievements:
            print(f"✗ Unknown achievement: {achievement_id}")
            return False
        
        # Check if already earned
        if await self.check_achievement(member.id, member.guild.id, achievement_id):
            return False
        
        achievement = self.achievements[achievement_id]
        
        try:
            # Store achievement
            await self.db.execute(
                """
                INSERT INTO user_achievements (
                    user_id, guild_id, achievement_id, earned_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    member.id,
                    member.guild.id,
                    achievement_id,
                    datetime.utcnow().isoformat()
                )
            )
            
            # Award XP
            await self.db.execute(
                "UPDATE users SET xp = xp + ? WHERE user_id = ?",
                (achievement["xp_reward"], member.id)
            )
            
            await self.db.commit()
            
            # Announce achievement
            await self.announce_achievement(member, achievement_id)
            
            print(f"✓ Awarded '{achievement_id}' to {member.name}")
            return True
            
        except Exception as e:
            print(f"✗ Error awarding achievement: {e}")
            return False
    
    async def announce_achievement(self, member: discord.Member, achievement_id: str):
        """
        Announce achievement in achievements channel
        
        Args:
            member: Member who earned it
            achievement_id: Achievement earned
        """
        achievement = self.achievements[achievement_id]
        
        # Find achievements channel
        channel = discord.utils.get(member.guild.text_channels, name=self.achievement_channel_name)
        if not channel:
            return
        
        # Create announcement embed
        embed = discord.Embed(
            title="🎉 Achievement Unlocked!",
            description=f"{member.mention} has earned a new achievement!",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name=achievement["name"],
            value=achievement["description"],
            inline=False
        )
        
        embed.add_field(
            name="XP Reward",
            value=f"+{achievement['xp_reward']} XP",
            inline=True
        )
        
        embed.add_field(
            name="Category",
            value=achievement["category"].title(),
            inline=True
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Total achievements: {await self.get_user_achievement_count(member.id, member.guild.id)}")
        
        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"✗ Error announcing achievement: {e}")
    
    async def get_user_achievement_count(self, user_id: int, guild_id: int) -> int:
        """Get total achievements earned by user"""
        try:
            cursor = await self.db.execute(
                "SELECT COUNT(*) FROM user_achievements WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            result = await cursor.fetchone()
            return result[0] if result else 0
        except:
            return 0
    
    async def get_user_achievements(self, user_id: int, guild_id: int) -> List[str]:
        """Get list of achievements earned by user"""
        try:
            cursor = await self.db.execute(
                """
                SELECT achievement_id FROM user_achievements
                WHERE user_id = ? AND guild_id = ?
                ORDER BY earned_at DESC
                """,
                (user_id, guild_id)
            )
            results = await cursor.fetchall()
            return [row[0] for row in results]
        except:
            return []
    
    # Achievement tracking methods
    
    async def track_early_bird(self, member: discord.Member):
        """Track early morning messages (5am-9am)"""
        now = datetime.utcnow()
        if 5 <= now.hour < 9:
            # Check if this is first message today
            cursor = await self.db.execute(
                """
                SELECT COUNT(*) FROM achievement_progress
                WHERE user_id = ? AND achievement_id = 'early_bird'
                AND date(tracked_at) = date('now')
                """,
                (member.id,)
            )
            count = (await cursor.fetchone())[0]
            
            if count == 0:
                # First message today - increment progress
                await self.increment_progress(member, 'early_bird')
    
    async def track_night_owl(self, member: discord.Member):
        """Track late night activity (12am-4am)"""
        now = datetime.utcnow()
        if 0 <= now.hour < 4:
            # Check if tracked today
            cursor = await self.db.execute(
                """
                SELECT COUNT(*) FROM achievement_progress
                WHERE user_id = ? AND achievement_id = 'night_owl'
                AND date(tracked_at) = date('now')
                """,
                (member.id,)
            )
            count = (await cursor.fetchone())[0]
            
            if count == 0:
                await self.increment_progress(member, 'night_owl')
    
    async def track_helpful_reactions(self, user_id: int, guild_id: int):
        """Track helpful reactions received"""
        # Count thank you reactions
        cursor = await self.db.execute(
            """
            SELECT COUNT(*) FROM message_reactions
            WHERE target_user_id = ? AND guild_id = ?
            AND reaction IN ('👍', '❤️', '🙏', '✅')
            """,
            (user_id, guild_id)
        )
        count = (await cursor.fetchone())[0]
        
        # Check if threshold met
        if count >= 50:
            member = self.bot.get_guild(guild_id).get_member(user_id)
            if member:
                await self.award_achievement(member, 'helpful_member')
    
    async def track_conversation_starter(self, message: discord.Message):
        """Track messages that start conversations"""
        # Check if message has 20+ replies
        if message.reference is None:  # Original message, not a reply
            # Count replies
            replies = 0
            async for msg in message.channel.history(after=message.created_at):
                if msg.reference and msg.reference.message_id == message.id:
                    replies += 1
            
            if replies >= 20:
                await self.increment_progress(message.author, 'conversation_starter')
    
    async def track_resource_share(self, message: discord.Message):
        """Track messages with links (resources)"""
        # Check if message contains URLs
        if 'http://' in message.content or 'https://' in message.content:
            await self.increment_progress(message.author, 'resource_sharer')
    
    async def increment_progress(self, member: discord.Member, achievement_id: str):
        """
        Increment progress toward achievement
        
        Args:
            member: Member making progress
            achievement_id: Achievement to progress
        """
        try:
            # Record progress
            await self.db.execute(
                """
                INSERT INTO achievement_progress (
                    user_id, guild_id, achievement_id, tracked_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    member.id,
                    member.guild.id,
                    achievement_id,
                    datetime.utcnow().isoformat()
                )
            )
            await self.db.commit()
            
            # Check if achievement earned
            cursor = await self.db.execute(
                """
                SELECT COUNT(*) FROM achievement_progress
                WHERE user_id = ? AND guild_id = ? AND achievement_id = ?
                """,
                (member.id, member.guild.id, achievement_id)
            )
            progress = (await cursor.fetchone())[0]
            
            achievement = self.achievements[achievement_id]
            if progress >= achievement["requirement"]:
                await self.award_achievement(member, achievement_id)
            
        except Exception as e:
            print(f"✗ Error incrementing achievement progress: {e}")


class AchievementCommands(commands.Cog):
    """Commands for achievement system"""
    
    def __init__(self, bot, achievement_system):
        self.bot = bot
        self.achievement_system = achievement_system
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track achievement progress from messages"""
        if message.author.bot or not message.guild:
            return
        
        # Track various achievements
        await self.achievement_system.track_early_bird(message.author)
        await self.achievement_system.track_night_owl(message.author)
        await self.achievement_system.track_resource_share(message)
    
    @commands.command(name='achievements')
    async def view_achievements(self, ctx, member: discord.Member = None):
        """
        View earned achievements
        
        Usage: !achievements [@user]
        """
        member = member or ctx.author
        
        earned = await self.achievement_system.get_user_achievements(member.id, ctx.guild.id)
        total = len(self.achievement_system.achievements)
        
        embed = discord.Embed(
            title=f"🏆 Achievements - {member.name}",
            description=f"Unlocked {len(earned)} / {total} achievements",
            color=discord.Color.gold()
        )
        
        # Group by category
        categories = {}
        for ach_id in earned:
            ach = self.achievement_system.achievements[ach_id]
            category = ach["category"]
            if category not in categories:
                categories[category] = []
            categories[category].append(ach["name"])
        
        # Display by category
        for category, names in categories.items():
            embed.add_field(
                name=f"{category.title()} ({len(names)})",
                value='\n'.join(names),
                inline=False
            )
        
        if not earned:
            embed.description = "No achievements earned yet. Keep being active!"
        
        embed.set_thumbnail(url=member.display_avatar.url)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='achievement_list')
    async def list_all_achievements(self, ctx):
        """View all available achievements"""
        embed = discord.Embed(
            title="🏆 All Available Achievements",
            description=f"Total: {len(self.achievement_system.achievements)}",
            color=discord.Color.gold()
        )
        
        # Group by category
        categories = {}
        for ach_id, ach in self.achievement_system.achievements.items():
            category = ach["category"]
            if category not in categories:
                categories[category] = []
            categories[category].append(f"{ach['name']}: {ach['description']} (+{ach['xp_reward']} XP)")
        
        for category, achievements in categories.items():
            embed.add_field(
                name=f"{category.title()} ({len(achievements)})",
                value='\n'.join(achievements[:5]),  # Limit to 5 per category
                inline=False
            )
        
        await ctx.send(embed=embed)


def setup(bot, db):
    """Setup function to initialize enhanced achievements"""
    achievement_system = EnhancedAchievements(bot, db)
    bot.add_cog(AchievementCommands(bot, achievement_system))
    return achievement_system
