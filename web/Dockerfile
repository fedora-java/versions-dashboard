FROM golang:1.17 as build
ENV CGO_ENABLED=0
COPY *.go /
RUN ["go","build","-o","/app","/app.go","/template.go"]

FROM gcr.io/distroless/static
COPY --from=build /app /
EXPOSE 8080
CMD ["/app"]
