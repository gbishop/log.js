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

bottle.TEMPLATE_PATH.insert(0, osp.join(osp.dirname(__file__), "views"))

app = application = Bottle()

# make get_url available in all templates
def my_get_url(name, user=None, **kwargs):
    """Add user query to the url if necessary"""
    url = app.get_url(name, **kwargs)
    real_user = get_user()
    if user and user_is_me(real_user) and real_user != user:
        url = url + f"?user={user}"
    return url


bottle.SimpleTemplate.defaults["get_url"] = my_get_url


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
    elif isinstance(item, dict):
        return str({k: format(v) for k, v in item.items()})
    elif isinstance(item, (list, tuple)):
        return str([format(i) for i in item])
    else:
        return str(item)


@app.get("/log")
@with_db
@view("log")
@allow_json
def readLog(db):
    """
    Display log entries
    """
    ips = [
        item["ip"]
        for item in db.execute(
            """
            select distinct ip from logs order by ip asc
            """
        )
    ]
    days = [
        item["day"]  # .strftime("%y/%m/%d")
        for item in db.execute(
            """
            select distinct date(time) as day from logs order by time asc
            """
        )
    ]
    refs = [
        item["ref"]
        for item in db.execute(
            """
            select distinct ref from logs order by ref asc
            """
        )
    ]
    records = db.execute(
        """
        select time, ip, ref, message
        from logs
        where (ip = :ip or :ip = "All") and
              (date(time) = :day or :day = "All") and
              (ref = :ref or :ref = "All")
        """,
        {
            "ip": request.query.ip or "All",
            "day": request.query.day or "All",
            "ref": request.query.ref or "All",
        },
    ).fetchall()
    return {
        "query": request.query,
        "records": records,
        "ips": ips,
        "days": days,
        "refs": refs,
        "format": format_message,
    }


@app.route("/<filename:path>", name="static")
def serveStatic(filename):
    """
    Serve static files in development
    """
    kwargs = {"root": "."}
    return bottle.static_file(filename, **kwargs)


@app.route("/", name="static")
def index():
    """
    Serve index.html
    """
    kwargs = {"root": "."}
    return bottle.static_file("index.html", **kwargs)


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
    from livereload import Server

    bottle.debug(True)
    server = Server(StripPathMiddleware(app))
    server.watch(".", ignore=lambda p: p.endswith(".swp") or p.endswith(".db"))
    server.watch("./views/", ignore=lambda p: p.endswith(".swp") or p.endswith(".db"))
    server.serve(port=8055, host="0.0.0.0", restart_delay=1)
    # bottle.run(
    #     app=ReverseProxied(app), reloader=True, debug=True, host="0.0.0.0", port=8055,
    # )
