import discord
import random
import smtplib
import ssl
import os
import aiosqlite
from redbot.core import commands, Config
from redbot.core.bot import Red
from discord.ui import Button, View, Modal, TextInput

DB_PATH = "data/emailverify/emailverify.sqlite"

class EmailVerify(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=98437829)
        default_global = {
            "smtp_server": "",
            "smtp_email": "",
            "smtp_password": "",
        }
        self.config.register_global(**default_global)
        self.bot.loop.create_task(self.initialize_db())

    async def initialize_db(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS verifications (
                    user_id INTEGER PRIMARY KEY,
                    email TEXT,
                    code TEXT,
                    verified INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS blacklist (
                    entry TEXT PRIMARY KEY
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            await db.commit()

    @commands.command()
    async def verifybutton(self, ctx):
        """Send the verify button."""
        button = Button(label="Verify Email", style=discord.ButtonStyle.green)

        async def button_callback(interaction: discord.Interaction):
            try:
                async with aiosqlite.connect(DB_PATH) as db:
                    async with db.execute("SELECT 1 FROM blacklist WHERE entry = ? OR entry = ?", 
                                          (str(interaction.user.id), interaction.user.name)) as cur:
                        if await cur.fetchone():
                            await interaction.response.send_message("❌ You are blacklisted from verification.", ephemeral=True)
                            return

                class EmailModal(Modal, title="Enter your Email"):
                    email = TextInput(label="Email", placeholder="you@example.com", required=True)

                    async def on_submit(modal_self, interaction: discord.Interaction):
                        code = str(random.randint(100000, 999999))
                        email = modal_self.email.value.strip()

                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute(
                                "INSERT OR REPLACE INTO verifications (user_id, email, code, verified) VALUES (?, ?, ?, 0)",
                                (interaction.user.id, email, code)
                            )
                            await db.commit()

                        await self.send_email(interaction, email, code)

                        class CodeModal(Modal, title="Enter Verification Code"):
                            code_input = TextInput(label="Code", placeholder="123456", required=True)

                            async def on_submit(code_modal_self, interaction: discord.Interaction):
                                async with aiosqlite.connect(DB_PATH) as db:
                                    async with db.execute("SELECT code FROM verifications WHERE user_id = ?", 
                                                          (interaction.user.id,)) as cur:
                                        row = await cur.fetchone()

                                    if not row or code_modal_self.code_input.value != row[0]:
                                        await interaction.response.send_message("❌ Invalid code.", ephemeral=True)
                                        return

                                    await db.execute("UPDATE verifications SET verified = 1 WHERE user_id = ?", 
                                                     (interaction.user.id,))
                                    await db.commit()

                                    async with db.execute("SELECT value FROM settings WHERE key = 'verified_role'") as cur:
                                        role_row = await cur.fetchone()
                                        if not role_row:
                                            await interaction.response.send_message("⚠️ No verified role set by admin.", ephemeral=True)
                                            return
                                        role_id = int(role_row[0])
                                        role = interaction.guild.get_role(role_id)
                                        if role:
                                            await interaction.user.add_roles(role)

                                await interaction.response.send_message("✅ You are verified!", ephemeral=True)

                        try:
                            await interaction.followup.send_modal(CodeModal())
                        except Exception as e:
                            await interaction.followup.send(f"❌ Failed to show code input: `{e}`", ephemeral=True)

                await interaction.response.send_modal(EmailModal())

            except Exception as e:
                import traceback
                traceback.print_exc()
                try:
                    await interaction.response.send_message(f"❌ Something went wrong: `{e}`", ephemeral=True)
                except:
                    await interaction.followup.send(f"❌ Something went wrong: `{e}`", ephemeral=True)

        button.callback = button_callback
        view = View()
        view.add_item(button)

        embed = discord.Embed(
            title="Email Verification",
            description="Click the button below to start the verification process!",
            color=discord.Color.teal()
        )

        await ctx.send(embed=embed, view=view)

    @commands.group()
    @commands.has_permissions(administrator=True)
    async def verifyadmin(self, ctx):
        """Admin commands for email verification."""
        pass

    @verifyadmin.command()
    async def setrole(self, ctx, role: discord.Role):
        """Set the global verified role."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('verified_role', ?)", 
                             (str(role.id),))
            await db.commit()
        await ctx.send(f"✅ Verified role set to: {role.name}")

    @verifyadmin.command()
    async def setemailconfig(self, ctx, smtp_server: str, email: str, password: str):
        """Set SMTP credentials for email sending."""
        await self.config.smtp_server.set(smtp_server)
        await self.config.smtp_email.set(email)
        await self.config.smtp_password.set(password)
        await ctx.send("✅ SMTP configuration set.")

    @verifyadmin.command()
    async def view(self, ctx):
        """View all verification entries."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id, email, verified FROM verifications") as cur:
                rows = await cur.fetchall()
                if not rows:
                    await ctx.send("No verification entries.")
                    return
                msg = "\n".join([f"<@{uid}> - {email} - {'✅' if v else '❌'}" for uid, email, v in rows])
                await ctx.send(f"**Verification Entries:**\n{msg}")

    @verifyadmin.command()
    async def remove(self, ctx, user: discord.User):
        """Remove a user's verification entry."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM verifications WHERE user_id = ?", (user.id,))
            await db.commit()
        await ctx.send(f"✅ Removed verification for {user.mention}.")

    @verifyadmin.command()
    async def blacklist(self, ctx, entry: str):
        """Blacklist a user ID or email."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR IGNORE INTO blacklist (entry) VALUES (?)", (entry,))
            await db.commit()
        await ctx.send(f"✅ Blacklisted `{entry}`.")

    @verifyadmin.command()
    async def unblacklist(self, ctx, entry: str):
        """Unblacklist a user ID or email."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM blacklist WHERE entry = ?", (entry,))
            await db.commit()
        await ctx.send(f"✅ Unblacklisted `{entry}`.")

    async def send_email(self, interaction, recipient_email, code):
        smtp_server = await self.config.smtp_server()
        sender_email = await self.config.smtp_email()
        password = await self.config.smtp_password()

        if not smtp_server or not sender_email or not password:
            await interaction.response.send_message("❌ Email configuration is not set. Please contact an admin.", ephemeral=True)
            return

        port = 465
        message = f"Subject: Your Verification Code\n\nYour code is: {code}"

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
                server.login(sender_email, password)
                server.sendmail(sender_email, recipient_email, message)
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.response.send_message(f"❌ Failed to send email: `{e}`", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM verifications WHERE user_id = ?", (member.id,))
            await db.commit()

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM verifications WHERE user_id = ?", (user.id,))
            await db.commit()

async def setup(bot: Red):
    await bot.add_cog(EmailVerify(bot))
