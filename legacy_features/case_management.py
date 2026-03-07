"""
Case Management System
Auto-assigned case numbers, audit trails, warnings, appeals, and evidence storage
"""

import discord
from discord.ext import commands
from datetime import datetime, timedelta
from typing import Optional, List
import json

class CaseManagement:
    """
    Comprehensive case management for moderation
    
    Features:
    - Auto-assigned case numbers
    - Complete audit trail
    - Warning system with progressive punishments
    - Appeal tracking
    - Evidence storage (messages, images, logs)
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        
        # Case types
        self.case_types = [
            "warning",
            "timeout",
            "kick",
            "ban",
            "spam_violation",
            "scam_attempt",
            "harassment",
            "other"
        ]
        
        # Warning thresholds (warnings -> action)
        self.warning_actions = {
            3: ("timeout", 3600),      # 3 warnings = 1 hour timeout
            5: ("timeout", 86400),     # 5 warnings = 24 hour timeout
            7: ("kick", None),         # 7 warnings = kick
            10: ("ban", None)          # 10 warnings = ban
        }
    
    async def create_case(
        self,
        guild: discord.Guild,
        user: discord.Member,
        moderator: discord.Member,
        case_type: str,
        reason: str,
        evidence: Optional[List[str]] = None,
        duration: Optional[int] = None
    ) -> int:
        """
        Create a new moderation case
        
        Returns:
            Case number
        """
        try:
            # Generate case number
            cursor = await self.db.execute(
                "SELECT MAX(case_number) FROM cases WHERE guild_id = ?",
                (guild.id,)
            )
            result = await cursor.fetchone()
            case_number = (result[0] or 0) + 1
            
            # Store evidence as JSON
            evidence_json = json.dumps(evidence) if evidence else None
            
            # Create case
            await self.db.execute(
                """
                INSERT INTO cases (
                    case_number, guild_id, user_id, moderator_id,
                    case_type, reason, evidence, duration,
                    created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (
                    case_number,
                    guild.id,
                    user.id,
                    moderator.id,
                    case_type,
                    reason,
                    evidence_json,
                    duration,
                    datetime.utcnow().isoformat()
                )
            )
            await self.db.commit()
            
            # Log to case-logs channel
            await self.log_case(guild, case_number, user, moderator, case_type, reason, evidence)
            
            # Check for warning threshold actions
            if case_type == "warning":
                await self.check_warning_threshold(guild, user)
            
            print(f"✓ Created case #{case_number} for {user.name}")
            return case_number
            
        except Exception as e:
            print(f"✗ Error creating case: {e}")
            return 0
    
    async def log_case(
        self,
        guild: discord.Guild,
        case_number: int,
        user: discord.Member,
        moderator: discord.Member,
        case_type: str,
        reason: str,
        evidence: Optional[List[str]] = None
    ):
        """Log case to case-logs channel"""
        case_log = discord.utils.get(guild.text_channels, name='case-logs')
        if not case_log:
            return
        
        # Color based on severity
        colors = {
            "warning": discord.Color.yellow(),
            "timeout": discord.Color.orange(),
            "kick": discord.Color.red(),
            "ban": discord.Color.dark_red(),
            "spam_violation": discord.Color.orange(),
            "scam_attempt": discord.Color.red(),
            "harassment": discord.Color.dark_red(),
            "other": discord.Color.blue()
        }
        
        embed = discord.Embed(
            title=f"📋 Case #{case_number} - {case_type.replace('_', ' ').title()}",
            color=colors.get(case_type, discord.Color.blue()),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="User",
            value=f"{user.mention}\n{user.name}#{user.discriminator}\nID: `{user.id}`",
            inline=True
        )
        
        embed.add_field(
            name="Moderator",
            value=f"{moderator.mention}\n{moderator.name}",
            inline=True
        )
        
        embed.add_field(
            name="Reason",
            value=reason[:1024],  # Discord field limit
            inline=False
        )
        
        if evidence:
            evidence_text = "\n".join(f"• {e[:100]}" for e in evidence[:5])
            if len(evidence) > 5:
                evidence_text += f"\n... and {len(evidence) - 5} more"
            
            embed.add_field(
                name="Evidence",
                value=evidence_text,
                inline=False
            )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"Case #{case_number}")
        
        await case_log.send(embed=embed)
    
    async def get_case(self, guild_id: int, case_number: int) -> Optional[dict]:
        """Get case details"""
        try:
            cursor = await self.db.execute(
                """
                SELECT case_number, user_id, moderator_id, case_type,
                       reason, evidence, duration, created_at, status
                FROM cases
                WHERE guild_id = ? AND case_number = ?
                """,
                (guild_id, case_number)
            )
            result = await cursor.fetchone()
            
            if result:
                return {
                    'case_number': result[0],
                    'user_id': result[1],
                    'moderator_id': result[2],
                    'case_type': result[3],
                    'reason': result[4],
                    'evidence': json.loads(result[5]) if result[5] else [],
                    'duration': result[6],
                    'created_at': result[7],
                    'status': result[8]
                }
            
            return None
            
        except Exception as e:
            print(f"✗ Error getting case: {e}")
            return None
    
    async def get_user_cases(self, guild_id: int, user_id: int) -> List[dict]:
        """Get all cases for a user"""
        try:
            cursor = await self.db.execute(
                """
                SELECT case_number, case_type, reason, created_at, status
                FROM cases
                WHERE guild_id = ? AND user_id = ?
                ORDER BY created_at DESC
                """,
                (guild_id, user_id)
            )
            results = await cursor.fetchall()
            
            return [
                {
                    'case_number': row[0],
                    'case_type': row[1],
                    'reason': row[2],
                    'created_at': row[3],
                    'status': row[4]
                }
                for row in results
            ]
            
        except Exception as e:
            print(f"✗ Error getting user cases: {e}")
            return []
    
    async def check_warning_threshold(self, guild: discord.Guild, user: discord.Member):
        """Check if user has reached warning threshold for automatic action"""
        try:
            # Count active warnings
            cursor = await self.db.execute(
                """
                SELECT COUNT(*) FROM cases
                WHERE guild_id = ? AND user_id = ? 
                AND case_type = 'warning' AND status = 'active'
                """,
                (guild.id, user.id)
            )
            warning_count = (await cursor.fetchone())[0]
            
            # Check thresholds
            for threshold, (action, duration) in self.warning_actions.items():
                if warning_count == threshold:
                    # Execute action
                    await self.execute_threshold_action(guild, user, action, duration, warning_count)
                    break
            
        except Exception as e:
            print(f"✗ Error checking warning threshold: {e}")
    
    async def execute_threshold_action(
        self,
        guild: discord.Guild,
        user: discord.Member,
        action: str,
        duration: Optional[int],
        warning_count: int
    ):
        """Execute automatic action based on warning threshold"""
        try:
            reason = f"Automatic action: {warning_count} warnings reached"
            
            if action == "timeout" and duration:
                timeout_until = datetime.utcnow() + timedelta(seconds=duration)
                await user.timeout(timeout_until, reason=reason)
                
                # Create case
                await self.create_case(
                    guild, user, guild.me, "timeout",
                    reason, duration=duration
                )
                
            elif action == "kick":
                await user.kick(reason=reason)
                
                # Create case
                await self.create_case(
                    guild, user, guild.me, "kick", reason
                )
                
            elif action == "ban":
                await user.ban(reason=reason)
                
                # Create case
                await self.create_case(
                    guild, user, guild.me, "ban", reason
                )
            
            # Notify user
            try:
                dm_embed = discord.Embed(
                    title="⚠️ Automatic Moderation Action",
                    description=f"You have received an automatic {action} in **{guild.name}**.",
                    color=discord.Color.red()
                )
                dm_embed.add_field(name="Reason", value=reason, inline=False)
                dm_embed.add_field(name="Warning Count", value=f"{warning_count}", inline=True)
                
                await user.send(embed=dm_embed)
            except:
                pass  # User has DMs disabled
            
        except Exception as e:
            print(f"✗ Error executing threshold action: {e}")
    
    async def create_appeal(self, guild_id: int, user_id: int, case_number: int, appeal_reason: str) -> bool:
        """Create an appeal for a case"""
        try:
            await self.db.execute(
                """
                INSERT INTO case_appeals (
                    guild_id, user_id, case_number, appeal_reason,
                    created_at, status
                ) VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (guild_id, user_id, case_number, appeal_reason, datetime.utcnow().isoformat())
            )
            await self.db.commit()
            
            return True
            
        except Exception as e:
            print(f"✗ Error creating appeal: {e}")
            return False
    
    async def update_case_status(self, guild_id: int, case_number: int, status: str, notes: Optional[str] = None):
        """Update case status (active, appealed, closed, etc.)"""
        try:
            if notes:
                await self.db.execute(
                    "UPDATE cases SET status = ?, notes = ? WHERE guild_id = ? AND case_number = ?",
                    (status, notes, guild_id, case_number)
                )
            else:
                await self.db.execute(
                    "UPDATE cases SET status = ? WHERE guild_id = ? AND case_number = ?",
                    (status, guild_id, case_number)
                )
            
            await self.db.commit()
            return True
            
        except Exception as e:
            print(f"✗ Error updating case status: {e}")
            return False


class CaseManagementCommands(commands.Cog):
    """Commands for case management"""
    
    def __init__(self, bot, case_management):
        self.bot = bot
        self.case_management = case_management
    
    @commands.command(name='warn')
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str):
        """
        Issue a warning to a user
        
        Usage: !warn @user <reason>
        """
        case_number = await self.case_management.create_case(
            ctx.guild, member, ctx.author, "warning", reason
        )
        
        if case_number:
            # Get warning count
            cases = await self.case_management.get_user_cases(ctx.guild.id, member.id)
            warning_count = sum(1 for c in cases if c['case_type'] == 'warning' and c['status'] == 'active')
            
            await ctx.send(f"⚠️ Warned {member.mention} | Case #{case_number} | Total warnings: {warning_count}")
            
            # DM user
            try:
                dm_embed = discord.Embed(
                    title="⚠️ Warning Received",
                    description=f"You have been warned in **{ctx.guild.name}**.",
                    color=discord.Color.yellow()
                )
                dm_embed.add_field(name="Reason", value=reason, inline=False)
                dm_embed.add_field(name="Case Number", value=f"#{case_number}", inline=True)
                dm_embed.add_field(name="Total Warnings", value=f"{warning_count}", inline=True)
                
                await member.send(embed=dm_embed)
            except:
                pass
    
    @commands.command(name='case')
    @commands.has_permissions(moderate_members=True)
    async def view_case(self, ctx, case_number: int):
        """
        View case details
        
        Usage: !case <number>
        """
        case = await self.case_management.get_case(ctx.guild.id, case_number)
        
        if not case:
            await ctx.send(f"❌ Case #{case_number} not found.")
            return
        
        user = ctx.guild.get_member(case['user_id'])
        moderator = ctx.guild.get_member(case['moderator_id'])
        
        embed = discord.Embed(
            title=f"📋 Case #{case_number}",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Type", value=case['case_type'].replace('_', ' ').title(), inline=True)
        embed.add_field(name="Status", value=case['status'].title(), inline=True)
        embed.add_field(name="Created", value=case['created_at'][:10], inline=True)
        
        embed.add_field(
            name="User",
            value=f"{user.mention if user else 'Unknown'}\nID: `{case['user_id']}`",
            inline=True
        )
        
        embed.add_field(
            name="Moderator",
            value=f"{moderator.mention if moderator else 'Unknown'}",
            inline=True
        )
        
        embed.add_field(name="Reason", value=case['reason'][:1024], inline=False)
        
        if case['evidence']:
            evidence_text = "\n".join(f"• {e[:100]}" for e in case['evidence'][:5])
            embed.add_field(name="Evidence", value=evidence_text, inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='cases')
    @commands.has_permissions(moderate_members=True)
    async def view_user_cases(self, ctx, member: discord.Member):
        """
        View all cases for a user
        
        Usage: !cases @user
        """
        cases = await self.case_management.get_user_cases(ctx.guild.id, member.id)
        
        if not cases:
            await ctx.send(f"{member.mention} has no cases.")
            return
        
        embed = discord.Embed(
            title=f"📋 Cases - {member.name}",
            description=f"Total: {len(cases)} cases",
            color=discord.Color.blue()
        )
        
        for case in cases[:10]:  # Show last 10
            status_emoji = "✅" if case['status'] == 'closed' else "🔴" if case['status'] == 'active' else "⏸️"
            
            embed.add_field(
                name=f"{status_emoji} Case #{case['case_number']} - {case['case_type'].replace('_', ' ').title()}",
                value=f"{case['reason'][:100]}\n{case['created_at'][:10]}",
                inline=False
            )
        
        if len(cases) > 10:
            embed.set_footer(text=f"Showing 10 of {len(cases)} cases")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='appeal')
    async def appeal_case(self, ctx, case_number: int, *, reason: str):
        """
        Appeal a case
        
        Usage: !appeal <case_number> <reason>
        """
        success = await self.case_management.create_appeal(
            ctx.guild.id, ctx.author.id, case_number, reason
        )
        
        if success:
            await ctx.send(f"✅ Appeal submitted for Case #{case_number}. A moderator will review it.")
        else:
            await ctx.send(f"❌ Failed to submit appeal.")
    
    @commands.command(name='close_case')
    @commands.has_permissions(moderate_members=True)
    async def close_case(self, ctx, case_number: int, *, notes: str = None):
        """
        Close a case
        
        Usage: !close_case <number> [notes]
        """
        success = await self.case_management.update_case_status(
            ctx.guild.id, case_number, "closed", notes
        )
        
        if success:
            await ctx.send(f"✅ Closed Case #{case_number}")
        else:
            await ctx.send(f"❌ Failed to close case.")


def setup(bot, db):
    """Setup function to initialize case management"""
    case_management = CaseManagement(bot, db)
    bot.add_cog(CaseManagementCommands(bot, case_management))
    return case_management
