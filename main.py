import os
import json
import random
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# --- BRANDING & CONFIGURATION ---
GUILD_ID = 1542254855891066890             # TUI Server ID
MODMAIL_CATEGORY_ID = 1542974680447844522  # Ticket Category ID
STAFF_ROLE_ID = 1548717708886020237        # TUI Staff Role ID

# Brand Settings
BRAND_NAME = "TUI"
EMBED_COLOR = discord.Color.from_str("#4A90E2")  # Light Blue Color

# Anonymous Staff Names for .areply
ANONYMOUS_AGENT_NAMES = [
    "Agent Alpha", "Agent Bravo", "Agent Charlie", 
    "Agent Delta", "Agent Echo"
]

# --- INTENTS SETUP ---
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
intents.guild_messages = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents)

# --- HELPER FUNCTIONS FOR DYNAMIC EMOJIS ---
def get_guild_emoji(name: str):
    """Finds a custom emoji by name in the target server."""
    guild = bot.get_guild(GUILD_ID)
    if guild:
        return discord.utils.get(guild.emojis, name=name)
    return None

# --- JSON DATA STORAGE HELPERS ---
def load_json(filename: str) -> dict:
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_json(filename: str, data: dict):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# Global Data Structures
SNIPPETS = load_json("snippets.json")
BANNED_USERS = load_json("banned_users.json")
SUBSCRIBERS = load_json("subscribers.json")


@bot.event
async def on_ready():
    print(f"✅ {BRAND_NAME} Chatbot active as {bot.user}")


# --- UI COMPONENTS FOR TICKET CREATION ---

class DepartmentSelect(discord.ui.Select):
    def __init__(self, initial_message: discord.Message):
        self.initial_message = initial_message
        options = [
            discord.SelectOption(label="Human Resources", value="Human Resources"),
            discord.SelectOption(label="Operations Department", value="Operations Department"),
            discord.SelectOption(label="Publicity Enquiry", value="Publicity Enquiry"),
            discord.SelectOption(label="General Inquiry", value="General Inquiry")
        ]
        super().__init__(placeholder="Select a department...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_dept = self.values[0]
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            await interaction.followup.send("⚠️ Error: Target server could not be found.", ephemeral=True)
            return

        category = guild.get_channel(MODMAIL_CATEGORY_ID)
        if not category:
            await interaction.followup.send("⚠️ Error: Ticket category channel could not be found.", ephemeral=True)
            return

        staff_role = guild.get_role(STAFF_ROLE_ID)

        channel_name = f"ticket-{interaction.user.id}"
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        ticket_channel = await category.create_text_channel(name=channel_name, overwrites=overwrites)

        staff_ping = f"<@&{STAFF_ROLE_ID}>" if STAFF_ROLE_ID else ""

        staff_embed = discord.Embed(
            title=f"New {BRAND_NAME} Ticket Created",
            description=(
                f"**User:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                f"**Department:** {selected_dept}\n"
                f"**Initial Message:**\n{self.initial_message.content}"
            ),
            color=EMBED_COLOR,
            timestamp=discord.utils.utcnow()
        )
        staff_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await ticket_channel.send(content=staff_ping, embed=staff_embed)

        if self.initial_message.attachments:
            for attachment in self.initial_message.attachments:
                await ticket_channel.send(attachment.url)

        # DM Confirmation sent to the user upon department selection
        user_opened_embed = discord.Embed(
            description="Your support ticket has been opened, please wait as an agent will be claiming your ticket shortly.",
            color=EMBED_COLOR
        )
        try:
            await interaction.user.send(embed=user_opened_embed)
        except discord.HTTPException:
            pass

        self.view.stop()


class DepartmentView(discord.ui.View):
    def __init__(self, initial_message: discord.Message):
        super().__init__(timeout=180)
        self.add_item(DepartmentSelect(initial_message))


class ConfirmationView(discord.ui.View):
    def __init__(self, initial_message: discord.Message):
        super().__init__(timeout=180)
        self.initial_message = initial_message

        # Fetch emojis dynamically from the guild
        check_emoji = get_guild_emoji("Check") or "✅"
        cross_emoji = get_guild_emoji("TUI_Cross") or "❌"

        # Create buttons with dynamically fetched emojis
        confirm_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji=check_emoji)
        confirm_btn.callback = self.confirm_button
        self.add_item(confirm_btn)

        cancel_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji=cross_emoji)
        cancel_btn.callback = self.cancel_button
        self.add_item(cancel_btn)

    async def confirm_button(self, interaction: discord.Interaction):
        dept_embed = discord.Embed(
            description=(
                "**Department Selection**\n\n"
                "Before we create a ticket, please select a department "
                "you are opening a ticket for from the dropdown menu below."
            ),
            color=EMBED_COLOR
        )
        await interaction.response.send_message(embed=dept_embed, view=DepartmentView(self.initial_message))
        self.stop()

    async def cancel_button(self, interaction: discord.Interaction):
        await interaction.response.send_message("❌ Ticket creation cancelled.", ephemeral=False)
        self.stop()


# --- MESSAGE & EVENT HANDLING ---

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.DMChannel):
        if str(message.author.id) in BANNED_USERS:
            await message.channel.send("You are currently blocked from creating support tickets.")
            return

        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print(f"❌ Error: Guild with ID {GUILD_ID} not found. Ensure the bot is joined to the server.")
            return

        category = guild.get_channel(MODMAIL_CATEGORY_ID)
        if not category:
            print(f"❌ Error: Category with ID {MODMAIL_CATEGORY_ID} not found in guild {guild.name}.")
            return

        channel_name = f"ticket-{message.author.id}"
        existing_channel = discord.utils.get(category.text_channels, name=channel_name)

        if existing_channel:
            dm_embed = discord.Embed(
                description=message.content,
                color=EMBED_COLOR,
                timestamp=discord.utils.utcnow()
            )
            dm_embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
            dm_embed.set_footer(text="User DM")

            if message.attachments:
                dm_embed.set_image(url=message.attachments[0].url)

            str_chan_id = str(existing_channel.id)
            pings = ""
            if str_chan_id in SUBSCRIBERS and SUBSCRIBERS[str_chan_id]:
                pings = " ".join([f"<@{uid}>" for uid in SUBSCRIBERS[str_chan_id]])

            await existing_channel.send(content=pings if pings else None, embed=dm_embed)
            
            # React with TUI_Logo or default check
            reaction_emoji = get_guild_emoji("TUI_Logo") or "👍"
            try:
                await message.add_reaction(reaction_emoji)
            except discord.HTTPException:
                pass
            return

        confirm_embed = discord.Embed(
            description=(
                f"**Almost There!**\n"
                f"-# Welcome to {BRAND_NAME} Support\n\n"
                f"Before proceeding, please confirm that you would like "
                f"to create a new support ticket with the {BRAND_NAME} team by reacting below."
            ),
            color=EMBED_COLOR
        )
        await message.channel.send(embed=confirm_embed, view=ConfirmationView(message))
        return

    await bot.process_commands(message)

    # DYNAMIC SNIPPET TRIGGER (.snippet_name) INSIDE TICKETS
    if message.content.startswith(".") and message.channel.name.startswith("ticket-"):
        ctx = await bot.get_context(message)
        if ctx.valid:
            return

        if not isinstance(message.author, discord.Member) or not any(role.id == STAFF_ROLE_ID for role in message.author.roles):
            return

        trigger = message.content[1:].split()[0].lower()
        if trigger in SNIPPETS:
            user_id = int(message.channel.name.split("-")[1])
            target_user = await bot.fetch_user(user_id)
            snippet_text = SNIPPETS[trigger]

            roles = [r.name for r in message.author.roles if r.name != "@everyone"]
            agent_rank = roles[-1] if roles else "Support Agent"

            embed = discord.Embed(
                description=snippet_text,
                color=EMBED_COLOR,
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
            embed.set_footer(text=agent_rank)

            if target_user:
                try:
                    await target_user.send(embed=embed)
                except discord.HTTPException:
                    await message.channel.send("⚠️ Could not DM user (DMs may be closed).")
                    return

            await message.channel.send(embed=embed)
            try:
                await message.delete()
            except discord.Forbidden:
                pass


# --- STAFF CHECK PERMISSION (STRICT ROLE CHECK) ---

def is_staff():
    async def predicate(ctx):
        if not isinstance(ctx.author, discord.Member):
            return False
        return any(role.id == STAFF_ROLE_ID for role in ctx.author.roles)
    return commands.check(predicate)


# --- STAFF TICKET COMMANDS ---

@bot.command(name="reply")
@is_staff()
async def reply(ctx, *, response: str):
    if not ctx.channel.name.startswith("ticket-"):
        return await ctx.send("This command can only be used inside a ticket channel.")

    user_id = int(ctx.channel.name.split("-")[1])
    target_user = await bot.fetch_user(user_id)

    roles = [r.name for r in ctx.author.roles if r.name != "@everyone"]
    agent_rank = roles[-1] if roles else "Support Agent"

    embed = discord.Embed(
        description=response,
        color=EMBED_COLOR,
        timestamp=discord.utils.utcnow()
    )
    embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
    embed.set_footer(text=agent_rank)

    if target_user:
        try:
            await target_user.send(embed=embed)
        except discord.HTTPException:
            return await ctx.send("⚠️ Could not DM user.")

    await ctx.send(embed=embed)
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass


@bot.command(name="areply")
@is_staff()
async def areply(ctx, *, response: str):
    if not ctx.channel.name.startswith("ticket-"):
        return await ctx.send("This command can only be used inside a ticket channel.")

    user_id = int(ctx.channel.name.split("-")[1])
    target_user = await bot.fetch_user(user_id)

    agent_name = random.choice(ANONYMOUS_AGENT_NAMES)

    embed = discord.Embed(
        description=response,
        color=EMBED_COLOR,
        timestamp=discord.utils.utcnow()
    )
    embed.set_author(name=f"Customer Support ({agent_name})")
    embed.set_footer(text=f"{BRAND_NAME} Helpdesk")

    if target_user:
        try:
            await target_user.send(embed=embed)
        except discord.HTTPException:
            return await ctx.send("⚠️ Could not DM user.")

    await ctx.send(embed=embed)
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass


@bot.command(name="sub")
@is_staff()
async def sub(ctx):
    if not ctx.channel.name.startswith("ticket-"):
        return await ctx.send("This command can only be used inside a ticket channel.")

    chan_id = str(ctx.channel.id)
    if chan_id not in SUBSCRIBERS:
        SUBSCRIBERS[chan_id] = []

    if ctx.author.id not in SUBSCRIBERS[chan_id]:
        SUBSCRIBERS[chan_id].append(ctx.author.id)
        save_json("subscribers.json", SUBSCRIBERS)
        await ctx.send(f"✅ {ctx.author.mention} subscribed to this ticket.")
    else:
        await ctx.send("You are already subscribed to this ticket.")


@bot.command(name="unsub")
@is_staff()
async def unsub(ctx):
    if not ctx.channel.name.startswith("ticket-"):
        return await ctx.send("This command can only be used inside a ticket channel.")

    chan_id = str(ctx.channel.id)
    if chan_id in SUBSCRIBERS and ctx.author.id in SUBSCRIBERS[chan_id]:
        SUBSCRIBERS[chan_id].remove(ctx.author.id)
        save_json("subscribers.json", SUBSCRIBERS)
        await ctx.send(f"❌ {ctx.author.mention} unsubscribed from this ticket.")
    else:
        await ctx.send("You are not subscribed to this ticket.")


@bot.command(name="ban")
@is_staff()
async def ban_user(ctx, user: discord.User):
    BANNED_USERS[str(user.id)] = True
    save_json("banned_users.json", BANNED_USERS)
    
    embed = discord.Embed(
        description=f"🚫 User {user.mention} (`{user.id}`) has been banned from opening tickets.",
        color=EMBED_COLOR
    )
    await ctx.send(embed=embed)


@bot.command(name="unban")
@is_staff()
async def unban_user(ctx, user: discord.User):
    if str(user.id) in BANNED_USERS:
        del BANNED_USERS[str(user.id)]
        save_json("banned_users.json", BANNED_USERS)
        
    embed = discord.Embed(
        description=f"✅ User {user.mention} (`{user.id}`) has been unbanned from opening tickets.",
        color=EMBED_COLOR
    )
    await ctx.send(embed=embed)


# --- SNIPPET MANAGEMENT COMMANDS ---

@bot.command(name="addsnippet")
@is_staff()
async def addsnippet(ctx, name: str, *, msg: str):
    snippet_name = name.lower()
    if bot.get_command(snippet_name):
        return await ctx.send(f"Cannot use `{snippet_name}` because it is a reserved command.")

    SNIPPETS[snippet_name] = msg
    save_json("snippets.json", SNIPPETS)

    embed = discord.Embed(description=f"Snippet `.{snippet_name}` created.", color=EMBED_COLOR)
    await ctx.send(embed=embed)


@bot.command(name="editsnippet")
@is_staff()
async def editsnippet(ctx, name: str, *, msg: str):
    snippet_name = name.lower()
    if snippet_name not in SNIPPETS:
        return await ctx.send(f"Snippet `.{snippet_name}` does not exist.")

    SNIPPETS[snippet_name] = msg
    save_json("snippets.json", SNIPPETS)

    embed = discord.Embed(description=f"Snippet `.{snippet_name}` updated.", color=EMBED_COLOR)
    await ctx.send(embed=embed)


@bot.command(name="deletesnippet")
@is_staff()
async def deletesnippet(ctx, name: str):
    snippet_name = name.lower()
    if snippet_name not in SNIPPETS:
        return await ctx.send(f"Snippet `.{snippet_name}` does not exist.")

    del SNIPPETS[snippet_name]
    save_json("snippets.json", SNIPPETS)

    embed = discord.Embed(description=f"Snippet `.{snippet_name}` deleted.", color=EMBED_COLOR)
    await ctx.send(embed=embed)


@bot.command(name="snippets")
@is_staff()
async def list_snippets(ctx):
    if not SNIPPETS:
        embed = discord.Embed(title="Saved Snippets", description="No snippets exist.", color=EMBED_COLOR)
        return await ctx.send(embed=embed)

    snippet_list = "\n".join([f"• `.{name}`" for name in SNIPPETS.keys()])
    embed = discord.Embed(title="Saved Snippets", description=snippet_list, color=EMBED_COLOR)
    await ctx.send(embed=embed)


@bot.command(name="close")
@is_staff()
async def close_ticket(ctx):
    if ctx.channel.name.startswith("ticket-"):
        user_id = int(ctx.channel.name.split("-")[1])
        user = await bot.fetch_user(user_id)
        if user:
            try:
                close_embed = discord.Embed(
                    description=f"Your ticket has been marked as closed. Thank you for contacting {BRAND_NAME} Support.",
                    color=EMBED_COLOR
                )
                await user.send(embed=close_embed)
            except discord.HTTPException:
                pass

        chan_id = str(ctx.channel.id)
        if chan_id in SUBSCRIBERS:
            del SUBSCRIBERS[chan_id]
            save_json("subscribers.json", SUBSCRIBERS)

        await ctx.channel.delete()

bot.run(os.getenv("DISCORD_TOKEN"))
