"""
Topic Detection & Smart Channel Routing
Analyzes message content to suggest appropriate channels
"""

import discord
from discord.ext import commands
from typing import Dict, List, Tuple, Optional
import re
from collections import defaultdict

class TopicDetection:
    """
    Analyzes message content and suggests appropriate channels
    
    Features:
    - Keyword-based topic detection
    - Channel-specific topic mapping
    - Smart routing suggestions
    - Cross-posting prevention
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        
        # Topic keywords mapped to channel categories
        self.topic_keywords = {
            'marketing': {
                'keywords': ['seo', 'ads', 'marketing', 'campaign', 'social media', 'instagram', 'facebook', 'tiktok', 'content', 'branding', 'email marketing', 'funnel'],
                'suggested_channels': ['marketing', 'social-media', 'advertising']
            },
            'crypto': {
                'keywords': ['crypto', 'bitcoin', 'ethereum', 'blockchain', 'defi', 'nft', 'wallet', 'token', 'coin', 'trading', 'btc', 'eth', 'web3', 'metamask'],
                'suggested_channels': ['crypto', 'nft', 'trading', 'blockchain']
            },
            'development': {
                'keywords': ['code', 'programming', 'python', 'javascript', 'api', 'database', 'github', 'bug', 'deploy', 'server', 'frontend', 'backend', 'react', 'node'],
                'suggested_channels': ['dev', 'tech', 'coding', 'programming']
            },
            'design': {
                'keywords': ['design', 'ui', 'ux', 'figma', 'photoshop', 'logo', 'branding', 'mockup', 'prototype', 'wireframe', 'canva'],
                'suggested_channels': ['design', 'creative', 'graphics']
            },
            'business': {
                'keywords': ['startup', 'business', 'entrepreneur', 'funding', 'investor', 'revenue', 'profit', 'llc', 'incorporation', 'partnership', 'contract'],
                'suggested_channels': ['business', 'startups', 'entrepreneurship']
            },
            'sales': {
                'keywords': ['sales', 'lead', 'prospect', 'client', 'deal', 'pitch', 'closing', 'negotiation', 'crm', 'outreach'],
                'suggested_channels': ['sales', 'deals', 'opportunities']
            },
            'help': {
                'keywords': ['help', 'question', 'how do i', 'can someone', 'need advice', 'stuck', 'problem', 'issue', 'error'],
                'suggested_channels': ['help', 'support', 'questions']
            },
            'general': {
                'keywords': ['hello', 'hi', 'hey', 'good morning', 'good night', 'how are you', 'whats up'],
                'suggested_channels': ['general', 'chat', 'lounge']
            }
        }
        
        # Whitelist for business terms (won't trigger spam detection)
        self.business_term_whitelist = [
            # Crypto addresses
            r'0x[a-fA-F0-9]{40}',  # Ethereum address
            r'[13][a-km-zA-HJ-NP-Z1-9]{25,34}',  # Bitcoin address
            # Contract addresses, ticker symbols
            r'\$[A-Z]{2,10}',  # Ticker symbols like $BTC
            # URLs for legitimate business purposes
            r'https?://(?:www\.)?(?:twitter|linkedin|github|medium)\.com/\S+',
        ]
        
        # Channel-specific threshold multipliers
        self.channel_thresholds = {
            'promotional': 2.0,  # Allow more promotional content
            'deals': 2.0,
            'opportunities': 2.0,
            'marketplace': 2.0,
            'general': 1.0,  # Normal thresholds
            'help': 0.8,  # Stricter in help channels
            'announcements': 0.5  # Very strict
        }
    
    def detect_topic(self, message_content: str) -> List[Tuple[str, float]]:
        """
        Detect topics in message content
        
        Returns:
            List of (topic, confidence) tuples
        """
        content_lower = message_content.lower()
        topic_scores = defaultdict(float)
        
        for topic, data in self.topic_keywords.items():
            keywords = data['keywords']
            matches = sum(1 for keyword in keywords if keyword in content_lower)
            
            if matches > 0:
                # Calculate confidence based on keyword matches
                confidence = min(matches / 3, 1.0)  # Cap at 1.0
                topic_scores[topic] = confidence
        
        # Sort by confidence
        sorted_topics = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_topics
    
    def is_whitelisted_content(self, content: str) -> bool:
        """Check if content contains whitelisted business terms"""
        for pattern in self.business_term_whitelist:
            if re.search(pattern, content):
                return True
        return False
    
    def get_channel_threshold_multiplier(self, channel_name: str) -> float:
        """Get spam threshold multiplier for channel"""
        channel_lower = channel_name.lower()
        
        for channel_type, multiplier in self.channel_thresholds.items():
            if channel_type in channel_lower:
                return multiplier
        
        return 1.0  # Default multiplier
    
    async def suggest_better_channel(self, message: discord.Message) -> Optional[discord.TextChannel]:
        """
        Suggest a better channel for the message
        
        Returns:
            Suggested channel or None
        """
        topics = self.detect_topic(message.content)
        
        if not topics or topics[0][1] < 0.3:  # Low confidence
            return None
        
        top_topic, confidence = topics[0]
        suggested_channel_names = self.topic_keywords[top_topic]['suggested_channels']
        
        # Find matching channel in guild
        for channel_name in suggested_channel_names:
            channel = discord.utils.get(message.guild.text_channels, name=channel_name)
            if channel and channel.id != message.channel.id:
                return channel
        
        return None
    
    async def check_and_suggest(self, message: discord.Message):
        """Check message and suggest better channel if needed"""
        if message.author.bot:
            return
        
        # Only suggest for messages with substantial content
        if len(message.content) < 20:
            return
        
        suggested_channel = await self.suggest_better_channel(message)
        
        if suggested_channel:
            # Send suggestion
            try:
                embed = discord.Embed(
                    title="💡 Channel Suggestion",
                    description=f"Hey {message.author.mention}! Your message might get better responses in {suggested_channel.mention}",
                    color=discord.Color.blue()
                )
                embed.set_footer(text="This is just a suggestion - you can continue here if you prefer!")
                
                await message.channel.send(embed=embed, delete_after=30)
            except:
                pass


class TopicDetectionCommands(commands.Cog):
    """Commands for topic detection"""
    
    def __init__(self, bot, topic_detection):
        self.bot = bot
        self.topic_detection = topic_detection
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Analyze messages for topic routing"""
        if message.author.bot or not message.guild:
            return
        
        await self.topic_detection.check_and_suggest(message)
    
    @commands.command(name='analyze_topic')
    @commands.has_permissions(moderate_members=True)
    async def analyze_topic(self, ctx, *, text: str):
        """
        Analyze text for topics (mods only)
        
        Usage: !analyze_topic <text>
        """
        topics = self.topic_detection.detect_topic(text)
        
        if not topics:
            await ctx.send("No topics detected.")
            return
        
        embed = discord.Embed(
            title="📊 Topic Analysis",
            color=discord.Color.blue()
        )
        
        for topic, confidence in topics[:5]:
            channels = ', '.join(f"#{ch}" for ch in self.topic_detection.topic_keywords[topic]['suggested_channels'])
            embed.add_field(
                name=f"{topic.title()} ({confidence*100:.0f}% confidence)",
                value=f"Suggested channels: {channels}",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='channel_threshold')
    @commands.has_permissions(administrator=True)
    async def channel_threshold(self, ctx):
        """View spam threshold multipliers for channels"""
        embed = discord.Embed(
            title="📊 Channel Spam Thresholds",
            description="Multipliers for spam detection (higher = more lenient)",
            color=discord.Color.blue()
        )
        
        for channel_type, multiplier in self.topic_detection.channel_thresholds.items():
            embed.add_field(
                name=channel_type.title(),
                value=f"{multiplier}x",
                inline=True
            )
        
        await ctx.send(embed=embed)


def setup(bot, db):
    """Setup function to initialize topic detection"""
    topic_detection = TopicDetection(bot, db)
    bot.add_cog(TopicDetectionCommands(bot, topic_detection))
    return topic_detection
