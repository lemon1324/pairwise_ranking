#!/bin/sh
# Container entrypoint: drop privileges if asked, check the data folder can be
# written, then exec the server command.
set -e

DATA_DIR="${PAIRRANK_DATA_DIR:-/data}"

# Optional privilege drop, so files written to an Unraid share keep its
# nobody:users (99:100) ownership instead of landing root-owned.
#
# Opt-in: with neither PUID nor PGID set the container stays root, and so it
# does with both set to 0. Running as root is accepted only because the app
# is meant for a LAN. When just one is set, the other defaults to Unraid's
# value. The whole script is re-executed as the target user rather than just
# the final command, so the mkdir and the write probe below test exactly the
# access the app will have.
#
# There is deliberately no chown here, recursive or otherwise: the data folder
# is the user's share, shared with the desktop app, and its ownership is theirs
# to set. If the target user cannot write to it, the probe says so and stops.
if [ -z "$PUID$PGID" ]; then
    echo "Running as uid:gid $(id -u):$(id -g) (PUID and PGID unset)."
elif [ "$(id -u)" = "0" ] && [ -z "$ENTRYPOINT_PRIVDROP_DONE" ]; then
    PUID="${PUID:-99}"
    PGID="${PGID:-100}"
    if [ "$PUID" = "0" ] && [ "$PGID" = "0" ]; then
        echo "Running as root (PUID=0, PGID=0)."
    else
        if [ "$PUID" = "0" ]; then
            echo "Running as root (PUID=0) with group $PGID."
        else
            echo "Dropping privileges to $PUID:$PGID..."
        fi
        # Guards against a re-exec loop.
        ENTRYPOINT_PRIVDROP_DONE=1
        export ENTRYPOINT_PRIVDROP_DONE
        exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups --no-new-privs "$0" "$@"
    fi
fi

# Whatever path led here, the process must now be the user that was asked
# for. This also catches ENTRYPOINT_PRIVDROP_DONE set from outside, which
# would otherwise skip the drop above and leave the app running as root.
if [ -n "$PUID$PGID" ]; then
    WANT="${PUID:-99}:${PGID:-100}"
    HAVE="$(id -u):$(id -g)"
    if [ "$HAVE" != "$WANT" ]; then
        echo "Cannot start: asked to run as uid:gid $WANT but running as $HAVE." >&2
        exit 1
    fi
fi

# The usual PUID (99) has no passwd entry in this image, so give it a HOME it
# can write to.
HOME=/tmp
export HOME

# 022 by default, the usual container umask. The Unraid stack sets UMASK=000:
# there, files the container writes (.pairrank, .tmp, .bak, .v<N>.bak) must
# stay writable by the share's SMB users, or the desktop app cannot save over
# them.
umask "${UMASK:-022}"

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
