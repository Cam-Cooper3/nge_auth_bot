import discord
import os
import sqlite3
import asyncio
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# Load the environment variables from .env
load_dotenv()

# Get the variables from .env
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_SERVER_ID"))

# Bot setup with required intents
intents = discord.Intents.default()
intents.guilds = True  # Required to fetch guild information
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# SQLite database setup
db_connection = sqlite3.connect(".myids.db")
db_cursor = db_connection.cursor()

# Create the user_data table if it doesn't already exist
db_cursor.execute("""
CREATE TABLE IF NOT EXISTS user_data (
    user_id INTEGER PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    my_id TEXT
)
""")
db_connection.commit()

# Helper function to check if command is in #moderator-general
async def is_moderator_channel(ctx):
    return ctx.channel.name == "moderator-general"

@bot.event
async def on_ready():
    await bot.wait_until_ready()
    try:
        print("Connected to the following guilds:")
        for guild in bot.guilds:
            print(f"- {guild.name} (ID: {guild.id})")

        guild_id = GUILD_ID
        print(f"Attempting to sync commands to guild with ID: {guild_id}")

        guild = bot.get_guild(guild_id)
        if guild is None:
            print(f"Guild with ID {guild_id} not found in bot.guilds.")
            print(f"List of connected guild IDs: {[g.id for g in bot.guilds]}")
            return

        print(f"Found guild: {guild.name} (ID: {guild.id})")
        await bot.tree.sync(guild=discord.Object(id=guild_id))
        print(f"Slash commands successfully synced for guild: {guild.id} ({guild.name})")

    except Exception as e:
        print(f"Failed to sync commands: {e}")

    print(f"Logged in as {bot.user}")

@bot.event
async def on_member_update(before, after):
    member_role = discord.utils.get(after.guild.roles, name="Member")

    if after == after.guild.owner:
        print(f"Skipping compliance checks for server owner: {after.display_name}.")
        return

    if member_role and member_role not in before.roles and member_role in after.roles:
        print(f"Member role assigned to {after.display_name}. Checking compliance...")

        if not after.nick or len(after.nick.split()) < 2:
            print(f"{after.display_name} does not have a compliant nickname.")
            asyncio.create_task(transfer_to_everyone_and_notify(after, reason="Invalid nickname format."))
            return

        try:
            db_cursor.execute("SELECT my_id FROM user_data WHERE user_id = ?", (after.id,))
            result = db_cursor.fetchone()
            if not result:
                print(f"No MyID found for {after.display_name}.")
                asyncio.create_task(transfer_to_everyone_and_notify(after, reason="Missing MyID in the database."))
            else:
                print(f"{after.display_name} is compliant with nickname and MyID.")
        except Exception as e:
            print(f"Database error while checking MyID for {after.display_name}: {e}")
            asyncio.create_task(transfer_to_everyone_and_notify(after, reason="Database error while verifying MyID."))

async def transfer_to_everyone_and_notify(member, reason):
    if member == member.guild.owner:
        print(f"Skipping transfer and notifications for server owner: {member.display_name}.")
        return

    try:
        member_role = discord.utils.get(member.guild.roles, name="Member")
        if member_role in member.roles:
            await member.remove_roles(member_role)
            print(f"Removed 'Member' role from {member.display_name} due to: {reason}.")

        dm_channel = await member.create_dm()
        await dm_channel.send(
            f"Hello! You have been transferred back to the general role because: {reason}. "
            "Please provide the necessary details to regain access."
        )

        # Initiate the update process in a separate background task
        asyncio.create_task(prompt_user_for_information(member, dm_channel))

    except Exception as e:
        print(f"Error handling member update for {member.display_name}: {e}")

async def prompt_user_for_information(member, dm_channel):
    try:
        try:
            await dm_channel.send("What is your First Name?")
            first_name = await bot.wait_for(
                "message",
                check=lambda m: m.author == member and m.channel == dm_channel,
                timeout=None  # Allow unlimited time for the user to respond
            )

            await dm_channel.send("What is your Last Name?")
            last_name = await bot.wait_for(
                "message",
                check=lambda m: m.author == member and m.channel == dm_channel,
                timeout=None
            )

            await dm_channel.send("What is your MyID? (This will only be shared with Server President and VP)")
            my_id = await bot.wait_for(
                "message",
                check=lambda m: m.author == member and m.channel == dm_channel,
                timeout=None
            )
        except asyncio.TimeoutError:
            await dm_channel.send("You did not respond in time. Please contact an admin to regain access.")
            print(f"{member.display_name} did not respond in time.")
            return

        try:
            new_nickname = f"{first_name.content} {last_name.content}"
            await member.edit(nick=new_nickname)
            print(f"Nickname updated to '{new_nickname}' for {member.display_name}.")
        except discord.Forbidden:
            print(f"Failed to update nickname for {member.display_name}.")
            await dm_channel.send(
                "I was unable to update your nickname. Please manually update it to match the required format: "
                "FirstName LastName."
            )
            return

        try:
            db_cursor.execute(
                """
                INSERT OR REPLACE INTO user_data (user_id, first_name, last_name, my_id)
                VALUES (?, ?, ?, ?)
                """,
                (member.id, first_name.content, last_name.content, my_id.content),
            )
            db_connection.commit()
            print(f"User data saved for {new_nickname}.")
        except Exception as e:
            print(f"Failed to save user data to the database: {e}")
            await dm_channel.send("There was an issue saving your information. Please contact a server admin.")
            return

        if member_role := discord.utils.get(member.guild.roles, name="Member"):
            try:
                await member.add_roles(member_role)
                print(f"Reassigned 'Member' role to {new_nickname}.")
            except discord.Forbidden:
                print(f"Failed to reassign 'Member' role to {new_nickname}.")
                await dm_channel.send(
                    "I was unable to reassign your 'Member' role. Please contact a server admin for assistance."
                )
        else:
            print("The 'Member' role does not exist.")
            await dm_channel.send(
                "Your information was saved, but the 'Member' role could not be assigned. Please contact a server admin."
            )

        await dm_channel.send(
            "Thank you! Your information has been updated, and you've been granted access to the server."
        )
    except Exception as e:
        print(f"Error handling user information update for {member.display_name}: {e}")

@bot.tree.command(name="scan_server", description="Scan all members in the server for compliance")
@app_commands.guild_only()
async def scan_server(ctx):
    if not ctx.user.guild_permissions.administrator:
        await ctx.response.send_message(f"{ctx.user.mention}, you do not have permission to use this command.")
        return

    if not await is_moderator_channel(ctx):
        await ctx.response.send_message("This command can only be used in #moderator-general.", ephemeral=True)
        return

    await ctx.response.send_message("Starting a server-wide compliance scan...", ephemeral=True)

    MEMBER_ROLE_NAME = "Member"
    role = discord.utils.get(ctx.guild.roles, name=MEMBER_ROLE_NAME)

    print("Starting compliance scan for @Members...")

    total_scanned = 0
    compliant_count = 0
    non_compliant_count = 0
    tasks = []

    for member in ctx.guild.members:
        if member.bot:
            continue

        print(f"Scanning {member.display_name}...")
        total_scanned += 1

        try:
            if member == ctx.guild.owner:
                print(f"Skipping server owner: {member.display_name}.")
                compliant_count += 1
                continue

            if role not in member.roles:
                print(f"{member.display_name} does not have the 'Member' role. Skipping.")
                continue

            if not member.nick or len(member.nick.split()) < 2:
                print(f"{member.display_name} does not have a compliant nickname.")
                task = asyncio.create_task(
                    transfer_to_everyone_and_notify(member, reason="Invalid nickname format.")
                )
                tasks.append(task)
                non_compliant_count += 1
                continue

            compliant_count += 1
        except Exception as e:
            print(f"Error scanning {member.display_name}: {e}")
            non_compliant_count += 1

    if tasks:
        print(f"Waiting for {len(tasks)} background tasks to complete...")
        await asyncio.gather(*tasks)

    print("Member scan completed.")
    print(f"Total members scanned: {total_scanned}")
    print(f"Compliant members: {compliant_count}")
    print(f"Non-compliant members: {non_compliant_count}")

    await ctx.followup.send(
        f"**Scan Completed**\n"
        f"Total members scanned: {total_scanned}\n"
        f"Compliant members: {compliant_count}\n"
        f"Non-compliant members: {non_compliant_count}"
    )

@bot.tree.command(name="scan_member", description="Scan a specific member in the server for compliance")
@app_commands.guild_only()
async def scan_member(ctx, member: discord.Member):
    if not ctx.user.guild_permissions.administrator:
        await ctx.response.send_message("You do not have permission to use this command.")
        return

    if not await is_moderator_channel(ctx):
        await ctx.response.send_message("This command can only be used in #moderator-general.", ephemeral=True)
        return

    await ctx.response.send_message(f"Scanning {member.display_name}...", ephemeral=True)

    if member.bot:
        await ctx.followup.send(f"{member.display_name} is a bot and cannot be scanned.")
        return

    if member == ctx.guild.owner:
        await ctx.followup.send(f"{member.display_name} is the server owner and will be skipped.")
        return

    member_role = discord.utils.get(ctx.guild.roles, name="Member")
    try:
        if member_role not in member.roles:
            await ctx.followup.send(f"{member.display_name} does not have the 'Member' role. Skipping.")
            return

        if not member.nick or len(member.nick.split()) < 2:
            await ctx.followup.send(f"{member.display_name} does not have a compliant nickname.")
            asyncio.create_task(transfer_to_everyone_and_notify(member, reason="Invalid nickname format."))
            return

        db_cursor.execute("SELECT my_id FROM user_data WHERE user_id = ?", (member.id,))
        result = db_cursor.fetchone()
        if not result:
            await ctx.followup.send(f"{member.display_name} is missing a MyID in the database.")
            asyncio.create_task(transfer_to_everyone_and_notify(member, reason="Missing MyID in the database."))
            return

        await ctx.followup.send(f"{member.display_name} is fully compliant!")
    except Exception as e:
        await ctx.followup.send(f"An error occurred while scanning {member.display_name}: {e}")

@bot.tree.command(name="add_myid", description="Add or update a MyID for a specific member")
@app_commands.guild_only()
async def add_myid(ctx, member: discord.Member = None, my_id: str = None):
    if not my_id:
        await ctx.response.send_message("Please provide a valid MyID.", ephemeral=True)
        return

    await ctx.response.send_message(f"Adding MyID for {member.display_name if member else ctx.user.display_name}...", ephemeral=True)

    if member.bot:
        await ctx.followup.send(f"Unable to add MyID, {member.display_name} is a bot.")
        return

    try:
        if not member:
            member = ctx.user

        if member.nick and len(member.nick.split()) >= 2:
            first_name, last_name = member.nick.split()[0], member.nick.split()[1]
            db_cursor.execute(
                """
                INSERT OR REPLACE INTO user_data (user_id, first_name, last_name, my_id)
                VALUES (?, ?, ?, ?)
                """,
                (member.id, first_name, last_name, my_id),
            )
            db_connection.commit()
            await ctx.followup.send(f"MyID for {member.display_name} has been successfully updated to: {my_id}")
        else:
            await ctx.followup.send(f"{member.display_name} does not have a valid nickname.")
    except Exception as e:
        await ctx.followup.send(f"An error occurred while adding the MyID: {e}")

@bot.tree.command(name="get_myid", description="Return a MyID for a specific member")
@app_commands.guild_only()
async def get_myid(ctx, member: discord.Member):
    if not ctx.user.guild_permissions.administrator:
        await ctx.response.send_message("You do not have permission to use this command.")
        return

    if not await is_moderator_channel(ctx):
        await ctx.response.send_message("This command can only be used in #moderator-general.", ephemeral=True)
        return

    await ctx.response.send_message(f"Fetching MyID for {member.display_name}...", ephemeral=True)

    if member.bot:
        await ctx.followup.send(f"Unable to get MyID, {member.display_name} is a bot.")
        return

    try:
        db_cursor.execute("SELECT first_name, last_name, my_id FROM user_data WHERE user_id = ?", (member.id,))
        result = db_cursor.fetchone()
        if result:
            first_name, last_name, my_id = result
            await ctx.followup.send(f"{first_name} {last_name}'s MyID is: {my_id}")
        else:
            await ctx.followup.send(f"No MyID found for {member.display_name}.")
    except Exception as e:
        await ctx.followup.send(f"An error occurred while fetching MyID for {member.display_name}: {e}")

@bot.tree.command(name="list_myids", description="Return a list of all users and their MyIDs")
@app_commands.guild_only()
async def list_myids(ctx):
    if not ctx.user.guild_permissions.administrator:
        await ctx.response.send_message("You do not have permission to use this command.")
        return

    if not await is_moderator_channel(ctx):
        await ctx.response.send_message("This command can only be used in #moderator-general.", ephemeral=True)
        return

    await ctx.response.send_message("Fetching all stored MyIDs...", ephemeral=True)

    try:
        db_cursor.execute("SELECT first_name, last_name, my_id FROM user_data")
        rows = db_cursor.fetchall()
        if rows:
            result = "\n".join([f"{first_name} {last_name}: {my_id}" for first_name, last_name, my_id in rows])
            await ctx.followup.send(f"**Stored MyIDs:**\n{result}")
        else:
            await ctx.followup.send("No MyIDs found in the database.")
    except Exception as e:
        await ctx.followup.send(f"An error occurred while fetching MyIDs: {e}")

@bot.tree.command(name="wipe_myids", description="Empty the database associating users with their MyIDs")
@app_commands.guild_only()
async def wipe_myids(ctx):
    if not ctx.user.guild_permissions.administrator:
        await ctx.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    if not await is_moderator_channel(ctx):
        await ctx.response.send_message("This command can only be used in #moderator-general.", ephemeral=True)
        return

    await ctx.response.send_message(
        "This action will wipe all MyIDs from the database. Type `Confirm` to proceed.",
        ephemeral=True
    )

    try:
        def check(m):
            return m.author == ctx.user and m.channel == ctx.channel

        msg = await bot.wait_for("message", check=check, timeout=10.0)

        if msg.content.lower() == "confirm":
            db_cursor.execute("DELETE FROM user_data")
            db_connection.commit()
            await ctx.followup.send("All MyIDs have been deleted from the database.")
        else:
            await ctx.followup.send("Operation canceled. You did not type `Confirm`.", ephemeral=True)

    except asyncio.TimeoutError:
        await ctx.followup.send("Operation canceled due to no response within the timeout period.", ephemeral=True)
    except Exception as e:
        await ctx.followup.send(f"An error occurred while wiping MyIDs: {e}", ephemeral=True)


# Run the bot
bot.run(TOKEN)
