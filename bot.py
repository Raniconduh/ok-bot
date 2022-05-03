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
from PIL import Image
from io import BytesIO


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


	if h: return f'{h}:{m:0>2}:{s:0>2}'
	else: return f'{m}:{s:0>2}'


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
			info = ydl.extract_info(esc_query, download=False)

	length = stotime(info.get('duration', 0)])
	title = info.get('title', 'No title')
	url = info['formats'][0]['url']

	return length, title, url


def get_summary(search):
	params = {
		"q": search,
		"format": "json"
	}

	response = requests.get(f"https://api.duckduckgo.com/?{urlencode(params)}")
	response = json.loads(response.text)
	return response


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
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


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
			msg = msg.content.strip()

		if not len(msg):
			embed = discord.Embed(title="Nothing to translate", color=0xFF0000)
			await ctx.send(embed=embed)
			print("no text")
			return

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
		will read from given arguments
		"""
		print(f'{date()} - define from "{ctx.message.author.name}" ... ', end='', flush=True)

		msg = ' '.join(args).strip().replace(' ', '%20')
		if not len(msg):
			embed = discord.Embed(title="Nothing to define", color=0xFF0000)
			await ctx.send(embed=embed)
			print("no text")
			return

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

		message = ' '.join(args).strip()
		if not len(message):
			embed = discord.Embed(title="Nothing to summarize", color=0xFF0000)
			await ctx.send(embed=embed)
			print("no text")
			return

		embed = None
		fname = None
		file = None
		async with ctx.typing():
			summ = get_summary(message)
			source = summ["AbstractSource"]
			link = summ["AbstractURL"]
			text = summ["AbstractText"]
			related = summ["RelatedTopics"]
			image = summ["Image"]

			if text:
				host = re.search(r'https?://[^/]+/?', link)[0]
				path = quote_plus(link[len(host):])
				link = host + path

				text = text[:4096 - len(link)]

				link = link.replace(')', '%29').replace('(', '%28')
				embed = discord.Embed(title=f"Summary from {source}")
				embed.description = f'{text}\n\n{link}'
				if image and summ["ImageIsLogo"]:
					embed.set_thumbnail(url=f'https://duckduckgo.com/{image}')
				elif image:
					img = requests.get(f'https://duckduckgo.com/{image}')
					img = img.content
					img = Image.open(BytesIO(img))
					ext = img.format
					img = img.resize((96, 96), resample=Image.Resampling.BILINEAR)
					fname = f'img.{ext}'
					img.save(fname)
					file = discord.File(fname)
					embed.set_image(url=f'attachment://img.{ext}')
			elif not len(related):
				embed = discord.Embed(title="No summary", color=0xFF0000)
			else:
				l = len(related)
				if l > 3: l = 3
				embed = discord.Embed(title="Related topics")
				for i in range(l):
					if not 'FirstURL' in related[i]: break
					embed.add_field(name=f"{related[i]['FirstURL']}",
							value=related[i]['Text'])

			if file:
				await ctx.send(file=file, embed=embed)
				os.remove(fname)
			else: await ctx.send(embed=embed)

		print("done")

class Music(commands.Cog):
	"""Control music playing"""

	def __init__(self, bot):
		self.bot = bot


	@commands.command(aliases=['p'])
	async def play(self, ctx: commands.Context, *args):
		"""play media"""
		print(f'{date()} - play from "{ctx.message.author.name}" ... ', end='', flush=True)

		if not ctx.message.author.voice:
			await ctx.send(embed=discord.Embed(title="You must be in a voice channel to use this command", color=0xFF0000))
			print("not in channel")
			return
		
		query = ' '.join(args).strip()
		title = ""
		guild = ctx.message.guild.id

		if not len(query):
			embed = discord.Embed(title="You must specofy something to play", color=0xFF0000)
			await ctx.send(embed=embed)
			print("nothing specified")
			return

		async with ctx.typing():
			length, title, query = get_yt_info(query)

			if not guild in voice_queue: voice_queue[guild] = []
			voice_queue[guild].append({"length": length, "title": title, "link": query, "started": -1})
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


	@commands.command(aliases=["q"])
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

		bot_info = await bot.application_info()
		nl = voice.channel.members
		for m in range(len(nl)):
			if nl[m].id == bot_info.id: del nl[m]
		if len(nl) == 0:
			await voice.disconnect()
			print("disconnected")


@bot.event
async def on_ready():
	print('Running')


bot.add_cog(General(bot))
bot.add_cog(Music(bot))
bot.run(os.getenv("DISCORD_TOKEN"))
