import discord
from discord import app_commands
from discord.ui import Button, View
import json
import os

intents = discord.Intents.default()
intents.members = True  # Required to track member changes
intents.message_content = True

class WelcomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # persistent button

    @discord.ui.button(label="Enter Server", style=discord.ButtonStyle.green, custom_id="enter_server_btn")
    # Added 'button: discord.ui.Button' below to fix the TypeError
    async def enter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = discord.utils.get(interaction.guild.roles, name="Newcomer")
        
        if role:
            if role in interaction.user.roles:
                try:
                    await interaction.user.remove_roles(role)
                    await interaction.response.send_message("✅ Welcome to Broken Crown! You now have access to the rest of the server.", ephemeral=True)
                except discord.Forbidden:
                    await interaction.response.send_message("❌ I don't have permission to remove your role! Tell an Admin to move my bot role higher.", ephemeral=True)
            else:
                await interaction.response.send_message("You have already entered!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ The 'Newcomer' role was not found. Please contact staff.", ephemeral=True)

class TownyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # This tells the bot to remember the "Enter Server" button
        # even if the bot restarts!
        self.add_view(WelcomeView()) 
        await self.tree.sync()

bot = TownyBot()

# --- Data Management ---
def load_towns():
    # If file doesn't exist, create it with empty brackets
    if not os.path.exists("towns.json"):
        with open("towns.json", "w") as f:
            json.dump({}, f)
        return {}
    
    # Try to read the file
    try:
        with open("towns.json", "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        # If the file is blank or corrupted, fix it automatically
        print("⚠️ towns.json was empty or corrupted. Resetting to {}")
        with open("towns.json", "w") as f:
            json.dump({}, f)
        return {}

def save_towns(towns):
    with open("towns.json", "w") as f:
        json.dump(towns, f, indent=4)

def load_nations():
    if not os.path.exists("nations.json"):
        with open("nations.json", "w") as f:
            json.dump({}, f)
        return {}
    
    try:
        with open("nations.json", "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        # If the file is empty or broken, reset it
        print("⚠️ nations.json was empty or corrupted. Resetting to {}")
        with open("nations.json", "w") as f:
            json.dump({}, f)
        return {}

def save_nations(nations):
    with open("nations.json", "w") as f:
        json.dump(nations, f, indent=4)
# --- Events ---
@bot.event
async def on_member_join(member):
    # Create the Newcomer role if it doesn't exist
    role = discord.utils.get(member.guild.roles, name="Newcomer")
    if not role:
        role = await member.guild.create_role(name="Newcomer", reason="Auto-joining role")
    
    await member.add_roles(role)

@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.playing, name="🎮 Playing Broken Crown MC..."),
        status=discord.Status.dnd
    )
    print(f'Logged in as {bot.user}!')

# --- Commands ---
@bot.tree.command(name="setup_welcome", description="Send the welcome button to this channel")
@app_commands.checks.has_permissions(administrator=True)
async def setup_welcome(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Welcome to Broken Crown MC!",
        description="Please read the rules and click the button below to gain access to the full server.",
        color=discord.Color.gold()
    )
    await interaction.channel.send(embed=embed, view=WelcomeView())
    await interaction.response.send_message("Welcome message sent!", ephemeral=True)
    

@bot.tree.command(name="towncreate", description="Create a new town role")
@app_commands.describe(name="Town name", colour="Role colour (hex, e.g. #ff5733)")
async def create(interaction: discord.Interaction, name: str, colour: str):
    guild = interaction.guild
    user = interaction.user
    towns = load_towns()

    if name in towns:
        return await interaction.response.send_message("That town already exists!", ephemeral=True)

    role = await guild.create_role(
        name=name,
        colour=discord.Colour.from_str(colour),
        reason="Town created"
    )

    await interaction.user.add_roles(role)

    towns[name] = {
        "role_id": role.id,
        "owner_id": user.id,
        "members": [user.id],
        "pending": [],
        "awaiting_confirmation": False,
        "guild_id": guild.id  # Crucial for DM interactions
    }

    save_towns(towns)
    await interaction.response.send_message(f"🏘️ Town **{name}** created!", ephemeral=True)

@bot.tree.command(name="townjoin", description="Request to join a town")
async def join(interaction: discord.Interaction, town_name: str):
    guild = interaction.guild
    user = interaction.user
    towns = load_towns()
   
    # CHECK: Is the user already in ANY town?
    already_in_town = any(user.id in t["members"] for t in towns.values())
    if already_in_town:
        return await interaction.response.send_message("❌ You are already a member of a town! You must `/leave` your current town first.", ephemeral=True)
    
    if town_name not in towns:
        return await interaction.response.send_message("Town not found!", ephemeral=True)

    town = towns[town_name]
    if user.id in town["members"]:
        return await interaction.response.send_message("You're already in that town!", ephemeral=True)
    if user.id in town["pending"]:
        return await interaction.response.send_message("You already requested to join!", ephemeral=True)

    town["pending"].append(user.id)
    save_towns(towns)

    # Create buttons
    accept_button = Button(label="Accept", style=discord.ButtonStyle.green, custom_id=f"accept_{town_name}_{user.id}")
    deny_button = Button(label="Deny", style=discord.ButtonStyle.red, custom_id=f"deny_{town_name}_{user.id}")
    view = View()
    view.add_item(accept_button)
    view.add_item(deny_button)

    owner = guild.get_member(town["owner_id"])
    if owner:
        await owner.send(f"📩 {user.mention} wants to join **{town_name}**. Click a button to respond.", view=view)
        await interaction.response.send_message("Join request sent!", ephemeral=True)
    else:
        await interaction.response.send_message("The town owner is not available.", ephemeral=True)

# --- Button Interaction Handler ---

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id", "")
    
    # Updated check to include nation prefixes (naccept_ and ndeny_)
    valid_prefixes = ("accept_", "deny_", "naccept_", "ndeny_")
    if not custom_id.startswith(valid_prefixes):
        return

    # --- NATION INTERACTION LOGIC ---
    if custom_id.startswith(("naccept_", "ndeny_")):
        try:
            parts = custom_id.split('_')
            action = parts[0]  # naccept or ndeny
            nation_name = parts[1]
            town_name = parts[2]
        except (IndexError, ValueError):
            return

        nations = load_nations()
        if nation_name not in nations:
            return await interaction.response.send_message("❌ This nation no longer exists.", ephemeral=True)

        if action == "naccept":
            # Check if the town joined another nation while this invite was pending
            if any(town_name in n["member_towns"] for n in nations.values()):
                 return await interaction.response.send_message("❌ This town is already part of a nation!", ephemeral=True)

            if town_name not in nations[nation_name]["member_towns"]:
                nations[nation_name]["member_towns"].append(town_name)
                save_nations(nations)
            
            await interaction.response.send_message(f"✅ Your town **{town_name}** has joined the nation of **{nation_name}**!", ephemeral=True)
            
            # Notify the Nation Leader
            leader = bot.get_user(nations[nation_name]["leader_id"])
            if leader:
                try:
                    await leader.send(f"🎉 **{town_name}** has accepted the invitation and joined **{nation_name}**!")
                except: pass

        elif action == "ndeny":
            await interaction.response.send_message(f"❌ You declined the invitation to join **{nation_name}**.", ephemeral=True)

        # Disable Buttons
        for item in interaction.message.components:
            for b in item.children:
                b.disabled = True
        await interaction.message.edit(view=discord.ui.View.from_message(interaction.message))
        return # Exit here so it doesn't run the Town logic below


    # --- TOWN INTERACTION LOGIC (Your Original Code) ---
    try:
        parts = custom_id.split('_')
        action = parts[0]
        town_name = parts[1]
        target_user_id = int(parts[2])
    except (IndexError, ValueError):
        return

    towns = load_towns()
    town = towns.get(town_name)

    if not town:
        return await interaction.response.send_message("Town not found in database.", ephemeral=True)

    guild_id = town.get("guild_id")
    target_guild = None
    if guild_id:
        target_guild = bot.get_guild(guild_id)
    
    if not target_guild:
        for g in bot.guilds:
            if g.get_member(town["owner_id"]):
                target_guild = g
                break

    if not target_guild:
        return await interaction.response.send_message("Could not locate the Minecraft Discord server.", ephemeral=True)

    target_member = target_guild.get_member(target_user_id)
    if not target_member:
        try:
            target_member = await target_guild.fetch_member(target_user_id)
        except:
            return await interaction.response.send_message("The player is no longer in the server.", ephemeral=True)

    if action == "accept":
        role = target_guild.get_role(town["role_id"])
        if role:
            try:
                await target_member.add_roles(role)
                if target_user_id not in town["members"]:
                    town["members"].append(target_user_id)
                if target_user_id in town["pending"]:
                    town["pending"].remove(target_user_id)
                
                save_towns(towns)
                await interaction.response.send_message(f"✅ Success! {target_member.display_name} is now a member of {town_name}.", ephemeral=True)
                await target_member.send(f"🎉 You've been accepted into **{town_name}**!")
            except discord.Forbidden:
                await interaction.response.send_message("❌ Role hierarchy error! Move bot role higher.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Town role not found.", ephemeral=True)

    elif action == "deny":
        if target_user_id in town["pending"]:
            town["pending"].remove(target_user_id)
        save_towns(towns)
        await interaction.response.send_message(f"❌ Denied the request for {town_name}.", ephemeral=True)
        await target_member.send(f"❌ Your request to join **{town_name}** was denied.")

    for item in interaction.message.components:
        for b in item.children:
            b.disabled = True
    await interaction.message.edit(view=discord.ui.View.from_message(interaction.message))

# (Rest of your original /jail, /announce, /war commands go here)
# Make sure to re-paste your War and Jail commands back in!
@bot.tree.command(name="townleave", description="Leave your current town")
async def leave(interaction: discord.Interaction):
    user = interaction.user
    towns = load_towns()
    town_name = next((name for name, town in towns.items() if user.id in town["members"]), None)

    if town_name is None:
        return await interaction.response.send_message("You are not in any town!", ephemeral=True)

    town = towns[town_name]
    if user.id == town["owner_id"]:
        return await interaction.response.send_message("You cannot leave your town without transferring ownership!", ephemeral=True)

    role = interaction.guild.get_role(town["role_id"])
    if role:
        await user.remove_roles(role)

    town["members"].remove(user.id)
    save_towns(towns)
    await interaction.response.send_message(f"You have left **{town_name}**.", ephemeral=True)

@bot.tree.command(name="townexile", description="Force a player to leave your town")
async def forceleave(interaction: discord.Interaction, user: discord.User):
    towns = load_towns()
    town_name = next((name for name, town in towns.items() if user.id in town["members"]), None)

    if town_name is None:
        return await interaction.response.send_message("That player isn't in any town!", ephemeral=True)

    town = towns[town_name]
    if interaction.user.id != town["owner_id"]:
        return await interaction.response.send_message("You are not the town owner!", ephemeral=True)

    role = interaction.guild.get_role(town["role_id"])
    if role:
        member = interaction.guild.get_member(user.id)
        if member:
            await member.remove_roles(role)

    town["members"].remove(user.id)
    save_towns(towns)
    await interaction.response.send_message(f"🚪 {user.mention} was removed from **{town_name}**.")

@bot.tree.command(name="townjail", description="Give a player a jail role")
async def jail(interaction: discord.Interaction, user: discord.User):
    guild = interaction.guild
    jail_role = discord.utils.get(guild.roles, name="Jail")
    if not jail_role:
        jail_role = await guild.create_role(name="Jail", colour=discord.Color.red())

    member = guild.get_member(user.id)
    if member:
        await member.add_roles(jail_role)
        await interaction.response.send_message(f"{user.mention} has been jailed!", ephemeral=True)

@bot.tree.command(name="townannounce", description="Send an announcement to all town members")
async def announce(interaction: discord.Interaction, message: str):
    towns = load_towns()
    user = interaction.user
    town_name = next((name for name, town in towns.items() if user.id == town["owner_id"]), None)

    if town_name is None:
        return await interaction.response.send_message("You are not a town owner!", ephemeral=True)

    town = towns[town_name]
    for member_id in town["members"]:
        member = interaction.guild.get_member(member_id)
        if member:
            try:
                await member.send(f"📣 **{town_name}** Announcement: {message}")
            except discord.Forbidden:
                continue

    await interaction.response.send_message(f"Announcement sent!", ephemeral=True)

###
@bot.tree.command(name="towndeclarewar", description="Declare war on another town")
async def declarewar(interaction: discord.Interaction, target_town: str):
    towns = load_towns()
    user = interaction.user
    town_name = next((name for name, town in towns.items() if user.id == town["owner_id"]), None)

    if town_name is None:
        return await interaction.response.send_message("You are not a town owner!", ephemeral=True)

    if target_town not in towns:
        return await interaction.response.send_message("Target town not found!", ephemeral=True)

    if target_town == town_name:
        return await interaction.response.send_message("You cannot declare war on yourself!", ephemeral=True)

    towns[town_name]["war_declared"] = target_town
    towns[town_name]["war_status"] = "pending" # Status is pending until accepted
    towns[target_town]["war_declared"] = town_name
    towns[target_town]["war_status"] = "pending"
    
    save_towns(towns)

    target_data = towns[target_town]
    target_owner = interaction.guild.get_member(target_data["owner_id"])
    if target_owner:
        await target_owner.send(f"⚔️ **{town_name}** has declared war on your town! Use `/townwaraccept` to start the conflict.")
    
    await interaction.response.send_message(f"War declaration sent to **{target_town}**!", ephemeral=True)

@bot.tree.command(name="townwaraccept", description="Accept a war declaration")
async def waraccept(interaction: discord.Interaction):
    towns = load_towns()
    town_name = next((name for name, town in towns.items() if interaction.user.id == town["owner_id"]), None)

    if town_name is None or towns[town_name].get("war_status") != "pending":
        return await interaction.response.send_message("No pending war declaration to accept!", ephemeral=True)

    target_town = towns[town_name]["war_declared"]
    
    # Set both towns to active war status
    towns[town_name]["war_status"] = "active"
    towns[target_town]["war_status"] = "active"
    save_towns(towns)

    await interaction.response.send_message(f"⚔️ War between **{town_name}** and **{target_town}** has officially begun!", ephemeral=False)

@bot.tree.command(name="townwardeny", description="Deny a war declaration")
async def wardeny(interaction: discord.Interaction):
    towns = load_towns()
    town_name = next((name for name, town in towns.items() if interaction.user.id == town["owner_id"]), None)

    if town_name and "war_declared" in towns[town_name]:
        target = towns[town_name]["war_declared"]
        towns[town_name].pop("war_declared", None)
        towns[town_name].pop("war_status", None)
        towns[target].pop("war_declared", None)
        towns[target].pop("war_status", None)
        save_towns(towns)
        await interaction.response.send_message("War declaration denied.")

@bot.tree.command(name="townwarceasefire", description="End the active war")
async def warceasefire(interaction: discord.Interaction):
    towns = load_towns()
    town_name = next((name for name, town in towns.items() if interaction.user.id == town["owner_id"]), None)
    
    if town_name and towns[town_name].get("war_status") == "active":
        target = towns[town_name]["war_declared"]
        
        towns[town_name].pop("war_declared", None)
        towns[town_name].pop("war_status", None)
        towns[target].pop("war_declared", None)
        towns[target].pop("war_status", None)
        save_towns(towns)
        await interaction.response.send_message(f"🏳️ A ceasefire has been signed between **{town_name}** and **{target}**.")
###
@bot.tree.command(name="townunjail", description="Remove the jail role from a player")
@app_commands.checks.has_permissions(manage_roles=True) # Only staff/admins should usually do this
async def unjail(interaction: discord.Interaction, user: discord.User):
    guild = interaction.guild
    jail_role = discord.utils.get(guild.roles, name="Jail")
    
    if not jail_role:
        return await interaction.response.send_message("The Jail role doesn't exist.", ephemeral=True)

    member = guild.get_member(user.id)
    if member and jail_role in member.roles:
        await member.remove_roles(jail_role)
        await interaction.response.send_message(f"🔓 {user.mention} has been released from jail!", ephemeral=True)
    else:
        await interaction.response.send_message(f"{user.mention} is not currently in jail.", ephemeral=True)

@bot.tree.command(name="towntransferownership", description="Transfer your town to another member")
async def transferownership(interaction: discord.Interaction, new_owner: discord.Member):
    towns = load_towns()
    user = interaction.user
    
    # Find the town the user owns
    town_name = next((name for name, town in towns.items() if user.id == town["owner_id"]), None)

    if town_name is None:
        return await interaction.response.send_message("❌ You do not own a town!", ephemeral=True)

    town = towns[town_name]

    # Verify the new owner is actually in the town
    if new_owner.id not in town["members"]:
        return await interaction.response.send_message(f"❌ {new_owner.display_name} must be a member of the town before they can own it.", ephemeral=True)

    if new_owner.id == user.id:
        return await interaction.response.send_message("You already own this town!", ephemeral=True)

    # Perform the transfer
    town["owner_id"] = new_owner.id
    save_towns(towns)

    await interaction.response.send_message(f"👑 Ownership of **{town_name}** has been transferred to {new_owner.mention}!")
    await new_owner.send(f"🏰 You are now the owner of **{town_name}**!")

@bot.tree.command(name="towndelete", description="Permanently delete your town and its role")
async def delete(interaction: discord.Interaction):
    towns = load_towns()
    user = interaction.user
    guild = interaction.guild

    # Find the town the user owns
    town_name = next((name for name, town in towns.items() if user.id == town["owner_id"]), None)

    if town_name is None:
        return await interaction.response.send_message("❌ You do not own a town to delete!", ephemeral=True)

    town_data = towns[town_name]

    # 1. Delete the role from the server
    role = guild.get_role(town_data["role_id"])
    if role:
        try:
            await role.delete(reason=f"Town {town_name} deleted by owner.")
        except discord.Forbidden:
            await interaction.channel.send("⚠️ I couldn't delete the role. Make sure my bot role is higher than the town role!")
        except discord.HTTPException:
            await interaction.channel.send("⚠️ An error occurred while trying to delete the role.")

    # 2. Remove the town from the database
    del towns[town_name]
    save_towns(towns)

    await interaction.response.send_message(f"💥 **{town_name}** has been permanently disbanded and its role has been deleted.", ephemeral=True)

### NATION COMMANDS ###
@bot.tree.command(name="nationcreate", description="Create a nation and a nation role")
# Changed 'name' to 'nation_name' below to match the function argument
@app_commands.describe(nation_name="Nation name", colour="Role colour (hex, e.g. #ff5733)")
async def nationcreate(interaction: discord.Interaction, nation_name: str, colour: str):
    towns = load_towns()
    nations = load_nations()
    user = interaction.user

    town_name = next((name for name, t in towns.items() if user.id == t["owner_id"]), None)
    if not town_name:
        return await interaction.response.send_message("❌ Only town owners can create nations!", ephemeral=True)

    # Create the Discord Role
    try:
        role = await interaction.guild.create_role(
            name=f"Nation: {nation_name}",
            colour=discord.Colour.from_str(colour),
            reason="Nation creation"
        )
    except:
        return await interaction.response.send_message("❌ Invalid hex color! Use something like #ff5733", ephemeral=True)

    await user.add_roles(role)

    nations[nation_name] = {
        "leader_id": user.id,
        "capital_town": town_name,
        "member_towns": [town_name],
        "role_id": role.id,
        "war_status": None,
        "war_target": None
    }
    
    save_nations(nations)
    await interaction.response.send_message(f"🚩 Nation **{nation_name}** founded! Role created.")

@bot.tree.command(name="nationinvite", description="Invite a town to join your nation")
async def nationinvite(interaction: discord.Interaction, target_town_name: str):
    nations = load_nations()
    towns = load_towns()
    
    # Check if sender leads a nation
    nation_name = next((name for name, n in nations.items() if interaction.user.id == n["leader_id"]), None)
    if not nation_name:
        return await interaction.response.send_message("❌ Only nation leaders can invite towns!", ephemeral=True)

    if target_town_name not in towns:
        return await interaction.response.send_message("❌ That town doesn't exist!", ephemeral=True)

    target_town = towns[target_town_name]
    
    # Check if they are already in a nation
    if any(target_town_name in n["member_towns"] for n in nations.values()):
        return await interaction.response.send_message("❌ That town is already in a nation!", ephemeral=True)

    target_owner = interaction.guild.get_member(target_town["owner_id"])
    if not target_owner:
        return await interaction.response.send_message("❌ Could not find the owner of that town.", ephemeral=True)

    # Create Buttons
    # custom_id format: naccept_NATIONNAME_TOWNNAME
    view = View()
    view.add_item(Button(label="Accept", style=discord.ButtonStyle.green, custom_id=f"naccept_{nation_name}_{target_town_name}"))
    view.add_item(Button(label="Deny", style=discord.ButtonStyle.red, custom_id=f"ndeny_{nation_name}_{target_town_name}"))

    await target_owner.send(f"🏰 **{interaction.user.display_name}** has invited your town (**{target_town_name}**) to join the nation of **{nation_name}**!", view=view)
    await interaction.response.send_message(f"📩 Invitation sent to the owner of **{target_town_name}**.", ephemeral=True)

@bot.tree.command(name="nationdisband", description="Disband your nation and delete its role")
async def nationdisband(interaction: discord.Interaction):
    nations = load_nations()
    nation_name = next((name for name, n in nations.items() if interaction.user.id == n["leader_id"]), None)

    if not nation_name:
        return await interaction.response.send_message("❌ You don't lead a nation!", ephemeral=True)

    # Delete Role
    role = interaction.guild.get_role(nations[nation_name]["role_id"])
    if role:
        await role.delete()

    del nations[nation_name]
    save_nations(nations)
    await interaction.response.send_message(f"💥 The nation of **{nation_name}** has been disbanded.")

##NATION WAR###
@bot.tree.command(name="nationdeclarewar", description="Declare war on another nation")
async def nationdeclarewar(interaction: discord.Interaction, target_nation: str):
    nations = load_nations()
    # Find which nation the user leads
    sender_nation = next((name for name, n in nations.items() if interaction.user.id == n["leader_id"]), None)

    if not sender_nation:
        return await interaction.response.send_message("❌ Only nation leaders can declare war!", ephemeral=True)

    if target_nation not in nations:
        return await interaction.response.send_message("❌ Target nation not found!", ephemeral=True)

    if target_nation == sender_nation:
        return await interaction.response.send_message("❌ You cannot declare war on yourself!", ephemeral=True)

    # Set statuses to pending
    nations[sender_nation]["war_target"] = target_nation
    nations[sender_nation]["war_status"] = "pending"
    nations[target_nation]["war_target"] = sender_nation
    nations[target_nation]["war_status"] = "pending"
    
    save_nations(nations)
    
    target_leader_id = nations[target_nation]["leader_id"]
    target_leader = await bot.fetch_user(target_leader_id)
    
    if target_leader:
        await target_leader.send(f"⚔️ **{sender_nation}** has declared war on **{target_nation}**! Use `/nationwaraccept` to begin the conflict.")

    await interaction.response.send_message(f"📡 War declaration sent to **{target_nation}**!", ephemeral=True)

@bot.tree.command(name="nationwaraccept", description="Accept a war declaration against your nation")
async def nationwaraccept(interaction: discord.Interaction):
    nations = load_nations()
    
    # 1. Find the nation the user leads
    nation_name = next((name for name, n in nations.items() if interaction.user.id == n["leader_id"]), None)

    if not nation_name:
        return await interaction.response.send_message("❌ You are not a nation leader!", ephemeral=True)

    # 2. Check if they have a pending war
    if nations[nation_name].get("war_status") != "pending":
        return await interaction.response.send_message("❌ You have no pending war declarations to accept.", ephemeral=True)

    # 3. SECURE CHECK: Did THIS nation receive the declaration?
    # We check if the target of the war is actually the nation the sender started it with
    target_nation_name = nations[nation_name].get("war_target")
    
    # In a pending state, both nations point to each other. 
    # To prevent the 'attacker' from accepting their own war, we ensure 
    # the person calling this is the one who WAS declared upon.
    
    # We look at the attacker's data to see if THEY were the ones who initiated
    # In our logic, the attacker is nations[target_nation_name]
    attacker_data = nations.get(target_nation_name)
    
    if attacker_data and attacker_data.get("leader_id") == interaction.user.id:
        return await interaction.response.send_message("❌ You cannot accept your own war declaration! You must wait for the other leader to respond.", ephemeral=True)

    # 4. Proceed with acceptance
    nations[nation_name]["war_status"] = "active"
    nations[target_nation_name]["war_status"] = "active"
    save_nations(nations)

    await interaction.response.send_message(f"⚔️ **WAR HAS BEGUN**! **{nation_name}** has accepted the challenge from **{target_nation_name}**!", ephemeral=False)

@bot.tree.command(name="nationwardeny", description="Deny a war declaration")
async def nationwardeny(interaction: discord.Interaction):
    nations = load_nations()
    nation_name = next((name for name, n in nations.items() if interaction.user.id == n["leader_id"]), None)

    if not nation_name or nations[nation_name].get("war_status") != "pending":
        return await interaction.response.send_message("❌ No pending war to deny.", ephemeral=True)

    target_nation_name = nations[nation_name].get("war_target")
    attacker_data = nations.get(target_nation_name)

    # SECURE CHECK: Prevent attacker from denying their own declaration
    if attacker_data and attacker_data.get("leader_id") == interaction.user.id:
        return await interaction.response.send_message("❌ You cannot deny your own declaration. You can only wait or use a ceasefire command if available.", ephemeral=True)

    # Clean up the war data for both
    nations[nation_name].pop("war_target", None)
    nations[nation_name].pop("war_status", None)
    nations[target_nation_name].pop("war_target", None)
    nations[target_nation_name].pop("war_status", None)
    save_nations(nations)

    await interaction.response.send_message(f"🛡️ **{nation_name}** has declined the war declaration from **{target_nation_name}**.")

# Create a temporary dictionary at the top of your script to track ceasefire requests
# ceasefire_requests = {} 

@bot.tree.command(name="nationceasefire", description="Propose or accept a ceasefire to end a nation war")
async def nationceasefire(interaction: discord.Interaction):
    nations = load_nations()
    nation_name = next((name for name, n in nations.items() if interaction.user.id == n["leader_id"]), None)

    if not nation_name:
        return await interaction.response.send_message("❌ Only nation leaders can call for a ceasefire!", ephemeral=True)

    if nations[nation_name].get("war_status") != "active":
        return await interaction.response.send_message("❌ Your nation is not currently in an active war.", ephemeral=True)

    target_nation = nations[nation_name]["war_target"]
    
    # Check if the other nation already proposed a ceasefire
    # We use the war_status 'ceasefire_offered' to track this in the JSON
    if nations[target_nation].get("war_status") == "ceasefire_requested":
        # Both agreed! End the war.
        nations[nation_name].pop("war_target", None)
        nations[nation_name].pop("war_status", None)
        nations[target_nation].pop("war_target", None)
        nations[target_nation].pop("war_status", None)
        save_nations(nations)
        
        await interaction.response.send_message(f"🏳️ **PEACE DECLARED!** Both **{nation_name}** and **{target_nation}** have agreed to a ceasefire.")
        
        # Notify the other leader
        other_leader = await bot.fetch_user(nations[target_nation]["leader_id"])
        if other_leader:
            await other_leader.send(f"🏳️ The war between **{nation_name}** and **{target_nation}** has ended by mutual agreement.")
    else:
        # First person to propose it
        nations[nation_name]["war_status"] = "ceasefire_requested"
        save_nations(nations)
        
        await interaction.response.send_message(f"📜 Ceasefire proposed to **{target_nation}**. They must also use `/nationceasefire` to accept.")
        
        other_leader = await bot.fetch_user(nations[target_nation]["leader_id"])
        if other_leader:
            await other_leader.send(f"🏳️ **{nation_name}** has proposed a ceasefire! Type `/nationceasefire` in the server to accept and end the war.")

@bot.tree.command(name="nationactivewars", description="Show all ongoing nation wars")
async def nationactivewars(interaction: discord.Interaction):
    nations = load_nations()
    embed = discord.Embed(title="⚔️ Active Nation Conflicts", color=discord.Color.red())
    
    active_wars = []
    processed_pairs = set()

    for nation_name, data in nations.items():
        if data.get("war_status") == "active":
            target = data.get("war_target")
            # Sort the pair so we don't list (A vs B) and (B vs A) separately
            pair = tuple(sorted([nation_name, target]))
            
            if pair not in processed_pairs:
                member_count = len(data.get("member_towns", []))
                target_member_count = len(nations[target].get("member_towns", []))
                active_wars.append(f"🚩 **{nation_name}** ({member_count} towns) vs **{target}** ({target_member_count} towns)")
                processed_pairs.add(pair)

    if active_wars:
        embed.description = "\n".join(active_wars)
    else:
        embed.description = "There are currently no active nation wars."

    await interaction.response.send_message(embed=embed)
##NATION OWNERSHIP CONTROL ###
@bot.tree.command(name="nationleave", description="Make your town leave its current nation")
async def nationleave(interaction: discord.Interaction):
    towns = load_towns()
    nations = load_nations()
    
    town_name = next((name for name, t in towns.items() if interaction.user.id == t["owner_id"]), None)
    if not town_name:
        return await interaction.response.send_message("❌ Only town owners can leave nations!", ephemeral=True)

    nation_name = next((name for name, n in nations.items() if town_name in n["member_towns"]), None)
    if not nation_name:
        return await interaction.response.send_message("❌ Your town isn't in a nation!", ephemeral=True)

    if nations[nation_name]["capital_town"] == town_name:
        return await interaction.response.send_message("❌ The capital town cannot leave! Disband the nation or transfer leadership first.", ephemeral=True)

    nations[nation_name]["member_towns"].remove(town_name)
    save_nations(nations)
    await interaction.response.send_message(f"🚪 **{town_name}** has left the nation of **{nation_name}**.")

@bot.tree.command(name="nationexile", description="Exile a player from a town within your nation")
@app_commands.describe(player="The player to exile")
async def nationexile(interaction: discord.Interaction, player: discord.Member):
    nations = load_nations()
    towns = load_towns()
    
    # 1. Find the nation the command user leads
    nation_name = next((name for name, n in nations.items() if interaction.user.id == n["leader_id"]), None)
    if not nation_name:
        return await interaction.response.send_message("❌ Only nation leaders can use this command!", ephemeral=True)

    # 2. Find which town the target player belongs to
    target_town_name = next((name for name, t in towns.items() if player.id in t["members"]), None)
    
    if not target_town_name:
        return await interaction.response.send_message("❌ That player is not in any town.", ephemeral=True)

    # 3. Check if that town is actually in the leader's nation
    if target_town_name not in nations[nation_name]["member_towns"]:
        return await interaction.response.send_message(f"❌ **{target_town_name}** is not part of your nation!", ephemeral=True)

    # 4. Prevent exiling the Nation Leader or the Town Owner (Safety check)
    if player.id == nations[nation_name]["leader_id"]:
        return await interaction.response.send_message("❌ You cannot exile yourself!", ephemeral=True)
    
    if player.id == towns[target_town_name]["owner_id"]:
        return await interaction.response.send_message("❌ You cannot exile a Town Owner. You must exile their entire town instead using a different method.", ephemeral=True)

    # 5. Remove the player from the town and role
    towns[target_town_name]["members"].remove(player.id)
    save_towns(towns)

    role = interaction.guild.get_role(towns[target_town_name]["role_id"])
    if role:
        try:
            await player.remove_roles(role)
        except discord.Forbidden:
            await interaction.channel.send(f"⚠️ Removed from database, but I couldn't remove the Discord role from {player.display_name}. Check role hierarchy!")

    await interaction.response.send_message(f"⚖️ **{player.display_name}** has been exiled from **{target_town_name}** by the Nation of **{nation_name}**.")
    try:
        await player.send(f"⚠️ You have been exiled from **{target_town_name}** by the leader of the nation **{nation_name}**.")
    except:
        pass
@bot.tree.command(name="nationannounce", description="Send an announcement to all towns in your nation")
async def nationannounce(interaction: discord.Interaction, message: str):
    nations = load_nations()
    towns = load_towns()
    nation_name = next((name for name, n in nations.items() if interaction.user.id == n["leader_id"]), None)

    if not nation_name:
        return await interaction.response.send_message("❌ Only nation leaders can announce!", ephemeral=True)

    for t_name in nations[nation_name]["member_towns"]:
        owner_id = towns[t_name]["owner_id"]
        owner = interaction.guild.get_member(owner_id)
        if owner:
            try:
                await owner.send(f"🚩 **{nation_name} Nation Announcement**: {message}")
            except: continue

    await interaction.response.send_message("Announcement sent to all town owners.", ephemeral=True)

@bot.tree.command(name="nationtransfer", description="Transfer leadership of the nation to another town owner")
async def nationtransfer(interaction: discord.Interaction, new_leader: discord.Member):
    nations = load_nations()
    towns = load_towns()
    nation_name = next((name for name, n in nations.items() if interaction.user.id == n["leader_id"]), None)

    if not nation_name:
        return await interaction.response.send_message("❌ You are not the nation leader!", ephemeral=True)

    # Check if new leader owns a town in the nation
    target_town = next((name for name, t in towns.items() if new_leader.id == t["owner_id"]), None)
    if not target_town or target_town not in nations[nation_name]["member_towns"]:
        return await interaction.response.send_message("❌ The new leader must be a town owner within your nation!", ephemeral=True)

    nations[nation_name]["leader_id"] = new_leader.id
    # Note: Capital stays the same as per your request
    save_nations(nations)

    await interaction.response.send_message(f"👑 **{new_leader.display_name}** is now the leader of **{nation_name}**! The capital remains **{nations[nation_name]['capital_town']}**.")

@bot.tree.command(name="nationsetcapital", description="Change the capital town of your nation")
async def nationsetcapital(interaction: discord.Interaction, new_capital: str):
    nations = load_nations()
    nation_name = next((name for name, n in nations.items() if interaction.user.id == n["leader_id"]), None)

    if not nation_name:
        return await interaction.response.send_message("❌ Only the nation leader can change the capital!", ephemeral=True)

    if new_capital not in nations[nation_name]["member_towns"]:
        return await interaction.response.send_message("❌ That town is not in your nation!", ephemeral=True)

    nations[nation_name]["capital_town"] = new_capital
    save_nations(nations)
    await interaction.response.send_message(f"🏛️ The capital of **{nation_name}** has been moved to **{new_capital}**!")

#BUG SQUASH COMMAND#
@bot.tree.command(name="bug", description="Report a bug to the developer")
@app_commands.describe(report="Describe the bug in detail")
async def bug(interaction: discord.Interaction, report: str):
    developer_id = 1357096626509975582 # <--- CHANGE THIS TO YOUR ID
    developer = await bot.fetch_user(developer_id)
    
    if developer:
        embed = discord.Embed(title="🐛 New Bug Report", color=discord.Color.orange())
        embed.add_field(name="Reporter", value=f"{interaction.user.name} ({interaction.user.id})", inline=False)
        embed.add_field(name="Server", value=interaction.guild.name if interaction.guild else "DMs", inline=False)
        embed.add_field(name="Report", value=report, inline=False)
        
        try:
            await developer.send(embed=embed)
            await interaction.response.send_message("✅ Your report has been sent to the developer. Thank you!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Failed to send report. My DMs might be closed.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Developer not found in cache.", ephemeral=True)
    

bot.run("nice try bucko")