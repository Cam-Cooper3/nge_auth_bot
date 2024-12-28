import discord
import os
import sqlite3
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

# Load the environment variables from .env
load_dotenv()

# Get the variables from the .env file
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Bot setup with required intents
intents = discord.Intents.default()
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

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    for guild in bot.guilds:
        bot_member = guild.get_member(bot.user.id)

        # Check if the bot's role is the highest
        if bot_member and bot_member.top_role.position != len(guild.roles) - 1:
            # Notify the server owner via DM
            owner = guild.owner
            if owner:
                try:
                    await owner.send(
                        f"To function correctly, please ensure my role is at the top of the role hierarchy in your server "
                        f"'{guild.name}'. You can do this in Server Settings > Roles."
                    )
                    print(f"Sent hierarchy notification to {owner.display_name}.")
                except discord.Forbidden:
                    print(f"Could not DM the server owner in {guild.name}.")
            else:
                print(f"No owner found for guild {guild.name}.")

@bot.event
async def on_member_update(before, after):
    """Triggered when a member's roles or details are updated."""
    # Define the Member role
    member_role = discord.utils.get(after.guild.roles, name="Member")

    # Skip server owner
    if after == after.guild.owner:
        print(f"Skipping compliance checks for server owner: {after.display_name}.")
        return

    # Check if the @Member role was added
    if member_role and member_role not in before.roles and member_role in after.roles:
        print(f"Member role assigned to {after.display_name}. Checking compliance...")

        # Check if the member's nickname conforms to "FirstName LastName"
        if not after.nick or len(after.nick.split()) < 2:
            print(f"{after.display_name} does not have a compliant nickname.")
            await transfer_to_everyone_and_notify(after, reason="Invalid nickname format.")
            return

        # Check if the member has a unique MyID in the database
        try:
            db_cursor.execute("SELECT my_id FROM user_data WHERE user_id = ?", (after.id,))
            result = db_cursor.fetchone()
            if not result:
                print(f"No MyID found for {after.display_name}.")
                await transfer_to_everyone_and_notify(after, reason="Missing MyID in the database.")
            else:
                print(f"{after.display_name} is compliant with nickname and MyID.")
        except Exception as e:
            print(f"Database error while checking MyID for {after.display_name}: {e}")
            await transfer_to_everyone_and_notify(after, reason="Database error while verifying MyID.")

async def transfer_to_everyone_and_notify(member, reason):
    """Transfer a user back to @everyone and notify them of the reason."""
    # Skip server owner
    if member == member.guild.owner:
        print(f"Skipping transfer and notifications for server owner: {member.display_name}.")
        return

    try:
        # Get the Member role and remove it
        member_role = discord.utils.get(member.guild.roles, name="Member")
        if member_role in member.roles:
            await member.remove_roles(member_role)
            print(f"Removed 'Member' role from {member.display_name} due to: {reason}.")

        # Open a DM channel and notify the user
        dm_channel = await member.create_dm()
        await dm_channel.send(
            f"Hello! You have been transferred back to the general role because: {reason}. "
            "Please provide the necessary details to regain access."
        )

        # Ask for First Name
        await dm_channel.send("What is your First Name?")
        first_name = await bot.wait_for("message", check=lambda m: m.author == member and m.channel == dm_channel)

        # Ask for Last Name
        await dm_channel.send("What is your Last Name?")
        last_name = await bot.wait_for("message", check=lambda m: m.author == member and m.channel == dm_channel)

        # Ask for MyID
        await dm_channel.send("What is your MyID? (This will only be shared with Server President and VP)")
        my_id = await bot.wait_for("message", check=lambda m: m.author == member and m.channel == dm_channel)

        # Update server nickname
        try:
            new_nickname = f"{first_name.content} {last_name.content}"
            await member.edit(nick=new_nickname)
            print(f"Nickname updated to '{new_nickname}' for {member.display_name}.")
        except discord.Forbidden:
            print(f"Failed to update nickname for {member.display_name}. Ensure the bot's role is higher in the hierarchy.")
            await dm_channel.send(
                "I was unable to update your nickname. Please manually update it to match the required format: "
                "FirstName LastName."
            )
            return

        # Store user data in the database
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

        # Reassign the Member role
        if member_role:
            try:
                await member.add_roles(member_role)
                print(f"Reassigned 'Member' role to {new_nickname}.")
            except discord.Forbidden:
                print(f"Failed to reassign 'Member' role to {new_nickname}. Ensure the bot's role is higher.")
                await dm_channel.send(
                    "I was unable to reassign your 'Member' role. Please contact a server admin for assistance."
                )
        else:
            print("The 'Member' role does not exist.")
            await dm_channel.send(
                "Your information was saved, but the 'Member' role could not be assigned. Please contact a server admin."
            )

        # Confirm success
        await dm_channel.send(
            "Thank you! Your information has been updated, and you've been granted access to the server."
        )
    except Exception as e:
        print(f"Error handling member update for {member.display_name}: {e}")

@bot.command()
async def check_members(ctx):
    """Command to check all members' nicknames and enforce compliance (Admin only)."""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send(f"{ctx.author.mention}, you do not have permission to use this command.")
        return

    await ctx.send("Scanning all members for nickname compliance...")
    await scan_members(ctx.guild)
    await ctx.send("Member scan complete. Non-compliant members have been notified.")

async def scan_members(guild):
    """Scan all members in the guild for compliance."""
    MEMBER_ROLE_NAME = "Member"
    role = discord.utils.get(guild.roles, name=MEMBER_ROLE_NAME)

    print(f"Starting compliance scan for @Members...")

    total_scanned = 0
    compliant_count = 0
    non_compliant_count = 0

    for member in guild.members:
        if member.bot:  # Ignore bots
            continue

        print(f"Scanning {member.display_name}...")  # Log the member being scanned
        total_scanned += 1

        try:
            # Skip the server owner
            if member == guild.owner:
                print(f"Skipping server owner: {member.display_name}.")
                compliant_count += 1  # Server owner is treated as compliant
                continue

            # Check if the member has the "Member" role
            if role not in member.roles:
                print(f"{member.display_name} does not have the 'Member' role. Skipping.")
                continue

            # Check if the member's nickname complies with "FirstName LastName"
            if not member.nick or len(member.nick.split()) < 2:
                print(f"{member.display_name} does not have a compliant nickname.")
                await transfer_to_everyone_and_notify(member, reason="Invalid nickname format.")
                non_compliant_count += 1
                continue

            # Check if the member has a unique MyID in the database
            db_cursor.execute("SELECT my_id FROM user_data WHERE user_id = ?", (member.id,))
            result = db_cursor.fetchone()
            if not result:
                print(f"No MyID found for {member.display_name}.")
                await transfer_to_everyone_and_notify(member, reason="Missing MyID in the database.")
                non_compliant_count += 1
                continue

            # If member is compliant
            compliant_count += 1

        except Exception as e:
            print(f"Error scanning {member.display_name}: {e}")
            non_compliant_count += 1  # Treat errors as non-compliance

    # Summary of scan results
    print(f"Member scan completed.")
    print(f"Total members scanned: {total_scanned}")
    print(f"Compliant members: {compliant_count}")
    print(f"Non-compliant members: {non_compliant_count}")

@bot.command()
async def get_myid(ctx, member: discord.Member):
    """Command for moderators to retrieve a user's MyID in a specific channel."""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You do not have permission to use this command.")
        return

    db_cursor.execute("SELECT first_name, last_name, my_id FROM user_data WHERE user_id = ?", (member.id,))
    result = db_cursor.fetchone()
    if result:
        first_name, last_name, my_id = result
        await ctx.send(f"{first_name} {last_name}'s MyID is: {my_id}")
    else:
        await ctx.send(f"No MyID found for {member.display_name}.")

@bot.command()
async def add_myid(ctx, member: discord.Member = None, my_id: str = None):
    """Allow users to add/update their MyID or let administrators update others' MyID."""
    if not my_id:
        await ctx.send("Please provide a valid MyID. Usage: `!add_myid [@user] [MyID]`")
        return

    if not member:
        member = ctx.author

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
        await ctx.send(f"MyID for {member.display_name} has been successfully updated to: {my_id}.")
    else:
        await ctx.send(f"{member.display_name} does not have a valid FirstName LastName nickname.")

@bot.command()
async def list_myids(ctx):
    """List all stored MyIDs (Admin only, restricted to #moderator-general channel)."""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You do not have permission to use this command.")
        return

    db_cursor.execute("SELECT first_name, last_name, my_id FROM user_data")
    rows = db_cursor.fetchall()
    if rows:
        result = "\n".join([f"{first_name} {last_name}: {my_id}" for first_name, last_name, my_id in rows])
        await ctx.send(f"**Stored MyIDs:**\n{result}")
    else:
        await ctx.send("No MyIDs found in the database.")

@bot.command()
async def wipe_myids(ctx):
    """Wipe all stored MyIDs from the database (Admin only, restricted to #moderator-general)."""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You do not have permission to use this command.")
        return

    await ctx.send("This action will wipe all MyIDs. Type `Confirm` to proceed.")
    try:
        def check(m):
            return m.author == ctx.author and m.content.lower() == "confirm"
        await bot.wait_for("message", check=check, timeout=30.0)
        db_cursor.execute("DELETE FROM user_data")
        db_connection.commit()
        await ctx.send("All MyIDs have been wiped.")
    except asyncio.TimeoutError:
        await ctx.send("Operation canceled due to no confirmation.")

# Run the bot
bot.run(TOKEN)
