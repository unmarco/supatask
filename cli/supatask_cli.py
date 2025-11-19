#!/usr/bin/env python3
"""Supatask CLI - Rich-based command-line interface."""
import sys
from datetime import datetime
from typing import Optional, List
import httpx
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

app = typer.Typer(help="Supatask - Redis-based Task Manager CLI")
console = Console()

# API Configuration
API_BASE = "http://localhost:8000"


def handle_error(error: Exception, message: str = "An error occurred"):
    """Handle and display errors."""
    console.print(f"[red]❌ {message}[/red]")
    console.print(f"[dim]{str(error)}[/dim]")
    raise typer.Exit(1)


@app.command()
def list(
    status: Optional[str] = typer.Option(None, help="Filter by status (pending, in_progress, completed, archived)"),
    tags: Optional[str] = typer.Option(None, help="Filter by tags (comma-separated)"),
    created_after: Optional[str] = typer.Option(None, help="Filter by created after date (YYYY-MM-DD)"),
    created_before: Optional[str] = typer.Option(None, help="Filter by created before date (YYYY-MM-DD)")
):
    """List all tasks with optional filters."""
    try:
        params = {}
        if status:
            params["status"] = status
        if tags:
            params["tags"] = tags
        if created_after:
            params["created_after"] = datetime.fromisoformat(created_after).isoformat()
        if created_before:
            params["created_before"] = datetime.fromisoformat(created_before).isoformat()
        
        response = httpx.get(f"{API_BASE}/tasks", params=params, timeout=10.0)
        response.raise_for_status()
        tasks = response.json()
        
        if not tasks:
            console.print("[yellow]📭 No tasks found[/yellow]")
            return
        
        # Create table
        table = Table(title="📋 Tasks", box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("ID", style="dim")
        table.add_column("Title", style="bold")
        table.add_column("Status")
        table.add_column("Tags", style="dim")
        table.add_column("Created")
        
        for task in tasks:
            # Color code status
            status_color = {
                "pending": "yellow",
                "in_progress": "blue",
                "completed": "green",
                "archived": "dim"
            }.get(task["status"], "white")
            
            status_display = f"[{status_color}]{task['status'].replace('_', ' ').title()}[/{status_color}]"
            tags_display = ", ".join(task.get("tags", [])) if task.get("tags") else "-"
            created = datetime.fromisoformat(task["created_at"]).strftime("%Y-%m-%d %H:%M")
            
            table.add_row(
                str(task["id"]),
                task["title"],
                status_display,
                tags_display,
                created
            )
        
        console.print(table)
        console.print(f"\n[dim]Total: {len(tasks)} task(s)[/dim]")
    
    except httpx.HTTPError as e:
        handle_error(e, "Failed to fetch tasks")
    except Exception as e:
        handle_error(e)


@app.command()
def add(
    title: str = typer.Argument(..., help="Task title"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Task description"),
    status: str = typer.Option("pending", "--status", "-s", help="Task status"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Task tags (comma-separated)")
):
    """Add a new task."""
    try:
        task_data = {
            "title": title,
            "description": description or "",
            "status": status,
            "tags": [t.strip() for t in tags.split(",")] if tags else []
        }
        
        response = httpx.post(f"{API_BASE}/tasks", json=task_data, timeout=10.0)
        response.raise_for_status()
        task = response.json()
        
        console.print(Panel(
            f"[bold green]✓ Task created[/bold green]\n\n"
            f"ID: {task['id']}\n"
            f"Title: {task['title']}\n"
            f"Status: {task['status']}\n"
            f"Tags: {', '.join(task['tags']) if task['tags'] else 'None'}",
            title="Success",
            border_style="green"
        ))
    
    except httpx.HTTPError as e:
        handle_error(e, "Failed to create task")
    except Exception as e:
        handle_error(e)


@app.command()
def view(task_id: int = typer.Argument(..., help="Task ID")):
    """View task details with time tracking."""
    try:
        response = httpx.get(f"{API_BASE}/tasks/{task_id}", timeout=10.0)
        response.raise_for_status()
        task = response.json()
        
        # Format time
        total_hours = task["total_time"] / 3600 if task["total_time"] else 0
        
        details = f"""
[bold cyan]Title:[/bold cyan] {task['title']}
[bold cyan]Status:[/bold cyan] {task['status'].replace('_', ' ').title()}
[bold cyan]Tags:[/bold cyan] {', '.join(task['tags']) if task['tags'] else 'None'}
[bold cyan]Description:[/bold cyan] {task['description'] or 'No description'}

[bold cyan]Time Tracking:[/bold cyan]
  Total Time: {total_hours:.2f} hours
  Entries: {len(task['time_entries'])}

[bold cyan]Created:[/bold cyan] {datetime.fromisoformat(task['created_at']).strftime('%Y-%m-%d %H:%M:%S')}
[bold cyan]Updated:[/bold cyan] {datetime.fromisoformat(task['updated_at']).strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        console.print(Panel(details.strip(), title=f"Task #{task_id}", border_style="cyan"))
    
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            console.print(f"[red]❌ Task #{task_id} not found[/red]")
        else:
            handle_error(e, "Failed to fetch task")
    except Exception as e:
        handle_error(e)


@app.command()
def update(
    task_id: int = typer.Argument(..., help="Task ID"),
    title: Optional[str] = typer.Option(None, "--title", help="New title"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="New status"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="New tags (comma-separated)")
):
    """Update a task."""
    try:
        update_data = {}
        if title:
            update_data["title"] = title
        if description is not None:
            update_data["description"] = description
        if status:
            update_data["status"] = status
        if tags is not None:
            update_data["tags"] = [t.strip() for t in tags.split(",")] if tags else []
        
        if not update_data:
            console.print("[yellow]⚠ No updates provided[/yellow]")
            return
        
        response = httpx.put(f"{API_BASE}/tasks/{task_id}", json=update_data, timeout=10.0)
        response.raise_for_status()
        task = response.json()
        
        console.print(f"[green]✓ Task #{task_id} updated successfully[/green]")
    
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            console.print(f"[red]❌ Task #{task_id} not found[/red]")
        else:
            handle_error(e, "Failed to update task")
    except Exception as e:
        handle_error(e)


@app.command()
def delete(task_id: int = typer.Argument(..., help="Task ID")):
    """Delete a task."""
    try:
        if not typer.confirm(f"Are you sure you want to delete task #{task_id}?"):
            console.print("[yellow]Cancelled[/yellow]")
            return
        
        response = httpx.delete(f"{API_BASE}/tasks/{task_id}", timeout=10.0)
        response.raise_for_status()
        
        console.print(f"[green]✓ Task #{task_id} deleted successfully[/green]")
    
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            console.print(f"[red]❌ Task #{task_id} not found[/red]")
        else:
            handle_error(e, "Failed to delete task")
    except Exception as e:
        handle_error(e)


@app.command()
def start(task_id: int = typer.Argument(..., help="Task ID")):
    """Start time tracking for a task."""
    try:
        response = httpx.post(f"{API_BASE}/tasks/{task_id}/start", timeout=10.0)
        response.raise_for_status()
        entry = response.json()
        
        console.print(f"[green]▶️ Time tracking started for task #{task_id}[/green]")
        console.print(f"[dim]Started at: {datetime.fromisoformat(entry['timestamp']).strftime('%H:%M:%S')}[/dim]")
    
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            console.print(f"[red]❌ Task #{task_id} not found[/red]")
        else:
            handle_error(e, "Failed to start timer")
    except Exception as e:
        handle_error(e)


@app.command()
def stop(task_id: int = typer.Argument(..., help="Task ID")):
    """Stop time tracking for a task."""
    try:
        response = httpx.post(f"{API_BASE}/tasks/{task_id}/stop", timeout=10.0)
        response.raise_for_status()
        entry = response.json()
        
        duration_minutes = entry["duration"] / 60 if entry.get("duration") else 0
        
        console.print(f"[green]⏸️ Time tracking stopped for task #{task_id}[/green]")
        console.print(f"[dim]Duration: {duration_minutes:.2f} minutes[/dim]")
    
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            console.print(f"[red]❌ Task #{task_id} not found[/red]")
        else:
            handle_error(e, "Failed to stop timer")
    except Exception as e:
        handle_error(e)


@app.command()
def logs(
    log_type: str = typer.Option("activity", "--type", help="Log type (activity/system)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of logs to show")
):
    """View activity or system logs."""
    try:
        params = {
            "log_type": log_type,
            "limit": limit
        }
        
        response = httpx.get(f"{API_BASE}/logs", params=params, timeout=10.0)
        response.raise_for_status()
        logs = response.json()
        
        if not logs:
            console.print("[yellow]📭 No logs found[/yellow]")
            return
        
        # Create table
        table = Table(
            title=f"📝 {log_type.title()} Logs",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )
        table.add_column("Timestamp", style="dim")
        table.add_column("Level")
        table.add_column("Message")
        
        for log in logs:
            timestamp = datetime.fromisoformat(log["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            level = log["level"]
            level_color = {
                "INFO": "blue",
                "WARNING": "yellow",
                "ERROR": "red",
                "DEBUG": "dim"
            }.get(level, "white")
            
            table.add_row(
                timestamp,
                f"[{level_color}]{level}[/{level_color}]",
                log["message"]
            )
        
        console.print(table)
        console.print(f"\n[dim]Showing {len(logs)} log(s)[/dim]")
    
    except httpx.HTTPError as e:
        handle_error(e, "Failed to fetch logs")
    except Exception as e:
        handle_error(e)


if __name__ == "__main__":
    app()
