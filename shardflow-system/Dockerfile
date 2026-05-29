FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /app
COPY pom.xml ./
COPY shardflow-common/pom.xml ./shardflow-common/
COPY shardflow-user-context/pom.xml ./shardflow-user-context/
COPY shardflow-callback/pom.xml ./shardflow-callback/
COPY shardflow-shard/pom.xml ./shardflow-shard/
COPY shardflow-strategy/pom.xml ./shardflow-strategy/
COPY shardflow-auth/pom.xml ./shardflow-auth/
COPY shardflow-profile/pom.xml ./shardflow-profile/
COPY shardflow-mcp/pom.xml ./shardflow-mcp/
COPY shardflow-task/pom.xml ./shardflow-task/
COPY shardflow-app/pom.xml ./shardflow-app/
RUN mvn dependency:go-offline -B -q
COPY . .
RUN mvn package -DskipTests -B -q

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/shardflow-app/target/*.jar app.jar
EXPOSE 8200
ENTRYPOINT ["java", "-jar", "app.jar"]
