"""The one owner of secrets: the kernel's and imperal-mcp's copies merged (they had drifted), with the masks recorded."""
from imperal_sdk import code_index
from imperal_sdk.secret_mask import SECRET_FILES, is_secret_file, mask, scrub_secrets, scrub_file_text


def test_mask_spans_name_the_value_without_it():
    out, masked = mask("url https://u:ghp_x1@h/x ok")
    assert out == "url https://u:<redacted:url-password>@h/x ok"   # scheme and user stay: more evidence, no secret
    assert len(masked) == 1
    m = masked[0]
    assert m.rule == "url-password" and m.length == len("ghp_x1")
    assert not hasattr(m, "sha256")                     # no guessable hash of a secret
    assert out[m.at:].startswith("<redacted:url-password>")


def test_token_alone_in_url_masked():
    out, masked = mask("git remote https://ghp_FAKEgate0000000000@github.com/x.git")
    assert "ghp_FAKEgate0000000000" not in out and out.startswith("git remote https://<redacted:url-token>@github.com")
    assert masked[0].rule == "url-token"


def test_every_rule_of_both_copies():
    cases = {
        "mysql -uroot -pS3cret db": "S3cret",
        "sshpass -p 'hunter2' ssh h": "hunter2",
        "Authorization: Basic dXNlcjpwYXNz": "dXNlcjpwYXNz",
        "DB_PASSWORD=abc123xyz": "abc123xyz",
        "bearer abcdefghijklmnop": "abcdefghijklmnop",
        "jwt eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl": "eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl",
        "key sk_live_ABCDEFGHIJKLMN": "sk_live_ABCDEFGHIJKLMN",
        "AKIAABCDEFGHIJKLMNOP": "AKIAABCDEFGHIJKLMNOP",
        "sk-ant-api03-abcdefghijklmnopqrst": "sk-ant-api03-abcdefghijklmnopqrst",
    }
    for text, secret in cases.items():
        assert secret not in scrub_secrets(text), text


def test_measures_and_code_stay():
    assert scrub_secrets("'token': 11.24") == "'token': 11.24"                 # seconds to the first token
    assert scrub_secrets("token=self.token", code=True) == "token=self.token"
    assert scrub_secrets("mkdir -p /tmp/x && ssh -p 22 h") == "mkdir -p /tmp/x && ssh -p 22 h"


def test_private_key_masked_whole():
    pem = "a\n-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----\nb"
    out, masked = mask(pem)
    assert out == "a\n<redacted:private-key>\n\n\nb" and masked[0].rule == "private-key"   # line numbers stay


def test_mask_positions_after_several_rules():
    text = "DB_PASS=one1 then https://u:two2@h and bearer threethreethree3"
    out, masked = mask(text)
    assert [m.at for m in masked] == sorted(m.at for m in masked)               # in reading order
    for m in masked:
        assert out[m.at:].startswith("<redacted:" + m.rule + ">")
    assert sorted(m.length for m in masked) == sorted(len(v) for v in ("one1", "two2", "threethreethree3"))


def test_git_is_skipped_never_secret():
    assert is_secret_file(".git/config") is False
    assert is_secret_file("app/.env.local") is True and is_secret_file("home/.ssh/id_ed25519") is True
    assert is_secret_file("x/.git-credentials") is True
    assert is_secret_file("~/.ssh") is True and is_secret_file("/home/u/.aws/") is True    # the folder itself
    assert is_secret_file("src/secrets_scrub.py") is False
    assert is_secret_file("C:\\proj\\.ENV") is True and is_secret_file("keys/SERVER.PEM") is True   # case-blind
    assert ".git/" not in SECRET_FILES and ".git/" in code_index.SKIP_PATTERNS
    assert set(SECRET_FILES) <= set(code_index.SKIP_PATTERNS)


def test_file_text_scrubbed_as_what_it_is():
    assert scrub_file_text("password = get()", "a.py") == "password = get()"
    assert "s3cr3t" not in scrub_file_text("password=s3cr3t", "notes.txt")


def test_the_vault_s_rules_are_here_too():
    cases = {
        "whsec_ABCDEFGHIJKLMNOPQRST": "stripe-webhook-secret",
        "github_pat_" + "A" * 40: "github-token",
        "glpat-abcdefghijklmnopqrstu": "gitlab-token",
        "ASIAABCDEFGHIJKLMNOP": "aws-access-key",
        "1234567890:AA" + "b" * 33: "telegram-bot-token",
        "hvs.ABCDEFGHIJKLMNOPQRSTUVWX": "vault-token",
        "X-Service-Token: abcdef123456ghij": "auth-header",
        "DATABASE_DSN=postgres_dsn_value_x": "assigned-secret",
        "password: Kq7L9xZp2Vw8Rt4Ny6": "assigned-secret",        # yaml, unquoted, random-looking
    }
    for text, kind in cases.items():
        out, masked = mask(text)
        assert masked and masked[0].rule == kind, (text, out, masked)


def test_settings_about_secrets_stay():
    for text in ("SECRET_NAME=jwt_signing", "AUTH_TOKEN_TTL=3600", "MAX_TOKENS=4096", "TOKEN_ID=abc"):
        assert mask(text)[0] == text, text


def test_code_and_config_stay():
    for text in ("API_KEY = settings.api_key", "SECRET_KEY=None", "https://example.com/docs/path?page=2",
                 "password: str = DEFAULT_PASSWORD_FROM_ENV", "passwd: files systemd",
                 "token_budget: conversational_max_tokens"):
        assert mask(text)[0] == text, text
    assert "hunter2" not in scrub_secrets("password=hunter2") and "hunter" not in scrub_secrets("DB_PASS=hunter")


def test_a_measure_only_under_a_key_secret_by_token_alone():
    """imperal-mcp's rule the merge had lost (2026-11-15): seconds to the first token stay; a key secret by another word
    too (secret_token) holds a credential, whatever its shape."""
    assert scrub_secrets("{'token': 10.33}") == "{'token': 10.33}"
    assert "<redacted:" in scrub_secrets("secret_token=12.5")
    assert "<redacted:" in scrub_secrets("token=482913")          # a whole number may be a one-time code


# ---- a secret file shown by its form (owner 2026-11-15, phase 6 decision 1)
from imperal_sdk.secret_mask import is_key_material, secret_file_view  # noqa: E402


def test_settings_file_keeps_every_key_and_masks_every_value_whatever_it_looks_like():
    env = "# db\nexport DB_HOST=db.local\nX=hunter2\nEMPTY=\n\nPORT: 5432\n"
    out, masked = secret_file_view(env, ".env")
    assert "hunter2" not in out and "db.local" not in out and "5432" not in out
    for key in ("export DB_HOST=", "X=", "EMPTY=", "PORT: "):
        assert key in out
    assert out.count("\n") == env.count("\n")           # a line number stays true
    assert {m.rule for m in masked} >= {"secret-file-value", "secret-file-comment"}
    assert all(out[m.at:].startswith("<redacted:") for m in masked)


def test_a_line_without_a_key_is_masked_whole():
    for line in ("machine h login u password p", "ghp_FAKEgate0000000000", "plain secret words",
                 "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7aX9=="):
        out, _ = secret_file_view(line, "credentials")
        assert out == "<redacted:secret-file-line>", line


def test_json_and_ini_shapes():
    out, _ = secret_file_view('{\n  "password": "x1",\n  "user": "bob"\n}\n[default]\naws_secret = k\n',
                              "service-account.json")
    assert '"password": <redacted:secret-file-value>' in out and "bob" not in out and "[default]" in out
    assert out.startswith("{\n") and "\n}\n" in out


def test_key_material_keeps_only_its_line_count():
    pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\ndef\n-----END OPENSSH PRIVATE KEY-----\n"
    for path in ("~/.ssh/config", "deploy/id_ed25519", "certs/site.pem", "a.p12"):
        assert is_key_material(path)
        out, masked = secret_file_view(pem, path)
        assert out == "<redacted:key-file>" + "\n" * 4 and masked[0].length == len(pem)
    assert not is_key_material(".env") and is_secret_file(".env")
    assert secret_file_view("", "a.pem") == ("", ())


def test_every_key_material_name_is_a_secret_file():
    for path in ("a.pem", "x/id_rsa", "w/wallet.dat", ".ssh/known_hosts", "k.gpg"):
        assert is_key_material(path) and is_secret_file(path)


def test_a_printed_secret_without_a_path_is_a_settings_view():
    out, _ = secret_file_view("HOME=/root\nAPI=abc\ntoken-alone\n")
    assert out == "HOME=<redacted:secret-file-value>\nAPI=<redacted:secret-file-value>\n" \
                  "<redacted:secret-file-line>\n"


def test_a_command_that_used_a_secret_file_loses_exactly_its_values():
    # live 2026-11-07: `. .env; python bench.py` -- the bench's numbers are facts, the file's values are not
    from imperal_sdk.secret_mask import mask_values, secret_file_values
    vals = secret_file_values('# a\nX=hunter2\nDB_URL="postgres://u:pw99@db/app"\nON=1\n', ".env")
    assert "hunter2" in vals and "postgres://u:pw99@db/app" in vals and "1" not in vals
    out, masked = mask_values("claims 65 held 53; login hunter2 ok", vals)
    assert out == "claims 65 held 53; login <redacted:secret-file-value> ok" and masked[0].length == 7
    key = "-----BEGIN KEY-----\nAAAAB3Nza\n-----END KEY-----\n"
    assert "AAAAB3Nza" in secret_file_values(key, "id_rsa")
    assert "AAAAB3Nza" not in mask_values("got AAAAB3Nza here", secret_file_values(key, "id_rsa"))[0]


def test_masking_values_never_breaks_a_mask_already_made():
    from imperal_sdk.secret_mask import mask_values
    vals = [f"v{i:03d}" for i in range(120)] + ["100"]
    out, _ = mask_values(" ".join(vals), vals)
    assert set(out.split()) == {"<redacted:secret-file-value>"}


def test_a_text_holding_nul_bytes_is_masked_and_kept_whole():
    """Live 2026-11-15 (vault on 6.7.0): a message holding NUL bytes -- one of them before digits, as a mask's own
    mark is -- made finish() look up a mask never made: IndexError, every such write a 500."""
    for text in ("a\x000\x00b", "\x00", "\x00\x00e1\x00", "x\x0012\x00 y"):
        assert mask(text) == (text, ())                    # nothing secret: the text whole, NULs kept
    out, masked = mask("x\x0012\x00 key ghp_FAKEgate00000000000000000 \x00")
    assert out == "x\x0012\x00 key <redacted:github-token> \x00"
    assert len(masked) == 1 and out[masked[0].at:].startswith("<redacted:github-token>")
    assert masked[0].length == len("ghp_FAKEgate00000000000000000")
    from imperal_sdk.secret_mask import mask_values, secret_file_view
    assert secret_file_view("A=1\x002\n", ".env")[0] == "A=<redacted:secret-file-value>\n"
    assert mask_values("v\x00al ok", ["v\x00al"])[0] == "<redacted:secret-file-value> ok"
