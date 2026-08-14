import pytest

from agora.markdown import MarkdownDocument, parse_markdown, render_markdown


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
