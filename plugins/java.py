from __future__ import annotations
from pathlib import Path
from plugins.base import StackPlugin


class JavaPlugin(StackPlugin):
    @property
    def name(self) -> str:
        return "Java"

    def detect(self, project_root: Path) -> bool:
        return (project_root / "pom.xml").exists() or (project_root / "build.gradle").exists()

    @property
    def test_runner(self) -> str:
        return "mvn test" if (Path(".") / "pom.xml").exists() else "gradle test"

    def test_file_path(self, source_file: Path, project_root: Path) -> Path:
        # src/main/java/com/Foo.java → src/test/java/com/FooTest.java
        rel = str(source_file.relative_to(project_root))
        rel = rel.replace("src/main/java", "src/test/java")
        p = Path(rel)
        return project_root / p.parent / (p.stem + "Test" + p.suffix)

    @property
    def coverage_formats(self) -> list[str]:
        return ["xml"]  # JaCoCo

    @property
    def prompt_hints(self) -> str:
        return (
            "You are writing Java tests using JUnit 5. "
            "Use @Test annotations. Follow AAA pattern. "
            "Use AssertJ for assertions. One test method per case."
        )

    def detect_framework(self, project_root: Path) -> str:
        pom = project_root / "pom.xml"
        if pom.exists():
            content = pom.read_text()
            return "junit5" if "junit-jupiter" in content else "junit4"
        return "junit5"
