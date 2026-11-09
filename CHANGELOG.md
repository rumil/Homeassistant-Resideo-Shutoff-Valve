# Changelog

All notable changes to this integration are documented here. The format is
loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0]

### Fixed

- **Entities no longer get stuck on stale data after an authentication failure.**
  When the Honeywell/Resideo token endpoint failed during a token refresh, the
  error escaped as Home Assistant's `OAuth2TokenRequestReauthError`, which the
  `DataUpdateCoordinator` handles by flipping `last_update_success` to `False`
  but returning *before* notifying entity listeners — and it stops polling. The
  result was that every entity (including the connectivity binary sensors) kept
  its last value indefinitely until the integration was manually reloaded,
  defeating any `unavailable`-based alerting. Token validation now runs inside
  the client's error mapping, so an auth failure surfaces as a normal
  `ConfigEntryAuthFailed`/`UpdateFailed` and all entities go `unavailable` on the
  same refresh, staying so until data is fetched successfully again.

### Changed

- **Single-flight token refresh.** Forced refreshes (after a premature `401`/
  `403`) now go through the same lock as expiry-based refreshes, so two callers
  — e.g. a valve command running during a coordinator poll — can no longer
  refresh concurrently. Before forcing a refresh, the client checks whether the
  access token was already refreshed by another caller and, if so, retries with
  the current token instead of making a second (racing) token request. This
  guards against refresh-token rotation invalidating the grant.
- **Transient vs. permanent token errors.** Only a clearly dead grant
  (`invalid_grant`, `invalid_client`, or HTTP `401`) escalates to reauth
  immediately. Other `4xx`, `5xx` and network errors are treated as transient:
  entities go `unavailable` but polling continues and recovers on its own. If
  transient failures persist for more than 15 minutes, the integration escalates
  to reauth so a stuck token endpoint still reaches the user.

### Added

- Token-endpoint errors now log the response body's `error` and
  `error_description` at WARNING level (never tokens, the client secret or auth
  headers).
- A pytest test suite covering the auth-failure, concurrency and
  transient/permanent classification behaviour, plus a CI job to run it.
