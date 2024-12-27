import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

# Load the environment variables from .env
load_dotenv()

# Get the variables from the .env file
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
MODERATOR_CHANNEL_ID = os.getenv("MODERATOR_CHANNEL")

# Bot setup with required intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Dictionary to store user data (replace with a database for production)
user_data = {}

@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")

@bot.event
async def on_member_join(member):
    try:
        # Send DM to the new member
        dm_channel = await member.create_dm()
        await dm_channel.send("Welcome to the server! Please provide your details.")
        
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
        await member.edit(nick=f"{first_name.content} {last_name.content}")
        
        # Store user data
        user_data[member.id] = {
            "FirstName": first_name.content,
            "LastName": last_name.content,
            "MyID": my_id.content
        }
        
        # Assign the "Member" role (ensure the role exists in your server)
        role = discord.utils.get(member.guild.roles, name="Member")
        if role:
            await member.add_roles(role)
        
        # Confirm success
        await dm_channel.send("Thank you! Your information has been updated, and you've been granted access to the server.")
    
    except Exception as e:
        print(f"Error handling new member: {e}")

@bot.command()
async def get_user(ctx, member: discord.Member):
    """Command for moderators to retrieve a user's MyID in a specific channel."""
    # Check if the command is used in the "moderator-general" channel
    if ctx.channel.name != "moderator-general":
        try:
            await ctx.author.send("This command can only be used in the #moderator-general channel.")
        except discord.Forbidden:
            await ctx.author.send("I couldn't DM you. Please check your privacy settings.")
        return

    # Check if the user has administrator permissions
    if ctx.author.guild_permissions.administrator:
        data = user_data.get(member.id)
        if data:
            await ctx.send(f"{member}'s MyID is: {data['MyID']}")
        else:
            await ctx.send("No data found for this user.")
    else:
        await ctx.author.send("You do not have permission to use this command.")




# Run the bot
bot.run(TOKEN)
