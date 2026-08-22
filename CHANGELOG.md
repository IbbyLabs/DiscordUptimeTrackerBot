# Changelog

## [0.8.0](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/compare/v0.7.1...v0.8.0) (2026-08-22)


### Features

* **tracker:** pin the panels, and post known issues only when set ([a582102](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/a5821025cbdc03822dd1852e36dcb99cf583fd99))
* **tracker:** point transient alerts at the pinned panels ([81bfc42](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/81bfc422d7b4e38e7bfdbebed9b514a6ff421dd7))
* **tracker:** read the page's verdict, group states and section order ([2189873](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/21898730ca5201d4364158117bbdf535eff6cd8e))

## [0.7.1](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/compare/v0.7.0...v0.7.1) (2026-08-22)


### Bug Fixes

* **tracker:** fetch the incident history in one request ([b725409](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/b725409b9e181ecabe0c6648a6140322e67acb26))
* **tracker:** say how many major outages the panel leaves out ([eea7b39](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/eea7b396ff2d1aabb836ac6eb6a1d07f6a4118b1))


### Code Refactoring

* **tracker:** read the label the status page publishes ([77d32c7](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/77d32c7))

## [0.7.0](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/compare/v0.6.0...v0.7.0) (2026-08-22)


### Features

* **alerts:** drive announcements from the page's incidents ([b65605f](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/b65605f183a48d5b1768ff8af2e073e7a0a06e19))
* **tracker:** credit IbbyLabs on the board and add /about ([0c3a94f](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/0c3a94f1fe589c7a0af64b80a4293dc13cdc20c7))
* **tracker:** keep three panels current in the alert channel ([8c69aa5](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/8c69aa52f2b1962d30c668eae7983eea31f1f3dc))
* **tracker:** list the outages the status page calls major ([3479c0f](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/3479c0f98b9d65fd108967c0b3654b3a27b63a08))
* **tracker:** read incident history from the status page ([236bffa](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/236bffa68e690fd04c4874f7f4198d4a077b6caa))
* **tracker:** show how an incident went, not just when it opened ([1c6cfa3](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/1c6cfa312366465e24ebd617f0162fd4477b9238))
* **tracker:** show the status page bulletin on the board ([9145f6f](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/9145f6f78a6a96bf16520666e396b60ea850d728))


### Bug Fixes

* **alerts:** keep the suppression list on the page-driven path ([8fa072f](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/8fa072f6a5de1ab5e00da67c713b23f17f25a370))
* **alerts:** name the services still down when an incident closes ([359a427](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/359a42747faa2a520f4c130185e7d6da8f6bd5bc))
* **alerts:** take the all-clear from the status payload ([e0d104d](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/e0d104d69ae96b00c37514f2e8e221835263751b))
* **bot:** read the version release-please maintains ([6b4823a](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/6b4823a27dd542431cfcc17c2eab5ea6dd24df0d))
* **tracker:** count a bouncing service once, under Unstable ([7922081](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/7922081971e45515464410035ef9aa426a57940d))
* **tracker:** delete the panels and board when tracking stops ([afc6969](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/afc69694d5d780d6824ef7c8882bff154cbae74a))
* **tracker:** report a service that is failing as down ([7ade053](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/7ade0531b5c1f5d4af7af7da8cea4dcd4abeb22e))

## [0.6.0](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/compare/v0.5.0...v0.6.0) (2026-08-21)


### Features

* **tracker:** count unstable services on the board ([d8bb51f](https://github.com/IbbyLabs/DiscordUptimeTrackerBot/commit/d8bb51ff24a65b7e4982c8d3b9cdd7be3b771fd8))

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
