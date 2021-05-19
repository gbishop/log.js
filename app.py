#!/usr/bin/python3
"""
A simple system for collecting messages from javascript in the wild
"""

import bottle
from bottle import Bottle, request, template, view, response
from datetime import datetime, timedelta
from db import with_db, insert
import os.path as osp

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


@app.route("/static/<filename:path>", name="static")
def serveStatic(filename):
    """
    Serve static files in development
    """
    kwargs = {"root": "./static"}
    if filename.endswith(".sqlite"):
        kwargs["mimetype"] = "application/octet-stream"
    # fake up errors for testing
    # import random
    # if random.random() < 0.5:
    #     return bottle.HTTPError(404, 'bogus')
    return bottle.static_file(filename, **kwargs)


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
    bottle.run(
        app=ReverseProxied(app), reloader=True, debug=True, host="0.0.0.0", port=8055,
    )
