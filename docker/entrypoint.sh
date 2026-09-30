#!/bin/sh
# Container entrypoint: drop privileges if asked, check the data folder can be
# written, then exec the server command.
set -e

DATA_DIR="${PAIRRANK_DATA_DIR:-/data}"

# Optional privilege drop, so files written to an Unraid share keep its
# nobody:users (99:100) ownership instead of landing root-owned.
#
# Opt-in: with neither PUID nor PGID set the
# container stays root. The whole script is re-executed as the target user
# rather than just the final command, so the mkdir and the write probe below
# test exactly the access the app will have.
#
# There is deliberately no chown here, recursive or otherwise: the data folder
# is the user's share, shared with the desktop app, and its ownership is theirs
# to set. If the target user cannot write to it, the probe says so and stops.
if [ "$(id -u)" = "0" ] && [ -n "$PUID$PGID" ] && [ -z "$ENTRYPOINT_PRIVDROP_DONE" ]; then
    PUID="${PUID:-99}"
    PGID="${PGID:-100}"
    # Guards against a re-exec loop.
    ENTRYPOINT_PRIVDROP_DONE=1
    export ENTRYPOINT_PRIVDROP_DONE
    echo "Dropping privileges to $PUID:$PGID..."
    exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$0" "$@"
fi

# The usual PUID (99) has no passwd entry in this image, so give it a HOME it
# can write to.
HOME=/tmp
export HOME

# 000 by default: files the container writes (.pairrank, .tmp, .bak, .v<N>.bak)
# must stay writable by SMB users in `users`, or the desktop app cannot save
# over them.
umask "${UMASK:-000}"

# Create and delete a file as the user the app will run as. Fails the start
# with a readable message rather than letting the first save fail later.
# touch rather than `: >`: a failed redirection on a special builtin like `:`
# exits a POSIX shell outright, before the message below can be printed.
PROBE="$DATA_DIR/.pairrank-write-probe.$$"
if ! { mkdir -p "$DATA_DIR" && touch "$PROBE" && rm -f "$PROBE"; } 2>/dev/null; then
    echo "Cannot start: the data folder $DATA_DIR is not writable by uid:gid $(id -u):$(id -g)." >&2
    echo "Mount a folder there that this user can write to, or set PUID and PGID to its owner." >&2
    exit 1
fi

exec "$@"
