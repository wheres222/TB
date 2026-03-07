"""
Cross-Server Intelligence & Global Threat Tracking
Feature 10 from beg.txt: Sharing banned IDs and patterns between servers.
"""

import discord
from discord.ext import commands
from datetime import datetime

class ThreatIntelligence:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    async def check_global_threat(self, target_id, target_type='user'):
        """Check if a user or domain is in the global threat database"""
        cursor = await self.db.execute(
            "SELECT reason, source, severity FROM global_threat_intel WHERE target_id = ? AND target_type = ?",
            (target_id, target_type)
        )
        return await cursor.fetchone()

    async def add_global_threat(self, target_id, target_type, reason, source, severity=1):
        """Add a new threat to the global database"""
        await self.db.execute(
            """
            INSERT OR REPLACE INTO global_threat_intel (target_id, target_type, reason, source, severity, added_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (target_id, target_type, reason, source, severity, datetime.utcnow().isoformat())
        )
        await self.db.commit()

class ThreatIntelCommands(commands.Cog):
    def __init__(self, bot, intel):
        self.bot = bot
        self.intel = intel

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Check joining members against global threat intel"""
        threat = await self.intel.check_global_threat(member.id, 'user')
        if threat:
            reason, source, severity = threat
            log_channel = discord.utils.get(member.guild.text_channels, name='mod-logs')
            
            embed = discord.Embed(title="🚨 Global Threat Detected")
            embed.description = f"**{member.name}** ({member.id}) just joined."
            embed.add_field(name="Reason", value=reason)
            embed.add_field(name="Source", value=source)
            embed.add_field(name="Severity", value="🔴 High" if severity >= 3 else "🟡 Medium")
            
            if log_channel:
                await log_channel.send(embed=embed)
            
            # If severity is high, auto-quarantine (move to verify or mute)
            if severity >= 2:
                # Assuming 'Unverified' role exists from captcha system
                unverified_role = discord.utils.get(member.guild.roles, name="Unverified")
                if unverified_role:
                    await member.add_roles(unverified_role, reason="Global threat match")

    @commands.command(name='flag_global')
    @commands.has_permissions(administrator=True)
    async def flag_global(self, ctx, target: str, type: str, *, reason: str):
        """Flag a user or domain in the global threat database"""
        await self.intel.add_global_threat(target, type.lower(), reason, f"Server: {ctx.guild.name}", 3)
        await ctx.send(f"✅ Successfully flagged **{target}** as a global threat.")

    @commands.command(name='import_blocklist')
    @commands.has_permissions(administrator=True)
    async def import_blocklist(self, ctx, url: str):
        """Simulate importing a blocklist from a shared source (Feature 10)"""
        await ctx.send("📥 Fetching shared threat intelligence from network...")
        # In a real scenario, this would fetch from a URL or API
        # Here we add some dummy data to simulate the functionality
        await self.intel.add_global_threat("123456789", "user", "Known Crypto Spammer", "Community Network", 3)
        await self.intel.add_global_threat("scam-site.com", "domain", "Phishing Site", "Shared Intel", 3)
        await ctx.send("✅ Threat database synchronized. 2 items added.")

def setup(bot, db):
    intel = ThreatIntelligence(bot, db)
    bot.add_cog(ThreatIntelCommands(bot, intel))
    return intel
