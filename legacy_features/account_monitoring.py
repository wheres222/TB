"""
New Account Monitoring & Raid Protection Module
Monitors new accounts and detects coordinated raid attempts
"""

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from typing import List, Dict
import asyncio

class AccountMonitoring:
    """
    Monitors new Discord accounts and detects raid patterns
    
    Features:
    - Track account age on join
    - Lower spam thresholds for new accounts
    - Require more time between messages for new accounts
    - Detect unusual join patterns (raids)
    - Temporary lockdown mode during raids
    - Auto-kick suspicious accounts during raids
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        
        # Configuration
        self.new_account_days = 7  # Accounts younger than this are "new"
        self.very_new_account_days = 1  # Extra scrutiny for accounts < 1 day
        
        # New account restrictions
        self.new_account_message_cooldown = 10  # Seconds between messages
        self.new_account_spam_threshold = 3  # Lower spam threshold
        
        # Raid detection
        self.raid_join_threshold = 10  # Members joining within time window
        self.raid_time_window = 60  # Seconds
        self.raid_mode_active = False
        self.raid_mode_duration = 600  # How long raid mode lasts (10 minutes)
        
        # Track recent joins for raid detection
        self.recent_joins = []  # List of (member_id, timestamp) tuples
        
        # Track last message time for new accounts
        self.new_account_last_message = {}  # {user_id: timestamp}
        
        # Start cleanup task
        self.cleanup_task.start()
    
    def is_new_account(self, member: discord.Member) -> bool:
        """
        Check if account is considered "new"
        
        Args:
            member: Member to check
            
        Returns:
            True if account is less than new_account_days old
        """
        account_age_days = (datetime.utcnow() - member.created_at).days
        return account_age_days < self.new_account_days
    
    def is_very_new_account(self, member: discord.Member) -> bool:
        """
        Check if account is very new (extra scrutiny)
        
        Args:
            member: Member to check
            
        Returns:
            True if account is less than 1 day old
        """
        account_age_days = (datetime.utcnow() - member.created_at).days
        return account_age_days < self.very_new_account_days
    
    def get_account_age_days(self, member: discord.Member) -> int:
        """Get account age in days"""
        return (datetime.utcnow() - member.created_at).days
    
    async def check_new_account_message_rate(self, message: discord.Message) -> bool:
        """
        Check if new account is messaging too quickly
        
        Args:
            message: Message to check
            
        Returns:
            True if message should be blocked (rate limited)
        """
        # Only check new accounts
        if not self.is_new_account(message.author):
            return False
        
        user_id = message.author.id
        now = datetime.utcnow()
        
        # Check if user has messaged recently
        if user_id in self.new_account_last_message:
            time_since_last = (now - self.new_account_last_message[user_id]).total_seconds()
            
            if time_since_last < self.new_account_message_cooldown:
                # Too fast - block message
                try:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention}, please wait {self.new_account_message_cooldown}s between messages (new account restriction).",
                        delete_after=10
                    )
                except:
                    pass
                
                return True
        
        # Update last message time
        self.new_account_last_message[user_id] = now
        return False
    
    async def track_join(self, member: discord.Member):
        """
        Track member join for raid detection
        
        Args:
            member: Member who joined
        """
        now = datetime.utcnow()
        
        # Add to recent joins
        self.recent_joins.append((member.id, now))
        
        # Clean old entries
        cutoff = now - timedelta(seconds=self.raid_time_window)
        self.recent_joins = [
            (user_id, timestamp) 
            for user_id, timestamp in self.recent_joins 
            if timestamp > cutoff
        ]
        
        # Check for raid
        if len(self.recent_joins) >= self.raid_join_threshold:
            await self.activate_raid_mode(member.guild)
    
    async def activate_raid_mode(self, guild: discord.Guild):
        """
        Activate raid protection mode
        
        Args:
            guild: Guild being raided
        """
        if self.raid_mode_active:
            return  # Already in raid mode
        
        self.raid_mode_active = True
        
        print(f"🚨 RAID DETECTED in {guild.name}! Activating protection mode...")
        
        # Alert moderators
        mod_log = discord.utils.get(guild.text_channels, name='mod-logs')
        if mod_log:
            alert_embed = discord.Embed(
                title="🚨 RAID DETECTED",
                description=f"**{len(self.recent_joins)} users** joined within {self.raid_time_window} seconds!\n\n"
                            "**Raid Mode Activated:**\n"
                            "• Auto-kicking suspicious new accounts\n"
                            "• Enhanced spam detection\n"
                            "• Increased monitoring\n\n"
                            f"Mode will automatically deactivate in {self.raid_mode_duration // 60} minutes.",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            
            await mod_log.send(embed=alert_embed)
        
        # Auto-kick very new accounts that joined during raid
        kicked_count = 0
        for user_id, join_time in self.recent_joins:
            member = guild.get_member(user_id)
            if member and self.is_very_new_account(member):
                try:
                    await member.kick(reason="Raid protection - very new account")
                    kicked_count += 1
                except:
                    pass
        
        if kicked_count > 0:
            print(f"⚔️ Auto-kicked {kicked_count} suspicious accounts")
        
        # Store raid event in database
        await self.db.execute(
            """
            INSERT INTO raid_events (
                guild_id, detected_at, member_count, 
                accounts_kicked, raid_mode_duration
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                guild.id,
                datetime.utcnow().isoformat(),
                len(self.recent_joins),
                kicked_count,
                self.raid_mode_duration
            )
        )
        await self.db.commit()
        
        # Schedule raid mode deactivation
        await asyncio.sleep(self.raid_mode_duration)
        await self.deactivate_raid_mode(guild)
    
    async def deactivate_raid_mode(self, guild: discord.Guild):
        """
        Deactivate raid protection mode
        
        Args:
            guild: Guild to deactivate raid mode in
        """
        self.raid_mode_active = False
        self.recent_joins = []
        
        print(f"✓ Raid mode deactivated in {guild.name}")
        
        # Notify moderators
        mod_log = discord.utils.get(guild.text_channels, name='mod-logs')
        if mod_log:
            embed = discord.Embed(
                title="✅ Raid Mode Deactivated",
                description="Server has returned to normal operation.",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            await mod_log.send(embed=embed)
    
    async def log_new_account_join(self, member: discord.Member):
        """
        Log when a new account joins for moderator awareness
        
        Args:
            member: New account that joined
        """
        if not self.is_new_account(member):
            return
        
        try:
            account_age_days = self.get_account_age_days(member)
            
            # Different alert levels
            if account_age_days < 1:
                alert_level = "🔴 VERY NEW"
                color = discord.Color.red()
            elif account_age_days < 3:
                alert_level = "🟠 NEW"
                color = discord.Color.orange()
            else:
                alert_level = "🟡 RECENT"
                color = discord.Color.gold()
            
            # Send to mod log
            mod_log = discord.utils.get(member.guild.text_channels, name='mod-logs')
            if mod_log:
                embed = discord.Embed(
                    title=f"{alert_level} Account Joined",
                    color=color,
                    timestamp=datetime.utcnow()
                )
                
                embed.add_field(
                    name="Member",
                    value=f"{member.mention}\n{member.name}#{member.discriminator}",
                    inline=True
                )
                
                embed.add_field(
                    name="Account Age",
                    value=f"{account_age_days} day(s) old\nCreated: <t:{int(member.created_at.timestamp())}:R>",
                    inline=True
                )
                
                embed.add_field(
                    name="ID",
                    value=f"`{member.id}`",
                    inline=True
                )
                
                if self.raid_mode_active:
                    embed.add_field(
                        name="⚠️ Raid Mode Active",
                        value="Extra scrutiny applied",
                        inline=False
                    )
                
                embed.set_thumbnail(url=member.display_avatar.url)
                
                await mod_log.send(embed=embed)
            
            # Store in database
            await self.db.execute(
                """
                INSERT INTO new_account_joins (
                    user_id, guild_id, joined_at, account_age_days, raid_mode
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    member.id,
                    member.guild.id,
                    datetime.utcnow().isoformat(),
                    account_age_days,
                    1 if self.raid_mode_active else 0
                )
            )
            await self.db.commit()
            
        except Exception as e:
            print(f"✗ Error logging new account join: {e}")
    
    @tasks.loop(minutes=5)
    async def cleanup_task(self):
        """Clean up old tracking data"""
        # Clean up last message tracking for users who haven't messaged in 10 minutes
        cutoff = datetime.utcnow() - timedelta(minutes=10)
        to_remove = [
            user_id for user_id, timestamp in self.new_account_last_message.items()
            if timestamp < cutoff
        ]
        for user_id in to_remove:
            del self.new_account_last_message[user_id]
    
    @cleanup_task.before_loop
    async def before_cleanup(self):
        """Wait for bot to be ready before starting cleanup task"""
        await self.bot.wait_until_ready()


class AccountMonitoringCommands(commands.Cog):
    """Commands for account monitoring"""
    
    def __init__(self, bot, account_monitoring):
        self.bot = bot
        self.account_monitoring = account_monitoring
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Track joins and check for raids"""
        # Track join for raid detection
        await self.account_monitoring.track_join(member)
        
        # Log if new account
        await self.account_monitoring.log_new_account_join(member)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Check new account message rate limiting"""
        # Skip bots and DMs
        if message.author.bot or not message.guild:
            return
        
        # Check if new account is messaging too fast
        await self.account_monitoring.check_new_account_message_rate(message)
    
    @commands.command(name='raid_mode')
    @commands.has_permissions(administrator=True)
    async def toggle_raid_mode(self, ctx, action: str = None):
        """
        Manually control raid mode
        
        Usage: 
        !raid_mode on - Activate raid mode
        !raid_mode off - Deactivate raid mode
        !raid_mode status - Check status
        """
        if not action:
            action = "status"
        
        action = action.lower()
        
        if action == "on":
            if self.account_monitoring.raid_mode_active:
                await ctx.send("⚠️ Raid mode is already active!")
            else:
                await self.account_monitoring.activate_raid_mode(ctx.guild)
                await ctx.send("✅ Raid mode manually activated!")
        
        elif action == "off":
            if not self.account_monitoring.raid_mode_active:
                await ctx.send("⚠️ Raid mode is not active!")
            else:
                await self.account_monitoring.deactivate_raid_mode(ctx.guild)
                await ctx.send("✅ Raid mode manually deactivated!")
        
        elif action == "status":
            status = "🔴 ACTIVE" if self.account_monitoring.raid_mode_active else "🟢 INACTIVE"
            
            embed = discord.Embed(
                title="Raid Protection Status",
                color=discord.Color.red() if self.account_monitoring.raid_mode_active else discord.Color.green()
            )
            
            embed.add_field(name="Status", value=status, inline=False)
            embed.add_field(
                name="Recent Joins",
                value=f"{len(self.account_monitoring.recent_joins)} in last {self.account_monitoring.raid_time_window}s",
                inline=True
            )
            embed.add_field(
                name="Threshold",
                value=f"{self.account_monitoring.raid_join_threshold} joins",
                inline=True
            )
            
            await ctx.send(embed=embed)
        
        else:
            await ctx.send("Usage: `!raid_mode [on|off|status]`")
    
    @commands.command(name='account_age')
    @commands.has_permissions(moderate_members=True)
    async def check_account_age(self, ctx, member: discord.Member = None):
        """
        Check account age and restrictions
        
        Usage: !account_age @user
        """
        member = member or ctx.author
        
        age_days = self.account_monitoring.get_account_age_days(member)
        is_new = self.account_monitoring.is_new_account(member)
        is_very_new = self.account_monitoring.is_very_new_account(member)
        
        embed = discord.Embed(
            title=f"Account Age - {member.name}",
            color=discord.Color.red() if is_very_new else (discord.Color.orange() if is_new else discord.Color.green())
        )
        
        embed.add_field(
            name="Account Created",
            value=f"<t:{int(member.created_at.timestamp())}:F>\n(<t:{int(member.created_at.timestamp())}:R>)",
            inline=False
        )
        
        embed.add_field(
            name="Age in Days",
            value=f"{age_days} days",
            inline=True
        )
        
        embed.add_field(
            name="Status",
            value="🔴 Very New" if is_very_new else ("🟠 New" if is_new else "🟢 Established"),
            inline=True
        )
        
        if is_new:
            embed.add_field(
                name="Active Restrictions",
                value=f"• Message cooldown: {self.account_monitoring.new_account_message_cooldown}s\n"
                      f"• Lower spam threshold\n"
                      f"• Enhanced monitoring",
                inline=False
            )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        
        await ctx.send(embed=embed)


def setup(bot, db):
    """Setup function to initialize account monitoring"""
    account_monitoring = AccountMonitoring(bot, db)
    bot.add_cog(AccountMonitoringCommands(bot, account_monitoring))
    return account_monitoring
