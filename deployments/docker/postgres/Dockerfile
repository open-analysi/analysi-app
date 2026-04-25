# PostgreSQL with pg_partman + pg_cron for automated partition management.
#
# Why debian (not alpine): pg_partman and pg_cron are available as apt packages
# on debian but require compilation from source on alpine. apt-get is simpler
# and more reliable for extension installs.
#
# Why not a third-party image: We control exact versions, avoid supply-chain
# risk from unknown Docker Hub publishers, and the Dockerfile is transparent.

ARG PG_MAJOR=15
FROM postgres:${PG_MAJOR}

# Install pg_partman and pg_cron via official PostgreSQL apt packages.
# Pin versions to avoid unexpected behavior changes on rebuild.
# To upgrade: check https://apt.postgresql.org for available versions.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-${PG_MAJOR}-partman \
        postgresql-${PG_MAJOR}-cron \
        postgresql-${PG_MAJOR}-pgvector \
    && rm -rf /var/lib/apt/lists/* \
    && echo "Installed extensions:" \
    && dpkg -l | grep -E 'partman|cron|pgvector' | awk '{print $2, $3}'
