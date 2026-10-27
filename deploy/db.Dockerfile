FROM postgres:17-bookworm@sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27
COPY deploy/init-db.sh /docker-entrypoint-initdb.d/10-app-user.sh
RUN chmod 755 /docker-entrypoint-initdb.d/10-app-user.sh
