from pathlib import Path
from types import SimpleNamespace

from test_agent.cli import _source_import_path, _test_code_rejection_reason


def test_rejects_fenced_typescript_output():
    reason = _test_code_rejection_reason("```typescript\nconst x = 1;\n```", "mocha + chai + sinon", SimpleNamespace(symbol="x", context_lines=""))

    assert reason == "output used Markdown code fences instead of raw code"


def test_rejects_jest_output_for_mocha_project():
    code = "import S3Service from '../../src/lib/s3';\nawait expect(service.uploadS3Bucket()).resolves.toBeUndefined();"
    reason = _test_code_rejection_reason(code, "mocha + chai + sinon", SimpleNamespace(symbol="uploadS3Bucket", context_lines=""), "../../src/lib/s3")

    assert reason == "output used Jest APIs in a Mocha/Chai/Sinon project"


def test_rejects_output_that_does_not_import_project_source():
    code = "import { S3Client } from '@aws-sdk/client-s3';\ndescribe('S3Client', () => {});"
    reason = _test_code_rejection_reason(code, "mocha + chai + sinon", SimpleNamespace(symbol="uploadS3Bucket", context_lines=""), "../../src/lib/s3")

    assert reason == "output did not import the project source from ../../src/lib/s3"


def test_source_import_path_is_relative_to_target_file():
    target = Path("/repo/tests/lib/s3.spec.ts")
    source = Path("/repo/src/lib/s3.ts")

    assert _source_import_path(target, source) == "../../src/lib/s3"
