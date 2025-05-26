[![Coverage Status](https://coveralls.io/repos/github/wildjames/SwearBot/badge.svg?branch=main)](https://coveralls.io/github/wildjames/SwearBot?branch=main)

# TODO: Write a README

I got the soundbites from [here](https://drive.google.com/drive/folders/1dr2XcAQAuCPJqZQkCRKa4Aq8IDOH8ZIz)

[Add to discord link](https://discord.com/oauth2/authorize?client_id=1376213084279930940)


# Immediate TODO List

These are smaller jobs, that shouldn't take too long to knock down individually.

- [ ] The bot shouldn't rely on a cache mapping of urls to file paths. Instead, just search the file path since they're deterministic.
- [ ] When downloading youtube audio, download to `/tmp` and only move the completed file in to the audio cache when it's ready. Also, don't start a new download job for a file which is in progress. When the bot exits, cleanup should purge that directory!
- [ ] Add a cronjob to remove cached audio files that are over a week old
- [ ] Report playback duration in the queue list command, and total queue duration as well. Add a method to the audio mixer class to do that.

# Mid-term TODO list

These are things that will likely take over an hour

- [ ] Youtube playlist support
- [ ] Multiple people sending commands at once seems to not work
- [ ] Commands need to have guard clauses abstracted out into some discord utility functions
- [ ] Send a message when a new track starts to play
- [ ] Test coverage is abysmal. Expand to cover all the stuff I've done since I last did a push on tests.


## Long term TODO

- [ ] Leave empty voice channels
- [ ] figure out voice listening [library](https://github.com/imayhaveborkedit/discord-ext-voice-recv)
  - [ ] check if we can capture output
  - [ ] Periodically dump data to a file which will contain the last 20 seconds of audio
- [ ] STT parsing [library](https://github.com/KoljaB/RealtimeSTT)
- [ ] SFX triggered by wakewords (make sure this is togglable)
- [ ] Really, I should stream youtube directly into the data buffer. But, I think that may result in possibly choppy audio when there's high load on the network, and this is running from my home server. So, I think fully buffering the files is better for now. I should add a status command to check which tracks the bot is currently buffering though.
