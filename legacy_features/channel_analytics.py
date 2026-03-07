"""
Channel Activity Analytics Module
Tracks and analyzes activity across all 48 channels
"""

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import json

class ChannelAnalytics:
    """
    Analyzes channel activity patterns
    
    Features:
    - Messages per channel per day/week
    - Unique active users per channel
    - Peak activity times per channel
    - Channel growth trends
    - Suggestions for merging dead channels
    - Activity heatmaps
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        
        # Configuration
        self.dead_channel_threshold_days = 7  # No activity for 7 days = dead
        self.low_activity_threshold = 10  # Less than 10 messages/day = low activity
        
        # Start daily analytics task
        self.daily_analytics_task.start()
    
    async def track_message(self, message: discord.Message):
        """
        Track message for analytics
        
        Args:
            message: Message to track
        """
        if not message.guild or message.author.bot:
            return
        
        try:
            # Store message activity
            await self.db.execute(
                """
                INSERT INTO channel_activity (
                    channel_id, guild_id, user_id, 
                    message_count, date
                ) VALUES (?, ?, ?, 1, date('now'))
                ON CONFLICT(channel_id, date) DO UPDATE SET
                    message_count = message_count + 1
                """,
                (message.channel.id, message.guild.id, message.author.id)
            )
            await self.db.commit()
            
        except Exception as e:
            print(f"✗ Error tracking channel activity: {e}")
    
    async def get_channel_stats(self, channel_id: int, days: int = 7) -> Dict:
        """
        Get activity statistics for a specific channel
        
        Args:
            channel_id: Channel to analyze
            days: Number of days to look back
            
        Returns:
            Dictionary with statistics
        """
        try:
            # Total messages
            cursor = await self.db.execute(
                """
                SELECT SUM(message_count) FROM channel_activity
                WHERE channel_id = ?
                AND date >= date('now', ?)
                """,
                (channel_id, f'-{days} days')
            )
            total_messages = (await cursor.fetchone())[0] or 0
            
            # Unique users
            cursor = await self.db.execute(
                """
                SELECT COUNT(DISTINCT user_id) FROM channel_activity
                WHERE channel_id = ?
                AND date >= date('now', ?)
                """,
                (channel_id, f'-{days} days')
            )
            unique_users = (await cursor.fetchone())[0] or 0
            
            # Average messages per day
            avg_per_day = total_messages / days if days > 0 else 0
            
            # Most active day
            cursor = await self.db.execute(
                """
                SELECT date, SUM(message_count) as count
                FROM channel_activity
                WHERE channel_id = ?
                AND date >= date('now', ?)
                GROUP BY date
                ORDER BY count DESC
                LIMIT 1
                """,
                (channel_id, f'-{days} days')
            )
            most_active = await cursor.fetchone()
            
            return {
                'total_messages': total_messages,
                'unique_users': unique_users,
                'avg_per_day': avg_per_day,
                'most_active_day': most_active[0] if most_active else None,
                'most_active_count': most_active[1] if most_active else 0
            }
            
        except Exception as e:
            print(f"✗ Error getting channel stats: {e}")
            return {}
    
    async def get_guild_channel_rankings(self, guild_id: int, days: int = 7) -> List[Tuple]:
        """
        Get all channels ranked by activity
        
        Args:
            guild_id: Guild to analyze
            days: Number of days to look back
            
        Returns:
            List of (channel_id, message_count, unique_users) sorted by activity
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT 
                    channel_id,
                    SUM(message_count) as total_messages,
                    COUNT(DISTINCT user_id) as unique_users
                FROM channel_activity
                WHERE guild_id = ?
                AND date >= date('now', ?)
                GROUP BY channel_id
                ORDER BY total_messages DESC
                """,
                (guild_id, f'-{days} days')
            )
            return await cursor.fetchall()
            
        except Exception as e:
            print(f"✗ Error getting channel rankings: {e}")
            return []
    
    async def identify_dead_channels(self, guild: discord.Guild) -> List[discord.TextChannel]:
        """
        Identify channels with no recent activity
        
        Args:
            guild: Guild to check
            
        Returns:
            List of dead channels
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT channel_id
                FROM channel_activity
                WHERE guild_id = ?
                AND date < date('now', ?)
                GROUP BY channel_id
                """,
                (guild.id, f'-{self.dead_channel_threshold_days} days')
            )
            dead_channel_ids = [row[0] for row in await cursor.fetchall()]
            
            # Get channel objects
            dead_channels = []
            for channel in guild.text_channels:
                if channel.id in dead_channel_ids or channel.id not in [c.id for c in guild.text_channels]:
                    dead_channels.append(channel)
            
            return dead_channels
            
        except Exception as e:
            print(f"✗ Error identifying dead channels: {e}")
            return []
    
    async def get_peak_activity_hours(self, channel_id: int, days: int = 7) -> Dict[int, int]:
        """
        Get peak activity hours for a channel
        
        Args:
            channel_id: Channel to analyze
            days: Number of days to look back
            
        Returns:
            Dictionary of {hour: message_count}
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT 
                    CAST(strftime('%H', timestamp) AS INTEGER) as hour,
                    COUNT(*) as count
                FROM messages
                WHERE channel_id = ?
                AND timestamp >= datetime('now', ?)
                GROUP BY hour
                ORDER BY count DESC
                """,
                (channel_id, f'-{days} days')
            )
            results = await cursor.fetchall()
            return {hour: count for hour, count in results}
            
        except Exception as e:
            print(f"✗ Error getting peak hours: {e}")
            return {}
    
    @tasks.loop(hours=24)
    async def daily_analytics_task(self):
        """Run daily analytics and generate reports"""
        for guild in self.bot.guilds:
            await self.generate_daily_report(guild)
    
    @daily_analytics_task.before_loop
    async def before_analytics(self):
        """Wait for bot to be ready"""
        await self.bot.wait_until_ready()
    
    async def generate_daily_report(self, guild: discord.Guild):
        """
        Generate daily activity report
        
        Args:
            guild: Guild to report on
        """
        try:
            # Get channel rankings
            rankings = await self.get_guild_channel_rankings(guild.id, days=1)
            
            if not rankings:
                return
            
            # Find analytics channel
            analytics_channel = discord.utils.get(guild.text_channels, name='analytics')
            if not analytics_channel:
                return
            
            # Create report embed
            embed = discord.Embed(
                title="📊 Daily Channel Activity Report",
                description=f"Activity summary for {datetime.utcnow().strftime('%B %d, %Y')}",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            # Top 10 most active channels
            top_channels = []
            for channel_id, messages, users in rankings[:10]:
                channel = guild.get_channel(channel_id)
                if channel:
                    top_channels.append(f"{channel.mention}: {messages} messages, {users} users")
            
            if top_channels:
                embed.add_field(
                    name="🔥 Top Active Channels",
                    value='\n'.join(top_channels),
                    inline=False
                )
            
            # Total server activity
            total_messages = sum(msg_count for _, msg_count, _ in rankings)
            total_active_users = len(set(user for _, _, user in rankings))
            
            embed.add_field(
                name="Server Totals",
                value=f"**Messages:** {total_messages}\n**Active Users:** {total_active_users}",
                inline=True
            )
            
            # Identify low activity channels
            low_activity = []
            for channel_id, messages, users in rankings:
                if messages < self.low_activity_threshold:
                    channel = guild.get_channel(channel_id)
                    if channel:
                        low_activity.append(f"{channel.mention}: {messages} messages")
            
            if low_activity:
                embed.add_field(
                    name="⚠️ Low Activity Channels",
                    value='\n'.join(low_activity[:5]),
                    inline=False
                )
            
            # Send report
            await analytics_channel.send(embed=embed)
            
            print(f"✓ Generated daily analytics report for {guild.name}")
            
        except Exception as e:
            print(f"✗ Error generating daily report: {e}")
    
    async def suggest_channel_merges(self, guild: discord.Guild) -> List[Tuple[str, str, str]]:
        """
        Suggest channels that could be merged
        
        Args:
            guild: Guild to analyze
            
        Returns:
            List of (channel1, channel2, reason) suggestions
        """
        suggestions = []
        
        # Get all channels with low activity
        rankings = await self.get_guild_channel_rankings(guild.id, days=7)
        low_activity_channels = [
            guild.get_channel(ch_id) 
            for ch_id, msgs, _ in rankings 
            if msgs < self.low_activity_threshold * 7  # Less than threshold per week
        ]
        
        # Find similar named channels
        for i, channel1 in enumerate(low_activity_channels):
            if not channel1:
                continue
            for channel2 in low_activity_channels[i+1:]:
                if not channel2:
                    continue
                
                # Check for similar names or categories
                if (channel1.category == channel2.category or
                    any(word in channel2.name for word in channel1.name.split('-'))):
                    
                    suggestions.append((
                        channel1.name,
                        channel2.name,
                        "Similar topics and low activity"
                    ))
        
        return suggestions


class ChannelAnalyticsCommands(commands.Cog):
    """Commands for channel analytics"""
    
    def __init__(self, bot, analytics):
        self.bot = bot
        self.analytics = analytics
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track messages for analytics"""
        await self.analytics.track_message(message)
    
    @commands.command(name='channel_stats')
    @commands.has_permissions(moderate_members=True)
    async def channel_stats(self, ctx, channel: discord.TextChannel = None, days: int = 7):
        """
        View detailed channel statistics
        
        Usage: !channel_stats #channel 30
        """
        channel = channel or ctx.channel
        
        stats = await self.analytics.get_channel_stats(channel.id, days)
        
        embed = discord.Embed(
            title=f"📊 Channel Statistics - #{channel.name}",
            description=f"Activity over the last {days} days",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Total Messages",
            value=f"{stats.get('total_messages', 0):,}",
            inline=True
        )
        
        embed.add_field(
            name="Unique Users",
            value=f"{stats.get('unique_users', 0):,}",
            inline=True
        )
        
        embed.add_field(
            name="Avg per Day",
            value=f"{stats.get('avg_per_day', 0):.1f}",
            inline=True
        )
        
        if stats.get('most_active_day'):
            embed.add_field(
                name="Most Active Day",
                value=f"{stats['most_active_day']}\n{stats['most_active_count']} messages",
                inline=False
            )
        
        # Activity status
        avg = stats.get('avg_per_day', 0)
        if avg == 0:
            status = "🔴 Dead"
        elif avg < 10:
            status = "🟠 Low"
        elif avg < 50:
            status = "🟡 Moderate"
        else:
            status = "🟢 High"
        
        embed.add_field(
            name="Activity Status",
            value=status,
            inline=True
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='channel_rankings')
    @commands.has_permissions(moderate_members=True)
    async def channel_rankings(self, ctx, days: int = 7):
        """
        View channel activity rankings
        
        Usage: !channel_rankings 30
        """
        rankings = await self.analytics.get_guild_channel_rankings(ctx.guild.id, days)
        
        if not rankings:
            await ctx.send("No activity data available.")
            return
        
        embed = discord.Embed(
            title=f"🏆 Channel Activity Rankings",
            description=f"Activity over the last {days} days",
            color=discord.Color.gold()
        )
        
        # Top 15 channels
        for i, (channel_id, messages, users) in enumerate(rankings[:15], 1):
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                embed.add_field(
                    name=f"#{i} - {channel.name}",
                    value=f"**{messages:,}** messages\n{users} unique users",
                    inline=True
                )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='dead_channels')
    @commands.has_permissions(administrator=True)
    async def list_dead_channels(self, ctx):
        """View channels with no recent activity"""
        dead_channels = await self.analytics.identify_dead_channels(ctx.guild)
        
        if not dead_channels:
            await ctx.send("✅ All channels have recent activity!")
            return
        
        embed = discord.Embed(
            title="💀 Dead Channels",
            description=f"Channels with no activity in {self.analytics.dead_channel_threshold_days} days",
            color=discord.Color.red()
        )
        
        channel_list = [f"• {channel.mention} ({channel.category.name if channel.category else 'No category'})" 
                       for channel in dead_channels]
        
        embed.add_field(
            name=f"Found {len(dead_channels)} dead channels",
            value='\n'.join(channel_list[:20]),  # Limit to 20
            inline=False
        )
        
        embed.add_field(
            name="Recommendation",
            value="Consider archiving or repurposing these channels",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='suggest_merges')
    @commands.has_permissions(administrator=True)
    async def suggest_merges(self, ctx):
        """Get suggestions for merging low-activity channels"""
        suggestions = await self.analytics.suggest_channel_merges(ctx.guild)
        
        if not suggestions:
            await ctx.send("No merge suggestions at this time.")
            return
        
        embed = discord.Embed(
            title="🔀 Channel Merge Suggestions",
            description="These channels have low activity and similar topics",
            color=discord.Color.orange()
        )
        
        for ch1, ch2, reason in suggestions[:10]:
            embed.add_field(
                name=f"#{ch1} + #{ch2}",
                value=reason,
                inline=False
            )
        
        await ctx.send(embed=embed)


def setup(bot, db):
    """Setup function to initialize channel analytics"""
    analytics = ChannelAnalytics(bot, db)
    bot.add_cog(ChannelAnalyticsCommands(bot, analytics))
    return analytics
