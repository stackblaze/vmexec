# Stock Caddy plus the Bunny DNS provider: Let's Encrypt through DNS-01.
FROM caddy:2.10.2-builder-alpine AS builder
RUN xcaddy build --with github.com/caddy-dns/bunny@v1.2.0

FROM caddy:2.10.2-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
