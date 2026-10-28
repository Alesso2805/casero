FROM postgres:17-trixie

RUN apt-get update \
    && apt-get install --yes --no-install-recommends age rclone curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --chmod=755 infra/backup/backup.sh /usr/local/bin/casero-backup

USER postgres
ENTRYPOINT ["casero-backup"]
