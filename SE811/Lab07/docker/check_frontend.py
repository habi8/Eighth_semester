#!/usr/bin/env python3
"""
Health-check the Codeface web frontend by *rendering* each app, not merely
fetching it.

An HTTP 200 on an app URL proves only that the initial HTML was served. Shiny
fills the page over a websocket afterwards, so an app whose R session dies
during render still returns 200 -- the user just sees "Disconnected from the
server". This script completes a real Shiny session per app and reports which
outputs actually came back.

Protocol notes (each of these cost a debugging cycle):

  * Shiny Server does not expose the plain runApp() endpoint /websocket/;
    sessions live at /apps/<app>/__sockjs__/<server-id>/<session-id>/.

  * The <server-id> segment must differ between sessions. It is nominally a
    SockJS load-balancing hint, but Shiny Server uses it to pick the worker
    process, so a hardcoded value pins every later session to the worker that
    claimed it first. With a constant id this script checked one app six times
    and reported the other five as healthy on that app's evidence.

  * Shiny Server wraps SockJS in its own multiplex layer: every frame is
    "<id>|<method>|<payload>"  ('o' opens a channel, 'm' carries a message).
    Sending raw Shiny JSON gets "Invalid multiplex packet received" and the
    connection is closed.

  * Shiny keeps every output observer *suspended* until the client says the
    output is on screen, by sending .clientdata_output_<id>_hidden = false in
    the init message. A real browser sends these because shiny.js enumerates
    the bound output elements in the DOM. An init that omits them yields a
    session that stays happily alive and never computes a single output -- so
    without them this script could only prove "the session opened", which is
    the weaker claim it exists to improve on.

  * Each /xhr poll returns one queued frame, and a render produces a
    recalculating/recalculated pair per output before the values arrive, so
    the poll budget has to be tens of frames, not a handful.

  * Only one poll may be in flight per session; overlapping polls get
    c[2010,"Another connection still open"]. Do not run two copies of this
    script against one server at the same time.

Usage:  python3 docker/check_frontend.py [base_url] [projectid]
"""
import json
import random
import sys
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8081"
PID = sys.argv[2] if len(sys.argv) > 2 else "2"
TIMEOUT = 60
POLLS = 60

# The shell outputs every page declares. Naming them is what un-suspends them.
OUTPUTS = ["quantarchHeader", "quantarchBreadcrumb", "quantarchContent",
           "selectpidsui", "main.panel", "selectionlistelements",
           "addWidgetDialog"]

# The details page renders whatever its widget parameter names, so it needs a
# real one; without it the page correctly reports that it has nothing to show,
# which would not exercise any rendering.
APPS = [
    ("projects", "?projectid=%s" % PID),
    ("dashboard", "?projectid=%s" % PID),
    ("details", "?projectid=%s&topic=collaboration"
                "&widget=widget.clusters.clusters,widget.clusters.summary" % PID),
    ("plots", "?projectid=%s&topic=complexity" % PID),
    ("timeseries", "?projectid=%s&topic=communication" % PID),
    ("timezones", "?projectid=%s&topic=collaboration" % PID),
]


def messages(frame):
    """Yield the Shiny messages carried by one SockJS frame."""
    if not frame.startswith("a["):
        return
    try:
        envelopes = json.loads(frame[1:])
    except ValueError:
        return
    for env in envelopes:
        parts = env.split("|", 2)
        if len(parts) != 3:
            continue
        try:
            yield json.loads(parts[2])
        except ValueError:
            continue


def session(app, search):
    """Run one Shiny session; return (status, detail)."""
    root = "%s/apps/%s/__sockjs__/%03d/%s" % (
        BASE, app, random.randint(0, 999), uuid.uuid4().hex[:12])

    def post(path, body=None):
        data = body.encode() if body else b""
        req = urllib.request.Request(root + path, data=data, method="POST",
                                     headers={"Content-Type": "text/plain"})
        return urllib.request.urlopen(req, timeout=TIMEOUT).read().decode()

    try:
        # Warm the app first: this is what makes Shiny Server spawn the R
        # worker. Without it the first SockJS poll can race the worker startup.
        urllib.request.urlopen("%s/apps/%s/%s" % (BASE, app, search),
                               timeout=TIMEOUT).read()

        # The first poll of a new session normally returns the open frame "o",
        # but a heartbeat "h" also means the session is live.
        opened = False
        first = ""
        for _ in range(3):
            first = post("/xhr")
            if first.startswith("o") or first.strip() == "h":
                opened = True
                break
        if not opened:
            return "FAIL", "SockJS session did not open (got %r)" % first[:60]

        post("/xhr_send", json.dumps(["0|o|"]))
        data = {
            ".clientdata_url_protocol": "http:",
            ".clientdata_url_hostname": "localhost",
            ".clientdata_url_port": BASE.rsplit(":", 1)[-1],
            ".clientdata_url_pathname": "/apps/%s/" % app,
            ".clientdata_url_search": search,
            ".clientdata_url_hash_initial": "",
            ".clientdata_pixelratio": 1,
            ".clientdata_allowDataUriScheme": True,
        }
        for name in OUTPUTS:
            data[".clientdata_output_%s_hidden" % name] = False
        post("/xhr_send",
             json.dumps(["0|m|" + json.dumps({"method": "init", "data": data})]))

        rendered = []
        for _ in range(POLLS):
            frame = post("/xhr").strip()
            if frame.startswith("c["):
                try:
                    reason = json.loads(frame[1:])[1]
                except Exception:                           # noqa: BLE001
                    reason = "closed"
                return "CRASH", str(reason)
            if frame == "h":
                break                                       # queue drained
            for msg in messages(frame):
                # An output that raised is reported per-output rather than by
                # killing the session, so look for it explicitly.
                if msg.get("errors"):
                    return "ERROR", "output %s failed: %s" % (
                        list(msg["errors"])[0],
                        list(msg["errors"].values())[0].get("message", "?"))
                for name in msg.get("values", {}):
                    if name not in rendered:
                        rendered.append(name)
                if msg.get("custom", {}).get("GridsterMessage") is not None \
                        and "widgets" not in rendered:
                    rendered.append("widgets")
            if len(rendered) >= 3:
                break
        if rendered:
            return "OK", "rendered " + ", ".join(rendered[:4])
        return "WARN", "session alive but produced no output"
    except urllib.error.URLError as e:
        return "FAIL", str(e)
    except Exception as e:                                  # noqa: BLE001
        return "FAIL", "%s: %s" % (type(e).__name__, e)


def main():
    print("Codeface frontend render check  --  %s  (projectid=%s)\n" % (BASE, PID))
    worst = 0
    severity = {"OK": 0, "WARN": 1, "ERROR": 2, "CRASH": 2, "FAIL": 2}
    for app, search in APPS:
        status, detail = session(app, search)
        print("  [%-5s] %-11s %s" % (status, app, detail))
        sys.stdout.flush()
        worst = max(worst, severity[status])
    print()
    print("All apps render." if worst == 0 else
          "Some apps did not render -- see /var/log/shiny-server/*.log")
    return worst


if __name__ == "__main__":
    sys.exit(main())
