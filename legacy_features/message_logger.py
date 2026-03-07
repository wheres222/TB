"""
Message Edit/Delete Logging Module
Tracks edited and deleted messages to catch users who spam then delete
"""

import discord
from discord.ext import commands
from datetime import datetime
from typing import Optional

class MessageLogger:
    """
    Logs message edits and deletions
    
    Features:
    - Log all edited messages with before/after content
    - Log all deleted messages
    - Track users who frequently delete messages
    - Send logs to private mod channel
    - Store in database for review
    - Flag suspicious patterns (post then quick delete)
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        
        # Configuration
        self.log_channel_name = "message-logs"
        self.quick_delete_threshold = 10  # Seconds - flag if deleted within this time
        
        # Cache recent messages for deletion tracking
        # Format: {message_id: {'content': str, 'timestamp': datetime, 'author_id': int}}
        self.message_cache = {}
        self.cache_limit = 10000  # Max messages to keep in cache
    
    async def cache_message(self, message: discord.Message):
        """
        Cache message for deletion tracking
        
        Args:
            message: Message to cache
        """
        # Don't cache bot messages or DMs
        if message.author.bot or not message.guild:
            return
        
        # Store message data
        self.message_cache[message.id] = {
            'content': message.content,
            'timestamp': datetime.utcnow(),
            'author_id': message.author.id,
            'channel_id': message.channel.id,
            'attachments': [att.url for att in message.attachments]
        }
        
        # Limit cache size
        if len(self.message_cache) > self.cache_limit:
            # Remove oldest entries
            oldest_keys = sorted(self.message_cache.keys())[:100]
            for key in oldest_keys:
                del self.message_cache[key]
    
    async def log_message_edit(self, before: discord.Message, after: discord.Message):
        """
        Log edited message to mod channel and database
        
        Args:
            before: Message before edit
            after: Message after edit
        """
        # Skip if no content change
        if before.content == after.content:
            return
        
        # Skip bot messages
        if before.author.bot:
            return
        
        try:
            # Store in database
            await self.db.execute(
                """
                INSERT INTO message_edits (
                    message_id, user_id, channel_id, guild_id,
                    content_before, content_after, edited_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    before.id,
                    before.author.id,
                    before.channel.id,
                    before.guild.id,
                    before.content[:2000],  # Limit length
                    after.content[:2000],
                    datetime.utcnow().isoformat()
                )
            )
            await self.db.commit()
            
            # Send to log channel
            log_channel = discord.utils.get(before.guild.text_channels, name=self.log_channel_name)
            if log_channel:
                embed = discord.Embed(
                    title="📝 Message Edited",
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                
                embed.add_field(
                    name="Author",
                    value=f"{before.author.mention} ({before.author.id})",
                    inline=True
                )
                
                embed.add_field(
                    name="Channel",
                    value=before.channel.mention,
                    inline=True
                )
                
                embed.add_field(
                    name="Message Link",
                    value=f"[Jump to Message]({after.jump_url})",
                    inline=True
                )
                
                # Before content
                before_text = before.content[:1000] if before.content else "*[No text content]*"
                embed.add_field(
                    name="Before",
                    value=before_text,
                    inline=False
                )
                
                # After content
                after_text = after.content[:1000] if after.content else "*[No text content]*"
                embed.add_field(
                    name="After",
                    value=after_text,
                    inline=False
                )
                
                embed.set_footer(text=f"Message ID: {before.id}")
                
                await log_channel.send(embed=embed)
            
            print(f"✓ Logged message edit from {before.author.name}")
            
        except Exception as e:
            print(f"✗ Error logging message edit: {e}")
    
    async def log_message_delete(self, message: discord.Message):
        """
        Log deleted message to mod channel and database
        
        Args:
            message: The deleted message
        """
        # Skip bot messages
        if message.author.bot:
            return
        
        try:
            # Calculate time from post to delete
            time_to_delete = None
            was_quick_delete = False
            
            if message.id in self.message_cache:
                cached = self.message_cache[message.id]
                time_to_delete = (datetime.utcnow() - cached['timestamp']).total_seconds()
                was_quick_delete = time_to_delete < self.quick_delete_threshold
            
            # Store in database
            await self.db.execute(
                """
                INSERT INTO message_deletions (
                    message_id, user_id, channel_id, guild_id,
                    content, deleted_at, time_to_delete, quick_delete
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.author.id,
                    message.channel.id,
                    message.guild.id,
                    message.content[:2000],
                    datetime.utcnow().isoformat(),
                    time_to_delete,
                    1 if was_quick_delete else 0
                )
            )
            await self.db.commit()
            
            # If quick delete, track for potential spam behavior
            if was_quick_delete:
                await self.track_quick_delete(message.author, message.guild)
            
            # Send to log channel
            log_channel = discord.utils.get(message.guild.text_channels, name=self.log_channel_name)
            if log_channel:
                embed = discord.Embed(
                    title="🗑️ Message Deleted",
                    color=discord.Color.red() if was_quick_delete else discord.Color.orange(),
                    timestamp=datetime.utcnow()
                )
                
                if was_quick_delete:
                    embed.description = f"⚠️ **Quick Delete** (within {self.quick_delete_threshold}s)"
                
                embed.add_field(
                    name="Author",
                    value=f"{message.author.mention} ({message.author.id})",
                    inline=True
                )
                
                embed.add_field(
                    name="Channel",
                    value=message.channel.mention,
                    inline=True
                )
                
                if time_to_delete:
                    embed.add_field(
                        name="Time to Delete",
                        value=f"{time_to_delete:.1f}s",
                        inline=True
                    )
                
                # Message content
                content_text = message.content[:1500] if message.content else "*[No text content]*"
                embed.add_field(
                    name="Content",
                    value=content_text,
                    inline=False
                )
                
                # Attachments
                if message.attachments:
                    attachment_list = '\n'.join([f"• {att.filename}" for att in message.attachments])
                    embed.add_field(
                        name="Attachments",
                        value=attachment_list,
                        inline=False
                    )
                
                embed.set_footer(text=f"Message ID: {message.id}")
                
                await log_channel.send(embed=embed)
            
            # Remove from cache
            self.message_cache.pop(message.id, None)
            
            print(f"✓ Logged message deletion from {message.author.name}")
            
        except Exception as e:
            print(f"✗ Error logging message deletion: {e}")
    
    async def track_quick_delete(self, user: discord.Member, guild: discord.Guild):
        """
        Track users who frequently quick-delete messages (potential spam)
        
        Args:
            user: User who quick-deleted
            guild: Guild where it happened
        """
        try:
            # Count quick deletes in last hour
            cursor = await self.db.execute(
                """
                SELECT COUNT(*) FROM message_deletions
                WHERE user_id = ?
                AND guild_id = ?
                AND quick_delete = 1
                AND deleted_at > datetime('now', '-1 hour')
                """,
                (user.id, guild.id)
            )
            count = (await cursor.fetchone())[0]
            
            # If 5+ quick deletes in an hour, notify moderators
            if count >= 5:
                mod_log = discord.utils.get(guild.text_channels, name='mod-logs')
                if mod_log:
                    alert_embed = discord.Embed(
                        title="⚠️ Suspicious Quick Delete Pattern",
                        description=f"{user.mention} has quick-deleted {count} messages in the last hour",
                        color=discord.Color.red(),
                        timestamp=datetime.utcnow()
                    )
                    
                    alert_embed.add_field(
                        name="User",
                        value=f"{user.mention}\n{user.name}#{user.discriminator}\nID: {user.id}",
                        inline=False
                    )
                    
                    alert_embed.add_field(
                        name="Recommended Action",
                        value="• Review recent messages in message-logs\n"
                              "• Check for spam patterns\n"
                              "• Consider investigation",
                        inline=False
                    )
                    
                    await mod_log.send(embed=alert_embed)
                    
                    print(f"⚠️ Alerted mods about quick delete pattern from {user.name}")
            
        except Exception as e:
            print(f"✗ Error tracking quick deletes: {e}")
    
    async def get_edit_history(self, user_id: int, guild_id: int, limit: int = 10):
        """
        Get recent edit history for a user
        
        Args:
            user_id: User to check
            guild_id: Guild to check in
            limit: Max number of edits to return
            
        Returns:
            List of edit records
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT message_id, channel_id, content_before, content_after, edited_at
                FROM message_edits
                WHERE user_id = ? AND guild_id = ?
                ORDER BY edited_at DESC
                LIMIT ?
                """,
                (user_id, guild_id, limit)
            )
            return await cursor.fetchall()
            
        except Exception as e:
            print(f"✗ Error getting edit history: {e}")
            return []
    
    async def get_deletion_history(self, user_id: int, guild_id: int, limit: int = 10):
        """
        Get recent deletion history for a user
        
        Args:
            user_id: User to check
            guild_id: Guild to check in
            limit: Max number of deletions to return
            
        Returns:
            List of deletion records
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT message_id, channel_id, content, deleted_at, time_to_delete, quick_delete
                FROM message_deletions
                WHERE user_id = ? AND guild_id = ?
                ORDER BY deleted_at DESC
                LIMIT ?
                """,
                (user_id, guild_id, limit)
            )
            return await cursor.fetchall()
            
        except Exception as e:
            print(f"✗ Error getting deletion history: {e}")
            return []


class MessageLoggerCommands(commands.Cog):
    """Commands for message logging"""
    
    def __init__(self, bot, message_logger):
        self.bot = bot
        self.message_logger = message_logger
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Cache messages for deletion tracking"""
        await self.message_logger.cache_message(message)
    
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Log message edits"""
        await self.message_logger.log_message_edit(before, after)
    
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Log message deletions"""
        await self.message_logger.log_message_delete(message)
    
    @commands.command(name='edit_history')
    @commands.has_permissions(moderate_members=True)
    async def edit_history(self, ctx, member: discord.Member = None, limit: int = 5):
        """
        View edit history for a user
        
        Usage: !edit_history @user 10
        """
        member = member or ctx.author
        
        edits = await self.message_logger.get_edit_history(member.id, ctx.guild.id, limit)
        
        if not edits:
            await ctx.send(f"No edit history found for {member.mention}")
            return
        
        embed = discord.Embed(
            title=f"Edit History - {member.name}",
            description=f"Last {len(edits)} edits",
            color=discord.Color.blue()
        )
        
        for edit in edits[:5]:  # Show max 5 in embed
            message_id, channel_id, before, after, edited_at = edit
            channel = ctx.guild.get_channel(channel_id)
            channel_name = channel.mention if channel else "Unknown"
            
            embed.add_field(
                name=f"Message {message_id}",
                value=f"**Channel:** {channel_name}\n"
                      f"**When:** {edited_at}\n"
                      f"**Before:** {before[:100]}...\n"
                      f"**After:** {after[:100]}...",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='deletion_history')
    @commands.has_permissions(moderate_members=True)
    async def deletion_history(self, ctx, member: discord.Member = None, limit: int = 5):
        """
        View deletion history for a user
        
        Usage: !deletion_history @user 10
        """
        member = member or ctx.author
        
        deletions = await self.message_logger.get_deletion_history(member.id, ctx.guild.id, limit)
        
        if not deletions:
            await ctx.send(f"No deletion history found for {member.mention}")
            return
        
        embed = discord.Embed(
            title=f"Deletion History - {member.name}",
            description=f"Last {len(deletions)} deletions",
            color=discord.Color.red()
        )
        
        for deletion in deletions[:5]:  # Show max 5 in embed
            message_id, channel_id, content, deleted_at, time_to_delete, quick_delete = deletion
            channel = ctx.guild.get_channel(channel_id)
            channel_name = channel.mention if channel else "Unknown"
            
            quick_flag = "⚠️ QUICK DELETE" if quick_delete else ""
            
            embed.add_field(
                name=f"Message {message_id} {quick_flag}",
                value=f"**Channel:** {channel_name}\n"
                      f"**When:** {deleted_at}\n"
                      f"**Time to delete:** {time_to_delete}s\n"
                      f"**Content:** {content[:100]}...",
                inline=False
            )
        
        await ctx.send(embed=embed)


def setup(bot, db):
    """Setup function to initialize message logger"""
    message_logger = MessageLogger(bot, db)
    bot.add_cog(MessageLoggerCommands(bot, message_logger))
    return message_logger
