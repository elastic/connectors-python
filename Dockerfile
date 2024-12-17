FROM cgr.dev/chainguard/wolfi-base
ARG python_version=3.11

USER root
RUN apk update && apk add python-${python_version} make git
COPY . /app
RUN chown -R nonroot:nonroot /app

USER nonroot
WORKDIR /app
RUN make clean install
RUN ln -s .venv/bin /app/bin

USER root
RUN apk del make git

USER nonroot
ENTRYPOINT []
