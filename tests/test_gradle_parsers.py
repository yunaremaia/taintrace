from pathlib import Path

from taintrace.lockfile import LockfileParser


def test_gradle_groovy_dependencies(tmp_path: Path):
    path = tmp_path / "build.gradle"
    path.write_text("""dependencies {\n implementation 'com.google.guava:guava:32.1.3-jre'\n testImplementation project(':core')\n api \"org.slf4j:slf4j-api:2.0.9\"\n}\n""")
    deps = LockfileParser().parse(path)
    assert [(d.name, d.version, d.ecosystem) for d in deps] == [
        ("com.google.guava:guava", "32.1.3-jre", "java"),
        ("org.slf4j:slf4j-api", "2.0.9", "java"),
    ]


def test_gradle_kotlin_dependencies(tmp_path: Path):
    path = tmp_path / "build.gradle.kts"
    path.write_text('dependencies {\n implementation("org.springframework.boot:spring-boot-starter-web:3.2.0")\n testImplementation("junit:junit:4.13.2")\n}\n')
    deps = LockfileParser().parse(path)
    assert [(d.name, d.version) for d in deps] == [
        ("org.springframework.boot:spring-boot-starter-web", "3.2.0"),
        ("junit:junit", "4.13.2"),
    ]


def test_gradle_version_catalog(tmp_path: Path):
    path = tmp_path / "libs.versions.toml"
    path.write_text('''[versions]\nkotlin = "1.9.22"\n[libraries]\nguava = { module = "com.google.guava:guava", version = "32.1.3-jre" }\nkotlin-stdlib = { module = "org.jetbrains.kotlin:kotlin-stdlib", version.ref = "kotlin" }\n''')
    deps = LockfileParser().parse(path)
    assert [(d.name, d.version) for d in deps] == [
        ("com.google.guava:guava", "32.1.3-jre"),
        ("org.jetbrains.kotlin:kotlin-stdlib", "1.9.22"),
    ]


def test_gradle_map_form_dependencies(tmp_path: Path):
    path = tmp_path / "build.gradle"
    path.write_text("""dependencies {\n    implementation group: 'org.slf4j', name: 'slf4j-api', version: '2.0.13'\n    api group: 'com.google.guava', name: 'guava', version: '32.1.3-jre'\n}\n""")
    deps = LockfileParser().parse(path)
    assert [(d.name, d.version, d.ecosystem) for d in deps] == [
        ("org.slf4j:slf4j-api", "2.0.13", "java"),
        ("com.google.guava:guava", "32.1.3-jre", "java"),
    ]


def test_gradle_extra_configuration_names(tmp_path: Path):
    path = tmp_path / "build.gradle"
    path.write_text("""dependencies {\n    debugImplementation 'com.squareup.leakcanary:leakcanary-android:2.12'\n    releaseImplementation 'com.squareup.leakcanary:leakcanary-android-no-op:2.12'\n    developmentOnly 'org.springframework.boot:spring-boot-devtools:3.2.0'\n    testFixturesImplementation 'com.google.code.gson:gson:2.10.1'\n    androidTestImplementation 'androidx.test.ext:junit:1.1.5'\n    compileOnlyApi 'org.projectlombok:lombok:1.18.30'\n}\n""")
    deps = LockfileParser().parse(path)
    assert [(d.name, d.version) for d in deps] == [
        ("com.squareup.leakcanary:leakcanary-android", "2.12"),
        ("com.squareup.leakcanary:leakcanary-android-no-op", "2.12"),
        ("org.springframework.boot:spring-boot-devtools", "3.2.0"),
        ("com.google.code.gson:gson", "2.10.1"),
        ("androidx.test.ext:junit", "1.1.5"),
        ("org.projectlombok:lombok", "1.18.30"),
    ]


def test_gradle_word_boundary_no_false_positive(tmp_path: Path):
    path = tmp_path / "build.gradle"
    path.write_text("""dependencies {\n    myImplementation 'com.example:foo:1.0'\n}\n""")
    deps = LockfileParser().parse(path)
    assert deps == []
