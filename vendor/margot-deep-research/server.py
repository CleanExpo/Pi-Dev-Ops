#!/usr/bin/env python3
"""
Packaged Margot deep-research MCP server for Pi-CEO production containers.

Canonical Margot source remains outside this repo at:
  ~/.margot/margot-deep-research/server.py

This runtime snapshot exists so Railway can spawn the same FastMCP contract
without relying on a home-directory checkout that is not present in the image.
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from google import genai
from google.genai import types


HOME = Path.home()
API_KEY_FILE = HOME / ".margot" / "gemini-api-key.txt"
IMAGE_OUT_DIR = HOME / ".margot" / "generated-images"
IMAGE_OUT_DIR.mkdir(parents=True, exist_ok=True)

_ENV_FILE = HOME / ".margot" / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _value = _line.partition("=")
            os.environ.setdefault(_key.strip(), _value.strip())

FILE_SEARCH_STORE = os.environ.get("MARGOT_FILE_SEARCH_STORE", "").strip()
TEXT_MODEL = os.environ.get(
    "MARGOT_TEXT_MODEL",
    os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.1-pro-preview-customtools"),
).removeprefix("models/")
DEEP_RESEARCH_AGENT = os.environ.get(
    "MARGOT_DEEP_RESEARCH_AGENT",
    "deep-research-max-preview-04-2026",
)
IMAGE_MODEL = os.environ.get(
    "MARGOT_IMAGE_MODEL",
    "gemini-3.1-flash-image-preview",
)


def _load_api_key() -> str:
    explicit = os.environ.get("GEMINI_API_KEY", "").strip()
    if explicit:
        return explicit
    if not API_KEY_FILE.exists():
        sys.exit(f"Gemini API key missing at {API_KEY_FILE}")
    return API_KEY_FILE.read_text(encoding="utf-8").strip()


_client: genai.Client | None = None


def _client_singleton() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=_load_api_key())
    return _client


def _tools_for_corpus(use_corpus: bool) -> list[types.Tool]:
    if not use_corpus or not FILE_SEARCH_STORE:
        return []
    return [
        types.Tool(
            file_search=types.FileSearch(
                file_search_store_names=[FILE_SEARCH_STORE],
            ),
        ),
    ]


mcp = FastMCP("margot-deep-research")


@mcp.tool()
def deep_research(topic: str, use_corpus: bool = False) -> dict[str, Any]:
    """Gemini text research, optionally grounded against File Search."""
    client = _client_singleton()
    tools = _tools_for_corpus(use_corpus)
    prompt = (
        "You are Margot, Phill McGurk's personal research assistant.\n"
        f"Topic: {topic}\n\n"
        + (
            "Cite specific filenames from the Unite-Group corpus where relevant.\n"
            if use_corpus and FILE_SEARCH_STORE
            else "Provide a concise, well-sourced brief.\n"
        )
    )
    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(tools=tools) if tools else None,
    )
    return {
        "topic": topic,
        "use_corpus": use_corpus and bool(FILE_SEARCH_STORE),
        "store": FILE_SEARCH_STORE or None,
        "model": TEXT_MODEL,
        "report": response.text,
    }


@mcp.tool()
def deep_research_max(topic: str, use_corpus: bool = True) -> dict[str, Any]:
    """Start a background Deep Research interaction and return its id."""
    import warnings

    warnings.filterwarnings("ignore", message="Interactions usage is experimental")
    client = _client_singleton()
    tools: list[Any] = [{"type": "google_search"}]
    if use_corpus and FILE_SEARCH_STORE:
        tools.append({
            "type": "file_search",
            "file_search_store_names": [FILE_SEARCH_STORE],
        })
    persona_prefix = (
        "You are Margot, Phill McGurk's personal research assistant. "
        "Cite specific filenames from the Unite-Group corpus where relevant.\n\n"
        if use_corpus and FILE_SEARCH_STORE
        else "You are Margot, Phill McGurk's personal research assistant.\n\n"
    )
    interaction = client.interactions.create(
        agent=DEEP_RESEARCH_AGENT,
        input=persona_prefix + topic,
        background=True,
        tools=tools,
    )
    return {
        "interaction_id": interaction.id,
        "status": interaction.status,
        "agent": DEEP_RESEARCH_AGENT,
        "topic": topic,
        "use_corpus": use_corpus and bool(FILE_SEARCH_STORE),
        "store": FILE_SEARCH_STORE or None,
        "message": "Research started. Poll with check_research(interaction_id) until status='completed'.",
    }


@mcp.tool()
def check_research(interaction_id: str) -> dict[str, Any]:
    """Poll a previously started Deep Research interaction."""
    import warnings

    warnings.filterwarnings("ignore", message="Interactions usage is experimental")
    client = _client_singleton()
    interaction = client.interactions.get(interaction_id)
    report = ""
    if interaction.outputs:
        for content in interaction.outputs:
            if hasattr(content, "text") and content.text:
                report += content.text
    return {
        "interaction_id": interaction_id,
        "status": interaction.status,
        "completed": interaction.status == "completed",
        "report": report or None,
    }


@mcp.tool()
def corpus_status() -> dict[str, Any]:
    """Return configured models, corpus store, and key source diagnostic."""
    return {
        "file_search_store": FILE_SEARCH_STORE or "(unset)",
        "text_model": TEXT_MODEL,
        "deep_research_agent": DEEP_RESEARCH_AGENT,
        "image_model": IMAGE_MODEL,
        "api_key_source": "env" if os.environ.get("GEMINI_API_KEY") else str(API_KEY_FILE),
    }


@mcp.tool()
def image_generate(
    prompt: str,
    aspect_ratio: str = "16:9",
    image_size: str = "1K",
    reference_image_path: str | None = None,
    save_as: str | None = None,
) -> dict[str, Any]:
    """Generate an image with Gemini image output."""
    import time

    client = _client_singleton()
    contents: list[Any] = [prompt]
    if reference_image_path:
        ref_path = Path(reference_image_path).expanduser()
        if not ref_path.exists():
            return {"error": f"reference image not found: {ref_path}"}
        contents.append(
            types.Part.from_bytes(
                data=ref_path.read_bytes(),
                mime_type="image/png" if ref_path.suffix.lower() == ".png" else "image/jpeg",
            )
        )
    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=aspect_ratio,
                image_size=image_size,
            ),
        ),
    )
    image_bytes: bytes | str | None = None
    mime_type = "image/png"
    for part in response.candidates[0].content.parts:
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            image_bytes = inline.data
            mime_type = getattr(inline, "mime_type", mime_type)
            break
    if image_bytes is None:
        return {
            "error": "Gemini image model returned no image data",
            "response_text": getattr(response, "text", None),
        }
    if isinstance(image_bytes, str):
        image_bytes = base64.b64decode(image_bytes)
    ext = ".png" if "png" in mime_type else ".jpg"
    filename = save_as if save_as else f"gen-{int(time.time())}{ext}"
    if not filename.endswith(ext):
        filename += ext
    out_path = IMAGE_OUT_DIR / filename
    out_path.write_bytes(image_bytes)
    cost = {"1K": 0.045, "2K": 0.067, "4K": 0.151}.get(image_size.upper(), 0.045)
    return {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "saved_path": str(out_path),
        "mime_type": mime_type,
        "aspect_ratio": aspect_ratio,
        "image_size": image_size,
        "cost_usd_approx": cost,
    }


if __name__ == "__main__":
    mcp.run()
