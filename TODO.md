# Mid-term TODO list

These are things that will likely take over an hour

- [ ] Separate and optimize CI pipelines more
  - [x] Separate the CI pipeline and use the dedicated pipelines instead
  - [ ] Speed up docker builds - make sure caching is working properly

# Long term TODO

- [ ] figure out voice listening [library](https://github.com/imayhaveborkedit/discord-ext-voice-recv)
  - [ ] check if we can capture output
  - [ ] Periodically dump data to a file which will contain the last 20 seconds of audio
- [ ] STT parsing [library](https://github.com/KoljaB/RealtimeSTT)
- [ ] SFX triggered by wakewords (make sure this is togglable)
- [ ] Really, I should stream youtube directly into the data buffer. But, I think that may result in possibly choppy audio when there's high load on the network, and this is running from my home server. So, I think fully buffering the files is better for now. I should add a status command to check which tracks the bot is currently buffering though.

