# Immediate TODO List

These are smaller jobs, that shouldn't take too long to knock down individually.

- [ ] Add a cronjob to remove cached audio files that are over a week old
- [ ] too many sounds in the zip. /list_sfx gives an error because it hits the message limit
- [ ] check if sfx file exists before running it and joining channel
- [ ] sanitize sfx file names and find files with similar names
- [ ] Bots should be segregated into their own dev channels on the dev server
- [ ] Refactor the video metadata
  - [x] Store metadata in a json file, and retrieve from there. Then, get the metadata in a subprocess whenever something is added to the queue.
  - [ ] Only download the next ~10 videos metadata, since the list_queue function doesn't need more than that
  - [ ] Really, this should be a cache of some kind. Redis probably, but it's a lot of effort and I'm not sure the juice is worth the squeeze just for this.
- [ ] Create a [help command](https://discordpy.readthedocs.io/en/stable/ext/commands/api.html#help-commands)

# Mid-term TODO list

These are things that will likely take over an hour

- [x] Some things are not async enough, it seems. Downloading videos can cause playback to stutter. Break out the downloading logic to multithreading/processing?
  - [ ] tentatively solved. Needs thorough testing though
- [ ] Should we stream opus data rather than PCM?
- [ ] Youtube age restricts some content, so I need to implement auth
 - [x] Commands need to have guard clauses abstracted out into some discord utility functions
- [ ] Add a way to scrub the currently playing track?
- [ ] Separate and optimize CI pipelines more
  - [x] Separate the CI pipeline and use the dedicated pipelines instead
  - [ ] Speed up docker builds - make sure caching is working properly

# Long term TODO

- [ ] Leave empty voice channels
- [ ] figure out voice listening [library](https://github.com/imayhaveborkedit/discord-ext-voice-recv)
  - [ ] check if we can capture output
  - [ ] Periodically dump data to a file which will contain the last 20 seconds of audio
- [ ] STT parsing [library](https://github.com/KoljaB/RealtimeSTT)
- [ ] SFX triggered by wakewords (make sure this is togglable)
- [ ] Really, I should stream youtube directly into the data buffer. But, I think that may result in possibly choppy audio when there's high load on the network, and this is running from my home server. So, I think fully buffering the files is better for now. I should add a status command to check which tracks the bot is currently buffering though.
'
