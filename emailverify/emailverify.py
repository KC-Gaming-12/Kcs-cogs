import discord
from discord.ext import commands
from redbot.core import Config, commands
import random
import string
import aiosqlite
import asyncio
import smtplib
from email.message import EmailMessage

class EmailVerify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        default_global = {"blacklist": [], "verified_role_id": None}
        default_user = {"email": None, "verified": False}
        self.config.register_global(**default_global)
        self.config.register_user(**default_user)
        self.db_path = "emailverify.sqlite3"
        self.bot.loop.create_task(self.initialize_db())

    async def initialize_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS verifications (
                    user_id INTEGER PRIMARY KEY,
                    email TEXT NOT NULL,
                    code TEXT NOT NULL,
                    verified INTEGER DEFAULT 0
                )
            """)
            await db.commit()

    @commands.command()
    @commands.admin()
    async def setverifiedrole(self, ctx, role: discord.Role):
        await self.config.verified_role_id.set(role.id)
        await ctx.send(f"✅ Verified role set to: {role.name}")

    @commands.command()
    @commands.admin()
    async def blacklistemail(self, ctx, email: str):
        bl = await self.config.blacklist()
        if email not in bl:
            bl.append(email)
            await self.config.blacklist.set(bl)
            await ctx.send(f"🚫 Blacklisted `{email}`")

    @commands.command()
    @commands.admin()
    async def viewpending(self, ctx):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id, email FROM verifications WHERE verified = 0") as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await ctx.send("✅ No pending verifications.")
            return
        msg = "\n".join([f"<@{uid}>: {email}" for uid, email in rows])
        await ctx.send(f"**Pending Verifications:**\n{msg}")

    @commands.command()
    async def verifysetup(self, ctx):
        embed = discord.Embed(
            title="Email Verification",
            description="Click the button below to start the verification process!",
            color=discord.Color.cyan()
        )
        await ctx.send(embed=embed, view=VerifyView(self))

    async def send_verification_email(self, email, code):
        msg = EmailMessage()
        msg.set_content(f"Your verification code is: {code}")
        msg["Subject"] = "Your Verification Code"
        msg["From"] = "yourbot@yourdomain.com"
        msg["To"] = email

        smtp_server = "smtp.zoho.com"
        smtp_port = 587
        smtp_username = "yourbot@yourdomain.com"
        smtp_password = "yourpassword"

        try:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
            server.quit()
            return True
        except Exception as e:
            print(f"Email sending failed: {e}")
            return False

    async def unverify_user(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM verifications WHERE user_id = ?", (user_id,))
            await db.commit()
        await self.config.user_from_id(user_id).verified.set(False)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self.unverify_user(member.id)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        await self.unverify_user(user.id)

    @commands.Cog.listener()
    async def on_member_kick(self, member):
        await self.unverify_user(member.id)

class VerifyView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.blurple, custom_id="start_verify")
    async def start_verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmailModal(self.cog))

class EmailModal(discord.ui.Modal, title="Enter your Email"):
    email = discord.ui.TextInput(label="Email", style=discord.TextStyle.short, required=True)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        email = self.email.value

        blacklist = await self.cog.config.blacklist()
        if email in blacklist:
            await interaction.followup.send("🚫 This email is blacklisted.", ephemeral=True)
            return

        code = ''.join(random.choices(string.digits, k=6))
        success = await self.cog.send_verification_email(email, code)

        if success:
            async with aiosqlite.connect(self.cog.db_path) as db:
                await db.execute("REPLACE INTO verifications (user_id, email, code, verified) VALUES (?, ?, ?, 0)",
                                 (interaction.user.id, email, code))
                await db.commit()
            await interaction.followup.send_modal(CodeEntryModal(self.cog, interaction.user.id))
        else:
            await interaction.followup.send("❌ Something went wrong sending the email. Please try again later.", ephemeral=True)

class CodeEntryModal(discord.ui.Modal, title="Enter Verification Code"):
    code = discord.ui.TextInput(label="Code", style=discord.TextStyle.short, required=True)

    def __init__(self, cog, user_id):
        super().__init__()
        self.cog = cog
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        input_code = self.code.value.strip()
        async with aiosqlite.connect(self.cog.db_path) as db:
            async with db.execute("SELECT code FROM verifications WHERE user_id = ?", (self.user_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0] == input_code:
                    await db.execute("UPDATE verifications SET verified = 1 WHERE user_id = ?", (self.user_id,))
                    await db.commit()
                    await self.cog.config.user(interaction.user).verified.set(True)
                    role_id = await self.cog.config.verified_role_id()
                    if role_id:
                        role = interaction.guild.get_role(role_id)
                        if role:
                            await interaction.user.add_roles(role, reason="Verified")
                    await interaction.response.send_message("✅ You have been verified!", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Invalid code. Please try again.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(EmailVerify(bot))
