import json
import discord
import requests
import asyncio
from flask import Flask, request
from threading import Thread
from discord.ext import commands
import random
import time

# Load config
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

token = config['token']
secret = config['secret']
client_id = config['id']
redirect = config['redirect']
api_endpoint = config['api_endpoint']
logs = config['logs']

prefix = '--'
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=prefix, intents=intents)
bot.remove_command('help')
app = Flask('web')

@app.route('/')
def index():
    return "Auth System Online. Ready to hustle."

@app.route('/done')
def authenticate():
    try:
        code = request.args.get('code')
        if not code:
            return "No code provided", 400

        data = {
            'client_id': client_id,
            'client_secret': secret,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect,
            'scope': 'identify guilds.join'
        }

        response = requests.post(f'{api_endpoint}/oauth2/token', data=data)
        response.raise_for_status()
        details = response.json()

        access_token = details['access_token']
        refresh_token = details['refresh_token']

        headers = {'Authorization': f'Bearer {access_token}'}
        user_info = requests.get(f'{api_endpoint}/users/@me', headers=headers).json()
        user_id = user_info['id']
        username = user_info.get('username', 'Unknown')

        hook_url = random.choice(logs)
        log_data = {"content": f"New Auth - User: {username} (ID: {user_id})"}
        requests.post(hook_url, json=log_data)

        with open('database.txt', 'a') as file:
            file.write(f'{user_id},{access_token},{refresh_token}\n')

        return "Authentication Successful. Welcome to the RUBINEXE  club."
    except Exception as e:
        print(f"Auth Error: {e}")
        return f"Authentication Failed: {e}", 500

def run_flask():
    app.run(host='0.0.0.0', port=5000)

def keep_alive():
    Thread(target=run_flask).start()

@bot.event
async def on_ready():
    print(f'Bot Online as {bot.user} - Time to move!')

def build_user_footer(ctx):
    avatar_url = ctx.author.avatar.url if ctx.author.avatar else None
    return (f"Requested by {ctx.author}", avatar_url)

def add_member_to_guild(guild_id, user_id, access_token):
    url = f"{api_endpoint}/guilds/{guild_id}/members/{user_id}"
    data = {"access_token": access_token}
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.put(url, headers=headers, json=data)
        return response.status_code in (201, 204)
    except Exception as e:
        print(f"Join Error: {e}")
        return False

async def fetch_username(access_token):
    headers = {'Authorization': f'Bearer {access_token}'}
    try:
        r = requests.get(f'{api_endpoint}/users/@me', headers=headers)
        if r.status_code == 200:
            return r.json()['username']
        return "Unknown"
    except:
        return "Unknown"

@bot.command(name='status')
async def status(ctx):
    embed = discord.Embed(
        title="Bot Status",
        description="✅ Bot is online and crushing it.",
        color=discord.Color.green()
    )
    footer_text, footer_icon = build_user_footer(ctx)
    embed.set_footer(text=footer_text, icon_url=footer_icon)
    await ctx.send(embed=embed)

@bot.command(name='count')
async def count(ctx):
    try:
        with open('refreshed.txt', 'r') as f:
            count = len(f.readlines())
        embed = discord.Embed(
            title="Authenticated Users Count",
            description=f"Total authenticated users: ```{count}```",
            color=discord.Color.blue()
        )
    except FileNotFoundError:
        embed = discord.Embed(
            title="Authenticated Users Count",
            description="```No users authenticated yet.```",
            color=discord.Color.red()
        )
    footer_text, footer_icon = build_user_footer(ctx)
    embed.set_footer(text=footer_text, icon_url=footer_icon)
    await ctx.send(embed=embed)

@bot.command(name='refresh')
async def refresh(ctx):
    start_time = time.time()

    def progress_bar(current, total, length=20):
        filled_len = int(length * current // total)
        bar = '█' * filled_len + '—' * (length - filled_len)
        return f"[{bar}] {current}/{total}"

    refreshed = []
    failed = []

    try:
        with open('database.txt', 'r') as f:
            lines = f.readlines()

        total = len(lines)
        if total == 0:
            embed = discord.Embed(
                title="No users to refresh",
                description="```The database is empty. Nothing to refresh.```",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author}")
            await ctx.send(embed=embed)
            return

        new_lines = []

        def build_embed(current=0):
            elapsed = int(time.time() - start_time)
            mins, secs = divmod(elapsed, 60)
            elapsed_str = f"{mins}m {secs}s"

            e = discord.Embed(
                title="🔄 Token Refresh - Live Update",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            e.description = f"Refreshing tokens for **{total}** users...\n\n"
            e.description += progress_bar(current, total) + "\n\n"

            e.add_field(name="✅ Success", value=f"```{len(refreshed)}```", inline=True)
            e.add_field(name="❌ Failed", value=f"```{len(failed)}```", inline=True)
            e.add_field(name="Remaining", value=f"```{total - current}```", inline=True)

            e.set_footer(text=f"Requested by {ctx.author} | Elapsed: {elapsed_str}")
            return e

        msg = await ctx.send(embed=build_embed(0))

        for i, line in enumerate(lines, start=1):
            try:
                user_id, _, refresh_token = line.strip().split(',')
                data = {
                    'client_id': client_id,
                    'client_secret': secret,
                    'grant_type': 'refresh_token',
                    'refresh_token': refresh_token,
                }
                headers = {'Content-Type': 'application/x-www-form-urlencoded'}
                response = requests.post(f'{api_endpoint}/oauth2/token', data=data, headers=headers)

                if response.status_code in (200, 201):
                    tokens = response.json()
                    new_access = tokens['access_token']
                    new_refresh = tokens['refresh_token']
                    new_lines.append(f'{user_id},{new_access},{new_refresh}\n')
                    refreshed.append(user_id)
                else:
                    failed.append(user_id)
                    continue  # skip failed tokens
            except Exception as e:
                print(f"Error refreshing token for user {user_id}: {e}")
                failed.append(user_id)
                continue  # skip failed tokens

            if i % 5 == 0 or i == total:
                await msg.edit(embed=build_embed(i))
                await asyncio.sleep(0.1)

        with open('database.txt', 'w') as f:
            f.writelines(new_lines)

        with open('refreshed.txt', 'w') as f:
            f.writelines(new_lines)

        total_time = int(time.time() - start_time)
        mins, secs = divmod(total_time, 60)
        time_str = f"{mins}m {secs}s"

        final_embed = discord.Embed(
            title="✔ Token Refresh Complete",
            description=f"Refreshed tokens for **{len(refreshed)}** users out of **{total}** in ```{time_str}```\nFailed refreshes: **{len(failed)}**",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        final_embed.add_field(name="✅ Success", value=f"```{len(refreshed)}```", inline=True)
        final_embed.add_field(name="❌ Failed", value=f"```{len(failed)}```", inline=True)
        final_embed.set_footer(text=f"Requested by {ctx.author} | Total processed: {total}")

        await ctx.send(embed=final_embed)

    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Error During Refresh",
            description=f"```{e}```",
            color=discord.Color.red()
        )
        error_embed.set_footer(text=f"Requested by {ctx.author}")
        await ctx.send(embed=error_embed)

@bot.command(name='pull')
async def pull(ctx, amount: int):
    start_time = time.time()

    def progress_bar(current, total, length=20):
        filled_len = int(length * current // total)
        bar = '█' * filled_len + '—' * (length - filled_len)
        return f"[{bar}] {current}/{total}"

    tries = 0
    added = 0
    failed = 0
    last_users = []

    def build_embed():
        elapsed = int(time.time() - start_time)
        mins, secs = divmod(elapsed, 60)
        elapsed_str = f"{mins}m {secs}s"

        e = discord.Embed(
            title="🔹 Pull Operation - Live Update",
            color=discord.Color.dark_blue(),
            timestamp=discord.utils.utcnow()
        )
        e.description = f"Pulling **{amount}** users into **{ctx.guild.name}**\n\n"
        e.description += progress_bar(added, amount) + "\n\n"

        e.add_field(name="Tries", value=f"```{tries}```", inline=True)
        e.add_field(name="Added", value=f"```{added}```", inline=True)
        e.add_field(name="Failed", value=f"```{failed}```", inline=True)
        if last_users:
            formatted_users = "\n".join(last_users[-10:])
            e.add_field(name="Last Added Users", value=f"```{formatted_users}```", inline=False)

        e.set_footer(text=f"Requested by {ctx.author} | Elapsed: {elapsed_str}")
        return e

    try:
        with open('refreshed.txt', 'r') as file:
            users = file.readlines()

        msg = await ctx.send(embed=build_embed())

        while added < amount and tries < amount * 3 and users:
            tries += 1
            line = random.choice(users)
            users.remove(line)
            user_id, access_token, _ = line.strip().split(',')

            success = add_member_to_guild(ctx.guild.id, user_id, access_token)
            if success:
                username = await fetch_username(access_token)
                last_users.append(f"{username} ({user_id})")
                added += 1
            else:
                failed += 1

            if tries % 5 == 0 or added == amount:
                await msg.edit(embed=build_embed())
                await asyncio.sleep(0.1)

        final_embed = discord.Embed(
            title="✔ Pull Operation Complete",
            description=f"Pulled **{added}** users into **{ctx.guild.name}** with **{failed}** failures after **{tries}** tries.",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        if last_users:
            formatted_users = "\n".join(last_users[-10:])
            final_embed.add_field(name="Last Added Users", value=f"```{formatted_users}```", inline=False)

        final_embed.set_footer(text=f"Requested by {ctx.author}")

        await ctx.send(embed=final_embed)

    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Error During Pull",
            description=f"```{e}```",
            color=discord.Color.red()
        )
        error_embed.set_footer(text=f"Requested by {ctx.author}")
        await ctx.send(embed=error_embed)

@bot.command(name='help')
async def help_command(ctx):
    embed = discord.Embed(
        title="RUBINEXE  Auth Bot Commands",
        description=(
            "```"
            f"{prefix}help - Show this message\n"
            f"{prefix}count - Show number of authenticated users\n"
            f"{prefix}refresh - Refresh all user tokens\n"
            f"{prefix}pull <amount> - Add <amount> users to your server\n"
            f"{prefix}status - Show bot status\n"
            "```"
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Requested by {ctx.author}")
    await ctx.send(embed=embed)

keep_alive()
bot.run(token)
