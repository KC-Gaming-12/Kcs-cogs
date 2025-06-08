from .emailverify import EmailVerify

async def setup(bot):
    await bot.add_cog(EmailVerify(bot))


