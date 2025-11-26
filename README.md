# ⚡ Supatask

A Redis-based local task manager with a modern web interface, rich CLI, and MCP server integration.

## Features

- ✅ **Task Management**: Full CRUD operations with tags and status tracking
- ⏱️ **Time Tracking**: Start/stop timers for tasks with historical tracking
- 📊 **Filtering**: Filter tasks by status, tags, and date ranges
- 📝 **Logging**: Activity and system logs with historical analysis
- 🌐 **Web Interface**: Modern, responsive dark-mode UI
- 💻 **Rich CLI**: Beautiful command-line interface with tables and colors
- 🤖 **MCP Server**: AI assistant integration via Model Context Protocol

## Architecture

- **Backend**: FastAPI (Python 3.11+)
- **Database**: Redis with AOF persistence
- **Frontend**: Vanilla JavaScript with modern CSS
- **CLI**: Typer + Rich
- **Deployment**: Docker Compose

## Quick Start

### 1. Start the Application

```bash
# Start Docker containers
docker compose up -d

# Verify services are running
curl http://localhost:8000/health
```

### 2. Access the Web Interface

Open http://localhost:8000 in your browser for the full-featured web UI.

### 3. Install CLI (Optional)

**One-line install:**
```bash
./install-cli.sh
```

**Manual install:**
```bash
cd cli
```

### 4. Use the CLI

```bash
# List tasks
python cli/supatask_cli.py list

# Add a task
python cli/supatask_cli.py add "Fix bug" --tags "urgent,backend"

# Start time tracking
python cli/supatask_cli.py start 1

# Stop time tracking
python cli/supatask_cli.py stop 1

# View logs
python cli/supatask_cli.py logs --limit 20
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `list` | List tasks with optional filters (--status, --tags, --created-after, --created-before) |
| `add <title>` | Create a new task (--description, --status, --tags) |
| `view <id>` | View task details with time tracking |
| `update <id>` | Update task (--title, --description, --status, --tags) |
| `delete <id>` | Delete a task |
| `start <id>` | Start time tracking |
| `stop <id>` | Stop time tracking |
| `logs` | View activity/system logs (--type, --limit) |

## API Endpoints

### Tasks
- `POST /tasks` - Create task
- `GET /tasks` - List tasks (query params: status, tags, created_after, created_before)
- `GET /tasks/{id}` - Get task details
- `PUT /tasks/{id}` - Update task
- `DELETE /tasks/{id}` - Delete task
- `POST /tasks/{id}/start` - Start timer
- `POST /tasks/{id}/stop` - Stop timer

### Logs
- `GET /logs` - Get logs (query params: log_type, start_time, end_time, limit)

### MCP (HTTP Streamable Transport)
- `POST /mcp/` - JSON-RPC 2.0 endpoint (initialize, tools/list, tools/call, ping)
- `GET /mcp/` - Optional SSE stream for server-initiated messages

## MCP Integration

Supatask includes an MCP server implementing the **HTTP Streamable Transport** (MCP spec 2025-06-18) for AI assistant integration.

### Available Tools

- `create_task` - Create tasks with tags
- `read_task` - Read task details
- `list_tasks` - List tasks with filters
- `update_task` - Update tasks
- `delete_task` - Delete tasks
- `get_logs` - Retrieve activity/system logs

### Claude Code Configuration

Add to `~/.config/claude-code/mcp.json`:

```json
{
  "mcpServers": {
    "supatask": {
      "url": "http://localhost:8000/mcp/",
      "transport": "http"
    }
  }
}
```

### Protocol Details

- **Specification**: MCP 2025-06-18
- **Transport**: HTTP Streamable
- **Message Format**: JSON-RPC 2.0
- **Session Management**: Via `Mcp-Session-Id` headers

### Example Usage

```bash
# Initialize connection
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'

# List available tools
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":2}'

# Create a task
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"create_task","arguments":{"title":"My Task","tags":["work"]}},"id":3}'
```

## Data Model

Tasks are stored in Redis with the following structure:

```
task:{id}          Hash with title, description, status, created_at, updated_at
task:{id}:tags     Set of tags
task:{id}:time     Stream of time tracking entries
tasks              Set of all task IDs
tasks:by_status:{status}  Set of task IDs by status
logs:activity      Stream of user-facing activity logs
logs:system        Stream of debug/system logs
```

## Development

### Backend Development

The backend supports hot reload in development mode:

```bash
docker-compose up
```

Edit files in `backend/` and the server will automatically reload.

### Stopping the Application

```bash
docker-compose down
```

To also remove the Redis data volume:

```bash
docker-compose down -v
```

## Configuration

Environment variables (set in `docker-compose.yml`):

- `REDIS_URL` - Redis connection URL (default: `redis://redis:6379`)
- `LOG_LEVEL` - Logging level (default: `INFO`)

## License

MIT
