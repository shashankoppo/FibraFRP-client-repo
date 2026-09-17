FROM docker:29.8.0-cli

RUN apk add --no-cache bash python3 openssl

# Code is read from the reviewed VPS checkout, never copied with its secrets.
ENTRYPOINT ["python3", "deploy/compose_deploy.py"]
