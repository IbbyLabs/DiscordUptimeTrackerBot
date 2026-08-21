# Changelog

## [0.5.0](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/compare/v0.4.0...v0.5.0) (2026-08-21)


### Features

* **bot:** report tracked services in the presence ([bce2ea0](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/bce2ea075d13ef37bfa3c2f28d97ae6d15ae7b33))

## [0.4.0](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/compare/v0.3.0...v0.4.0) (2026-08-21)


### Features

* **alerts:** make the incident the unit rather than the service ([06528fc](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/06528fc07eaee066ccf955ca06379aaadb72d260))
* **tracker:** add /incidents for recent outage history ([a1a48d0](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/a1a48d0e59ae4c929b96897e6f48b34f5f0771f0))
* **tracker:** show active outages at the top of the board ([e5e4bc7](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/e5e4bc76293aef652f161db2807808d26c2a4b07))


### Bug Fixes

* **alerts:** count only services the payload still carries ([348d6b8](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/348d6b892bdf4bc37ae28581e6dd0aa3287b2eac))
* **tracker:** render /incidents as a chunked container ([e3c7c3c](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/e3c7c3c66f8415ec4aed1f7522ffab694761ff27))

## [0.3.0](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/compare/v0.2.0...v0.3.0) (2026-08-21)


### ⚠ BREAKING CHANGES

* drop the prefix commands and the Message Content intent

### Features

* **alerts:** announce only crossings of the down boundary ([af60d32](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/af60d3213f85b99148dfc0ae6129853e0a33125b))
* drop the prefix commands and the Message Content intent ([168e6de](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/168e6de1af3beda57445f09401cfbc9edd7c6fcb))
* **tracker:** add /status with group, host and state views ([4f96ae6](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/4f96ae6ab4f774497f9722a0cf348f4854c464b1))
* **tracker:** hide the tracker group from members without Manage Server ([657ab3c](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/657ab3ceee4a4f863689829322edbb505b910dcb))
* **tracker:** per-guild status emoji and page URL ([b068ed6](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/b068ed6d6c461338bee557387cc949898d41eb02))
* **tracker:** rate limit /tracker refresh per guild ([03d1903](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/03d1903047209949ccc103a8abc9d27c70cd6fb7))
* **tracker:** render tracker messages with Components V2 ([5ca01c3](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/5ca01c3df9b2727b965440e49294bf095ed52219))


### Bug Fixes

* **alerts:** keep maintenance out of the alert boundary ([b0ce0e6](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/b0ce0e6cf6dd6a07a8876cf08f8fd4a5a0da7a49))

## 0.2.0 - 2026-05-24

Initial tracked release changes:

- feat(uptime): add status alerts and automate releases
- chore: tighten linting and typing
- feat: bootstrap DiscordUptimeTrackerBot

# Changelog
