import pytest

from agora.markdown import (
    MarkdownDocument,
    optional_integer_record_attribute,
    parse_markdown,
    render_markdown,
)


def test_round_trips_protocol_metadata_and_readable_content() -> None:
    rendered = render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/example/v1",
                "states": ["ready", "running"],
                "assignments": {"developer": "project:ada"},
                "limit": 3,
                "version-label": "0.1.0",
            },
            body="# Example\n\nDurable collaboration context.",
        )
    )

    assert parse_markdown(rendered) == MarkdownDocument(
        attributes={
            "schema": "agora/example/v1",
            "states": ["ready", "running"],
            "assignments": {"developer": "project:ada"},
            "limit": 3,
            "version-label": "0.1.0",
        },
        body="# Example\n\nDurable collaboration context.\n",
    )


def test_rejects_documents_without_protocol_metadata() -> None:
    with pytest.raises(ValueError, match="must start with YAML front matter"):
        parse_markdown("# Plain Markdown")


def test_reads_optional_integer_maps_without_accepting_booleans() -> None:
    assert optional_integer_record_attribute({"budget": None}, "budget") is None
    assert optional_integer_record_attribute(
        {"budget": {"effort": 8, "tokens": 50000}}, "budget"
    ) == {"effort": 8, "tokens": 50000}
    with pytest.raises(ValueError, match="Expected integer map"):
        optional_integer_record_attribute({"budget": {"effort": True}}, "budget")
