"""WSGI entry point for a production server (gunicorn).

``platform/app.py`` stays as it is -- it is how you run the app on a laptop,
and its ``app.run()`` starts Werkzeug's development server. This module is the
other door into the same application: gunicorn imports ``application`` from
here and serves it.

Why a separate file rather than pointing gunicorn at ``app.py``: the package
``platform/app/`` and the module ``platform/app.py`` share the name ``app``,
and Python resolves the package first, so ``gunicorn app:app`` would import
``platform/app/`` and find no ``app`` attribute on it. Naming the entry point
``wsgi`` removes the ambiguity.

The application object is identical either way -- same ``create_app()``, same
blueprints, same configuration -- so nothing about request handling changes
between development and production.
"""

from app import create_app

application = create_app()
