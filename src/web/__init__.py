"""The web frontend: a server-rendered FastAPI application over the core.

Nothing in here may import PyQt6. The desktop app and the web app are two
frontends over the same :mod:`src.app` service layer and the same ``.pairrank``
files, and the web app has to run in a container that has no Qt in it.
"""
