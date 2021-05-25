# log.js - a super simple remote logging tool for javascript

I'm trying to debug with remote users. I banged this simple hack together to
allow me to see what happened when they ran my code.

I use the snippet in `mylog.conf` to map the `/log` path into my nginx server.

I include the `log.js` script in my Javascript code and deploy it.

Then I run `python app.py`. It soaks up the HTTP POST requests from `log.js` and
puts them in the Sqlite database.

Later I can access `/log` with my browser to poke through the messages.
