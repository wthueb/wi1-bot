# Changelog

## [4.2.2](https://github.com/wthueb/wi1-bot/compare/v4.2.1...v4.2.2) (2026-07-17)


### Bug Fixes

* remove invalid characters from add-tag/!addtag ([7d23567](https://github.com/wthueb/wi1-bot/commit/7d235679fbff60e8dbe42b83cae3223447ace3c6))

## [4.2.1](https://github.com/wthueb/wi1-bot/compare/v4.2.0...v4.2.1) (2026-07-17)


### Bug Fixes

* debug logs for ignored known event types ([01d2c13](https://github.com/wthueb/wi1-bot/commit/01d2c13d5844db509aa7943a7b124f70fc9f2567))
* ignore On Import Complete events ([9917a32](https://github.com/wthueb/wi1-bot/commit/9917a3296c22ed31478f067b1ce7cf507c66ecf5))

## [4.2.0](https://github.com/wthueb/wi1-bot/compare/v4.1.0...v4.2.0) (2026-07-16)


### Features

* display downloaded/monitored state in `!addmovie` / `!addshow` ([#15](https://github.com/wthueb/wi1-bot/issues/15)) ([249dc22](https://github.com/wthueb/wi1-bot/commit/249dc2224ca16c5fb470f36d8f69c874e8869086))

## [4.1.0](https://github.com/wthueb/wi1-bot/compare/v4.0.2...v4.1.0) (2026-07-16)


### Features

* define heartbeat interval and missed heartbeats on webhook ([2d9c7da](https://github.com/wthueb/wi1-bot/commit/2d9c7da62c8e3e4c72ef69c5e8cd59481e8031c0))


### Bug Fixes

* transcode queue ids properly autoincrement, never duplicating ([3be995f](https://github.com/wthueb/wi1-bot/commit/3be995f9ec1d0b7bd1857e43abbb2b933e20ee78))

## [4.0.2](https://github.com/wthueb/wi1-bot/compare/v4.0.1...v4.0.2) (2026-07-16)


### Bug Fixes

* log job and worker ids in transcode process ([d929ff3](https://github.com/wthueb/wi1-bot/commit/d929ff32b4cdc9f71e2b367ad5a956d7ee25e085))

## [4.0.1](https://github.com/wthueb/wi1-bot/compare/v4.0.0...v4.0.1) (2026-07-16)


### Bug Fixes

* create log dir if it doesn't exist ([6a0984a](https://github.com/wthueb/wi1-bot/commit/6a0984a3f1540d5cc55b21bbdfb8b79f1ed28cfc))

## [4.0.0](https://github.com/wthueb/wi1-bot/compare/v3.7.0...v4.0.0) (2026-07-16)


### ⚠ BREAKING CHANGES

* split bot, webhook, and transcoder into their own separate services/images
* rename main -> master

### Bug Fixes

* cleanup log fields for better cardinality ([3ff434f](https://github.com/wthueb/wi1-bot/commit/3ff434fffa814fb29a303f3b1fe92f3b4b10f595))


### Miscellaneous Chores

* rename main -&gt; master ([96a0ed0](https://github.com/wthueb/wi1-bot/commit/96a0ed005fa7f71f07302e614179946d0bd70e76))


### Code Refactoring

* split bot, webhook, and transcoder into their own separate services/images ([18c9964](https://github.com/wthueb/wi1-bot/commit/18c99640eeac082eb273e3c0a3fb1fe3de94972b))

## [3.7.0](https://github.com/wthueb/wi1-bot/compare/v3.6.0...v3.7.0) (2026-07-10)


### Features

* add configurable log format (logfmt or json) ([77e0bdd](https://github.com/wthueb/wi1-bot/commit/77e0bddf24ae85d0d3225893263e885b384e0d72))

## [3.6.0](https://github.com/wthueb/wi1-bot/compare/v3.5.0...v3.6.0) (2026-07-10)


### Features

* keep original language audio/subtitles when transcoding ([a190c53](https://github.com/wthueb/wi1-bot/commit/a190c538ee4be8dadfc10eb35bfb24853ea929c5))
* try optional fallback transcoding parameters if initial transcode fails ([892db5d](https://github.com/wthueb/wi1-bot/commit/892db5d0c1916ae51e63fe66b67e8613d62a06a3))


### Bug Fixes

* make hwaccel per-profile instead of global ([0e099ba](https://github.com/wthueb/wi1-bot/commit/0e099ba1fa90ac64e4b2435dd09f772e51a8c336))

## [3.5.0](https://github.com/wthueb/wi1-bot/compare/v3.4.0...v3.5.0) (2026-07-06)


### Features

* add log line for remaining transcode queue count ([131bb05](https://github.com/wthueb/wi1-bot/commit/131bb05a7bc074cd6b319ea58a45a5fc4a0fe92a))
* push downloads to 4k instances ([8081a56](https://github.com/wthueb/wi1-bot/commit/8081a568cd0d5947207100c9bdf9e3522c9835f1))

## [3.4.0](https://github.com/wthueb/wi1-bot/compare/v3.3.0...v3.4.0) (2026-06-18)


### Features

* allow quota users to be grouped ([70a864a](https://github.com/wthueb/wi1-bot/commit/70a864a395533fc6fbc1af765e30e91dad151479))

## [3.3.0](https://github.com/wthueb/wi1-bot/compare/v3.2.0...v3.3.0) (2026-05-16)


### Features

* remove pushover download notifications ([a4a99c2](https://github.com/wthueb/wi1-bot/commit/a4a99c29fe26d668a59f7780eb63ea36f17a401b))
