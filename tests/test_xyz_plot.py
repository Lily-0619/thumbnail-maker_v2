import pytest

from tools.model_tester.comfy_client import GenParams, LoraSpec
from tools.model_tester.xyz_plot import (
    AXIS_CFG,
    AXIS_PROMPT_SR,
    AXIS_SEED,
    AXIS_STEPS,
    Axis,
    AxisError,
    apply_axis,
    build_jobs,
    parse_values,
)


def test_parse_values_numeric_lists():
    assert parse_values(AXIS_STEPS, "20, 28, 35") == [20, 28, 35]
    assert parse_values(AXIS_CFG, "6.5, 7, 8.25") == [6.5, 7.0, 8.25]
    assert parse_values(AXIS_SEED, "-1, 1, 42") == [-1, 1, 42]


def test_parse_values_prompt_sr():
    assert parse_values(AXIS_PROMPT_SR, "knight, mage, archer") == ["knight", "mage", "archer"]


@pytest.mark.parametrize(
    "kind, raw",
    [
        (AXIS_STEPS, "20, nope"),
        (AXIS_CFG, "7.0, nope"),
        (AXIS_SEED, "1.5"),
        (AXIS_PROMPT_SR, "knight"),
        (AXIS_STEPS, ""),
    ],
)
def test_parse_values_rejects_invalid_input(kind, raw):
    with pytest.raises(AxisError):
        parse_values(kind, raw)


def test_apply_axis_prompt_sr_replaces_prompt_and_negative():
    base = GenParams(prompt="a knight in armor", negative="bad knight", loras=[LoraSpec("old.safetensors")])
    result = apply_axis(base, AXIS_PROMPT_SR, "mage", sr_search="knight")
    assert result.prompt == "a mage in armor"
    assert result.negative == "bad mage"
    assert base.prompt == "a knight in armor"


def test_build_jobs_expands_prompt_sr_axis_values():
    base = GenParams(prompt="red castle", negative="red blur")
    x = Axis(AXIS_PROMPT_SR, ["red", "blue", "gold"])
    y = Axis(AXIS_STEPS, [20, 30])
    z = Axis("none", [])
    jobs = build_jobs(base, x, y, z)
    assert len(jobs) == 4
    assert [job.params.prompt for job in jobs] == [
        "blue castle",
        "gold castle",
        "blue castle",
        "gold castle",
    ]
    assert [job.params.steps for job in jobs] == [20, 20, 30, 30]
