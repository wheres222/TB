"""
DM Spam Protection
Feature 5 from beg.txt: Protect members from sliding into DMs.
"""

import discord
from discord.ext import commands
from datetime import datetime

class DMProtection:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    async def report_dm_spam(self, reporter_id, reported_id, guild_id, evidence):
        """Log a DM spam report for investigation"""
        await self.db.execute(
            """
            INSERT INTO dm_reports (reporter_id, reported_id, guild_id, evidence, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (reporter_id, reported_id, guild_id, evidence, datetime.utcnow().isoformat())
        )
        await self.db.commit()

class DMProtectionCommands(commands.Cog):
    def __init__(self, bot, protection):
        self.bot = bot
        self.protection = protection

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Remind new members about DM safety"""
        try:
            embed = discord.Embed(title="🛡️ Security Reminder")
            embed.description = (
                f"Welcome to **{member.guild.name}**!\n\n"
                "**DM Safety Warning:** We never send links via DM. If anyone messages you "
                "privately about this community, it is likely a scam.\n\n"
                "To report DM spam, use `!report_dm @user [reason]` in an appropriate channel."
            )
            await member.send(embed=embed)
        except:
            pass # Ignore if DMs are closed

    @commands.command(name='report_dm')
    async def report_dm(self, ctx, member: discord.Member, *, reason: str):
        """Report a user for sending spam DMs"""
        await self.protection.report_dm_spam(ctx.author.id, member.id, ctx.guild.id, reason)
        
        # Send receipt to user
        await ctx.author.send(f"✅ Your report against **{member.name}** has been received by moderators.")
        
        # Notify moderators
        mod_channel = discord.utils.get(ctx.guild.text_channels, name='mod-logs')
        if mod_channel:
            embed = discord.Embed(title="📬 DM Spam Report Received")
            embed.add_field(name="Reporter", value=ctx.author.mention)
            embed.add_field(name="Reported", value=member.mention)
            embed.add_field(name="Reason", value=reason)
            embed.add_field(name="Action", value="Check reporter's DMs and member join dates.")
            await mod_channel.send(embed=embed)
        
        await ctx.message.delete()
        await ctx.send("✅ Report submitted quietly to moderators.", delete_after=5)

    @commands.command(name='review_dm_reports')
    @commands.has_permissions(moderate_members=True)
    async def review_dm_reports(self, ctx):
        """View pending DM spam reports"""
        cursor = await self.protection.db.execute(
            "SELECT reporter_id, reported_id, evidence, timestamp FROM dm_reports WHERE status = 'pending' LIMIT 5"
        )
        reports = await cursor.fetchall()
        
        if not reports:
            return await ctx.send("No pending DM reports.")
            
        embed = discord.Embed(title="📋 Pending DM Reports")
        for rep in reports:
            rter_id, rted_id, evid, ts = rep
            embed.add_field(
                name=f"From: {rter_id} | Against: {rted_id}",
                value=f"**Reason:** {evid}\n**Date:** {ts[:10]}",
                inline=False
            )
        await ctx.send(embed=embed)

def setup(bot, db):
    protection = DMProtection(bot, db)
    bot.add_cog(DMProtectionCommands(bot, protection))
    return protection
