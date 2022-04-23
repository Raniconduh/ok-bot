import discord
from discord.ext import commands
import os
import json
import time
import requests
from urllib.parse import urlencode, quote_plus
import re
import asyncio
import youtube_dl

ydl_opts = {
	'format': 'bestaudio',
}

voice_queue = {}


### General Functions ###
def date():
	return time.strftime("%m/%d/%Y, %H:%M:%S")


def stotime(seconds):
	s = int(seconds) % 60
	m = int(seconds // (60)) % 60
	h = int(seconds // (60 * 60))

	if h: return f'{h}:{m}:{s}'
	else: return f'{m}:{s}'


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

	info = {}
	with youtube_dl.YoutubeDL(ydl_opts) as ydl:
		# search for video
		if not re.match(r'^https?://.+', query):
			info = ydl.extract_info(f'ytsearch1:{esc_query}', download=False)
			info = info['entries'][0]
		# play directly
		else:
			info = ydl.extract_info(repr(esc_query), download=False)

	length = stotime(info['duration'])
	title = info['title']
	url = info['formats'][0]['url']

	return length, title, url


def get_summary(search):
	params = {
		"q": search,
		"format": "json"
	}

	response = requests.get(f"https://api.duckduckgo.com/?{urlencode(params)}")
	response = json.loads(response.text)

	return response["AbstractSource"], response["AbstractURL"], response["AbstractText"], response["RelatedTopics"]


async def start_next_queue(ctx, voice_client):
	global voice_queue

	guild = ctx.message.guild.id

	if len(voice_queue[guild]) == 1:
		await ctx.send(embed=discord.Embed(title="Queue empty"))

		if voice_client:
			voice_client.stop()
			await voice_client.disconnect()

		voice_queue[guild] = []
		return

	voice_queue[guild] = voice_queue[guild][1:]
	if not len(voice_queue[guild]): return

	if not voice_client.is_connected():
		channel = ctx.message.author.voice.channel
		voice = discord.utils.get(ctx.guild.voice_channels, name=channel.name)
		voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
		voice.connect()
	

	audio_source = discord.FFmpegPCMAudio(voice_queue[guild][0]["link"])
	voice_client.play(audio_source, after=lambda _: ctx.bot.loop.create_task(start_next_queue(ctx, voice_client)))
	voice_queue[guild][0]["started"] = int(time.time())

	embed = discord.Embed(title="Now Playing")
	embed.add_field(name="Title", value=voice_queue[guild][0]["title"])
	embed.add_field(name="Duration", value=voice_queue[guild][0]["length"])
	await ctx.send(embed=embed)


### Discord Functions ###
bot = commands.Bot(command_prefix="!")


class General(commands.Cog):
	"""General commands"""

	def __init__(self, bot):
		self.bot = bot


	@commands.command(name="translate", aliases=["t"])
	async def translate(self, ctx: commands.Context, *args):
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


		async with ctx.typing():
			msg = gtranslate(msg)
			msg = re.sub("<@[!#$%^&*]?([0-9]+)>", "@-", msg)

			embed = discord.Embed()
			embed.add_field(name='** **', value=f'{gtranslate(msg)}')
			await ctx.send(msg)

		print("done")


	@commands.command(name="define", aliases=["d"])
	async def define(self, ctx: commands.Context, *args):
		"""
		define a word
		will read from reply or given arguments
		"""
		print(f'{date()} - define from "{ctx.message.author.name}" ... ', end='', flush=True)

		if not ctx.message.reference:
			msg = ' '.join(args).strip().replace(' ', '%20')
		else:
			msg = await ctx.fetch_message(ctx.message.reference.message_id)

		msg = re.sub("<@[!#$%^&*]?([0-9]+)>", "@-", msg)

		async with ctx.typing():
			response = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote_plus(msg)}")
			response = json.loads(response.text)

		if "title" in response and response["title"].lower() == "no definitions found":
			embed = discord.Embed(title="Word does not exist", color=0xFF0000)
			await ctx.send(embed=embed)
			print("word does not exist")
			return


		word = response[0]["word"]
		if "phonetic" in response[0]:
			phonetic = "*" + response[0]["phonetic"] + "*"
		elif len(response[0]["phonetics"]) > 1:
			phonetic = response[0]["phonetics"]
			if len(phonetic) > 1: phonetic = phonetic[1]
			if "text" in phonetic and len(phonetic["text"]) > 1:
				phonetic = "*" + phonetic["text"] + "*"
			else: phonetic = ""
		elif len(response[0]["phonetics"]) > 0:
			phonetic = response[0]["phonetics"]
			if len(phonetic): phonetic = phonetic[0]
			if "text" in phonetic and len(phonetic["text"]) > 1:
				phonetic = "*" + phonetic["text"] + "*"
			else: phonetic = ""
		else:
			phonetic = ""

		embed = discord.Embed(title=f'{word} {phonetic}')

		n = 1
		for meaning in response[0]["meanings"]:
			embed.add_field(name=f'{n}. {meaning["partOfSpeech"]}', value=meaning["definitions"][0]["definition"])
			n += 1

		await ctx.send(embed=embed)
		print("done")


	@commands.command(aliases=["a"])
	async def avatar(self, ctx: commands.Context, *, member: discord.Member = None):
		"""get a user's avatar"""
		print(f'{date()} - avatar from "{ctx.message.author.name}" ... ', end='', flush=True)
		if not member:
			if ctx.message.reference:
				member = await ctx.fetch_message(ctx.message.reference.message_id)
				member = member.author
			else:
				member = ctx.message.author
		avatar = member.avatar_url

		embed = discord.Embed(title=f"Avatar for {member.name}#{member.discriminator}")
		embed.set_image(url=avatar)

		await ctx.send(embed=embed)
		print("done")


	@commands.command(aliases=["s"])
	async def summarize(self, ctx: commands.Context, *args):
		"""
		get a summary of a term or phrase
		gets result from Wikipedia or, if not found, performs a duckduckgo search and returns related topics
		"""
		print(f'{date()} - summarize from "{ctx.message.author.name}" ... ', end='', flush=True)

		message = ' '.join(args)

		async with ctx.typing():
			source, link, text, related = get_summary(message)

			embed = None
			if text:
				host = re.search(r'https?://[^/]+/?', link)[0]
				path = quote_plus(link[len(host):])
				link = host + path

				text = text[:4096 - len(link)]

				link = link.replace(')', '%29').replace('(', '%28')
				embed = discord.Embed(title=f"Summary from {source}")
				embed.description = f'{text}\n\n{link}'
			elif not len(related):
				embed = discord.Embed(title="No summary", color=0xFF0000)
			else:
				l = len(related)
				if l > 3: l = 3
				embed = discord.Embed(title="Related topics")
				for i in range(l):
					embed.add_field(name=f"{related[i]['FirstURL']}",
							value=related[i]['Text'])

			await ctx.send(embed=embed)

		print("done")

class Music(commands.Cog):
	"""Control music playing"""

	def __init__(self, bot):
		self.bot = bot


	@commands.command(aliases=['p'])
	async def play(self, ctx: commands.Context, *args):
		"""play media"""
		query = ' '.join(args)

		print(f'{date()} - play from "{ctx.message.author.name}" ... ', end='', flush=True)

		if not ctx.message.author.voice:
			await ctx.send(embed=discord.Embed(title="You must be in a voice channel to use this command", color=0xFF0000))
			print("not in channel")
			return
		
		title = ""
		guild = ctx.message.guild.id

		async with ctx.typing():
			length, title, query = get_yt_info(query)

			if not guild in voice_queue: voice_queue[guild] = []
			voice_queue[guild].append({"length": length, "title": title[:-1], "link": query, "started": -1})
			if len(voice_queue[guild]) > 1:
				print("added to queue")
				embed = discord.Embed(title="Added to queue")
				embed.add_field(name="Title", value=title)
				await ctx.send(embed=embed)
				return

			# get voice channel
			channel = ctx.message.author.voice.channel
			voice = discord.utils.get(ctx.guild.voice_channels, name=channel.name)
			voice_client = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
			# connect to voice channel
			if voice_client == None:
				voice_client = await voice.connect()
			else:
				await voice_client.move_to(channel)

			# play audio
			audio_source = discord.FFmpegPCMAudio(query)
			voice_client.play(audio_source, after=lambda _: ctx.bot.loop.create_task(start_next_queue(ctx, voice_client)))
			voice_queue[guild][0]["started"] = int(time.time())

			embed = discord.Embed(title="Now Playing")
			embed.add_field(name="Title", value=voice_queue[guild][0]["title"])
			embed.add_field(name="Duration", value=voice_queue[guild][0]["length"])
			await ctx.send(embed=embed)

		print("done")


	@commands.command()
	async def stop(self, ctx: commands.Context):
		"""stop playing media"""
		global voice_queue

		print(f'{date()} - stop from "{ctx.message.author.name}" ... ', end='', flush=True)

		if not ctx.message.author.voice:
			await ctx.send(embed=discord.Embed(title="You must be in a voice channel to use this command", color=0xFF0000))
			print("not in channel")
			return

		guild = ctx.message.guild.id

		if not guild in voice_queue or not len(voice_queue[guild]):
			await ctx.send(embed=discord.Embed(title="Nothing is playing", color=0xFF0000))
			print("nothing playing")
			return

		async with ctx.typing():
			channel = ctx.message.author.voice.channel
			voice_client = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)

			voice_client.stop()
			await voice_client.disconnect()
		
		voice_queue[guild] = []

		await ctx.send(embed=discord.Embed(title="Stopped playing"))

		print("done")


	@commands.command()
	async def queue(self, ctx: commands.Context):
		"""Show current audio queue"""
		print(f'{date()} - queue from "{ctx.message.author.name}" ... ', end='', flush=True)

		guild = ctx.message.guild.id

		if not guild in voice_queue or len(voice_queue[guild]) < 2:
			await ctx.send(embed=discord.Embed(title="Empty queue"))
			print("done")
			return

		embed = discord.Embed(title="Queue")
		n = 1
		for item in voice_queue[guild][1:]:
			embed.add_field(name=f"{n}.", value=item["title"], inline=True)
			n += 1
		await ctx.send(embed=embed)

		print("done")


	@commands.command()
	async def skip(self, ctx: commands.Context):
		"""skip whatever is currently playing"""

		print(f'{date()} - skip from "{ctx.message.author.name}" ... ', end='', flush=True)

		if not ctx.message.author.voice:
			await ctx.send(embed=discord.Embed(title="You must be in a voice channel to use this command", color=0xFF0000))
			print("not in channel")
			return

		channel = ctx.message.author.voice.channel
		voice_client = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
		voice_client.stop()

		print("done")


	@commands.command(aliases=["now"])
	async def np(self, ctx: commands.Context):
		"""view currently playing audio information"""
		print(f'{date()} - np from "{ctx.message.author.name}" ... ', end='', flush=True)

		guild = ctx.message.guild.id

		if not guild in voice_queue or not len(voice_queue[guild]):
			await ctx.send(embed=discord.Embed(title="Nothing is playing"))
			print("nothing playing")
			return

		title = voice_queue[guild][0]["title"]
		length = voice_queue[guild][0]["length"]

		played = time.time() - voice_queue[guild][0]["started"]
		played = stotime(played)

		embed = discord.Embed(title="Now Playing")
		embed.add_field(name="Title", value=title, inline=True)
		embed.add_field(name="Progress", value=f'{played}/{length}', inline=True)

		await ctx.send(embed=embed)

		print("done")


	@bot.event
	async def on_voice_state_update(self, before: discord.VoiceState, after: discord.VoiceState):
		print(f'{date()} - voice state update" ... ', end='', flush=True)

		guild = getattr(before.channel, 'guild', None)
		if guild is None:
			print("no guild or channel")
			return

		voice = guild.voice_client
		if voice is None or not voice.is_connected():
			print("not connected to voice")
			return
		if len(voice.channel.members) == 1:
			await voice.disconnect()
			print("disconnected")


@bot.event
async def on_ready():
	print('Running')


bot.add_cog(General(bot))
bot.add_cog(Music(bot))
bot.run(os.getenv("DISCORD_TOKEN"))
