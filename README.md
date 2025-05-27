[![Coverage Status](https://coveralls.io/repos/github/wildjames/BalaamBot/badge.svg?branch=main)](https://coveralls.io/github/wildjames/BalaamBot?branch=main)

# TODO: Write a README

I got the soundbites from [here](https://drive.google.com/drive/folders/1dr2XcAQAuCPJqZQkCRKa4Aq8IDOH8ZIz)

## Setting up a bot

Follow the instructions [here](https://discordpy.readthedocs.io/en/stable/discord.html). If it helps, this is the [Discord applications page](https://discord.com/developers/applications) which will house your bot settings in the future.

## Required bot permissions

Set the bot to install only to Guilds - not to users. There are no features that would work for individuals I think.

Scopes:
 - `applications.commands`
 - `bot`

Permissions:
 - `Connect`
 - `Send Messages`
 - `Speak`
 - `Use Voice Activity`
 - `View Channels`

Priviledged Intents:
 - `Message Content Intent`


# Immediate TODO List

These are smaller jobs, that shouldn't take too long to knock down individually.

- [x] The bot shouldn't rely on a cache mapping of urls to file paths. Instead, just search the file path since they're deterministic.
- [x] When downloading youtube audio, download to `/tmp` and only move the completed file in to the audio cache when it's ready. Also, don't start a new download job for a file which is in progress. When the bot exits, cleanup should purge that directory!
- [x] Only build and push the docker image if the tests pass
- [ ] Add a cronjob to remove cached audio files that are over a week old
- [x] Report playback duration in the queue list command. Add a method to the audio mixer class to do that.
- [x] If the play command doesnt get a valid youtube url, reject it and inform the user.

# Mid-term TODO list

These are things that will likely take over an hour

- [x] Youtube playlist support
- [ ] Youtube age restricts some content, so I need to implement auth
- [ ] Allow users to search youtube for videos
- [ ] Add a way to scrub the currently playing track?
- [ ] Multiple people sending commands at once seems to not work - test
- [ ] Commands need to have guard clauses abstracted out into some discord utility functions
- [ ] Send a message when a new track starts to play
- [x] Test coverage is abysmal. Expand to cover all the stuff I've done since I last did a push on tests.


## Long term TODO

- [ ] Leave empty voice channels
- [ ] figure out voice listening [library](https://github.com/imayhaveborkedit/discord-ext-voice-recv)
  - [ ] check if we can capture output
  - [ ] Periodically dump data to a file which will contain the last 20 seconds of audio
- [ ] STT parsing [library](https://github.com/KoljaB/RealtimeSTT)
- [ ] SFX triggered by wakewords (make sure this is togglable)
- [ ] Really, I should stream youtube directly into the data buffer. But, I think that may result in possibly choppy audio when there's high load on the network, and this is running from my home server. So, I think fully buffering the files is better for now. I should add a status command to check which tracks the bot is currently buffering though.
