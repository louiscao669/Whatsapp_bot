"""WSGI entry point for a production server (gunicorn).

``platform/app.py`` stays as it is -- it is how you run the app on a laptop,
and its ``app.run()`` starts Werkzeug's development server. This module is the
other door into the same application: gunicorn imports ``application`` from
here and serves it.

The separate module gives Gunicorn an unambiguous production entrypoint while
``app.py`` remains the local-development launcher.

The application object is identical either way -- same ``create_app()``, same
blueprints, same configuration -- so nothing about request handling changes
between development and production.
"""

from backend import create_app

application = create_app()
