"""
Welcome/Onboarding System Module
Handles new member welcome messages, intro prompts, and first-time bonuses
"""

import discord
from discord.ext import commands
from datetime import datetime
import asyncio
from typing import Optional

class WelcomeSystem:
    """
    Manages welcome messages and new member onboarding
    
    Features:
    - Customized welcome DM with server info
    - Server rules and channel guide
    - Intro channel prompt
    - First-time XP bonus for completing profile
    - Welcome message in designated channel
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        
        # Welcome message configuration
        self.welcome_channel_name = "welcome"
        self.intro_channel_name = "introductions"
        self.rules_channel_name = "rules"
        
        # Bonuses
        self.intro_bonus_xp = 100
        self.profile_complete_bonus = 50
        
    async def send_welcome_dm(self, member: discord.Member):
        """
        Send personalized welcome DM to new member
        
        Args:
            member: The member who just joined
            
        Includes:
        - Welcome message
        - Server overview
        - Link to rules
        - Link to intro channel
        - Quick start guide
        """
        try:
            # Find important channels
            intro_channel = discord.utils.get(member.guild.text_channels, name=self.intro_channel_name)
            rules_channel = discord.utils.get(member.guild.text_channels, name=self.rules_channel_name)
            
            # Create embed
            embed = discord.Embed(
                title=f"Welcome to {member.guild.name}! 🎉",
                description=f"Hey {member.mention}, welcome to our entrepreneur community!",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            # Add server overview
            embed.add_field(
                name="📚 What We're About",
                value="This is a community for entrepreneurs focused on business ideas, marketing, crypto, trading, and NFTs. "
                      "We value engagement, learning, and helping each other grow.",
                inline=False
            )
            
            # Add rules link
            if rules_channel:
                embed.add_field(
                    name="📜 Server Rules",
                    value=f"Please read our rules in {rules_channel.mention} before participating.",
                    inline=False
                )
            
            # Add intro prompt
            if intro_channel:
                embed.add_field(
                    name="👋 Introduce Yourself",
                    value=f"Head over to {intro_channel.mention} and tell us:\n"
                          f"• What brings you here?\n"
                          f"• What are you working on?\n"
                          f"• What expertise can you share?\n\n"
                          f"**Bonus:** Earn {self.intro_bonus_xp} XP for posting your intro!",
                    inline=False
                )
            
            # Add quick start guide
            embed.add_field(
                name="🚀 Quick Start",
                value="**Level Up System:**\n"
                      "• Earn XP by chatting and being active\n"
                      "• Unlock roles at levels 5, 10, 20, 30, 50\n"
                      "• Check your progress with `/rank`\n\n"
                      "**Stay Active:**\n"
                      "• Build daily streaks for bonus XP\n"
                      "• Earn achievements\n"
                      "• Climb the leaderboard with `/leaderboard`",
                inline=False
            )
            
            # Add helpful commands
            embed.add_field(
                name="💡 Useful Commands",
                value="`/rank` - Check your level and XP\n"
                      "`/stats` - View your detailed stats\n"
                      "`/leaderboard` - See top members\n"
                      "`/trust` - Check your trust score",
                inline=False
            )
            
            embed.set_footer(text=f"{member.guild.name} | Member #{member.guild.member_count}")
            embed.set_thumbnail(url=member.guild.icon.url if member.guild.icon else None)
            
            # Send DM
            await member.send(embed=embed)
            
            # Log successful DM
            print(f"✓ Sent welcome DM to {member.name}")
            
        except discord.Forbidden:
            # User has DMs disabled
            print(f"✗ Could not send welcome DM to {member.name} (DMs disabled)")
        except Exception as e:
            print(f"✗ Error sending welcome DM to {member.name}: {e}")
    
    async def send_welcome_message(self, member: discord.Member):
        """
        Send welcome message in designated welcome channel
        
        Args:
            member: The member who just joined
        """
        try:
            # Find welcome channel
            welcome_channel = discord.utils.get(member.guild.text_channels, name=self.welcome_channel_name)
            if not welcome_channel:
                print(f"⚠ Welcome channel '{self.welcome_channel_name}' not found")
                return
            
            # Create welcome embed
            embed = discord.Embed(
                title="New Member Joined! 🎉",
                description=f"Everyone welcome {member.mention} to the community!",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="Account Created",
                value=f"<t:{int(member.created_at.timestamp())}:R>",
                inline=True
            )
            
            embed.add_field(
                name="Member Number",
                value=f"#{member.guild.member_count}",
                inline=True
            )
            
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"User ID: {member.id}")
            
            # Send to channel
            await welcome_channel.send(embed=embed)
            
            # Log
            print(f"✓ Sent welcome message for {member.name} in #{welcome_channel.name}")
            
        except Exception as e:
            print(f"✗ Error sending welcome message for {member.name}: {e}")
    
    async def check_intro_posted(self, message: discord.Message):
        """
        Check if message is in intro channel and award bonus
        
        Args:
            message: The message to check
            
        Returns:
            bool: True if intro bonus was awarded
        """
        # Check if in intro channel
        if message.channel.name != self.intro_channel_name:
            return False
        
        # Check if user already got intro bonus
        cursor = await self.db.execute(
            "SELECT intro_bonus_claimed FROM users WHERE user_id = ?",
            (message.author.id,)
        )
        result = await cursor.fetchone()
        
        # If already claimed, skip
        if result and result[0]:
            return False
        
        # Check if message is long enough (at least 50 characters)
        if len(message.content) < 50:
            return False
        
        # Award intro bonus
        try:
            # Update user record
            await self.db.execute(
                """
                UPDATE users 
                SET intro_bonus_claimed = 1,
                    xp = xp + ?
                WHERE user_id = ?
                """,
                (self.intro_bonus_xp, message.author.id)
            )
            await self.db.commit()
            
            # Send confirmation
            await message.add_reaction("✅")
            await message.reply(
                f"🎉 Thanks for introducing yourself! You've earned **{self.intro_bonus_xp} bonus XP**!",
                delete_after=30
            )
            
            print(f"✓ Awarded intro bonus to {message.author.name}")
            return True
            
        except Exception as e:
            print(f"✗ Error awarding intro bonus to {message.author.name}: {e}")
            return False
    
    async def initialize_new_member(self, member: discord.Member):
        """
        Initialize new member in database with welcome timestamp
        
        Args:
            member: The member who just joined
        """
        try:
            # Check if user already exists
            cursor = await self.db.execute(
                "SELECT user_id FROM users WHERE user_id = ?",
                (member.id,)
            )
            result = await cursor.fetchone()
            
            if not result:
                # Create new user record
                await self.db.execute(
                    """
                    INSERT INTO users (
                        user_id, username, discriminator, 
                        joined_at, intro_bonus_claimed
                    ) VALUES (?, ?, ?, ?, 0)
                    """,
                    (
                        member.id,
                        member.name,
                        member.discriminator,
                        datetime.utcnow().isoformat()
                    )
                )
                await self.db.commit()
                print(f"✓ Initialized new member: {member.name}")
            
        except Exception as e:
            print(f"✗ Error initializing member {member.name}: {e}")


class WelcomeCommands(commands.Cog):
    """Commands for welcome system management"""
    
    def __init__(self, bot, welcome_system):
        self.bot = bot
        self.welcome_system = welcome_system
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Handle new member join events"""
        # Initialize member in database
        await self.welcome_system.initialize_new_member(member)
        
        # Send welcome DM
        await self.welcome_system.send_welcome_dm(member)
        
        # Send welcome message in channel
        await self.welcome_system.send_welcome_message(member)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Check for intro posts"""
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Check if intro bonus should be awarded
        await self.welcome_system.check_intro_posted(message)


def setup(bot, db):
    """Setup function to initialize the welcome system"""
    welcome_system = WelcomeSystem(bot, db)
    bot.add_cog(WelcomeCommands(bot, welcome_system))
    return welcome_system
