# TODO: Write a README

I got the soundbites from [here](https://drive.google.com/drive/folders/1dr2XcAQAuCPJqZQkCRKa4Aq8IDOH8ZIz)


# TODO List

 - [x] ffmpeg REALLY doesn't like long videos, and hangs indefinitely. Fix.
 - [x] Add skip command for youtube queue
 - [x] Add clearqueue command for youtube
 - [x] Parse youtube URLs into video titles
 - [ ] Send a message when a new track starts to play
 - [ ] Add a crontab to remove cached audio files that are over a week old
 - [ ] Youtube playlist support
 - [ ] figure out voice listening [library](https://github.com/imayhaveborkedit/discord-ext-voice-recv)
 - [ ] STT parsing [library](https://github.com/KoljaB/RealtimeSTT)
 - [ ] SFX triggered by wakewords (make sure this is togglable)


[Add to discord link](https://discord.com/oauth2/authorize?client_id=1376213084279930940)


## Long term TODO

 - [ ] Really, I should stream youtube directly into the data buffer. But, I think that may result in possibly choppy audio when there's high load on the network, and this is running from my home server. So, I think fully buffering the files is better for now. I should add a status command to check which tracks the bot is currently buffering though.
