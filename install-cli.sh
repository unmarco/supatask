#!/bin/bash
# Supatask CLI Installation Script

set -e

echo "🚀 Installing Supatask CLI..."

# Check if backend is running
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "⚠️  Warning: Backend not running on http://localhost:8000"
    echo "   Make sure to start it with: docker compose up -d"
    echo ""
fi

# Install CLI
cd cli
pip3 install --user -e .

echo ""
echo "✅ Installation complete!"
echo ""
echo "Usage:"
echo "  supatask list                    # List all tasks"
echo "  supatask add 'Task title'        # Create a task"
echo "  supatask view <id>               # View task details"
echo "  supatask start <id>              # Start time tracking"
echo "  supatask stop <id>               # Stop time tracking"
echo "  supatask logs                    # View activity logs"
echo "  supatask --help                  # Show all commands"
echo ""
echo "📖 Full documentation: ../README.md"
