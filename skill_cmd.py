"""``jarvis skill`` — skill management commands."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table


@click.group()
def skill() -> None:
    """Manage skills — list, install, remove."""


@skill.command("list")
def list_skills() -> None:
    """List installed skills."""
    console = Console(stderr=True)
    try:
        from openjarvis.core.registry import SkillRegistry

        keys = sorted(SkillRegistry.keys())
        if not keys:
            console.print("[dim]No skills installed.[/dim]")
            return
        table = Table(title="Installed Skills")
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="green")
        for key in keys:
            skill_cls = SkillRegistry.get(key)
            desc = ""
            if hasattr(skill_cls, "manifest"):
                m = skill_cls.manifest if not callable(skill_cls.manifest) else None
                if m and hasattr(m, "description"):
                    desc = m.description[:60]
            table.add_row(key, desc)
        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")


@skill.command()
@click.argument("skill_name")
def install(skill_name: str) -> None:
    """Install a skill from the bundled library."""
    console = Console(stderr=True)
    console.print(f"[yellow]Installing skill: {skill_name}[/yellow]")
    # Skills are discovered from TOML files — point user to the right place
    console.print(
        f"[dim]Place skill TOML file in ~/.openjarvis/skills/{skill_name}.toml[/dim]"
    )


@skill.command()
@click.argument("skill_name")
def remove(skill_name: str) -> None:
    """Remove an installed skill."""
    console = Console(stderr=True)
    console.print(f"[yellow]Removing skill: {skill_name}[/yellow]")
    console.print("[dim]Skill removal not yet implemented.[/dim]")


@skill.command()
@click.argument("query", default="")
def search(query: str) -> None:
    """Search for available skills."""
    console = Console(stderr=True)
    if not query:
        console.print("[dim]Provide a search query.[/dim]")
        return
    console.print(f"[dim]Searching for skills matching '{query}'...[/dim]")
    console.print("[dim]Skill search not yet implemented.[/dim]")


@skill.command("run")
@click.argument("skill_name")
@click.argument("inputs", nargs=-1)
def run_skill_cmd(skill_name: str, inputs: tuple) -> None:
    """Run a skill by name. Pass inputs as key=value pairs.

    Examples:\n
        jarvis skill run web-summarize url=https://example.com\n
        jarvis skill run meeting-notes transcript_path=C:/notes.txt\n
        jarvis skill run email-draft context="meeting request" intent="accept" recipient="Alice"
    """
    import sys
    from pathlib import Path

    # skill_runner.py lives next to the openjarvis package root (C:\openjarvis\)
    runner = Path(__file__).resolve().parent.parent.parent.parent / "skill_runner.py"
    if not runner.exists():
        runner = Path("C:/openjarvis/skill_runner.py")

    import subprocess
    cmd = [sys.executable, str(runner), skill_name] + list(inputs)
    subprocess.run(cmd)


@skill.command("list-available")
def list_available() -> None:
    """List all skills available to run (from ~/.openjarvis/skills/)."""
    from pathlib import Path
    console = Console()
    skills_dir = Path.home() / ".openjarvis" / "skills"
    if not skills_dir.exists() or not list(skills_dir.glob("*.toml")):
        console.print("[yellow]No skills found in ~/.openjarvis/skills/[/yellow]")
        return
    table = Table(title="Available Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="green")
    import tomllib
    for f in sorted(skills_dir.glob("*.toml")):
        with open(f, "rb") as fp:
            data = tomllib.load(fp)
        s = data.get("skill", {})
        table.add_row(f.stem, s.get("description", "")[:70])
    console.print(table)


__all__ = ["skill"]
