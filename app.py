#!/usr/bin/python3
"""
A simple system for collecting messages from javascript in the wild
"""

import bottle
from bottle import Bottle, request, template, view, response
from datetime import datetime, timedelta
from db import with_db, insert
import os.path as osp
import json
import html
import hashlib
import ipaddress

bottle.TEMPLATE_PATH.insert(0, osp.join(osp.dirname(__file__), "views"))

app = application = Bottle()


def static(filename):
    """
    Produce the path to a static file
    """
    p = osp.join("./static", filename)
    m = osp.getmtime(p)
    s = "%x" % int(m)
    u = app.get_url("static", filename=filename)
    return u + "?" + s


bottle.SimpleTemplate.defaults["static"] = static


def allow_json(func):
    """ Decorator: renders as json if requested """

    def wrapper(*args, **kwargs):
        """wrapper"""
        result = func(*args, **kwargs)
        if "application/json" in request.headers.get("Accept", "") and isinstance(
            result, dict
        ):
            return bottle.HTTPResponse(result)
        return result

    return wrapper


@app.post("/log")
@with_db
def log(db):
    """
    Accept a post and store the fields in the db
    """
    now = datetime.now()
    ip = request.remote_addr
    referrer = request.headers.get("Referer")
    insert(
        db,
        "logs",
        time=now,
        ip=ip,
        ref=referrer,
        message=request.body.getvalue().decode("utf-8"),
    )
    return "ok"


def format_message(msg):
    """
    Format the json encoded message for printing
    """
    return " ".join(format(item) for item in json.loads(msg))


def format(item):
    """
    Format a single item for printing
    """
    if isinstance(item, float):
        return "{:.3f}".format(item)
    elif isinstance(item, (dict, list, tuple)):
        return f"""<details><summary>Object</summary><pre>{html.escape(json.dumps(item, indent=2), True)}</pre></details>"""
    elif not isinstance(item, str):
        return str(item)
    else:
        return item


@app.get("/log")
@with_db
@view("log")
@allow_json
def readLog(db):
    """
    Display log entries
    """
    # compute the ETag
    nrecords = db.execute(
        """
        select count(*) as count from logs
    """
    ).fetchone()["count"]
    h = hashlib.sha256()
    for v in [
        request.query.get("ip", "All"),
        request.query.get("day", "All"),
        str(nrecords),
    ]:
        h.update(v.encode("utf-8"))
    etag = f'"{h.hexdigest()}"'
    if etag == request.headers.get("If-None-Match", "").lstrip("W/"):
        response.status = 304
        return ""
    response.headers["ETag"] = etag
    ips = sorted(
        [
            item["ip"]
            for item in db.execute(
                """
            select distinct ip from logs
            """
            )
        ],
        key=ipaddress.IPv4Address,
    )
    days = [
        item["day"]
        for item in db.execute(
            """
            select distinct date(time) as day from logs order by time asc
            """
        )
    ]
    records = db.execute(
        """
        select time, ip, ref, message
        from logs
        where (ip = :ip or :ip = "All") and
              (date(time) = :day or :day = "All")
        """,
        {"ip": request.query.ip or "All", "day": request.query.day or "All",},
    ).fetchall()
    return {
        "query": request.query,
        "records": records,
        "ips": ips,
        "days": days,
        "format": format_message,
    }


@app.route("/<filename:path>", name="static")
def serveStatic(filename):
    """
    Serve static files in development
    """
    kwargs = {"root": "."}
    return bottle.static_file(filename, **kwargs)


class ReverseProxied:
    """Wrap the application in this middleware and configure the
    front-end server to add these headers, to let you quietly bind
    this to a URL other than / and to an HTTP scheme that is
    different than what is used locally.

    In nginx:
    location ~* ^/([0-9]+) { # encoding the port number in the URI
        proxy_pass http://127.0.0.1:$1/; # forward to that port
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Scheme $scheme;
        proxy_set_header X-Script-Name /$1; # pass the port number to the app
        }

    :param app: the WSGI application

    hacked from: http://flask.pocoo.org/snippets/35/ and
    https://stackoverflow.com/questions/25106424/nginx-proxy-redirection-with-port-from-uri
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = environ.get("HTTP_X_SCRIPT_NAME", "")
        if script_name:
            environ["SCRIPT_NAME"] = script_name
            path_info = environ["PATH_INFO"]
            if path_info.startswith(script_name):
                environ["PATH_INFO"] = path_info[len(script_name) :]
            elif path_info == "/":
                environ["PATH_INFO"] = ""

        scheme = environ.get("HTTP_X_SCHEME", "")
        if scheme:
            environ["wsgi.url_scheme"] = scheme
        return self.app(environ, start_response)


class StripPathMiddleware:
    """
    Get that slash out of the request
    """

    def __init__(self, a):
        self.a = a

    def __call__(self, e, h):
        e["PATH_INFO"] = e["PATH_INFO"].rstrip("/")
        return self.a(e, h)


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 2 and sys.argv[1] == "-live":
        from livereload import Server

        bottle.debug(True)
        server = Server(StripPathMiddleware(app))
        server.watch(".", ignore=lambda p: p.endswith(".swp") or p.endswith(".db"))
        server.watch(
            "./views/", ignore=lambda p: p.endswith(".swp") or p.endswith(".db")
        )
        server.serve(port=8055, host="0.0.0.0", restart_delay=1)
    else:
        bottle.run(app, port=8055)
