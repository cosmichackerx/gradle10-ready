plugins { java }

group = "com.example"
version = "1.0"

repositories { mavenCentral() }
dependencies {
    implementation("com.google.guava:guava:33.0.0-jre")
}

tasks.test {
    maxHeapSize = "1g"
}

val greeting = providers.gradleProperty("greeting").orElse("hi")
