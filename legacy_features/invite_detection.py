"""
Invite Link Detection Module
Detects and manages Discord invite links to prevent unauthorized server promotion
"""

import discord
from discord.ext import commands
import re
from datetime import datetime
from typing import List, Optional

class InviteLinkDetection:
    """
    Detects Discord invite links and manages whitelist
    
    Features:
    - Detect Discord invite links (discord.gg, discord.com/invite)
    - Whitelist for partner servers
    - Auto-delete unauthorized invites
    - Warn users posting unauthorized invites
    - Track invite violations
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        
        # Regex patterns for Discord invites
        self.invite_patterns = [
            r'discord\.gg/[a-zA-Z0-9]+',
            r'discord\.com/invite/[a-zA-Z0-9]+',
            r'discordapp\.com/invite/[a-zA-Z0-9]+',
        ]
        
        # Compiled regex for performance
        self.invite_regex = re.compile('|'.join(self.invite_patterns), re.IGNORECASE)
        
        # Whitelist of allowed invite codes (partner servers)
        self.whitelisted_invites = set()
        
        # Roles that can post any invite
        self.exempt_role_names = ['Moderator', 'Admin', 'Staff', 'Trusted']
        
        # Load whitelist from database
        self.bot.loop.create_task(self.load_whitelist())
    
    async def load_whitelist(self):
        """Load whitelisted invite codes from database"""
        try:
            cursor = await self.db.execute(
                "SELECT invite_code FROM whitelisted_invites WHERE active = 1"
            )
            results = await cursor.fetchall()
            
            self.whitelisted_invites = {row[0] for row in results}
            print(f"✓ Loaded {len(self.whitelisted_invites)} whitelisted invites")
            
        except Exception as e:
            print(f"✗ Error loading invite whitelist: {e}")
    
    async def add_to_whitelist(self, invite_code: str, added_by: int, reason: str = None):
        """
        Add invite code to whitelist
        
        Args:
            invite_code: The Discord invite code (e.g., 'abc123')
            added_by: User ID who added it
            reason: Optional reason for whitelisting
        """
        try:
            await self.db.execute(
                """
                INSERT INTO whitelisted_invites (invite_code, added_by, reason, added_at, active)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(invite_code) DO UPDATE SET active = 1
                """,
                (invite_code, added_by, reason, datetime.utcnow().isoformat())
            )
            await self.db.commit()
            
            # Add to in-memory set
            self.whitelisted_invites.add(invite_code)
            
            print(f"✓ Added invite '{invite_code}' to whitelist")
            return True
            
        except Exception as e:
            print(f"✗ Error adding invite to whitelist: {e}")
            return False
    
    async def remove_from_whitelist(self, invite_code: str):
        """
        Remove invite code from whitelist
        
        Args:
            invite_code: The Discord invite code to remove
        """
        try:
            await self.db.execute(
                "UPDATE whitelisted_invites SET active = 0 WHERE invite_code = ?",
                (invite_code,)
            )
            await self.db.commit()
            
            # Remove from in-memory set
            self.whitelisted_invites.discard(invite_code)
            
            print(f"✓ Removed invite '{invite_code}' from whitelist")
            return True
            
        except Exception as e:
            print(f"✗ Error removing invite from whitelist: {e}")
            return False
    
    def extract_invite_codes(self, text: str) -> List[str]:
        """
        Extract all Discord invite codes from text
        
        Args:
            text: The text to search
            
        Returns:
            List of invite codes found
        """
        matches = self.invite_regex.findall(text)
        
        # Extract just the code part
        codes = []
        for match in matches:
            # Get the code after the slash
            code = match.split('/')[-1]
            codes.append(code)
        
        return codes
    
    def is_user_exempt(self, member: discord.Member) -> bool:
        """
        Check if user is exempt from invite link restrictions
        
        Args:
            member: The member to check
            
        Returns:
            True if user has exempt role
        """
        # Check if user has any exempt roles
        user_role_names = [role.name for role in member.roles]
        return any(exempt_role in user_role_names for exempt_role in self.exempt_role_names)
    
    async def check_message(self, message: discord.Message) -> bool:
        """
        Check message for unauthorized invite links
        
        Args:
            message: The message to check
            
        Returns:
            True if message contains unauthorized invite, False otherwise
        """
        # Skip if user is exempt
        if self.is_user_exempt(message.author):
            return False
        
        # Extract invite codes from message
        invite_codes = self.extract_invite_codes(message.content)
        
        if not invite_codes:
            return False
        
        # Check if any invites are unauthorized
        unauthorized_invites = [
            code for code in invite_codes 
            if code not in self.whitelisted_invites
        ]
        
        if unauthorized_invites:
            # Unauthorized invite found
            await self.handle_unauthorized_invite(message, unauthorized_invites)
            return True
        
        return False
    
    async def handle_unauthorized_invite(self, message: discord.Message, invite_codes: List[str]):
        """
        Handle message with unauthorized invite link
        
        Args:
            message: The message containing unauthorized invite
            invite_codes: List of unauthorized invite codes
        """
        try:
            # Delete the message
            await message.delete()
            
            # Log the violation
            await self.log_invite_violation(message.author, invite_codes, message.channel)
            
            # Send warning to user
            warning_embed = discord.Embed(
                title="⚠️ Unauthorized Invite Link Detected",
                description=f"{message.author.mention}, posting invite links to other Discord servers is not allowed.",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            
            warning_embed.add_field(
                name="What Happened?",
                value="Your message was deleted because it contained an unauthorized Discord invite link.",
                inline=False
            )
            
            warning_embed.add_field(
                name="What Can I Do?",
                value="• If you need to share a partner server invite, ask a moderator first\n"
                      "• Focus on discussing topics rather than promoting other servers\n"
                      "• Repeated violations may result in timeouts",
                inline=False
            )
            
            warning_embed.set_footer(text=f"User ID: {message.author.id}")
            
            # Send warning in channel (auto-delete after 30 seconds)
            await message.channel.send(embed=warning_embed, delete_after=30)
            
            # Check if user needs punishment
            await self.check_for_punishment(message.author, message.guild)
            
            print(f"✓ Blocked unauthorized invite from {message.author.name}: {invite_codes}")
            
        except discord.Forbidden:
            print(f"✗ Missing permissions to delete invite from {message.author.name}")
        except Exception as e:
            print(f"✗ Error handling unauthorized invite: {e}")
    
    async def log_invite_violation(self, user: discord.Member, invite_codes: List[str], channel: discord.TextChannel):
        """
        Log invite violation to database and mod log
        
        Args:
            user: User who posted the invite
            invite_codes: List of unauthorized invites
            channel: Channel where it was posted
        """
        try:
            # Store in database
            await self.db.execute(
                """
                INSERT INTO invite_violations (
                    user_id, guild_id, channel_id, 
                    invite_codes, timestamp
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.guild.id,
                    channel.id,
                    ','.join(invite_codes),
                    datetime.utcnow().isoformat()
                )
            )
            await self.db.commit()
            
            # Send to mod log
            mod_log = discord.utils.get(user.guild.text_channels, name='mod-logs')
            if mod_log:
                log_embed = discord.Embed(
                    title="🔗 Unauthorized Invite Blocked",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                
                log_embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=True)
                log_embed.add_field(name="Channel", value=channel.mention, inline=True)
                log_embed.add_field(name="Invite Codes", value=', '.join(invite_codes), inline=False)
                
                await mod_log.send(embed=log_embed)
            
        except Exception as e:
            print(f"✗ Error logging invite violation: {e}")
    
    async def check_for_punishment(self, user: discord.Member, guild: discord.Guild):
        """
        Check if user needs punishment for repeat invite violations
        
        Args:
            user: User to check
            guild: Guild where violation occurred
        """
        try:
            # Count violations in last 24 hours
            cursor = await self.db.execute(
                """
                SELECT COUNT(*) FROM invite_violations 
                WHERE user_id = ? 
                AND guild_id = ?
                AND timestamp > datetime('now', '-24 hours')
                """,
                (user.id, guild.id)
            )
            count = (await cursor.fetchone())[0]
            
            # Progressive punishment
            if count >= 3:
                # 3+ violations = timeout
                timeout_duration = 3600  # 1 hour
                await user.timeout(discord.utils.utcnow() + discord.timedelta(seconds=timeout_duration))
                
                # Notify user
                try:
                    await user.send(
                        f"⚠️ You have been timed out for 1 hour in {guild.name} "
                        f"due to repeated unauthorized invite link posting."
                    )
                except:
                    pass
                
                print(f"⏱ Timed out {user.name} for repeated invite violations")
            
        except Exception as e:
            print(f"✗ Error checking punishment for invite violations: {e}")


class InviteLinkCommands(commands.Cog):
    """Commands for managing invite link detection"""
    
    def __init__(self, bot, invite_detection):
        self.bot = bot
        self.invite_detection = invite_detection
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Check all messages for invite links"""
        # Ignore bot messages and DMs
        if message.author.bot or not message.guild:
            return
        
        # Check message for invites
        await self.invite_detection.check_message(message)
    
    @commands.command(name='whitelist_invite')
    @commands.has_permissions(administrator=True)
    async def whitelist_invite(self, ctx, invite_code: str, *, reason: str = None):
        """
        Add an invite code to the whitelist
        
        Usage: !whitelist_invite abc123 Partner server
        """
        success = await self.invite_detection.add_to_whitelist(
            invite_code, 
            ctx.author.id, 
            reason
        )
        
        if success:
            await ctx.send(f"✅ Added invite code `{invite_code}` to whitelist.")
        else:
            await ctx.send(f"❌ Failed to add invite code to whitelist.")
    
    @commands.command(name='unwhitelist_invite')
    @commands.has_permissions(administrator=True)
    async def unwhitelist_invite(self, ctx, invite_code: str):
        """
        Remove an invite code from the whitelist
        
        Usage: !unwhitelist_invite abc123
        """
        success = await self.invite_detection.remove_from_whitelist(invite_code)
        
        if success:
            await ctx.send(f"✅ Removed invite code `{invite_code}` from whitelist.")
        else:
            await ctx.send(f"❌ Failed to remove invite code from whitelist.")
    
    @commands.command(name='list_whitelisted_invites')
    @commands.has_permissions(moderate_members=True)
    async def list_whitelisted_invites(self, ctx):
        """Show all whitelisted invite codes"""
        if not self.invite_detection.whitelisted_invites:
            await ctx.send("No whitelisted invites currently.")
            return
        
        embed = discord.Embed(
            title="Whitelisted Discord Invites",
            description=f"Total: {len(self.invite_detection.whitelisted_invites)}",
            color=discord.Color.blue()
        )
        
        invites_text = '\n'.join([f"• `{code}`" for code in self.invite_detection.whitelisted_invites])
        embed.add_field(name="Invite Codes", value=invites_text or "None", inline=False)
        
        await ctx.send(embed=embed)


def setup(bot, db):
    """Setup function to initialize invite link detection"""
    invite_detection = InviteLinkDetection(bot, db)
    bot.add_cog(InviteLinkCommands(bot, invite_detection))
    return invite_detection
