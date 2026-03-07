"""
Business Features Module
Deal/Opportunity Board, Collaboration Matcher, Resource Library, Community Health
"""

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json

class DealBoard:
    """
    Business opportunity and deal posting system
    
    Features:
    - Post business opportunities
    - Categorize by type (marketing, crypto, NFT, general)
    - Upvote/downvote system
    - Auto-expire old posts (30 days)
    - Track successful deals
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.deal_channel_name = "deals-opportunities"
        self.categories = ['marketing', 'crypto', 'nft', 'trading', 'general', 'partnership']
        
        # Start cleanup task
        self.cleanup_expired_deals.start()
    
    async def create_deal(self, author: discord.Member, title: str, 
                         description: str, category: str) -> Optional[int]:
        """
        Create a new deal/opportunity post
        
        Args:
            author: User posting the deal
            title: Deal title
            description: Deal description
            category: Category (marketing, crypto, etc.)
            
        Returns:
            Deal ID if successful
        """
        if category not in self.categories:
            return None
        
        try:
            cursor = await self.db.execute(
                """
                INSERT INTO deals (
                    user_id, guild_id, title, description, 
                    category, posted_at, expires_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    author.id,
                    author.guild.id,
                    title,
                    description,
                    category,
                    datetime.utcnow().isoformat(),
                    (datetime.utcnow() + timedelta(days=30)).isoformat()
                )
            )
            await self.db.commit()
            
            deal_id = cursor.lastrowid
            
            # Post to channel
            await self.post_deal_to_channel(author.guild, deal_id, author, title, description, category)
            
            return deal_id
            
        except Exception as e:
            print(f"✗ Error creating deal: {e}")
            return None
    
    async def post_deal_to_channel(self, guild: discord.Guild, deal_id: int,
                                   author: discord.Member, title: str, 
                                   description: str, category: str):
        """Post deal to deals channel"""
        channel = discord.utils.get(guild.text_channels, name=self.deal_channel_name)
        if not channel:
            return
        
        # Category emoji mapping
        category_emojis = {
            'marketing': '📢',
            'crypto': '₿',
            'nft': '🖼️',
            'trading': '📈',
            'general': '💼',
            'partnership': '🤝'
        }
        
        embed = discord.Embed(
            title=f"{category_emojis.get(category, '💼')} {title}",
            description=description,
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="Category", value=category.title(), inline=True)
        embed.add_field(name="Posted by", value=author.mention, inline=True)
        embed.add_field(name="Deal ID", value=f"`{deal_id}`", inline=True)
        embed.add_field(name="Expires", value="<t:{}:R>".format(
            int((datetime.utcnow() + timedelta(days=30)).timestamp())
        ), inline=True)
        
        embed.set_footer(text="React with 👍 if interested • 👎 to flag as spam")
        
        message = await channel.send(embed=embed)
        
        # Add reaction buttons
        await message.add_reaction("👍")
        await message.add_reaction("👎")
        
        # Store message ID
        await self.db.execute(
            "UPDATE deals SET message_id = ? WHERE id = ?",
            (message.id, deal_id)
        )
        await self.db.commit()
    
    @tasks.loop(hours=24)
    async def cleanup_expired_deals(self):
        """Remove expired deals"""
        try:
            cursor = await self.db.execute(
                """
                SELECT id, guild_id, message_id FROM deals
                WHERE active = 1 AND expires_at < ?
                """,
                (datetime.utcnow().isoformat(),)
            )
            expired = await cursor.fetchall()
            
            for deal_id, guild_id, message_id in expired:
                # Mark as inactive
                await self.db.execute(
                    "UPDATE deals SET active = 0 WHERE id = ?",
                    (deal_id,)
                )
                
                # Try to delete message
                guild = self.bot.get_guild(guild_id)
                if guild and message_id:
                    channel = discord.utils.get(guild.text_channels, name=self.deal_channel_name)
                    if channel:
                        try:
                            message = await channel.fetch_message(message_id)
                            await message.delete()
                        except:
                            pass
            
            await self.db.commit()
            print(f"✓ Cleaned up {len(expired)} expired deals")
            
        except Exception as e:
            print(f"✗ Error cleaning up deals: {e}")
    
    @cleanup_expired_deals.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()


class CollaborationMatcher:
    """
    Matches entrepreneurs with complementary skills
    
    Features:
    - Members set skills and interests
    - Bot suggests potential collaborators
    - DM introductions with mutual consent
    - Track successful collaborations
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        
        # Skill categories
        self.skill_categories = [
            'development', 'design', 'marketing', 'sales', 
            'finance', 'operations', 'content', 'community',
            'crypto', 'trading', 'nft'
        ]
    
    async def set_user_profile(self, user_id: int, guild_id: int, 
                               skills: List[str], interests: List[str], 
                               looking_for: str):
        """
        Set or update user collaboration profile
        
        Args:
            user_id: User ID
            guild_id: Guild ID
            skills: List of skills user has
            interests: List of interests
            looking_for: What they're looking for in collaborators
        """
        try:
            await self.db.execute(
                """
                INSERT INTO collaboration_profiles (
                    user_id, guild_id, skills, interests, 
                    looking_for, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    skills = ?, interests = ?, looking_for = ?, updated_at = ?
                """,
                (
                    user_id, guild_id, 
                    json.dumps(skills), json.dumps(interests), looking_for,
                    datetime.utcnow().isoformat(),
                    json.dumps(skills), json.dumps(interests), looking_for,
                    datetime.utcnow().isoformat()
                )
            )
            await self.db.commit()
            return True
            
        except Exception as e:
            print(f"✗ Error setting collaboration profile: {e}")
            return False
    
    async def find_matches(self, user_id: int, guild_id: int, limit: int = 5) -> List[Dict]:
        """
        Find potential collaborators for user
        
        Args:
            user_id: User to find matches for
            guild_id: Guild context
            limit: Max number of matches
            
        Returns:
            List of matched user profiles with match scores
        """
        try:
            # Get user's profile
            cursor = await self.db.execute(
                """
                SELECT skills, interests FROM collaboration_profiles
                WHERE user_id = ? AND guild_id = ?
                """,
                (user_id, guild_id)
            )
            user_profile = await cursor.fetchone()
            
            if not user_profile:
                return []
            
            user_skills = set(json.loads(user_profile[0]))
            user_interests = set(json.loads(user_profile[1]))
            
            # Get all other profiles
            cursor = await self.db.execute(
                """
                SELECT user_id, skills, interests, looking_for
                FROM collaboration_profiles
                WHERE guild_id = ? AND user_id != ?
                """,
                (guild_id, user_id)
            )
            profiles = await cursor.fetchall()
            
            # Calculate match scores
            matches = []
            for other_id, skills_json, interests_json, looking_for in profiles:
                other_skills = set(json.loads(skills_json))
                other_interests = set(json.loads(interests_json))
                
                # Calculate complementary skills score
                complementary_score = len(user_skills - other_skills) * 2
                
                # Calculate shared interests score
                shared_interests_score = len(user_interests & other_interests) * 3
                
                # Total match score
                match_score = complementary_score + shared_interests_score
                
                if match_score > 0:
                    matches.append({
                        'user_id': other_id,
                        'score': match_score,
                        'complementary_skills': list(user_skills - other_skills),
                        'shared_interests': list(user_interests & other_interests),
                        'looking_for': looking_for
                    })
            
            # Sort by match score
            matches.sort(key=lambda x: x['score'], reverse=True)
            return matches[:limit]
            
        except Exception as e:
            print(f"✗ Error finding matches: {e}")
            return []


class ResourceLibrary:
    """
    Centralizes valuable resources shared in channels
    
    Features:
    - Save important messages to library
    - Categorize resources
    - Search functionality
    - Upvote best resources
    - Auto-categorize by channel topic
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        
        self.categories = [
            'marketing', 'crypto', 'nft', 'trading', 
            'business', 'tools', 'education', 'guides'
        ]
    
    async def save_resource(self, message: discord.Message, category: str, 
                           saved_by: int, tags: List[str] = None) -> Optional[int]:
        """
        Save a message as a resource
        
        Args:
            message: Message to save
            category: Resource category
            saved_by: User who saved it
            tags: Optional tags
            
        Returns:
            Resource ID if successful
        """
        try:
            cursor = await self.db.execute(
                """
                INSERT INTO resource_library (
                    message_id, channel_id, guild_id, author_id,
                    content, category, tags, saved_by, saved_at, upvotes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    message.id,
                    message.channel.id,
                    message.guild.id,
                    message.author.id,
                    message.content[:2000],
                    category,
                    json.dumps(tags or []),
                    saved_by,
                    datetime.utcnow().isoformat()
                )
            )
            await self.db.commit()
            
            return cursor.lastrowid
            
        except Exception as e:
            print(f"✗ Error saving resource: {e}")
            return None
    
    async def search_resources(self, guild_id: int, query: str = None, 
                              category: str = None, limit: int = 10) -> List[Dict]:
        """
        Search resources in library
        
        Args:
            guild_id: Guild to search in
            query: Text to search for
            category: Filter by category
            limit: Max results
            
        Returns:
            List of matching resources
        """
        try:
            sql = """
                SELECT id, content, category, tags, saved_at, upvotes, author_id
                FROM resource_library
                WHERE guild_id = ?
            """
            params = [guild_id]
            
            if query:
                sql += " AND content LIKE ?"
                params.append(f"%{query}%")
            
            if category:
                sql += " AND category = ?"
                params.append(category)
            
            sql += " ORDER BY upvotes DESC, saved_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = await self.db.execute(sql, params)
            results = await cursor.fetchall()
            
            return [
                {
                    'id': row[0],
                    'content': row[1],
                    'category': row[2],
                    'tags': json.loads(row[3]),
                    'saved_at': row[4],
                    'upvotes': row[5],
                    'author_id': row[6]
                }
                for row in results
            ]
            
        except Exception as e:
            print(f"✗ Error searching resources: {e}")
            return []


class CommunityHealth:
    """
    Monitors overall community health and generates reports
    
    Features:
    - Track active vs inactive members
    - Measure engagement trends
    - Identify at-risk members (sudden inactivity)
    - Weekly health reports
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.weekly_report_task.start()
    
    async def calculate_health_score(self, guild_id: int) -> Dict:
        """
        Calculate overall community health score (0-100)
        
        Args:
            guild_id: Guild to analyze
            
        Returns:
            Dictionary with health metrics
        """
        try:
            # Active users (messaged in last 7 days)
            cursor = await self.db.execute(
                """
                SELECT COUNT(DISTINCT user_id) FROM channel_activity
                WHERE guild_id = ? AND date >= date('now', '-7 days')
                """,
                (guild_id,)
            )
            active_users = (await cursor.fetchone())[0] or 0
            
            # Total users
            guild = self.bot.get_guild(guild_id)
            total_users = len([m for m in guild.members if not m.bot]) if guild else 0
            
            # Activity rate
            activity_rate = (active_users / total_users * 100) if total_users > 0 else 0
            
            # Average messages per active user
            cursor = await self.db.execute(
                """
                SELECT AVG(message_count) FROM (
                    SELECT SUM(message_count) as message_count
                    FROM channel_activity
                    WHERE guild_id = ? AND date >= date('now', '-7 days')
                    GROUP BY user_id
                )
                """,
                (guild_id,)
            )
            avg_messages = (await cursor.fetchone())[0] or 0
            
            # Health score calculation
            health_score = min(100, int(
                (activity_rate * 0.4) +  # 40% weight on active users
                (min(avg_messages / 10, 1) * 30) +  # 30% weight on message volume
                (30)  # 30% base score
            ))
            
            return {
                'health_score': health_score,
                'active_users': active_users,
                'total_users': total_users,
                'activity_rate': activity_rate,
                'avg_messages_per_user': avg_messages
            }
            
        except Exception as e:
            print(f"✗ Error calculating health score: {e}")
            return {}
    
    @tasks.loop(hours=168)  # Weekly
    async def weekly_report_task(self):
        """Generate weekly community health report"""
        for guild in self.bot.guilds:
            await self.generate_weekly_report(guild)
    
    @weekly_report_task.before_loop
    async def before_weekly_report(self):
        await self.bot.wait_until_ready()
    
    async def generate_weekly_report(self, guild: discord.Guild):
        """Generate and post weekly health report"""
        try:
            health = await self.calculate_health_score(guild.id)
            
            # Find reports channel
            channel = discord.utils.get(guild.text_channels, name='analytics')
            if not channel:
                return
            
            # Determine health status
            score = health.get('health_score', 0)
            if score >= 80:
                status = "🟢 Excellent"
                color = discord.Color.green()
            elif score >= 60:
                status = "🟡 Good"
                color = discord.Color.gold()
            elif score >= 40:
                status = "🟠 Fair"
                color = discord.Color.orange()
            else:
                status = "🔴 Needs Attention"
                color = discord.Color.red()
            
            embed = discord.Embed(
                title="📊 Weekly Community Health Report",
                description=f"**Overall Health: {status}** (Score: {score}/100)",
                color=color,
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="Active Members",
                value=f"{health.get('active_users', 0)} / {health.get('total_users', 0)}\n"
                      f"({health.get('activity_rate', 0):.1f}% activity rate)",
                inline=True
            )
            
            embed.add_field(
                name="Engagement",
                value=f"{health.get('avg_messages_per_user', 0):.1f} messages per active user",
                inline=True
            )
            
            # Add recommendations
            recommendations = []
            if score < 60:
                recommendations.append("• Consider hosting community events")
                recommendations.append("• Reach out to inactive members")
            if health.get('activity_rate', 0) < 30:
                recommendations.append("• Focus on member retention")
            if health.get('avg_messages_per_user', 0) < 5:
                recommendations.append("• Encourage more engagement")
            
            if recommendations:
                embed.add_field(
                    name="📋 Recommendations",
                    value='\n'.join(recommendations),
                    inline=False
                )
            
            await channel.send(embed=embed)
            print(f"✓ Generated weekly health report for {guild.name}")
            
        except Exception as e:
            print(f"✗ Error generating weekly report: {e}")


# Combined commands cog
class BusinessFeaturesCommands(commands.Cog):
    """Commands for all business features"""
    
    def __init__(self, bot, deal_board, collab_matcher, resource_lib, community_health):
        self.bot = bot
        self.deal_board = deal_board
        self.collab_matcher = collab_matcher
        self.resource_lib = resource_lib
        self.community_health = community_health
    
    # Deal Board Commands
    @commands.command(name='post_deal')
    async def post_deal(self, ctx, category: str, title: str, *, description: str):
        """
        Post a business opportunity or deal
        
        Usage: !post_deal marketing "Looking for Marketing Partner" Full description here...
        Categories: marketing, crypto, nft, trading, general, partnership
        """
        if category not in self.deal_board.categories:
            await ctx.send(f"Invalid category. Choose from: {', '.join(self.deal_board.categories)}")
            return
        
        deal_id = await self.deal_board.create_deal(ctx.author, title, description, category)
        
        if deal_id:
            await ctx.send(f"✅ Deal posted successfully! ID: `{deal_id}`")
        else:
            await ctx.send("❌ Failed to post deal. Try again.")
    
    # Collaboration Matcher Commands
    @commands.command(name='set_profile')
    async def set_collaboration_profile(self, ctx, *, profile_text: str):
        """
        Set your collaboration profile
        
        Usage: !set_profile skills: development, design | interests: crypto, nft | looking for: marketing expert
        """
        try:
            parts = profile_text.split('|')
            skills_part = [p for p in parts if 'skills:' in p.lower()][0]
            interests_part = [p for p in parts if 'interests:' in p.lower()][0]
            looking_part = [p for p in parts if 'looking' in p.lower()][0]
            
            skills = [s.strip() for s in skills_part.split(':')[1].split(',')]
            interests = [i.strip() for i in interests_part.split(':')[1].split(',')]
            looking_for = looking_part.split(':')[1].strip()
            
            success = await self.collab_matcher.set_user_profile(
                ctx.author.id, ctx.guild.id, skills, interests, looking_for
            )
            
            if success:
                await ctx.send("✅ Your collaboration profile has been updated!")
            else:
                await ctx.send("❌ Failed to update profile.")
                
        except Exception as e:
            await ctx.send("Format: `!set_profile skills: x, y | interests: a, b | looking for: description`")
    
    @commands.command(name='find_collaborators')
    async def find_collaborators(self, ctx):
        """Find potential collaborators based on your profile"""
        matches = await self.collab_matcher.find_matches(ctx.author.id, ctx.guild.id)
        
        if not matches:
            await ctx.send("No matches found. Make sure you've set your profile with `!set_profile`")
            return
        
        embed = discord.Embed(
            title="🤝 Potential Collaborators",
            description="Here are some members with complementary skills",
            color=discord.Color.blue()
        )
        
        for i, match in enumerate(matches[:5], 1):
            member = ctx.guild.get_member(match['user_id'])
            if member:
                embed.add_field(
                    name=f"#{i} - {member.name}",
                    value=f"**Match Score:** {match['score']}\n"
                          f"**Complementary:** {', '.join(match['complementary_skills'][:3])}\n"
                          f"**Shared Interests:** {', '.join(match['shared_interests'][:3])}",
                    inline=False
                )
        
        await ctx.send(embed=embed)
    
    # Resource Library Commands
    @commands.command(name='save_resource')
    async def save_resource(self, ctx, message_id: int, category: str, *, tags: str = ""):
        """
        Save a message to the resource library
        
        Usage: !save_resource 123456789 marketing growth, ads, strategy
        """
        if category not in self.resource_lib.categories:
            await ctx.send(f"Invalid category. Choose from: {', '.join(self.resource_lib.categories)}")
            return
        
        try:
            message = await ctx.channel.fetch_message(message_id)
            tag_list = [t.strip() for t in tags.split(',')] if tags else []
            
            resource_id = await self.resource_lib.save_resource(
                message, category, ctx.author.id, tag_list
            )
            
            if resource_id:
                await ctx.send(f"✅ Resource saved! ID: `{resource_id}`")
            else:
                await ctx.send("❌ Failed to save resource.")
                
        except discord.NotFound:
            await ctx.send("❌ Message not found.")
    
    @commands.command(name='search_resources')
    async def search_resources(self, ctx, *, query: str):
        """
        Search the resource library
        
        Usage: !search_resources crypto trading
        """
        results = await self.resource_lib.search_resources(ctx.guild.id, query=query)
        
        if not results:
            await ctx.send("No resources found matching your query.")
            return
        
        embed = discord.Embed(
            title=f"📚 Resource Search: '{query}'",
            description=f"Found {len(results)} resources",
            color=discord.Color.blue()
        )
        
        for resource in results[:5]:
            embed.add_field(
                name=f"[{resource['category'].title()}] - {resource['upvotes']} 👍",
                value=f"{resource['content'][:100]}...\nID: `{resource['id']}`",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    # Community Health Commands
    @commands.command(name='health_check')
    @commands.has_permissions(moderate_members=True)
    async def health_check(self, ctx):
        """View current community health metrics"""
        health = await self.community_health.calculate_health_score(ctx.guild.id)
        
        score = health.get('health_score', 0)
        if score >= 80:
            status = "🟢 Excellent"
            color = discord.Color.green()
        elif score >= 60:
            status = "🟡 Good"
            color = discord.Color.gold()
        elif score >= 40:
            status = "🟠 Fair"
            color = discord.Color.orange()
        else:
            status = "🔴 Needs Attention"
            color = discord.Color.red()
        
        embed = discord.Embed(
            title="📊 Community Health Check",
            description=f"**Status: {status}**\nScore: {score}/100",
            color=color,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="Active Members",
            value=f"{health.get('active_users', 0)} / {health.get('total_users', 0)}",
            inline=True
        )
        
        embed.add_field(
            name="Activity Rate",
            value=f"{health.get('activity_rate', 0):.1f}%",
            inline=True
        )
        
        embed.add_field(
            name="Avg Messages",
            value=f"{health.get('avg_messages_per_user', 0):.1f} per user",
            inline=True
        )
        
        await ctx.send(embed=embed)


def setup(bot, db):
    """Setup function to initialize all business features"""
    deal_board = DealBoard(bot, db)
    collab_matcher = CollaborationMatcher(bot, db)
    resource_lib = ResourceLibrary(bot, db)
    community_health = CommunityHealth(bot, db)
    
    bot.add_cog(BusinessFeaturesCommands(bot, deal_board, collab_matcher, resource_lib, community_health))
    
    return {
        'deal_board': deal_board,
        'collab_matcher': collab_matcher,
        'resource_lib': resource_lib,
        'community_health': community_health
    }
