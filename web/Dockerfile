FROM golang:1.22 as build
ENV CGO_ENABLED=0
COPY *.go *.html /
RUN ["go","build","-o","/app","/app.go","/rpmvercmp.go"]

FROM gcr.io/distroless/static:nonroot
COPY --from=build /app /*.html /
EXPOSE 8080
CMD ["/app"]
