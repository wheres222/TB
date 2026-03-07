"""
Advanced Networking Features
Virtual Coffee Chats, Project Showcase, and Network Search
"""

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import asyncio
import json
import random

class AdvancedNetworking:
    """
    Advanced networking and community features
    
    Features:
    - Virtual Coffee Chats (1-on-1 matchmaking)
    - Project Showcase (Share work, voting)
    - Network Search (Find people by skills/interests)
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.match_coffee_chats.start()
        
    # --- Project Showcase ---
    
    async def submit_project(self, user_id, guild_id, title, description, link, category, image_url=None):
        """Submit a new project"""
        try:
            await self.db.execute(
                """
                INSERT INTO projects (user_id, guild_id, title, description, link, category, image_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, guild_id, title, description, link, category.lower(), image_url, datetime.utcnow().isoformat())
            )
            await self.db.commit()
            return True
        except Exception as e:
            print(f"✗ Error submitting project: {e}")
            return False

    async def get_projects(self, guild_id, category=None, limit=10):
        """Get projects, optionally filtered by category"""
        query = "SELECT id, user_id, title, description, link, category, upvotes, image_url FROM projects WHERE guild_id = ? AND active = 1"
        params = [guild_id]
        
        if category:
            query += " AND category = ?"
            params.append(category.lower())
            
        query += " ORDER BY upvotes DESC, created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor = await self.db.execute(query, tuple(params))
        return await cursor.fetchall()

    async def vote_project(self, project_id, user_id, vote_type=1):
        """Vote on a project"""
        # Check if project exists
        cursor = await self.db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if not await cursor.fetchone():
            return "not_found"
            
        try:
            # Try to insert vote
            await self.db.execute(
                "INSERT INTO project_votes (project_id, user_id, vote_type) VALUES (?, ?, ?)",
                (project_id, user_id, vote_type)
            )
            
            # Update project score
            await self.db.execute(
                "UPDATE projects SET upvotes = upvotes + ? WHERE id = ?",
                (vote_type, project_id)
            )
            await self.db.commit()
            return "success"
        except Exception:
            # User likely already voted
            return "already_voted"

    # --- Virtual Coffee Chats ---
    
    async def update_coffee_preferences(self, user_id, guild_id, interests, skills, looking_for, opt_in=1):
        """Update networking profile"""
        # Upsert preferences
        await self.db.execute(
            """
            INSERT INTO coffee_preferences (user_id, guild_id, interests, skills, looking_for, opt_in)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, guild_id) DO UPDATE SET
            interests = excluded.interests,
            skills = excluded.skills,
            looking_for = excluded.looking_for,
            opt_in = excluded.opt_in
            """,
            (user_id, guild_id, json.dumps(interests), json.dumps(skills), looking_for, opt_in)
        )
        await self.db.commit()

    async def find_matches(self, guild_id):
        """Find matches for coffee chats"""
        # Get all opted-in users
        cursor = await self.db.execute(
            "SELECT user_id, interests, skills FROM coffee_preferences WHERE guild_id = ? AND opt_in = 1",
            (guild_id,)
        )
        users = await cursor.fetchall()
        
        # Simple random matching for now, could be enhanced with interest overlap
        # Filter out users who already have a match this week (checked in loop or query)
        
        # This is a simplified matching logic
        candidates = []
        for u in users:
            uid, interests_json, skills_json = u
            candidates.append({
                'id': uid,
                'interests': json.loads(interests_json) if interests_json else [],
                'skills': json.loads(skills_json) if skills_json else []
            })
            
        random.shuffle(candidates)
        matches = []
        
        while len(candidates) >= 2:
            u1 = candidates.pop()
            u2 = candidates.pop()
            matches.append((u1, u2))
            
        return matches

    # --- Network Search ---
    
    async def search_users(self, guild_id, query, search_type="interest"):
        """Search users by interest or skill"""
        # This does a broad text search on the JSON stored fields
        sql_query = f"""
            SELECT user_id, interests, skills, looking_for 
            FROM coffee_preferences 
            WHERE guild_id = ? AND {search_type}s LIKE ?
        """
        cursor = await self.db.execute(sql_query, (guild_id, f"%{query}%"))
        return await cursor.fetchall()

    @tasks.loop(hours=168) # Weekly
    async def match_coffee_chats(self):
        """Weekly task to generate coffee chat matches"""
        for guild in self.bot.guilds:
            matches = await self.find_matches(guild.id)
            week_of = datetime.utcnow().date().isoformat()
            
            for u1, u2 in matches:
                # Store match
                try:
                    await self.db.execute(
                        """
                        INSERT INTO coffee_matches (user1_id, user2_id, week_of, status, created_at)
                        VALUES (?, ?, ?, 'pending', ?)
                        """,
                        (u1['id'], u2['id'], week_of, datetime.utcnow().isoformat())
                    )
                    
                    # Notify users
                    member1 = guild.get_member(u1['id'])
                    member2 = guild.get_member(u2['id'])
                    
                    if member1 and member2:
                        embed = discord.Embed(
                            title="☕ Your Weekly Coffee Match!"
                        )
                        embed.description = f"You've been matched with **{member2.name}**!"
                        embed.add_field(name="Their Interests", value=", ".join(u2['interests']) or "None listed", inline=False)
                        embed.add_field(name="Their Skills", value=", ".join(u2['skills']) or "None listed", inline=False)
                        embed.set_footer(text="Schedule a time to chat!")
                        
                        try:
                            await member1.send(embed=embed)
                        except: pass
                        
                        embed.description = f"You've been matched with **{member1.name}**!"
                        embed.clear_fields()
                        embed.add_field(name="Their Interests", value=", ".join(u1['interests']) or "None listed", inline=False)
                        embed.add_field(name="Their Skills", value=", ".join(u1['skills']) or "None listed", inline=False)
                        
                        try:
                            await member2.send(embed=embed)
                        except: pass
                        
                except Exception as e:
                    print(f"Error creating match: {e}")
                    
            await self.db.commit()

    @match_coffee_chats.before_loop
    async def before_match(self):
        await self.bot.wait_until_ready()


class AdvancedNetworkingCommands(commands.Cog):
    """Commands for Advanced Networking"""
    
    def __init__(self, bot, networking):
        self.bot = bot
        self.networking = networking
        
    # --- Project Showcase Commands ---
    
    @commands.command(name='submit_project')
    async def submit_project(self, ctx, category: str, link: str, *, title_desc: str):
        """
        Submit a project to the showcase.
        Usage: !submit_project <category> <link> <Title | Description>
        """
        if '|' in title_desc:
            title, desc = title_desc.split('|', 1)
        else:
            title = title_desc
            desc = "No description provided."
            
        title = title.strip()
        desc = desc.strip()
        
        success = await self.networking.submit_project(ctx.author.id, ctx.guild.id, title, desc, link, category)
        
        if success:
            embed = discord.Embed(title="✅ Project Submitted!")
            # No color set
            embed.description = f"**{title}** has been added to the {category} showcase."
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Failed to submit project.")

    @commands.command(name='browse_projects')
    async def browse_projects(self, ctx, category: str = None):
        """Browse submitted projects"""
        projects = await self.networking.get_projects(ctx.guild.id, category)
        
        if not projects:
            await ctx.send("No projects found.")
            return
            
        embed = discord.Embed(title=f"🎨 Project Showcase {f'- {category.title()}' if category else ''}")
        # No color set
        
        for p in projects:
            pid, uid, title, desc, link, cat, upvotes, img = p
            member = ctx.guild.get_member(uid)
            author_name = member.name if member else "Unknown"
            
            embed.add_field(
                name=f"#{pid} {title} (by {author_name})",
                value=f"⭐ {upvotes}\n{desc[:100]}...\n[Link]({link})",
                inline=False
            )
            
        await ctx.send(embed=embed)

    @commands.command(name='vote_project')
    async def vote_project(self, ctx, project_id: int):
        """Upvote a project"""
        result = await self.networking.vote_project(project_id, ctx.author.id)
        
        if result == "success":
            await ctx.send(f"✅ Voted for project #{project_id}!")
        elif result == "already_voted":
            await ctx.send("⚠️ You already voted for this project.")
        else:
            await ctx.send("❌ Project not found.")

    # --- Coffee Chat Commands ---

    @commands.command(name='coffee_profile')
    async def coffee_profile(self, ctx):
        """Set up your networking profile"""
        # Interactive setup
        await ctx.send("☕ **Networking Profile Setup**\n\n1. What are your interests? (Comma separated)")
        
        def check(m): return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            msg1 = await self.bot.wait_for('message', timeout=60.0, check=check)
            interests = [x.strip() for x in msg1.content.split(',')]
            
            await ctx.send("2. What are your skills? (Comma separated)")
            msg2 = await self.bot.wait_for('message', timeout=60.0, check=check)
            skills = [x.strip() for x in msg2.content.split(',')]
            
            await ctx.send("3. What are you looking for? (e.g. Co-founder, Mentor, Chat)")
            msg3 = await self.bot.wait_for('message', timeout=60.0, check=check)
            looking_for = msg3.content
            
            await self.networking.update_coffee_preferences(ctx.author.id, ctx.guild.id, interests, skills, looking_for)
            
            embed = discord.Embed(title="✅ Profile Updated")
            # No color set
            embed.description = "You've been opted in to weekly matches!"
            await ctx.send(embed=embed)
            
        except asyncio.TimeoutError:
            await ctx.send("❌ Timed out.")

    @commands.command(name='network_search')
    async def network_search(self, ctx, *, query: str):
        """
        Search for people with specific interests or skills.
        Usage: !network_search <interest/skill>
        """
        # Search both skills and interests
        results_interest = await self.networking.search_users(ctx.guild.id, query, "interest")
        results_skill = await self.networking.search_users(ctx.guild.id, query, "skill")
        
        # Merge unique based on user_id
        combined = {r[0]: r for r in results_interest + results_skill}
        
        if not combined:
            await ctx.send(f"No results found for '{query}'.")
            return
            
        embed = discord.Embed(title=f"🔍 Network Search: {query}")
        # No color set
        
        count = 0
        for uid, row in combined.items():
            if count >= 10: break
            member = ctx.guild.get_member(uid)
            if not member: continue
            
            uid, interests_json, skills_json, looking_for = row
            interests = json.loads(interests_json) if interests_json else []
            skills = json.loads(skills_json) if skills_json else []
            
            embed.add_field(
                name=f"👤 {member.name}",
                value=f"**Skills:** {', '.join(skills[:3])}\n**Interests:** {', '.join(interests[:3])}\n**Looking for:** {looking_for}",
                inline=False
            )
            count += 1
            
        await ctx.send(embed=embed)


def setup(bot, db):
    networking = AdvancedNetworking(bot, db)
    bot.add_cog(AdvancedNetworkingCommands(bot, networking))
    return networking
