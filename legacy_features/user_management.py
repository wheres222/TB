"""
User Management & Cleanup Tools
Voice channel management, bulk operations, and administrative utilities
"""

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from typing import List, Optional
import asyncio

class UserManagement:
    """
    Advanced user management tools
    
    Features:
    - Voice channel bulk operations
    - Inactive member cleanup
    - Bulk role management
    - User purge tools
    - Activity tracking
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        
        # Configuration
        self.inactive_threshold_days = 30  # Tag as inactive
        self.cleanup_threshold_days = 60   # Auto-remove
        
        # Start cleanup task
        self.check_inactive_members.start()
    
    async def move_all_members(
        self,
        from_channel: discord.VoiceChannel,
        to_channel: discord.VoiceChannel,
        exclude_ids: List[int] = None
    ) -> int:
        """
        Move all members from one voice channel to another
        
        Returns:
            Number of members moved
        """
        exclude_ids = exclude_ids or []
        moved_count = 0
        
        # Get all members in source channel
        members = list(from_channel.members)
        
        for member in members:
            if member.id in exclude_ids:
                continue
            
            try:
                await member.move_to(to_channel)
                moved_count += 1
                await asyncio.sleep(0.5)  # Rate limit protection
            except Exception as e:
                print(f"✗ Error moving {member.name}: {e}")
        
        return moved_count
    
    async def disconnect_all_members(self, voice_channel: discord.VoiceChannel) -> int:
        """
        Disconnect all members from a voice channel
        
        Returns:
            Number of members disconnected
        """
        disconnected_count = 0
        members = list(voice_channel.members)
        
        for member in members:
            try:
                await member.move_to(None)  # Disconnect
                disconnected_count += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"✗ Error disconnecting {member.name}: {e}")
        
        return disconnected_count
    
    async def get_inactive_members(
        self,
        guild: discord.Guild,
        days: int = 30
    ) -> List[discord.Member]:
        """Get members inactive for specified days"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            cursor = await self.db.execute(
                """
                SELECT user_id FROM users
                WHERE guild_id = ?
                AND (last_activity IS NULL OR datetime(last_activity) < datetime(?))
                """,
                (guild.id, cutoff_date.isoformat())
            )
            results = await cursor.fetchall()
            
            inactive_members = []
            for (user_id,) in results:
                member = guild.get_member(user_id)
                if member and not member.bot:
                    inactive_members.append(member)
            
            return inactive_members
            
        except Exception as e:
            print(f"✗ Error getting inactive members: {e}")
            return []
    
    async def cleanup_inactive_members(
        self,
        guild: discord.Guild,
        days: int = 60,
        dry_run: bool = True
    ) -> int:
        """
        Remove members inactive for specified days
        
        Returns:
            Number of members removed
        """
        inactive_members = await self.get_inactive_members(guild, days)
        removed_count = 0
        
        for member in inactive_members:
            # Check if member has opted out
            cursor = await self.db.execute(
                "SELECT cleanup_opt_out FROM users WHERE user_id = ?",
                (member.id,)
            )
            result = await cursor.fetchone()
            
            if result and result[0]:
                continue  # Skip opted-out members
            
            if dry_run:
                print(f"[DRY RUN] Would remove: {member.name}")
                removed_count += 1
            else:
                try:
                    # Send DM notification
                    try:
                        embed = discord.Embed(
                            title="⚠️ Removed from Server",
                            description=f"You've been removed from **{guild.name}** due to {days} days of inactivity.",
                            color=discord.Color.orange()
                        )
                        embed.add_field(
                            name="Want to rejoin?",
                            value="You're welcome back anytime! Just use the invite link.",
                            inline=False
                        )
                        await member.send(embed=embed)
                    except:
                        pass  # DMs disabled
                    
                    # Remove member
                    await member.kick(reason=f"Inactive for {days} days")
                    removed_count += 1
                    print(f"✓ Removed inactive member: {member.name}")
                    
                except Exception as e:
                    print(f"✗ Error removing {member.name}: {e}")
        
        return removed_count
    
    async def bulk_add_role(
        self,
        members: List[discord.Member],
        role: discord.Role
    ) -> int:
        """
        Add role to multiple members
        
        Returns:
            Number of members updated
        """
        updated_count = 0
        
        for member in members:
            if role in member.roles:
                continue
            
            try:
                await member.add_roles(role, reason="Bulk role assignment")
                updated_count += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"✗ Error adding role to {member.name}: {e}")
        
        return updated_count
    
    async def bulk_remove_role(
        self,
        members: List[discord.Member],
        role: discord.Role
    ) -> int:
        """
        Remove role from multiple members
        
        Returns:
            Number of members updated
        """
        updated_count = 0
        
        for member in members:
            if role not in member.roles:
                continue
            
            try:
                await member.remove_roles(role, reason="Bulk role removal")
                updated_count += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"✗ Error removing role from {member.name}: {e}")
        
        return updated_count
    
    async def purge_bots(self, guild: discord.Guild, exclude_ids: List[int] = None) -> int:
        """
        Remove all bot accounts except excluded ones
        
        Returns:
            Number of bots removed
        """
        exclude_ids = exclude_ids or [self.bot.user.id]
        removed_count = 0
        
        for member in guild.members:
            if not member.bot or member.id in exclude_ids:
                continue
            
            try:
                await member.kick(reason="Bot purge")
                removed_count += 1
                print(f"✓ Removed bot: {member.name}")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"✗ Error removing bot {member.name}: {e}")
        
        return removed_count
    
    async def clone_permissions(
        self,
        source_member: discord.Member,
        target_member: discord.Member
    ) -> bool:
        """Clone roles from source to target member"""
        try:
            # Get roles (excluding @everyone)
            roles = [role for role in source_member.roles if role.name != "@everyone"]
            
            # Add roles to target
            await target_member.add_roles(*roles, reason=f"Cloned from {source_member.name}")
            return True
            
        except Exception as e:
            print(f"✗ Error cloning permissions: {e}")
            return False
    
    @tasks.loop(hours=24)
    async def check_inactive_members(self):
        """Daily check for inactive members"""
        try:
            for guild in self.bot.guilds:
                # Get inactive members (30 days)
                inactive_30 = await self.get_inactive_members(guild, 30)
                
                if inactive_30:
                    # Tag them with inactive role
                    inactive_role = discord.utils.get(guild.roles, name="Inactive")
                    
                    if not inactive_role:
                        inactive_role = await guild.create_role(
                            name="Inactive",
                            color=discord.Color.light_gray(),
                            reason="Auto-tag inactive members"
                        )
                    
                    await self.bulk_add_role(inactive_30, inactive_role)
                    print(f"✓ Tagged {len(inactive_30)} inactive members in {guild.name}")
                
                # Get very inactive members (60 days) - send warning
                inactive_60 = await self.get_inactive_members(guild, 60)
                
                for member in inactive_60:
                    try:
                        embed = discord.Embed(
                            title="⚠️ Inactivity Warning",
                            description=f"You've been inactive in **{guild.name}** for 60 days.",
                            color=discord.Color.orange()
                        )
                        embed.add_field(
                            name="Action Required",
                            value="Send a message in the server to avoid removal, or use `!opt_out_cleanup` to stay as a lurker.",
                            inline=False
                        )
                        await member.send(embed=embed)
                    except:
                        pass  # DMs disabled
            
        except Exception as e:
            print(f"✗ Error in inactive member check: {e}")
    
    @check_inactive_members.before_loop
    async def before_inactive_check(self):
        """Wait for bot to be ready"""
        await self.bot.wait_until_ready()


class UserManagementCommands(commands.Cog):
    """Commands for user management"""
    
    def __init__(self, bot, user_management):
        self.bot = bot
        self.user_management = user_management
    
    @commands.command(name='move_all')
    @commands.has_permissions(move_members=True)
    async def move_all(self, ctx, from_channel: discord.VoiceChannel, to_channel: discord.VoiceChannel):
        """
        Move all members from one voice channel to another
        
        Usage: !move_all <from_channel> <to_channel>
        Example: !move_all "General VC" "Meeting Room"
        """
        if not from_channel.members:
            await ctx.send("❌ Source channel is empty.")
            return
        
        member_count = len(from_channel.members)
        
        # Confirmation
        embed = discord.Embed(
            title="⚠️ Confirm Bulk Move",
            description=f"Move **{member_count} members** from {from_channel.mention} to {to_channel.mention}?",
            color=discord.Color.orange()
        )
        
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            
            if str(reaction.emoji) == "✅":
                await ctx.send(f"🔄 Moving {member_count} members...")
                
                moved = await self.user_management.move_all_members(from_channel, to_channel)
                
                await ctx.send(f"✅ Moved **{moved}/{member_count}** members to {to_channel.mention}")
            else:
                await ctx.send("❌ Move cancelled.")
                
        except asyncio.TimeoutError:
            await ctx.send("❌ Move cancelled (timeout).")
    
    @commands.command(name='disconnect_all')
    @commands.has_permissions(move_members=True)
    async def disconnect_all(self, ctx, voice_channel: discord.VoiceChannel):
        """
        Disconnect all members from a voice channel
        
        Usage: !disconnect_all <channel>
        """
        if not voice_channel.members:
            await ctx.send("❌ Channel is empty.")
            return
        
        member_count = len(voice_channel.members)
        
        # Confirmation
        embed = discord.Embed(
            title="⚠️ Confirm Bulk Disconnect",
            description=f"Disconnect **{member_count} members** from {voice_channel.mention}?",
            color=discord.Color.red()
        )
        
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            
            if str(reaction.emoji) == "✅":
                await ctx.send(f"🔄 Disconnecting {member_count} members...")
                
                disconnected = await self.user_management.disconnect_all_members(voice_channel)
                
                await ctx.send(f"✅ Disconnected **{disconnected}/{member_count}** members")
            else:
                await ctx.send("❌ Disconnect cancelled.")
                
        except asyncio.TimeoutError:
            await ctx.send("❌ Disconnect cancelled (timeout).")
    
    @commands.command(name='inactive_list')
    @commands.has_permissions(moderate_members=True)
    async def inactive_list(self, ctx, days: int = 30):
        """
        List inactive members
        
        Usage: !inactive_list [days]
        """
        inactive = await self.user_management.get_inactive_members(ctx.guild, days)
        
        if not inactive:
            await ctx.send(f"✅ No members inactive for {days}+ days!")
            return
        
        # Create pages
        per_page = 20
        pages = [inactive[i:i+per_page] for i in range(0, len(inactive), per_page)]
        
        for i, page in enumerate(pages, 1):
            embed = discord.Embed(
                title=f"📊 Inactive Members ({days}+ days)",
                description=f"Page {i}/{len(pages)} | Total: {len(inactive)}",
                color=discord.Color.orange()
            )
            
            for member in page:
                # Get last activity
                cursor = await self.user_management.db.execute(
                    "SELECT last_activity FROM users WHERE user_id = ?",
                    (member.id,)
                )
                result = await cursor.fetchone()
                
                last_activity = "Never"
                if result and result[0]:
                    last_date = datetime.fromisoformat(result[0])
                    days_ago = (datetime.utcnow() - last_date).days
                    last_activity = f"{days_ago} days ago"
                
                embed.add_field(
                    name=member.name,
                    value=f"Last active: {last_activity}",
                    inline=True
                )
            
            await ctx.send(embed=embed)
    
    @commands.command(name='cleanup_inactive')
    @commands.has_permissions(administrator=True)
    async def cleanup_inactive(self, ctx, days: int = 60, dry_run: str = "yes"):
        """
        Remove inactive members
        
        Usage: !cleanup_inactive [days] [dry_run]
        Example: !cleanup_inactive 60 yes  (preview)
        Example: !cleanup_inactive 60 no   (actually remove)
        """
        is_dry_run = dry_run.lower() in ["yes", "true", "1", "preview"]
        
        if not is_dry_run:
            # Extra confirmation for actual removal
            embed = discord.Embed(
                title="⚠️ CONFIRM MEMBER REMOVAL",
                description=f"This will **PERMANENTLY REMOVE** members inactive for {days}+ days!",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Are you absolutely sure?",
                value="React with ✅ to proceed or ❌ to cancel",
                inline=False
            )
            
            msg = await ctx.send(embed=embed)
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            
            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id
            
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
                
                if str(reaction.emoji) != "✅":
                    await ctx.send("❌ Cleanup cancelled.")
                    return
            except asyncio.TimeoutError:
                await ctx.send("❌ Cleanup cancelled (timeout).")
                return
        
        await ctx.send(f"{'🔍 Previewing' if is_dry_run else '🔄 Removing'} inactive members...")
        
        removed = await self.user_management.cleanup_inactive_members(
            ctx.guild,
            days,
            dry_run=is_dry_run
        )
        
        if is_dry_run:
            await ctx.send(f"📊 **Preview:** Would remove {removed} members\nRun `!cleanup_inactive {days} no` to actually remove them.")
        else:
            await ctx.send(f"✅ Removed {removed} inactive members")
    
    @commands.command(name='bulk_role_add')
    @commands.has_permissions(manage_roles=True)
    async def bulk_role_add(self, ctx, role: discord.Role, *members: discord.Member):
        """
        Add role to multiple members
        
        Usage: !bulk_role_add <role> <@user1> <@user2> ...
        """
        if not members:
            await ctx.send("❌ No members specified.")
            return
        
        await ctx.send(f"🔄 Adding {role.mention} to {len(members)} members...")
        
        updated = await self.user_management.bulk_add_role(list(members), role)
        
        await ctx.send(f"✅ Added role to **{updated}/{len(members)}** members")
    
    @commands.command(name='bulk_role_remove')
    @commands.has_permissions(manage_roles=True)
    async def bulk_role_remove(self, ctx, role: discord.Role, *members: discord.Member):
        """
        Remove role from multiple members
        
        Usage: !bulk_role_remove <role> <@user1> <@user2> ...
        """
        if not members:
            await ctx.send("❌ No members specified.")
            return
        
        await ctx.send(f"🔄 Removing {role.mention} from {len(members)} members...")
        
        updated = await self.user_management.bulk_remove_role(list(members), role)
        
        await ctx.send(f"✅ Removed role from **{updated}/{len(members)}** members")
    
    @commands.command(name='clone_roles')
    @commands.has_permissions(manage_roles=True)
    async def clone_roles(self, ctx, source: discord.Member, target: discord.Member):
        """
        Clone roles from one member to another
        
        Usage: !clone_roles <@source> <@target>
        """
        success = await self.user_management.clone_permissions(source, target)
        
        if success:
            await ctx.send(f"✅ Cloned roles from {source.mention} to {target.mention}")
        else:
            await ctx.send("❌ Failed to clone roles")
    
    @commands.command(name='purge_bots')
    @commands.has_permissions(administrator=True)
    async def purge_bots(self, ctx):
        """
        Remove all bot accounts (except this bot)
        
        Usage: !purge_bots
        """
        # Confirmation
        embed = discord.Embed(
            title="⚠️ CONFIRM BOT PURGE",
            description="This will remove **ALL BOT ACCOUNTS** from the server!",
            color=discord.Color.red()
        )
        
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            
            if str(reaction.emoji) == "✅":
                await ctx.send("🔄 Purging bots...")
                
                removed = await self.user_management.purge_bots(ctx.guild)
                
                await ctx.send(f"✅ Removed {removed} bot accounts")
            else:
                await ctx.send("❌ Purge cancelled.")
                
        except asyncio.TimeoutError:
            await ctx.send("❌ Purge cancelled (timeout).")
    
    @commands.command(name='opt_out_cleanup')
    async def opt_out_cleanup(self, ctx):
        """
        Opt out of automatic inactive member cleanup
        
        Usage: !opt_out_cleanup
        """
        try:
            await self.user_management.db.execute(
                "UPDATE users SET cleanup_opt_out = 1 WHERE user_id = ?",
                (ctx.author.id,)
            )
            await self.user_management.db.commit()
            
            await ctx.send("✅ You've opted out of automatic cleanup. You can lurk in peace! 👀")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
    
    @commands.command(name='server_stats')
    @commands.has_permissions(moderate_members=True)
    async def server_stats(self, ctx):
        """View detailed server statistics"""
        guild = ctx.guild
        
        # Count members by status
        online = sum(1 for m in guild.members if m.status == discord.Status.online)
        idle = sum(1 for m in guild.members if m.status == discord.Status.idle)
        dnd = sum(1 for m in guild.members if m.status == discord.Status.dnd)
        offline = sum(1 for m in guild.members if m.status == discord.Status.offline)
        
        # Count bots
        bots = sum(1 for m in guild.members if m.bot)
        humans = len(guild.members) - bots
        
        # Get inactive counts
        inactive_30 = len(await self.user_management.get_inactive_members(guild, 30))
        inactive_60 = len(await self.user_management.get_inactive_members(guild, 60))
        
        embed = discord.Embed(
            title=f"📊 Server Statistics - {guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="👥 Members",
            value=f"Total: {guild.member_count}\nHumans: {humans}\nBots: {bots}",
            inline=True
        )
        
        embed.add_field(
            name="🟢 Status",
            value=f"Online: {online}\nIdle: {idle}\nDND: {dnd}\nOffline: {offline}",
            inline=True
        )
        
        embed.add_field(
            name="💤 Inactive",
            value=f"30+ days: {inactive_30}\n60+ days: {inactive_60}",
            inline=True
        )
        
        embed.add_field(
            name="📝 Channels",
            value=f"Text: {len(guild.text_channels)}\nVoice: {len(guild.voice_channels)}\nCategories: {len(guild.categories)}",
            inline=True
        )
        
        embed.add_field(
            name="🎭 Roles",
            value=f"Total: {len(guild.roles)}",
            inline=True
        )
        
        embed.add_field(
            name="😀 Emojis",
            value=f"Total: {len(guild.emojis)}/{guild.emoji_limit}",
            inline=True
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        await ctx.send(embed=embed)


def setup(bot, db):
    """Setup function to initialize user management"""
    # Add cleanup_opt_out column if it doesn't exist
    asyncio.create_task(db.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS cleanup_opt_out INTEGER DEFAULT 0"
    ))
    
    user_management = UserManagement(bot, db)
    bot.add_cog(UserManagementCommands(bot, user_management))
    return user_management
