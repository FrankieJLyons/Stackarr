FROM ghcr.io/seerr-team/seerr@sha256:27602401178d54f1964442287b9f23f67a3fa2252645ee8065839ea1c3f69e45 AS frontend
USER root
ENV NEXT_TELEMETRY_DISABLED=1
RUN CI=true corepack pnpm install --prod=false --frozen-lockfile --ignore-scripts
COPY permissions.cjs patch.cjs setup-patch.cjs plex-login.ts plex-callback.tsx upstream.lock.json LICENSE-Seerr Dockerfile /usr/share/stackarr-seerr/
RUN node /usr/share/stackarr-seerr/patch.cjs /app
RUN corepack pnpm build:next

FROM ghcr.io/seerr-team/seerr@sha256:27602401178d54f1964442287b9f23f67a3fa2252645ee8065839ea1c3f69e45
USER root
COPY permissions.cjs patch.cjs setup-patch.cjs plex-login.ts plex-callback.tsx upstream.lock.json LICENSE-Seerr Dockerfile /usr/share/stackarr-seerr/
RUN node /usr/share/stackarr-seerr/patch.cjs /app
COPY --from=frontend /app/.next /app/.next
LABEL org.opencontainers.image.version="3.5.0-stackarr.2" \
      io.stackarr.seerr.security-patch="manage-users-1" \
      io.stackarr.seerr.setup-patch="plex-setup-1" \
      io.stackarr.seerr.upstream="3.5.0"
USER node
