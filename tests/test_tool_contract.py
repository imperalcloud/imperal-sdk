"""One tool contract for every shell (ICNLI §3.5): one name per capability, one parameter set per shared tool."""
from imperal_sdk.tool_contract import as_function_schema, as_mcp_schema, names_by_effect, shell_tools, tool


def test_one_name_per_capability():
    names = {t.name for t in shell_tools()}
    assert not names & {"diff", "rollback", "grep"}
    assert {"checkpoint_diff", "checkpoint_rollback", "grep_code"} <= names


def test_shared_tools_carry_the_decided_params():
    assert set(tool("checkpoint").params) == {"label", "root"}
    assert set(tool("checkpoint_diff").params) == {"target", "paths", "root"}
    assert set(tool("checkpoint_rollback").params) == {"target", "paths", "allow_nested", "root"}
    assert {"pattern", "regex", "path_glob", "k", "root", "target"} <= set(tool("grep_code").params)
    assert set(tool("state_lens").params) == {"section", "focus", "offset", "conversation"}
    for name in ("outline", "read_symbol", "repo_profile", "search_code", "impact_of_change", "contract_slice",
                 "orient", "graph_slice"):
        assert {"root", "target"} <= set(tool(name).params), name


def test_shells_and_runner():
    assert tool("bash").shells == frozenset({"webbee"})
    assert tool("frame").shells == frozenset({"mcp"})
    assert tool("grep_code").shells == frozenset({"webbee", "mcp"})
    assert tool("state_lens").executed_by == "kernel" and tool("read_file").executed_by == "client"
    assert len(shell_tools("webbee")) == len([t for t in shell_tools() if "webbee" in t.shells])


def test_descriptions_say_the_contract():
    rf = tool("read_file").description
    assert "up to 5000 lines is always read whole" not in rf and "window is always honoured" in rf
    assert "nothing filtered" not in tool("state_lens").description
    assert "focus: only the rows holding that word" in tool("state_lens").description
    assert "unknown one is an error" in tool("checkpoint_diff").description


def test_schema_shapes():
    k = as_function_schema(tool("checkpoint"))
    assert set(k) == {"name", "description", "input_schema"} and k["input_schema"]["type"] == "object"
    m = as_mcp_schema(tool("grep_code"))
    assert m["inputSchema"]["required"] == ["pattern"] and m["name"] == "grep_code"


def test_every_tool_has_one_effect():
    effects = {t.effect for t in shell_tools()}
    assert effects <= {"read", "write", "run", "snapshot"}
    assert {"read_file", "grep_code", "checkpoint_diff", "outline"} <= names_by_effect("read", "webbee")
    assert {"write_file", "edit_file", "checkpoint_rollback"} <= names_by_effect("write", "webbee")
    # a tool that carries a command is judged by what it runs, wherever it runs (job_start: on a machine of the account)
    assert names_by_effect("run") == {"bash", "job_start"} and names_by_effect("snapshot") == {"checkpoint"}
    assert names_by_effect("run", executed_by="client") == {"bash"}


def test_session_jobs_are_kernel_tools_of_one_shape():
    # a long command runs as a job of the session: started and ended through the kernel, watched by it (2026-11-25)
    for name, effect in (("job_start", "run"), ("job_status", "read"), ("job_cancel", "write")):
        t = tool(name)
        assert t.executed_by == "kernel" and t.shells == frozenset({"webbee"}) and t.effect == effect, name
    # the machine is optional (6.12.0): no connection_id is the person's own machine, where the terminal runs
    assert tool("job_start").required == ("command", "title")
    assert "connection_id" in tool("job_start").params
    assert tool("job_cancel").required == ("id",) and tool("job_status").required == ()
