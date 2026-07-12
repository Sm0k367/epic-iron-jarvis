# Epic Tech AI — soundtrack

Brand / demo audio for Epic Tech AI.

## Play (recommended)

GitHub’s README often **cannot** embed `<audio>` (tags are stripped). Use:

| | Link |
|--|------|
| **Dual player page** | https://cdn.jsdelivr.net/gh/Sm0k367/epic-iron-jarvis@master/assets/audio/play.html |
| **Track 1 stream** | https://cdn.jsdelivr.net/gh/Sm0k367/epic-iron-jarvis@master/assets/audio/epic-tech-ai-edm-instrumental.mp3 |
| **Track 2 stream** | https://cdn.jsdelivr.net/gh/Sm0k367/epic-iron-jarvis@master/assets/audio/epic-tech-ai-dale-club.mp3 |

jsDelivr serves `Content-Type: audio/mpeg` with range requests so browsers can stream.
`raw.githubusercontent.com` often sends `Content-Disposition: attachment`, which breaks in-page players.

## Tracks

### 1 · EDM instrumental (3:30)

High-energy electronic / club instrumental — synths, punchy drums, ~128 BPM.

<audio controls preload="metadata" src="https://cdn.jsdelivr.net/gh/Sm0k367/epic-iron-jarvis@master/assets/audio/epic-tech-ai-edm-instrumental.mp3">
  <a href="https://cdn.jsdelivr.net/gh/Sm0k367/epic-iron-jarvis@master/assets/audio/epic-tech-ai-edm-instrumental.mp3">Play MP3</a>
</audio>

- File: [epic-tech-ai-edm-instrumental.mp3](epic-tech-ai-edm-instrumental.mp3)
- Style: instrumental EDM / house-trap energy, no vocals

### 2 · Dale club hook (3:18)

Club electronic with a rhythmic vocal hook (“Dale, le le le…”).

<audio controls preload="metadata" src="https://cdn.jsdelivr.net/gh/Sm0k367/epic-iron-jarvis@master/assets/audio/epic-tech-ai-dale-club.mp3">
  <a href="https://cdn.jsdelivr.net/gh/Sm0k367/epic-iron-jarvis@master/assets/audio/epic-tech-ai-dale-club.mp3">Play MP3</a>
</audio>

- File: [epic-tech-ai-dale-club.mp3](epic-tech-ai-dale-club.mp3)
- Style: house / electronic pop, vocal sample hook

## Local

```bash
# from repo root
python3 -m http.server 8080 --directory assets/audio
# open http://127.0.0.1:8080/play.html
```

## License / use

Provided for Epic Tech AI product demos, README, and local branding. Do not
redistribute as standalone commercial releases without rights clearance.
