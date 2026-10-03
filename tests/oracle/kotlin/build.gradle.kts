// Every deprecated construct sits on its own line; see tests/oracle/run_oracle.py.
plugins { java }

repositories { mavenCentral() }
dependencies {
    implementation(group = "org.apache.commons", name = "commons-lang3", version = "3.14.0")
    implementation("com.google.guava:guava:33.0.0-jre")
}

extra["greeting"] = "hi"
val fromExtra by extra("x")
val greeting: String by extra
val jar by tasks.getting
val helloTask by tasks.registering { }
val projProp: String? by project
val test by tasks.existing
val viaProject = project.properties["nothing"]
val compileJava by tasks.getting(JavaCompile::class) { }
val sample by tasks.creating { }
val viaSettings: String? by project

// negative cases
val explicit = tasks.register("explicit") { }
val lazyProp = providers.gradleProperty("x").orNull
val extraRead = extra["greeting"]
