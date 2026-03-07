"""
CAPTCHA Verification System
Prevents bots from joining the server
"""

import discord
from discord.ext import commands
from discord.ui import View, Button
from datetime import datetime, timedelta
from typing import Optional
import random
import string

class CaptchaVerification:
    """
    CAPTCHA system for new members
    
    Features:
    - Text-based CAPTCHA challenges
    - Verification channel jail
    - Auto-kick after timeout
    - Bypass for trusted invites
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        
        # Pending verifications {user_id: (code, timestamp)}
        self.pending_verifications = {}
        
        # Configuration
        self.verification_timeout = 300  # 5 minutes
        self.code_length = 6
    
    def generate_code(self) -> str:
        """Generate random CAPTCHA code"""
        # Use mix of letters and numbers, avoiding confusing characters
        chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        return ''.join(random.choice(chars) for _ in range(self.code_length))
    
    async def create_verification_challenge(self, member: discord.Member):
        """Create CAPTCHA challenge for new member"""
        try:
            # Generate code
            code = self.generate_code()
            timestamp = datetime.utcnow()
            
            # Store pending verification
            self.pending_verifications[member.id] = (code, timestamp)
            
            # Store in database
            await self.db.execute(
                """
                INSERT INTO captcha_verifications (
                    user_id, guild_id, code, created_at, status
                ) VALUES (?, ?, ?, ?, 'pending')
                """,
                (member.id, member.guild.id, code, timestamp.isoformat())
            )
            await self.db.commit()
            
            # Send DM with CAPTCHA
            try:
                embed = discord.Embed(
                    title="🔐 Verification Required",
                    description=f"Welcome to **{member.guild.name}**!\n\nTo verify you're human, please complete this CAPTCHA.",
                    color=discord.Color.blue()
                )
                
                embed.add_field(
                    name="Your Verification Code",
                    value=f"```\n{code}\n```",
                    inline=False
                )
                
                embed.add_field(
                    name="How to Verify",
                    value=f"Go to the #verify channel and type:\n`!verify {code}`",
                    inline=False
                )
                
                embed.add_field(
                    name="⏰ Time Limit",
                    value=f"{self.verification_timeout // 60} minutes",
                    inline=True
                )
                
                embed.set_footer(text="This helps keep our server safe from bots!")
                
                await member.send(embed=embed)
                print(f"✓ Sent CAPTCHA to {member.name}")
                
            except discord.Forbidden:
                # User has DMs disabled, send in verify channel
                verify_channel = discord.utils.get(member.guild.text_channels, name='verify')
                if verify_channel:
                    await verify_channel.send(
                        f"{member.mention} Please check your DMs for verification instructions! If you can't receive DMs, type `!verify {code}` here.",
                        delete_after=60
                    )
            
            # Assign unverified role
            await self.assign_unverified_role(member)
            
        except Exception as e:
            print(f"✗ Error creating verification challenge: {e}")
    
    async def assign_unverified_role(self, member: discord.Member):
        """Assign unverified role to restrict access"""
        try:
            # Find or create unverified role
            unverified_role = discord.utils.get(member.guild.roles, name="Unverified")
            
            if not unverified_role:
                # Create role
                unverified_role = await member.guild.create_role(
                    name="Unverified",
                    color=discord.Color.light_gray(),
                    reason="CAPTCHA verification system"
                )
                
                # Set permissions for verify channel only
                verify_channel = discord.utils.get(member.guild.text_channels, name='verify')
                if verify_channel:
                    # Deny access to all channels except verify
                    for channel in member.guild.text_channels:
                        if channel.id == verify_channel.id:
                            await channel.set_permissions(unverified_role, read_messages=True, send_messages=True)
                        else:
                            await channel.set_permissions(unverified_role, read_messages=False)
                
                print(f"✓ Created Unverified role")
            
            # Assign role
            await member.add_roles(unverified_role, reason="Pending CAPTCHA verification")
            
        except Exception as e:
            print(f"✗ Error assigning unverified role: {e}")
    
    async def verify_user(self, member: discord.Member, code: str) -> bool:
        """Verify user's CAPTCHA code"""
        try:
            user_id = member.id
            
            # Check if pending
            if user_id not in self.pending_verifications:
                return False
            
            correct_code, timestamp = self.pending_verifications[user_id]
            
            # Check timeout
            if datetime.utcnow() - timestamp > timedelta(seconds=self.verification_timeout):
                # Timeout
                del self.pending_verifications[user_id]
                return False
            
            # Check code
            if code.upper() != correct_code:
                return False
            
            # Verification successful
            del self.pending_verifications[user_id]
            
            # Update database
            await self.db.execute(
                """
                UPDATE captcha_verifications
                SET status = 'verified', verified_at = ?
                WHERE user_id = ? AND status = 'pending'
                """,
                (datetime.utcnow().isoformat(), user_id)
            )
            await self.db.commit()
            
            # Remove unverified role
            unverified_role = discord.utils.get(member.guild.roles, name="Unverified")
            if unverified_role in member.roles:
                await member.remove_roles(unverified_role, reason="CAPTCHA verified")
            
            # Assign verified role
            verified_role = discord.utils.get(member.guild.roles, name="Verified")
            if not verified_role:
                verified_role = await member.guild.create_role(
                    name="Verified",
                    color=discord.Color.green(),
                    reason="CAPTCHA verification system"
                )
            
            await member.add_roles(verified_role, reason="CAPTCHA verified")
            
            print(f"✓ Verified {member.name}")
            return True
            
        except Exception as e:
            print(f"✗ Error verifying user: {e}")
            return False
    
    async def check_timeouts(self):
        """Check for expired verifications and kick users"""
        try:
            now = datetime.utcnow()
            expired_users = []
            
            for user_id, (code, timestamp) in list(self.pending_verifications.items()):
                if now - timestamp > timedelta(seconds=self.verification_timeout):
                    expired_users.append(user_id)
            
            # Kick expired users
            for user_id in expired_users:
                del self.pending_verifications[user_id]
                
                # Find member and kick
                for guild in self.bot.guilds:
                    member = guild.get_member(user_id)
                    if member:
                        try:
                            await member.kick(reason="Failed CAPTCHA verification (timeout)")
                            print(f"✓ Kicked {member.name} for verification timeout")
                        except:
                            pass
            
        except Exception as e:
            print(f"✗ Error checking timeouts: {e}")


class CaptchaCommands(commands.Cog):
    """Commands for CAPTCHA verification"""
    
    def __init__(self, bot, captcha):
        self.bot = bot
        self.captcha = captcha
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Send CAPTCHA to new members"""
        if member.bot:
            return
        
        # Check if CAPTCHA is enabled for this guild
        # For now, always enable
        await self.captcha.create_verification_challenge(member)
    
    @commands.command(name='verify')
    async def verify(self, ctx, code: str):
        """
        Verify your CAPTCHA code
        
        Usage: !verify <code>
        """
        success = await self.captcha.verify_user(ctx.author, code)
        
        if success:
            embed = discord.Embed(
                title="✅ Verification Successful!",
                description=f"Welcome to **{ctx.guild.name}**, {ctx.author.mention}!",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Next Steps",
                value="• Read the rules in #rules\n• Introduce yourself in #introductions\n• Start chatting!",
                inline=False
            )
            
            await ctx.send(embed=embed)
            
            # Delete verification message
            try:
                await ctx.message.delete()
            except:
                pass
        else:
            await ctx.send(
                f"❌ {ctx.author.mention} Invalid or expired verification code. Please check your DMs for the correct code.",
                delete_after=10
            )
            
            # Delete failed attempt
            try:
                await ctx.message.delete()
            except:
                pass
    
    @commands.command(name='resend_captcha')
    async def resend_captcha(self, ctx):
        """Resend CAPTCHA code"""
        # Check if user is unverified
        unverified_role = discord.utils.get(ctx.guild.roles, name="Unverified")
        
        if not unverified_role or unverified_role not in ctx.author.roles:
            await ctx.send("You're already verified!", delete_after=5)
            return
        
        # Resend CAPTCHA
        await self.captcha.create_verification_challenge(ctx.author)
        await ctx.send(f"{ctx.author.mention} New CAPTCHA sent! Check your DMs.", delete_after=10)
    
    @commands.command(name='bypass_captcha')
    @commands.has_permissions(administrator=True)
    async def bypass_captcha(self, ctx, member: discord.Member):
        """
        Manually verify a user (admin only)
        
        Usage: !bypass_captcha @user
        """
        # Remove from pending
        if member.id in self.captcha.pending_verifications:
            del self.captcha.pending_verifications[member.id]
        
        # Remove unverified role
        unverified_role = discord.utils.get(ctx.guild.roles, name="Unverified")
        if unverified_role in member.roles:
            await member.remove_roles(unverified_role)
        
        # Add verified role
        verified_role = discord.utils.get(ctx.guild.roles, name="Verified")
        if not verified_role:
            verified_role = await ctx.guild.create_role(name="Verified", color=discord.Color.green())
        
        await member.add_roles(verified_role)
        
        await ctx.send(f"✅ {member.mention} has been manually verified.")
    
    @commands.command(name='captcha_stats')
    @commands.has_permissions(moderate_members=True)
    async def captcha_stats(self, ctx):
        """View CAPTCHA verification statistics"""
        try:
            # Get stats
            cursor = await self.captcha.db.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'verified' THEN 1 ELSE 0 END) as verified,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
                FROM captcha_verifications
                WHERE guild_id = ?
                """,
                (ctx.guild.id,)
            )
            result = await cursor.fetchone()
            
            total, verified, pending = result or (0, 0, 0)
            failed = total - (verified or 0) - (pending or 0)
            
            embed = discord.Embed(
                title="🔐 CAPTCHA Statistics",
                color=discord.Color.blue()
            )
            
            embed.add_field(name="Total Challenges", value=str(total), inline=True)
            embed.add_field(name="✅ Verified", value=str(verified or 0), inline=True)
            embed.add_field(name="⏳ Pending", value=str(pending or 0), inline=True)
            embed.add_field(name="❌ Failed/Kicked", value=str(failed), inline=True)
            
            if total > 0:
                success_rate = ((verified or 0) / total) * 100
                embed.add_field(name="Success Rate", value=f"{success_rate:.1f}%", inline=True)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")


def setup(bot, db):
    """Setup function to initialize CAPTCHA system"""
    captcha = CaptchaVerification(bot, db)
    bot.add_cog(CaptchaCommands(bot, captcha))
    return captcha
