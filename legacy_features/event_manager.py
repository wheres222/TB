"""
Event & AMA Manager
Schedule events, manage RSVPs, send reminders
"""

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio

class EventManager:
    """
    Manages community events and AMAs
    
    Features:
    - Event scheduling
    - RSVP tracking
    - Automatic reminders (1 hour before)
    - Event notifications
    """
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        
        # Active events {event_id: event_data}
        self.active_events = {}
        
        # RSVP tracking {event_id: [user_ids]}
        self.rsvps = {}
        
        # Start reminder task
        self.check_reminders.start()
    
    async def create_event(
        self,
        guild_id: int,
        creator_id: int,
        title: str,
        description: str,
        event_time: datetime,
        event_type: str = "general"
    ) -> int:
        """
        Create a new event
        
        Returns:
            Event ID
        """
        try:
            cursor = await self.db.execute(
                """
                INSERT INTO events (
                    guild_id, creator_id, title, description,
                    event_time, event_type, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'scheduled')
                """,
                (
                    guild_id,
                    creator_id,
                    title,
                    description,
                    event_time.isoformat(),
                    event_type,
                    datetime.utcnow().isoformat()
                )
            )
            await self.db.commit()
            
            event_id = cursor.lastrowid
            
            # Store in active events
            self.active_events[event_id] = {
                'guild_id': guild_id,
                'title': title,
                'description': description,
                'event_time': event_time,
                'event_type': event_type
            }
            
            self.rsvps[event_id] = []
            
            print(f"✓ Created event #{event_id}: {title}")
            return event_id
            
        except Exception as e:
            print(f"✗ Error creating event: {e}")
            return 0
    
    async def rsvp_event(self, event_id: int, user_id: int) -> bool:
        """RSVP to an event"""
        try:
            # Check if already RSVP'd
            cursor = await self.db.execute(
                "SELECT 1 FROM event_rsvps WHERE event_id = ? AND user_id = ?",
                (event_id, user_id)
            )
            if await cursor.fetchone():
                return False  # Already RSVP'd
            
            # Add RSVP
            await self.db.execute(
                """
                INSERT INTO event_rsvps (event_id, user_id, rsvp_time)
                VALUES (?, ?, ?)
                """,
                (event_id, user_id, datetime.utcnow().isoformat())
            )
            await self.db.commit()
            
            # Update cache
            if event_id not in self.rsvps:
                self.rsvps[event_id] = []
            self.rsvps[event_id].append(user_id)
            
            return True
            
        except Exception as e:
            print(f"✗ Error RSVPing to event: {e}")
            return False
    
    async def get_event_rsvps(self, event_id: int) -> List[int]:
        """Get all RSVPs for an event"""
        try:
            cursor = await self.db.execute(
                "SELECT user_id FROM event_rsvps WHERE event_id = ?",
                (event_id,)
            )
            results = await cursor.fetchall()
            return [row[0] for row in results]
        except:
            return []
    
    async def send_reminder(self, event_id: int):
        """Send reminder 1 hour before event"""
        if event_id not in self.active_events:
            return
        
        event = self.active_events[event_id]
        guild = self.bot.get_guild(event['guild_id'])
        
        if not guild:
            return
        
        # Get RSVPs
        rsvp_users = await self.get_event_rsvps(event_id)
        
        if not rsvp_users:
            return
        
        # Create reminder embed
        embed = discord.Embed(
            title="⏰ Event Reminder",
            description=f"**{event['title']}** starts in 1 hour!",
            color=discord.Color.orange(),
            timestamp=event['event_time']
        )
        
        embed.add_field(
            name="Description",
            value=event['description'][:1024],
            inline=False
        )
        
        embed.add_field(
            name="Type",
            value=event['event_type'].title(),
            inline=True
        )
        
        embed.add_field(
            name="RSVPs",
            value=f"{len(rsvp_users)} attending",
            inline=True
        )
        
        # Send to event channel or general
        event_channel = discord.utils.get(guild.text_channels, name='events') or \
                       discord.utils.get(guild.text_channels, name='general')
        
        if event_channel:
            # Mention all RSVP'd users
            mentions = ' '.join(f"<@{user_id}>" for user_id in rsvp_users[:50])  # Limit to 50
            
            try:
                await event_channel.send(content=mentions, embed=embed)
                print(f"✓ Sent reminder for event #{event_id}")
            except Exception as e:
                print(f"✗ Error sending reminder: {e}")
    
    @tasks.loop(minutes=5)
    async def check_reminders(self):
        """Check for events needing reminders"""
        try:
            now = datetime.utcnow()
            reminder_time = now + timedelta(hours=1)
            
            # Get events starting in ~1 hour
            cursor = await self.db.execute(
                """
                SELECT id, guild_id, title, description, event_time, event_type
                FROM events
                WHERE status = 'scheduled'
                AND datetime(event_time) BETWEEN datetime(?) AND datetime(?)
                AND reminder_sent = 0
                """,
                (now.isoformat(), reminder_time.isoformat())
            )
            events = await cursor.fetchall()
            
            for event_id, guild_id, title, description, event_time_str, event_type in events:
                event_time = datetime.fromisoformat(event_time_str)
                
                # Store in active events
                self.active_events[event_id] = {
                    'guild_id': guild_id,
                    'title': title,
                    'description': description,
                    'event_time': event_time,
                    'event_type': event_type
                }
                
                # Send reminder
                await self.send_reminder(event_id)
                
                # Mark reminder as sent
                await self.db.execute(
                    "UPDATE events SET reminder_sent = 1 WHERE id = ?",
                    (event_id,)
                )
            
            await self.db.commit()
            
        except Exception as e:
            print(f"✗ Error checking reminders: {e}")
    
    @check_reminders.before_loop
    async def before_reminders(self):
        """Wait for bot to be ready"""
        await self.bot.wait_until_ready()


class EventCommands(commands.Cog):
    """Commands for event management"""
    
    def __init__(self, bot, event_manager):
        self.bot = bot
        self.event_manager = event_manager
    
    @commands.command(name='create_event')
    @commands.has_permissions(manage_events=True)
    async def create_event(self, ctx, event_time: str, *, title_and_desc: str):
        """
        Create a new event
        
        Usage: !create_event "2024-12-25 18:00" Title | Description
        Time format: YYYY-MM-DD HH:MM (24-hour, UTC)
        """
        try:
            # Parse time
            event_datetime = datetime.strptime(event_time, "%Y-%m-%d %H:%M")
            
            # Parse title and description
            if '|' in title_and_desc:
                title, description = title_and_desc.split('|', 1)
                title = title.strip()
                description = description.strip()
            else:
                title = title_and_desc.strip()
                description = "No description provided"
            
            # Detect event type
            event_type = "general"
            if "ama" in title.lower():
                event_type = "ama"
            elif "mastermind" in title.lower():
                event_type = "mastermind"
            elif "workshop" in title.lower():
                event_type = "workshop"
            
            # Create event
            event_id = await self.event_manager.create_event(
                ctx.guild.id,
                ctx.author.id,
                title,
                description,
                event_datetime,
                event_type
            )
            
            if event_id:
                embed = discord.Embed(
                    title="✅ Event Created",
                    description=f"**{title}**",
                    color=discord.Color.green()
                )
                
                embed.add_field(name="Event ID", value=f"#{event_id}", inline=True)
                embed.add_field(name="Type", value=event_type.title(), inline=True)
                embed.add_field(name="Time", value=event_datetime.strftime("%Y-%m-%d %H:%M UTC"), inline=False)
                embed.add_field(name="Description", value=description[:1024], inline=False)
                embed.add_field(name="RSVP", value=f"Use `!rsvp {event_id}` to attend", inline=False)
                
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Failed to create event.")
                
        except ValueError:
            await ctx.send("❌ Invalid time format. Use: YYYY-MM-DD HH:MM (e.g., 2024-12-25 18:00)")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
    
    @commands.command(name='rsvp')
    async def rsvp(self, ctx, event_id: int):
        """
        RSVP to an event
        
        Usage: !rsvp <event_id>
        """
        success = await self.event_manager.rsvp_event(event_id, ctx.author.id)
        
        if success:
            await ctx.send(f"✅ {ctx.author.mention} You're registered for event #{event_id}! You'll get a reminder 1 hour before.")
        else:
            await ctx.send(f"⚠️ You're already registered for this event, or the event doesn't exist.")
    
    @commands.command(name='event_info')
    async def event_info(self, ctx, event_id: int):
        """
        View event details
        
        Usage: !event_info <event_id>
        """
        try:
            cursor = await self.event_manager.db.execute(
                """
                SELECT title, description, event_time, event_type, status
                FROM events WHERE id = ?
                """,
                (event_id,)
            )
            result = await cursor.fetchone()
            
            if not result:
                await ctx.send(f"❌ Event #{event_id} not found.")
                return
            
            title, description, event_time_str, event_type, status = result
            event_time = datetime.fromisoformat(event_time_str)
            
            # Get RSVPs
            rsvps = await self.event_manager.get_event_rsvps(event_id)
            
            embed = discord.Embed(
                title=f"📅 Event #{event_id}: {title}",
                description=description,
                color=discord.Color.blue(),
                timestamp=event_time
            )
            
            embed.add_field(name="Type", value=event_type.title(), inline=True)
            embed.add_field(name="Status", value=status.title(), inline=True)
            embed.add_field(name="RSVPs", value=f"{len(rsvps)} attending", inline=True)
            embed.add_field(name="Time", value=event_time.strftime("%Y-%m-%d %H:%M UTC"), inline=False)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
    
    @commands.command(name='upcoming_events')
    async def upcoming_events(self, ctx):
        """View all upcoming events"""
        try:
            cursor = await self.event_manager.db.execute(
                """
                SELECT id, title, event_time, event_type
                FROM events
                WHERE status = 'scheduled'
                AND datetime(event_time) > datetime('now')
                ORDER BY event_time ASC
                LIMIT 10
                """
            )
            events = await cursor.fetchall()
            
            if not events:
                await ctx.send("No upcoming events scheduled.")
                return
            
            embed = discord.Embed(
                title="📅 Upcoming Events",
                color=discord.Color.blue()
            )
            
            for event_id, title, event_time_str, event_type in events:
                event_time = datetime.fromisoformat(event_time_str)
                rsvps = await self.event_manager.get_event_rsvps(event_id)
                
                embed.add_field(
                    name=f"#{event_id} - {title}",
                    value=f"**Type:** {event_type.title()}\n**Time:** {event_time.strftime('%Y-%m-%d %H:%M UTC')}\n**RSVPs:** {len(rsvps)}\nUse `!rsvp {event_id}` to attend",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")


def setup(bot, db):
    """Setup function to initialize event manager"""
    event_manager = EventManager(bot, db)
    bot.add_cog(EventCommands(bot, event_manager))
    return event_manager
