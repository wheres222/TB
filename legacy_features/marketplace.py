"""
Marketplace Module - DM-based Service Listing System
Allows users to create and browse service listings through an interactive DM flow
"""

import discord
from discord.ext import commands
from discord import ui
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import asyncio
import re

class MarketplaceListingSession:
    """Manages a single user's listing creation session"""
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.listing_type = None
        self.skills = []
        self.expertise = None
        self.scope = None
        self.rate_type = None
        self.rate_amount = None
        self.portfolio_links = []
        self.attachments = []
        self.communication_preference = None
        self.current_step = 1
        self.created_at = datetime.utcnow()
        
    def to_dict(self):
        """Convert session to dictionary for database storage"""
        return {
            'user_id': self.user_id,
            'listing_type': self.listing_type,
            'skills': ','.join(self.skills) if self.skills else None,
            'expertise': self.expertise,
            'scope': self.scope,
            'rate_type': self.rate_type,
            'rate_amount': self.rate_amount,
            'portfolio_links': ','.join(self.portfolio_links) if self.portfolio_links else None,
            'attachments': ','.join(self.attachments) if self.attachments else None,
            'communication_preference': self.communication_preference,
            'created_at': self.created_at.isoformat()
        }


class ListingTypeSelect(ui.Select):
    """Step 1: Select listing type dropdown"""
    
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Sell Services",
                description="Offer your skills and services to others",
                emoji="💼"
            ),
            discord.SelectOption(
                label="Buy Services",
                description="Looking to hire someone for a project",
                emoji="🛒"
            )
        ]
        super().__init__(
            placeholder="Select listing type",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        self.view.session.listing_type = self.values[0]
        await interaction.response.defer()
        await self.view.next_step(interaction)


class ListingTypeView(ui.View):
    """View for Step 1: Listing Type Selection"""
    
    def __init__(self, session: MarketplaceListingSession, marketplace):
        super().__init__(timeout=300)
        self.session = session
        self.marketplace = marketplace
        self.add_item(ListingTypeSelect())
    
    async def next_step(self, interaction: discord.Interaction):
        self.stop()
        await self.marketplace.show_skills_step(interaction.user, self.session)


class SkillsSelect(ui.Select):
    """Step 2: Select skills (up to 3)"""
    
    def __init__(self):
        options = [
            discord.SelectOption(label="Marketing", emoji="🌐"),
            discord.SelectOption(label="Advertising", emoji="🎥"),
            discord.SelectOption(label="Graphic Design", emoji="🎨"),
            discord.SelectOption(label="Web Development", emoji="💻"),
            discord.SelectOption(label="Music Production", emoji="🎵"),
            discord.SelectOption(label="Backend", emoji="🔙"),
            discord.SelectOption(label="Marketing", emoji="📢"),
            discord.SelectOption(label="Animation", emoji="🎬"),
            discord.SelectOption(label="3D Modeling", emoji="🗿"),
            discord.SelectOption(label="Frontend", emoji="🖥️"),
            discord.SelectOption(label="Consulting", emoji="💡"),
            discord.SelectOption(label="Product Design", emoji="📦"),
            discord.SelectOption(label="Social Media", emoji="📱"),
            discord.SelectOption(label="SEO", emoji="🔍"),
        ]
        super().__init__(
            placeholder="Select up to 3 skills",
            min_values=1,
            max_values=3,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        self.view.session.skills = self.values
        await interaction.response.defer()
        await self.view.next_step(interaction)


class SkillsView(ui.View):
    """View for Step 2: Skills Selection"""
    
    def __init__(self, session: MarketplaceListingSession, marketplace):
        super().__init__(timeout=300)
        self.session = session
        self.marketplace = marketplace
        self.add_item(SkillsSelect())
    
    async def next_step(self, interaction: discord.Interaction):
        self.stop()
        await self.marketplace.show_rates_step(interaction.user, self.session)


class RateTypeSelect(ui.Select):
    """Step 3: Select rate type"""
    
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Per Hour",
                description="Charged by time spent working",
                emoji="⏰"
            ),
            discord.SelectOption(
                label="Per Project",
                description="Flat fee for complete deliverables",
                emoji="📁"
            ),
            discord.SelectOption(
                label="Per Minute",
                description="For video/audio work by duration",
                emoji="⏱️"
            ),
            discord.SelectOption(
                label="Per Page/Screen",
                description="For multi-page documents or screens",
                emoji="📄"
            ),
            discord.SelectOption(
                label="Negotiable",
                description="Pricing discussed per project",
                emoji="💬"
            )
        ]
        super().__init__(
            placeholder="Select rate type",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        self.view.session.rate_type = self.values[0]
        await interaction.response.defer()
        await self.view.next_step(interaction)


class RateTypeView(ui.View):
    """View for Step 3: Rate Type Selection"""
    
    def __init__(self, session: MarketplaceListingSession, marketplace):
        super().__init__(timeout=300)
        self.session = session
        self.marketplace = marketplace
        self.add_item(RateTypeSelect())
    
    async def next_step(self, interaction: discord.Interaction):
        self.stop()
        await self.marketplace.show_rate_amount_step(interaction.user, self.session)


class ScopeSelect(ui.Select):
    """Step 5: Select work scope"""
    
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Full-Time",
                description="Available for ongoing, consistent work",
                emoji="🔵"
            ),
            discord.SelectOption(
                label="Part-Time",
                description="Available for regular, limited hours",
                emoji="🟠"
            ),
            discord.SelectOption(
                label="One-Time",
                description="Available for individual projects",
                emoji="⚪"
            ),
            discord.SelectOption(
                label="Any",
                description="Open to all types of work",
                emoji="🔵"
            )
        ]
        super().__init__(
            placeholder="Select work scope",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        self.view.session.scope = self.values[0]
        await interaction.response.defer()
        await self.view.next_step(interaction)


class ScopeView(ui.View):
    """View for Step 5: Scope Selection"""
    
    def __init__(self, session: MarketplaceListingSession, marketplace):
        super().__init__(timeout=300)
        self.session = session
        self.marketplace = marketplace
        self.add_item(ScopeSelect())
    
    async def next_step(self, interaction: discord.Interaction):
        self.stop()
        await self.marketplace.show_portfolio_step(interaction.user, self.session)


class CommunicationPreferenceView(ui.View):
    """Step 8: Communication Preference"""
    
    def __init__(self, session: MarketplaceListingSession, marketplace):
        super().__init__(timeout=300)
        self.session = session
        self.marketplace = marketplace
    
    @ui.button(label="🔒 Private Channel", style=discord.ButtonStyle.primary, custom_id="private_channel")
    async def private_channel_button(self, interaction: discord.Interaction, button: ui.Button):
        self.session.communication_preference = "Private Channel"
        await interaction.response.defer()
        await self.next_step(interaction)
    
    @ui.button(label="📩 DM Open (No Support)", style=discord.ButtonStyle.secondary, custom_id="dm_open")
    async def dm_open_button(self, interaction: discord.Interaction, button: ui.Button):
        self.session.communication_preference = "DM Open"
        await interaction.response.defer()
        await self.next_step(interaction)
    
    async def next_step(self, interaction: discord.Interaction):
        self.stop()
        await self.marketplace.show_confirmation_step(interaction.user, self.session)


class FinalConfirmationView(ui.View):
    """Step 9: Final Confirmation"""
    
    def __init__(self, session: MarketplaceListingSession, marketplace):
        super().__init__(timeout=300)
        self.session = session
        self.marketplace = marketplace
    
    @ui.button(label="✅ Publish", style=discord.ButtonStyle.success, custom_id="publish")
    async def publish_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        await self.marketplace.publish_listing(interaction.user, self.session)
        self.stop()
    
    @ui.button(label="❌ Abort", style=discord.ButtonStyle.danger, custom_id="abort")
    async def abort_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("❌ Listing creation cancelled.", ephemeral=True)
        self.marketplace.active_sessions.pop(interaction.user.id, None)
        self.stop()


class Marketplace:
    """
    Main Marketplace System
    Handles service listing creation, browsing, and management
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.marketplace_channel_name = "marketplace"
        self.active_sessions: Dict[int, MarketplaceListingSession] = {}
        self.minimum_level = 5  # Minimum level required to create listings
        self.submission_webhook_url = None  # Webhook for open submissions
    
    async def check_user_level(self, user_id: int) -> tuple[bool, int]:
        """Check if user meets minimum level requirement"""
        try:
            cursor = await self.db.execute(
                "SELECT level FROM users WHERE user_id = ?",
                (user_id,)
            )
            result = await cursor.fetchone()
            
            if result:
                level = result[0]
                return level >= self.minimum_level, level
            return False, 0
            
        except Exception as e:
            print(f"✗ Error checking user level: {e}")
            return False, 0
    
    async def start_listing_creation(self, user: discord.User):
        """Step 1: Start the listing creation process"""
        
        # Check if user already has an active session
        if user.id in self.active_sessions:
            try:
                await user.send("⚠️ You already have an active listing in progress. Please complete or cancel it first.")
            except:
                pass
            return
        
        # Check user level
        can_create, level = await self.check_user_level(user.id)
        if not can_create:
            try:
                await user.send(
                    f"❌ You need to be at least level {self.minimum_level} to create marketplace listings.\n"
                    f"Your current level: {level}\n\n"
                    f"Keep participating in the community to level up!"
                )
            except:
                pass
            return
        
        # Create new session
        session = MarketplaceListingSession(user.id)
        self.active_sessions[user.id] = session
        
        # Send Step 1: Listing Type
        embed = discord.Embed(
            title="📋 NEW LISTING",
            description="Hello! I'm here to help you with your journey into the TEN Marketplace.\n\n"
                       "First, what would you like to post?",
            color=discord.Color.blue()
        )
        embed.set_footer(text='Step 1 of 9 • Send "abort" to cancel')
        
        try:
            view = ListingTypeView(session, self)
            await user.send(embed=embed, view=view)
        except discord.Forbidden:
            print(f"Cannot send DM to {user.name}")
            self.active_sessions.pop(user.id, None)
    
    async def show_skills_step(self, user: discord.User, session: MarketplaceListingSession):
        """Step 2: Skills Selection"""
        
        tips_embed = discord.Embed(
            title="💡 TIPS FOR SELLING",
            description=(
                "• Showcase your best and most relevant work in your portfolio\n"
                "• Be honest about your skill level and turnaround times\n"
                "• Respond promptly when buyers apply—first impressions matter\n"
                "• Set clear rates to avoid negotiation friction\n"
                "• Use the job channel for ALL communication—never DM"
            ),
            color=discord.Color.gold()
        )
        
        skills_embed = discord.Embed(
            title="🛠️ SKILLS",
            description="Select the skills that best describe your services.\n"
                       "You can select up to 3 skills.",
            color=discord.Color.blue()
        )
        skills_embed.set_footer(text='Step 2 of 9 • Send "abort" to cancel')
        
        try:
            await user.send(embed=tips_embed)
            view = SkillsView(session, self)
            await user.send(embed=skills_embed, view=view)
        except Exception as e:
            print(f"Error in skills step: {e}")
    
    async def show_rates_step(self, user: discord.User, session: MarketplaceListingSession):
        """Step 3: Rate Type Selection"""
        
        embed = discord.Embed(
            title="💵 RATES",
            description="How do you charge for your services?\n\n"
                       "First, select your rate type:",
            color=discord.Color.green()
        )
        embed.set_footer(text='Step 3 of 9 • Send "abort" to cancel')
        
        try:
            view = RateTypeView(session, self)
            await user.send(embed=embed, view=view)
        except Exception as e:
            print(f"Error in rates step: {e}")
    
    async def show_rate_amount_step(self, user: discord.User, session: MarketplaceListingSession):
        """Step 3b: Rate Amount Input"""
        
        rate_type_display = session.rate_type.lower().replace(" ", "/")
        
        embed = discord.Embed(
            title="💵 RATES",
            description=f"You selected: **{session.rate_type}**\n\n"
                       f"Now enter your rate amount in USD (numbers only).\n"
                       f"Example: `30` for ${rate_type_display}",
            color=discord.Color.green()
        )
        embed.add_field(
            name="⚠️ Minimum rate is $10",
            value="",
            inline=False
        )
        embed.set_footer(text='Step 3 of 9 • Send "abort" to cancel')
        
        try:
            await user.send(embed=embed)
            
            # Wait for user response
            def check(m):
                return m.author.id == user.id and isinstance(m.channel, discord.DMChannel)
            
            try:
                msg = await self.bot.wait_for('message', timeout=300.0, check=check)
                
                if msg.content.lower() == 'abort':
                    await user.send("❌ Listing creation cancelled.")
                    self.active_sessions.pop(user.id, None)
                    return
                
                # Parse rate amount
                rate_match = re.search(r'\d+', msg.content)
                if rate_match:
                    rate_amount = int(rate_match.group())
                    if rate_amount < 10:
                        await user.send("❌ Minimum rate is $10. Please try again.")
                        await self.show_rate_amount_step(user, session)
                        return
                    
                    session.rate_amount = rate_amount
                    await self.show_expertise_step(user, session)
                else:
                    await user.send("❌ Invalid amount. Please enter numbers only.")
                    await self.show_rate_amount_step(user, session)
                    
            except asyncio.TimeoutError:
                await user.send("⏱️ Listing creation timed out. Please start over with `!create_listing`")
                self.active_sessions.pop(user.id, None)
                
        except Exception as e:
            print(f"Error in rate amount step: {e}")
    
    async def show_expertise_step(self, user: discord.User, session: MarketplaceListingSession):
        """Step 4: Expertise Description"""
        
        embed = discord.Embed(
            title="✨ EXPERTISE",
            description="Describe your expertise and what makes your services unique.\n\n"
                       "This is your pitch—tell potential clients:\n"
                       "• What you specialize in\n"
                       "• Your style or approach\n"
                       "• Tools/software you use\n"
                       "• What clients can expect",
            color=discord.Color.purple()
        )
        embed.add_field(
            name="✨ Maximum 1024 characters",
            value="✨ You can use Discord formatting",
            inline=False
        )
        embed.set_footer(text='Step 4 of 9 • Send "abort" to cancel')
        
        try:
            await user.send(embed=embed)
            
            # Wait for user response
            def check(m):
                return m.author.id == user.id and isinstance(m.channel, discord.DMChannel)
            
            try:
                msg = await self.bot.wait_for('message', timeout=600.0, check=check)
                
                if msg.content.lower() == 'abort':
                    await user.send("❌ Listing creation cancelled.")
                    self.active_sessions.pop(user.id, None)
                    return
                
                if len(msg.content) > 1024:
                    await user.send(f"❌ Your expertise description is too long ({len(msg.content)} characters). Maximum is 1024. Please try again.")
                    await self.show_expertise_step(user, session)
                    return
                
                session.expertise = msg.content
                await self.show_scope_step(user, session)
                
            except asyncio.TimeoutError:
                await user.send("⏱️ Listing creation timed out. Please start over with `!create_listing`")
                self.active_sessions.pop(user.id, None)
                
        except Exception as e:
            print(f"Error in expertise step: {e}")
    
    async def show_scope_step(self, user: discord.User, session: MarketplaceListingSession):
        """Step 5: Scope Selection"""
        
        embed = discord.Embed(
            title="⚠️ SCOPE",
            description="What type of work are you available for?",
            color=discord.Color.orange()
        )
        embed.set_footer(text='Step 5 of 9 • Send "abort" to cancel')
        
        try:
            view = ScopeView(session, self)
            await user.send(embed=embed, view=view)
        except Exception as e:
            print(f"Error in scope step: {e}")
    
    async def show_portfolio_step(self, user: discord.User, session: MarketplaceListingSession):
        """Step 6: Portfolio Links"""
        
        embed = discord.Embed(
            title="🔗 PORTFOLIO",
            description="Share links to your portfolio or previous work.\n\n"
                       "You can provide up to 5 links, one per message.\n"
                       "Accepted platforms: Behance, Dribbble, ArtStation, Fiverr, personal websites, or any other portfolio site.\n\n"
                       'Send your links now, or click "Next" when done.',
            color=discord.Color.blue()
        )
        embed.set_footer(text='Step 6 of 9 • Send "abort" to cancel')
        
        try:
            # Create a view with Next button
            view = ui.View(timeout=600)
            next_button = ui.Button(label="Next ➡️", style=discord.ButtonStyle.primary)
            
            async def next_callback(interaction: discord.Interaction):
                await interaction.response.defer()
                view.stop()
                await self.show_attachments_step(user, session)
            
            next_button.callback = next_callback
            view.add_item(next_button)
            
            await user.send(embed=embed, view=view)
            
            # Collect portfolio links
            def check(m):
                return m.author.id == user.id and isinstance(m.channel, discord.DMChannel)
            
            while len(session.portfolio_links) < 5:
                try:
                    msg = await self.bot.wait_for('message', timeout=600.0, check=check)
                    
                    if msg.content.lower() == 'abort':
                        await user.send("❌ Listing creation cancelled.")
                        self.active_sessions.pop(user.id, None)
                        return
                    
                    # Check if it's a URL
                    url_pattern = r'https?://[^\s]+'
                    urls = re.findall(url_pattern, msg.content)
                    
                    if urls:
                        for url in urls[:5 - len(session.portfolio_links)]:
                            session.portfolio_links.append(url)
                            await msg.add_reaction("✅")
                        
                        if len(session.portfolio_links) >= 5:
                            await user.send("✅ Maximum 5 links reached. Moving to next step...")
                            await self.show_attachments_step(user, session)
                            return
                    
                except asyncio.TimeoutError:
                    # Timeout means they're done or clicked Next
                    break
                    
        except Exception as e:
            print(f"Error in portfolio step: {e}")
    
    async def show_attachments_step(self, user: discord.User, session: MarketplaceListingSession):
        """Step 7: File Attachments"""
        
        embed = discord.Embed(
            title="📎 FILE ATTACHMENTS",
            description="You can attach files to your listing to help showcase your work better.\n\n"
                       "• You can upload up to 5 files\n"
                       "• The first image submitted will be featured in the embed\n"
                       "• Other images and files will be linked\n"
                       "• File names will be shown, so you can reference them\n\n"
                       'Upload your files now, or click "Next" to skip.',
            color=discord.Color.blue()
        )
        embed.set_footer(text='Step 7 of 9 • Send "abort" to cancel')
        
        try:
            # Create a view with Next button
            view = ui.View(timeout=600)
            next_button = ui.Button(label="Next ➡️", style=discord.ButtonStyle.primary)
            
            async def next_callback(interaction: discord.Interaction):
                await interaction.response.defer()
                view.stop()
                await self.show_communication_step(user, session)
            
            next_button.callback = next_callback
            view.add_item(next_button)
            
            await user.send(embed=embed, view=view)
            
            # Collect attachments
            def check(m):
                return m.author.id == user.id and isinstance(m.channel, discord.DMChannel)
            
            while len(session.attachments) < 5:
                try:
                    msg = await self.bot.wait_for('message', timeout=600.0, check=check)
                    
                    if msg.content.lower() == 'abort':
                        await user.send("❌ Listing creation cancelled.")
                        self.active_sessions.pop(user.id, None)
                        return
                    
                    # Check for attachments
                    if msg.attachments:
                        for attachment in msg.attachments[:5 - len(session.attachments)]:
                            session.attachments.append(attachment.url)
                            await msg.add_reaction("✅")
                        
                        if len(session.attachments) >= 5:
                            await user.send("✅ Maximum 5 files reached. Moving to next step...")
                            await self.show_communication_step(user, session)
                            return
                    
                except asyncio.TimeoutError:
                    break
                    
        except Exception as e:
            print(f"Error in attachments step: {e}")
    
    async def show_communication_step(self, user: discord.User, session: MarketplaceListingSession):
        """Step 8: Communication Preference"""
        
        embed = discord.Embed(
            title="💬 COMMUNICATION PREFERENCE",
            description="How would you like applicants to reach you?",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🔒 Private Channel (Recommended)",
            value="Communication happens in a TEN-managed channel. Staff can assist if issues arise. DM spam is prohibited and enforced.",
            inline=False
        )
        
        embed.add_field(
            name="📩 DM Open (No Support)",
            value="Your name is visible for direct contact. **By choosing this, you waive all TEN staff support** for this listing. Proceed at your own risk.",
            inline=False
        )
        
        embed.set_footer(text='Step 8 of 9 • Send "abort" to cancel')
        
        try:
            view = CommunicationPreferenceView(session, self)
            await user.send(embed=embed, view=view)
        except Exception as e:
            print(f"Error in communication step: {e}")
    
    async def show_confirmation_step(self, user: discord.User, session: MarketplaceListingSession):
        """Step 9: Final Confirmation"""
        
        # Generate listing ID
        listing_id = f"{user.id % 100000:05d}"
        
        embed = discord.Embed(
            title="🟢 Services Available!",
            description=f"**Sell Listing #{listing_id}**",
            color=discord.Color.green()
        )
        
        # Skills
        skills_text = ", ".join(session.skills)
        embed.add_field(
            name="🛠️ Skills",
            value=skills_text,
            inline=True
        )
        
        # Rate
        rate_text = f"${session.rate_amount}/{session.rate_type.lower().replace(' ', '')}"
        embed.add_field(
            name="💵 Rate",
            value=rate_text,
            inline=True
        )
        
        # Contact
        contact_emoji = "🔒" if session.communication_preference == "Private Channel" else "📩"
        embed.add_field(
            name="📞 Contact",
            value=f"{contact_emoji} {session.communication_preference}",
            inline=True
        )
        
        # Expertise
        expertise_preview = session.expertise[:100] + "..." if len(session.expertise) > 100 else session.expertise
        embed.add_field(
            name="✨ Expertise",
            value=expertise_preview,
            inline=False
        )
        
        # Scope
        scope_emoji = {"Full-Time": "🔵", "Part-Time": "🟠", "One-Time": "⚪", "Any": "🔵"}.get(session.scope, "⚪")
        embed.add_field(
            name="⚠️ Scope",
            value=f"{scope_emoji} {session.scope}",
            inline=False
        )
        
        # Footer with expiration
        expires_at = datetime.utcnow() + timedelta(days=5)
        embed.set_footer(
            text=f"Listing ID: {listing_id} • 0 edits • Expires in 5 days • Today at {datetime.utcnow().strftime('%H:%M')}"
        )
        
        try:
            view = FinalConfirmationView(session, self)
            await user.send(embed=embed, view=view)
        except Exception as e:
            print(f"Error in confirmation step: {e}")
    
    async def publish_listing(self, user: discord.User, session: MarketplaceListingSession):
        """Publish the listing to the marketplace channel"""
        
        try:
            # Save to database
            listing_id = await self.save_listing_to_db(user.id, session)
            
            # Find marketplace channel
            marketplace_channel = None
            for guild in self.bot.guilds:
                channel = discord.utils.get(guild.text_channels, name=self.marketplace_channel_name)
                if channel:
                    marketplace_channel = channel
                    break
            
            if not marketplace_channel:
                await user.send("❌ Error: Marketplace channel not found. Please contact an administrator.")
                return
            
            # Create listing embed
            embed = discord.Embed(
                title="🟢 Services Available!",
                description=f"**Sell Listing #{listing_id}**",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            # Add fields
            embed.add_field(
                name="🛠️ Skills",
                value=", ".join(session.skills),
                inline=True
            )
            
            embed.add_field(
                name="💵 Rate",
                value=f"${session.rate_amount}/{session.rate_type.lower().replace(' ', '')}",
                inline=True
            )
            
            contact_emoji = "🔒" if session.communication_preference == "Private Channel" else "📩"
            embed.add_field(
                name="📞 Contact",
                value=f"{contact_emoji} {session.communication_preference}",
                inline=True
            )
            
            embed.add_field(
                name="✨ Expertise",
                value=session.expertise,
                inline=False
            )
            
            scope_emoji = {"Full-Time": "🔵", "Part-Time": "🟠", "One-Time": "⚪", "Any": "🔵"}.get(session.scope, "⚪")
            embed.add_field(
                name="⚠️ Scope",
                value=f"{scope_emoji} {session.scope}",
                inline=False
            )
            
            # Add portfolio links if any
            if session.portfolio_links:
                portfolio_text = "\n".join([f"[Link {i+1}]({link})" for i, link in enumerate(session.portfolio_links)])
                embed.add_field(
                    name="🔗 Portfolio",
                    value=portfolio_text,
                    inline=False
                )
            
            # Set thumbnail if attachments exist
            if session.attachments:
                embed.set_image(url=session.attachments[0])
                
                if len(session.attachments) > 1:
                    other_files = "\n".join([f"[Attachment {i+1}]({url})" for i, url in enumerate(session.attachments[1:])])
                    embed.add_field(
                        name="📎 Additional Files",
                        value=other_files,
                        inline=False
                    )
            
            embed.set_footer(
                text=f"Listing ID: {listing_id} • Posted by {user.name} • Expires in 5 days"
            )
            
            # Post to marketplace
            message = await marketplace_channel.send(embed=embed)
            
            # Send to webhook if configured
            if self.submission_webhook_url:
                await self.send_to_webhook(embed, listing_id)
            
            # Confirm to user
            await user.send(
                f"✅ **Your listing has been published!**\n\n"
                f"Listing ID: `{listing_id}`\n"
                f"Posted in: {marketplace_channel.mention}\n"
                f"Expires: <t:{int((datetime.utcnow() + timedelta(days=5)).timestamp())}:R>\n\n"
                f"Good luck with your services! 🎉"
            )
            
            # Clean up session
            self.active_sessions.pop(user.id, None)
            
            print(f"✓ Published marketplace listing #{listing_id} by {user.name}")
            
        except Exception as e:
            print(f"✗ Error publishing listing: {e}")
            await user.send("❌ An error occurred while publishing your listing. Please try again later.")
    
    async def save_listing_to_db(self, user_id: int, session: MarketplaceListingSession) -> int:
        """Save listing to database and return listing ID"""
        try:
            expires_at = datetime.utcnow() + timedelta(days=5)
            
            cursor = await self.db.execute(
                """
                INSERT INTO marketplace_listings (
                    user_id, listing_type, skills, expertise, scope,
                    rate_type, rate_amount, portfolio_links, attachments,
                    communication_preference, created_at, expires_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    user_id,
                    session.listing_type,
                    ",".join(session.skills),
                    session.expertise,
                    session.scope,
                    session.rate_type,
                    session.rate_amount,
                    ",".join(session.portfolio_links) if session.portfolio_links else None,
                    ",".join(session.attachments) if session.attachments else None,
                    session.communication_preference,
                    datetime.utcnow().isoformat(),
                    expires_at.isoformat()
                )
            )
            
            await self.db.commit()
            return cursor.lastrowid
            
        except Exception as e:
            print(f"✗ Error saving listing to database: {e}")
            raise
    
    async def send_to_webhook(self, embed: discord.Embed, listing_id: int):
        """Send listing to configured webhook"""
        try:
            from discord import Webhook
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                webhook = Webhook.from_url(self.submission_webhook_url, session=session)
                await webhook.send(
                    content=f"🆕 New TEN Marketplace Listing #{listing_id}",
                    embed=embed,
                    username="TEN Marketplace"
                )
                print(f"✓ Sent listing #{listing_id} to webhook")
        except Exception as e:
            print(f"✗ Error sending to webhook: {e}")
    
    async def set_webhook(self, webhook_url: str) -> bool:
        """Set the submission webhook URL"""
        try:
            # Validate webhook URL
            if not webhook_url.startswith('https://discord.com/api/webhooks/'):
                return False
            
            self.submission_webhook_url = webhook_url
            
            # Save to database
            await self.db.execute(
                """INSERT OR REPLACE INTO marketplace_config (key, value) 
                   VALUES ('submission_webhook', ?)""",
                (webhook_url,)
            )
            await self.db.commit()
            return True
        except Exception as e:
            print(f"✗ Error setting webhook: {e}")
            return False
    
    async def load_webhook(self):
        """Load webhook URL from database"""
        try:
            cursor = await self.db.execute(
                "SELECT value FROM marketplace_config WHERE key = 'submission_webhook'"
            )
            result = await cursor.fetchone()
            if result:
                self.submission_webhook_url = result[0]
                print(f"✓ Loaded marketplace webhook configuration")
        except Exception as e:
            print(f"✗ Error loading webhook: {e}")


class MarketplaceCommands(commands.Cog):
    """Commands for marketplace system"""
    
    def __init__(self, bot, marketplace):
        self.bot = bot
        self.marketplace = marketplace
    
    @commands.command(name='create_listing')
    async def create_listing(self, ctx):
        """
        Start creating a marketplace listing
        
        Usage: !create_listing
        """
        # Delete command message for privacy
        try:
            await ctx.message.delete()
        except:
            pass
        
        # Start listing creation in DMs
        await self.marketplace.start_listing_creation(ctx.author)
        
        # Send confirmation in channel
        msg = await ctx.send(f"{ctx.author.mention} Check your DMs to create your marketplace listing! 📬")
        await asyncio.sleep(10)
        try:
            await msg.delete()
        except:
            pass
    
    @commands.command(name='my_listings')
    async def my_listings(self, ctx):
        """
        View your active marketplace listings
        
        Usage: !my_listings
        """
        try:
            cursor = await self.marketplace.db.execute(
                """
                SELECT id, listing_type, skills, rate_amount, rate_type, created_at, expires_at
                FROM marketplace_listings
                WHERE user_id = ? AND active = 1
                ORDER BY created_at DESC
                """,
                (ctx.author.id,)
            )
            listings = await cursor.fetchall()
            
            if not listings:
                await ctx.send("You don't have any active marketplace listings.")
                return
            
            embed = discord.Embed(
                title=f"📋 Your Marketplace Listings",
                description=f"You have {len(listings)} active listing(s)",
                color=discord.Color.blue()
            )
            
            for listing in listings[:5]:  # Show max 5
                listing_id, listing_type, skills, rate_amount, rate_type, created_at, expires_at = listing
                
                embed.add_field(
                    name=f"Listing #{listing_id}",
                    value=f"**Type:** {listing_type}\n"
                          f"**Skills:** {skills}\n"
                          f"**Rate:** ${rate_amount}/{rate_type}\n"
                          f"**Expires:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:R>",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"Error fetching user listings: {e}")
            await ctx.send("❌ Error fetching your listings.")
    
    @commands.command(name='setup_marketplace_webhook')
    @commands.has_permissions(administrator=True)
    async def setup_marketplace_webhook(self, ctx, webhook_url: str = None):
        """
        Configure the marketplace submission webhook (Admin only)
        
        Usage: !setup_marketplace_webhook <webhook_url>
        Example: !setup_marketplace_webhook https://discord.com/api/webhooks/...
        
        To remove: !setup_marketplace_webhook remove
        """
        if not webhook_url:
            # Show current configuration
            if self.marketplace.submission_webhook_url:
                embed = discord.Embed(
                    title="🔧 Marketplace Webhook Configuration",
                    description="Webhook is currently configured.",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="Status",
                    value="✅ Active",
                    inline=True
                )
                embed.add_field(
                    name="URL",
                    value=f"`{self.marketplace.submission_webhook_url[:50]}...`",
                    inline=False
                )
            else:
                embed = discord.Embed(
                    title="🔧 Marketplace Webhook Configuration",
                    description="No webhook configured.",
                    color=discord.Color.orange()
                )
                embed.add_field(
                    name="Setup",
                    value="Use `!setup_marketplace_webhook <url>` to configure",
                    inline=False
                )
            await ctx.send(embed=embed)
            return
        
        if webhook_url.lower() == 'remove':
            self.marketplace.submission_webhook_url = None
            await self.marketplace.db.execute(
                "DELETE FROM marketplace_config WHERE key = 'submission_webhook'"
            )
            await self.marketplace.db.commit()
            await ctx.send("✅ Marketplace webhook removed.")
            return
        
        # Set webhook
        success = await self.marketplace.set_webhook(webhook_url)
        
        if success:
            embed = discord.Embed(
                title="✅ Webhook Configured",
                description="Marketplace submissions will now be sent to the configured webhook.",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Test",
                value="Create a test listing to verify the webhook works.",
                inline=False
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Invalid webhook URL. Please provide a valid Discord webhook URL.")
    
    @commands.command(name='marketplace_help')
    async def marketplace_help(self, ctx):
        """Show marketplace help and information"""
        
        embed = discord.Embed(
            title="📋 TEN Marketplace Help",
            description="Welcome to the TEN Marketplace! Here's how to use it:",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Creating a Listing",
            value="Use `!create_listing` to start the interactive listing creation process in DMs.\n"
                  f"**Minimum Level Required:** {self.marketplace.minimum_level}",
            inline=False
        )
        
        embed.add_field(
            name="Managing Listings",
            value="`!my_listings` - View your active listings\n"
                  "`!delete_listing <id>` - Delete a listing\n"
                  "`!edit_listing <id>` - Edit a listing",
            inline=False
        )
        
        embed.add_field(
            name="Listing Duration",
            value="Listings expire after 5 days and must be renewed.",
            inline=False
        )
        
        embed.add_field(
            name="Communication",
            value="Choose between:\n"
                  "🔒 **Private Channel** - Managed communication with staff support\n"
                  "📩 **DM Open** - Direct contact (no staff support)",
            inline=False
        )
        
        if ctx.author.guild_permissions.administrator:
            embed.add_field(
                name="⚙️ Admin Commands",
                value="`!setup_marketplace_webhook <url>` - Configure submission webhook\n"
                      "`!setup_marketplace_webhook` - View current configuration\n"
                      "`!setup_marketplace_webhook remove` - Remove webhook",
                inline=False
            )
        
        await ctx.send(embed=embed)


def setup(bot, db):
    """Setup function to initialize marketplace"""
    marketplace = Marketplace(bot, db)
    
    # Load webhook configuration
    import asyncio
    asyncio.create_task(marketplace.load_webhook())
    
    bot.add_cog(MarketplaceCommands(bot, marketplace))
    return marketplace
