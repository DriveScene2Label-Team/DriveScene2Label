# Ship the browser app and API together, under the same origin.
FROM node:24-bookworm-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Integration tests run in CI against a separate PostgreSQL database.
# Keep this Gradle version aligned with gradle-wrapper.properties. The official
# image avoids downloading the distribution again through the redirect service.
FROM gradle:9.7.1-jdk21@sha256:3695cd3c4b617ccb7b351ff1481c0f141c5e87a89872dc8ca1e5a8eeac6a85e3 AS build
USER root
WORKDIR /workspace
COPY gradlew build.gradle settings.gradle ./
COPY gradle/ gradle/
COPY src/main/ src/main/
COPY --from=frontend /frontend/dist/ src/main/resources/static/
RUN gradle --no-daemon bootJar

FROM eclipse-temurin:21-jre-jammy AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN curl --fail --silent --show-error --location --retry 5 --retry-all-errors --connect-timeout 20 --max-time 120 https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem --output /app/rds-ca.pem
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /uploads && chown app:app /uploads
ENV UPLOAD_ROOT=/uploads
COPY --from=build --chown=app:app /workspace/build/libs/*.jar /app/app.jar
USER app
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
