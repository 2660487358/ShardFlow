FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /app
COPY pom.xml ./
COPY shardflow-common/pom.xml ./shardflow-common/
COPY shardflow-user-context/pom.xml ./shardflow-user-context/
COPY shardflow-callback/pom.xml ./shardflow-callback/
COPY shardflow-auth/pom.xml ./shardflow-auth/
COPY shardflow-mcp/pom.xml ./shardflow-mcp/
COPY shardflow-task/pom.xml ./shardflow-task/
COPY shardflow-config/pom.xml ./shardflow-config/
COPY shardflow-kb/pom.xml ./shardflow-kb/
COPY shardflow-app/pom.xml ./shardflow-app/
RUN mvn dependency:go-offline -B -q
COPY . .
RUN mvn package -DskipTests -B -q

FROM eclipse-temurin:21-jre
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /app/shardflow-app/target/*.jar app.jar
EXPOSE 8200
HEALTHCHECK --interval=10s --timeout=5s --retries=10 \
  CMD curl -f -s -o /dev/null -w '%{http_code}' http://localhost:8200/auth/login -H 'Content-Type: application/json' -d '{}' | grep -qE '^(200|400|401|403|422)' || exit 1
ENTRYPOINT ["java", "-Xms256m", "-Xmx512m", "-XX:+TieredCompilation", "-XX:TieredStopAtLevel=1", "-XX:+UseG1GC", "-jar", "app.jar"]
