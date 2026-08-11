# webhook

Part of the wi1-bot workspace. See the repo root README.

The service exposes Prometheus metrics, including HTTP, Arr event, transcode queue,
worker lifecycle, and rescan metrics, at `GET /metrics`.

## Autobrr Arr façade

The webhook presents the small part of the Radarr and Sonarr APIs used by Autobrr's
native Arr actions and Lists. This lets Autobrr limit filters to titles monitored by Arr
and record real Arr approvals and rejection reasons instead of treating every generic
Webhook action as approved. It also combines the standard and optional 4K instances.

Create two download clients in Autobrr:

| Type | Host |
| --- | --- |
| Radarr | `http://<webhook-host>:9000/autobrr/radarr` |
| Sonarr | `http://<webhook-host>:9000/autobrr/sonarr` |

The façade does not validate `X-Api-Key`, so the API key field can be empty or an
arbitrary placeholder. If a reverse proxy requires basic authentication, configure it
in Autobrr's download-client settings. The Test button calls the façade's compatible
`system/status` endpoint.

### Lists

In Autobrr, create a Radarr or Sonarr List under **Settings → Lists**, select the façade
download client of the same type, and attach the List to the desired filters. The List
uses these endpoints:

| Type | Endpoint |
| --- | --- |
| Radarr | `GET /autobrr/radarr/api/v3/movie` |
| Sonarr | `GET /autobrr/sonarr/api/v3/series` |

By default, Autobrr writes monitored titles to the filter's **Movies/Shows** field. Turn
on **Match Releases** if the generated title patterns should instead match against the
whole release name. Autobrr's **Include Unmonitored** and **Alternate Titles** options
are also supported. Arr tag filtering is not supported by the façade.

Each List is the union of the standard and optional 4K instance of its type. A refresh
fails if any included instance is unavailable, so Autobrr keeps its last successful
filter contents instead of replacing them with an incomplete title set.

### Release actions

Use the Radarr client as the native action on movie filters and the Sonarr client on TV
filters. Do not configure an external filter or generic Webhook action. Prefer making
the Arr action the filter's only action; if other actions are necessary, put the Arr
action last so a later always-successful action cannot obscure a rejection.

Every configured Arr of the selected type evaluates the release using its own library,
monitoring, quality, custom-format, and upgrade rules. The combined result follows these
rules:

- If any Arr approves the release, Autobrr sees an approval.
- If every Arr rejects it, Autobrr sees one line per instance with that instance's reasons
  grouped into a list.
- If no Arr approves and any request fails, Autobrr sees an action error.

An approval means an Arr accepted the grab; it does not confirm that the download later
completed. Mixed per-instance outcomes remain available in the webhook's structured
logs.

Download and magnet URLs can contain tracker credentials. These endpoints are not
authenticated by the webhook, so keep them on a trusted network or protect them with a
reverse proxy.
