from test_agent.gap_finder import Gap
from test_agent.plugins.go import GoPlugin
from test_agent.plugins.python import PythonPlugin
from test_agent.plugins.typescript import TypeScriptPlugin
from test_agent.target_resolver import read_reference_test_context, resolve_test_target


def _gap(file: str) -> Gap:
    return Gap(file=file, symbol="example", kind="uncovered", priority=1, context_lines="")


def test_reuses_existing_python_test_file(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    src = tmp_path / "src" / "math_utils.py"
    test_file = tmp_path / "tests" / "test_math_utils.py"
    src.write_text("def add(a, b): return a + b")
    test_file.write_text("def test_existing(): pass")

    target = resolve_test_target(_gap("src/math_utils.py"), tmp_path, PythonPlugin(), [test_file])

    assert target.path == test_file
    assert target.status == "existing file"


def test_reuses_existing_typescript_test_file(tmp_path):
    (tmp_path / "src").mkdir()
    src = tmp_path / "src" / "foo.ts"
    test_file = tmp_path / "src" / "foo.test.ts"
    src.write_text("export function foo() {}")
    test_file.write_text("describe('foo', () => {})")

    target = resolve_test_target(_gap("src/foo.ts"), tmp_path, TypeScriptPlugin(), [test_file])

    assert target.path == test_file
    assert target.status == "existing file"


def test_typescript_learns_tests_spec_structure(tmp_path):
    (tmp_path / "src" / "utils").mkdir(parents=True)
    (tmp_path / "tests" / "user").mkdir(parents=True)
    src = tmp_path / "src" / "utils" / "fileUpload.ts"
    existing = tmp_path / "tests" / "user" / "userService.spec.ts"
    src.write_text("export function profileImageUpload() {}")
    existing.write_text("import { expect } from 'chai';")

    target = resolve_test_target(_gap("src/utils/fileUpload.ts"), tmp_path, TypeScriptPlugin(), [existing])

    assert target.path == tmp_path / "tests" / "utils" / "fileUpload.spec.ts"
    assert target.status == "new file"


def test_typescript_service_file_uses_domain_from_filename(tmp_path):
    (tmp_path / "src" / "services").mkdir(parents=True)
    (tmp_path / "tests" / "document").mkdir(parents=True)
    src = tmp_path / "src" / "services" / "user.service.ts"
    existing = tmp_path / "tests" / "document" / "documentService.spec.ts"
    src.write_text("export class UserService {}")
    existing.write_text("import { expect } from 'chai';")

    target = resolve_test_target(_gap("src/services/user.service.ts"), tmp_path, TypeScriptPlugin(), [existing])

    assert target.path == tmp_path / "tests" / "user" / "userService.spec.ts"
    assert target.status == "new file"


def test_new_target_uses_existing_spec_as_reference_context(tmp_path):
    (tmp_path / "src" / "utils").mkdir(parents=True)
    (tmp_path / "tests" / "user").mkdir(parents=True)
    src = tmp_path / "src" / "utils" / "fileUpload.ts"
    existing = tmp_path / "tests" / "user" / "userService.spec.ts"
    src.write_text("export function profileImageUpload() {}")
    existing.write_text("import { expect } from 'chai';\nimport sinon from 'sinon';\n")
    target = resolve_test_target(_gap("src/utils/fileUpload.ts"), tmp_path, TypeScriptPlugin(), [existing])

    context = read_reference_test_context(target, [existing])

    assert "from 'chai'" in context
    assert "sinon" in context


def test_typescript_tests_structure_overrides_source_adjacent_generated_file(tmp_path):
    (tmp_path / "src" / "utils").mkdir(parents=True)
    (tmp_path / "tests" / "user").mkdir(parents=True)
    src = tmp_path / "src" / "utils" / "fileUpload.ts"
    bad_generated = tmp_path / "src" / "utils" / "fileUpload.test.ts"
    existing = tmp_path / "tests" / "user" / "userService.spec.ts"
    src.write_text("export function profileImageUpload() {}")
    bad_generated.write_text("jest.mock('fs')")
    existing.write_text("import { expect } from 'chai';")

    target = resolve_test_target(_gap("src/utils/fileUpload.ts"), tmp_path, TypeScriptPlugin(), [bad_generated, existing])

    assert target.path == tmp_path / "tests" / "utils" / "fileUpload.spec.ts"
    assert target.status == "new file"


def test_reuses_existing_go_test_file(tmp_path):
    (tmp_path / "pkg").mkdir()
    src = tmp_path / "pkg" / "foo.go"
    test_file = tmp_path / "pkg" / "foo_test.go"
    src.write_text("package pkg")
    test_file.write_text("package pkg")

    target = resolve_test_target(_gap("pkg/foo.go"), tmp_path, GoPlugin(), [test_file])

    assert target.path == test_file
    assert target.status == "existing file"


def test_falls_back_to_plugin_path_when_no_existing_test_file(tmp_path):
    (tmp_path / "src").mkdir()
    src = tmp_path / "src" / "math_utils.py"
    src.write_text("def add(a, b): return a + b")

    target = resolve_test_target(_gap("src/math_utils.py"), tmp_path, PythonPlugin(), [])

    assert target.path == tmp_path / "tests" / "test_math_utils.py"
    assert target.status == "new file"
