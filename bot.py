import discord
from discord.ext import commands
import os
import json
import time
import requests
from urllib.parse import urlencode, quote_plus
import re
import asyncio


voice_queue = []


### General Functions ###
def date():
	return time.strftime("%m/%d/%Y, %H:%M:%S")


def gtranslate(text):
	params = {
		"engine": "google",
		"from": "auto",
		"to": "en",
		"text": text
	}

	response = requests.get(f"https://simplytranslate.org/api/translate?{urlencode(params)}")
	response = json.loads(response.text)
	return response["translated-text"]


def get_yt_info(query):
	esc_query = query.replace("'", "\\'")
	# search for video
	if not re.match(r'^https?://.+', query):
		u = os.popen(f"youtube-dl --get-duration -seg --extract-audio --audio-quality 0 'ytsearch1:{esc_query}'")
	# play directly
	else:
		u = os.popen(f"youtube-dl --get-duration -seg --extract-audio --audio-quality 0 '{repr(esc_query)}'")

	query = u.readlines()
	u.close()
	
	length = query[-1]
	title = query[0]
	query = query[1]

	return length, title, query


async def start_next_queue(ctx, voice_client):
	global voice_queue

	if len(voice_queue) == 1:
		await ctx.send(f'Queue empty')

		if voice_client:
			voice_client.stop()
			await voice_client.disconnect()

		voice_queue = []
		return
	
	if not voice_client.is_connected():
		channel = ctx.message.author.voice.channel
		voice = discord.utils.get(ctx.guild.voice_channels, name=channel.name)
		voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
		voice.connect()
	
	voice_queue = voice_queue[1:]
	audio_source = discord.FFmpegPCMAudio(voice_queue[0]["link"])
	voice_client.play(audio_source, after=lambda _: (await start_next_queue(ctx, voice_client) for _ in '_').__anext__())
	voice_queue[0]["started"] = int(time.time())

	await ctx.send(f'Playing {voice_queue[0]["title"]}')


### Discord Functions ###
bot = commands.Bot(command_prefix="!")


@bot.event
async def on_ready():
	print('Running')


@bot.command(name="translate", aliases=["t"])
async def translate(ctx: commands.Context, *args):
	"""
	translate text to english
	takes a reply or text as arguments
	"""
	print(f'{date()} - translate from "{ctx.message.author.name}" ... ', end='', flush=True)

	if not ctx.message.reference:
		msg = ' '.join(args).strip()
	else:
		msg = await ctx.fetch_message(ctx.message.reference.message_id)
		msg = msg.content

	async with ctx.message.channel.typing():
		await ctx.send(gtranslate(msg))

	print("done")


@bot.command(name="define", aliases=["d"])
async def define(ctx: commands.Context, *args):
	"""
	define a word
	will read from reply or given arguments
	"""
	print(f'{date()} - define from "{ctx.message.author.name}" ... ', end='', flush=True)

	if not ctx.message.reference:
		msg = ' '.join(args).strip().replace(' ', '%20')
	else:
		msg = await ctx.fetch_message(ctx.message.reference.message_id)

	async with ctx.message.channel.typing():
		response = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote_plus(msg)}")
		response = json.loads(response.text)

	if "title" in response and response["title"].lower() == "no definitions found":
		await ctx.send("This word doesn't exist")
		print("word does not exist")
		return


	word = response[0]["word"]
	if "phonetic" in response[0]:
		phonetic = "*" + response[0]["phonetic"] + "*"
	elif len(response[0]["phonetics"]) > 1:
		phonetic = "*" + response[0]["phonetics"][1]["text"] + "*"
	elif len(response[0]["phonetics"]) > 0:
		phonetic = "*" + response[0]["phonetics"][0]["text"] + "*"
	else:
		phonetic = ""
	meanings = ""
	n = 1
	for meaning in response[0]["meanings"]:
		meanings += f'{n}. {meaning["partOfSpeech"]}\n   {meaning["definitions"][0]["definition"]}\n\n'
		n += 1
	await ctx.send(f'**{word}**	{phonetic}\n{meanings}')

	print("done")


@bot.command(name="avatar")
async def avatar(ctx: commands.Context, *, member: discord.Member = None):
	"""get a user's avatar"""
	print(f'{date()} - avatar from "{ctx.message.author.name}" ... ', end='', flush=True)
	if not member:
		if ctx.message.reference:
			member = await ctx.fetch_message(ctx.message.reference.message_id)
			member = member.author
		else:
			member = ctx.message.author
	avatar = member.avatar_url
	await ctx.send(avatar)
	print("done")


@bot.command(aliases=['p'])
async def play(ctx: commands.Context, *args):
	"""play media"""
	query = ' '.join(args)

	print(f'{date()} - play from "{ctx.message.author.name}" ... ', end='', flush=True)
	if not ctx.message.author.voice:
		await ctx.send("You must be in a voice channel to use this command")
		print("not in channel")
		return
	
	title = ""

	async with ctx.message.channel.typing():
		length, title, query = get_yt_info(query)

		voice_queue.append({"length": length, "title": title[:-1], "link": query, "started": -1})
		if len(voice_queue) > 1:
			print("added to queue")
			await ctx.send(f'{title} added to queue')
			return

		# get voice channel
		channel = ctx.message.author.voice.channel
		voice = discord.utils.get(ctx.guild.voice_channels, name=channel.name)
		voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
		# connect to voice channel
		if voice_client == None:
			voice_client = await voice.connect()
		else:
			await voice_client.move_to(channel)

		# play audio
		audio_source = discord.FFmpegPCMAudio(query)
		voice_client.play(audio_source, after=lambda _: (await start_next_queue(ctx, voice_client) for _ in '_').__anext__())
		voice_queue[0]["started"] = int(time.time())
		await ctx.send(f'Playing {title}')

	print("done")


@bot.command()
async def stop(ctx: commands.Context):
	"""stop playing media"""
	global voice_queue

	print(f'{date()} - stop from "{ctx.message.author.name}" ... ', end='', flush=True)

	if not len(voice_queue):
		await ctx.send("Nothing is playing")
		print("nothing playing")
		return

	async with ctx.message.channel.typing():
		channel = ctx.message.author.voice.channel
		voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

		voice_client.stop()
		await voice_client.disconnect()
	
	voice_queue = []

	await ctx.send("Stopped playing")

	print("done")


@bot.command()
async def queue(ctx: commands.Context):
	"""Show current audio queue"""
	print(f'{date()} - queue from "{ctx.message.author.name}" ... ', end='', flush=True)

	if len(voice_queue) < 2:
		await ctx.send("Empty queue")
		return
	msg = ""
	for item in voice_queue[1:]:
		msg += item["title"] + '\n'
	await ctx.send(f"Queue:\n{msg}")

	print("done")


@bot.command()
async def skip(ctx: commands.Context):
	"""skip whatever is currently playing"""
	print(f'{date()} - skip from "{ctx.message.author.name}" ... ', end='', flush=True)

	channel = ctx.message.author.voice.channel
	voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
	voice_client.stop()
	await start_next_queue(ctx, voice_client)

	print("done")


@bot.command(aliases=["now"])
async def np(ctx: commands.Context):
	"""view currently playing audio information"""
	print(f'{date()} - np from "{ctx.message.author.name}" ... ', end='', flush=True)

	title = voice_queue[0]["title"]
	length = voice_queue[0]["length"]

	played = time.time() - voice_queue[0]["started"]
	s = int(played) % 60
	m = int(played // (60)) % 60
	h = int(played // (60 * 60))
	
	if h: played = f'{h}:{m}:{s}'
	else: played = f'{m}:{s}'

	embed = discord.Embed(title="Now Playing")
	embed.add_field(name="Title", value=title, inline=True)
	embed.add_field(name="Progress", value=f'{played}/{length}', inline=True)

	await ctx.send(embed=embed)

	print("done")

bot.run(os.getenv("DISCORD_TOKEN"))
