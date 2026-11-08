ARG GO_VERSION
FROM golang:${GO_VERSION}-alpine AS build
ARG DERPER_VERSION
RUN CGO_ENABLED=0 go install "tailscale.com/cmd/derper@v${DERPER_VERSION}"

FROM alpine:3.22
COPY --from=build /go/bin/derper /usr/local/bin/derper
ENTRYPOINT ["/usr/local/bin/derper"]
