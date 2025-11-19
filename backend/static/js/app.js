// Configuration
const CONFIG = {
    API_BASE: '/tasks',
    LOGS_BASE: '/logs',
    DEFAULT_LOG_LIMIT: 50,
    TOAST_DURATION: 3000,
    LOG_REFRESH_INTERVAL: 5000
};

// Application State
const AppState = {
    tasks: [],
    filters: {
        status: '',
        tags: '',
        dateAfter: '',
        dateBefore: ''
    },
    ui: {
        editingTaskId: null,
        isLoading: false,
        logPanelActive: false,
        logRefreshInterval: null,
        pendingConfirmation: null
    },

    update(path, value) {
        const keys = path.split('.');
        let obj = this;
        for (let i = 0; i < keys.length - 1; i++) {
            obj = obj[keys[i]];
        }
        obj[keys[keys.length - 1]] = value;
    },

    setLoading(isLoading) {
        this.ui.isLoading = isLoading;
        toggleLoadingState(isLoading);
    }
};

// Toast Notification System
const Toast = {
    container: null,

    init() {
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        }
    },

    show(message, type = 'info') {
        this.init();

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        const icon = {
            success: '✓',
            error: '✕',
            info: 'ℹ',
            warning: '⚠'
        }[type] || 'ℹ';

        toast.innerHTML = `
            <span class="toast-icon">${icon}</span>
            <span class="toast-message">${escapeHtml(message)}</span>
        `;

        this.container.appendChild(toast);

        // Trigger animation
        setTimeout(() => toast.classList.add('toast-show'), 10);

        // Auto-dismiss
        setTimeout(() => {
            toast.classList.remove('toast-show');
            setTimeout(() => toast.remove(), 300);
        }, CONFIG.TOAST_DURATION);
    },

    success(message) { this.show(message, 'success'); },
    error(message) { this.show(message, 'error'); },
    info(message) { this.show(message, 'info'); },
    warning(message) { this.show(message, 'warning'); }
};

// Confirmation Modal System
const ConfirmDialog = {
    show(message, onConfirm, onCancel) {
        // Create modal if needed
        let modal = document.getElementById('confirmModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'confirmModal';
            modal.className = 'modal';
            modal.innerHTML = `
                <div class="modal-content" style="max-width: 400px;">
                    <div class="modal-header">
                        <h2>Confirm Action</h2>
                    </div>
                    <div class="confirm-message" style="padding: 1rem 0; color: var(--text-primary);"></div>
                    <div class="modal-actions">
                        <button type="button" class="btn btn-secondary" data-action="confirm-cancel">Cancel</button>
                        <button type="button" class="btn btn-primary" data-action="confirm-ok" style="background: var(--danger);">Delete</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }

        // Set message
        modal.querySelector('.confirm-message').textContent = message;

        // Show modal
        modal.classList.add('active');

        // Handle buttons
        const handleConfirm = () => {
            cleanup();
            if (onConfirm) onConfirm();
        };

        const handleCancel = () => {
            cleanup();
            if (onCancel) onCancel();
        };

        const cleanup = () => {
            modal.classList.remove('active');
            modal.querySelector('[data-action="confirm-ok"]').removeEventListener('click', handleConfirm);
            modal.querySelector('[data-action="confirm-cancel"]').removeEventListener('click', handleCancel);
        };

        modal.querySelector('[data-action="confirm-ok"]').addEventListener('click', handleConfirm);
        modal.querySelector('[data-action="confirm-cancel"]').addEventListener('click', handleCancel);

        // Esc to cancel
        const handleEsc = (e) => {
            if (e.key === 'Escape') {
                handleCancel();
                document.removeEventListener('keydown', handleEsc);
            }
        };
        document.addEventListener('keydown', handleEsc);
    }
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    Toast.init();
    loadTasks();
    initEventListeners();
    initKeyboardShortcuts();
});

// Event Listeners Setup
function initEventListeners() {
    // Task grid - event delegation
    const taskGrid = document.getElementById('taskGrid');
    taskGrid.addEventListener('click', handleTaskGridClick);

    // Filters
    document.getElementById('statusFilter').addEventListener('change', loadTasks);
    document.getElementById('tagFilter').addEventListener('change', loadTasks);
    document.getElementById('dateAfter').addEventListener('change', loadTasks);
    document.getElementById('dateBefore').addEventListener('change', loadTasks);

    // Modal
    document.getElementById('taskForm').addEventListener('submit', saveTask);

    // Header actions delegation
    document.addEventListener('click', (e) => {
        const action = e.target.closest('[data-action]');
        if (!action) return;

        const actionType = action.dataset.action;

        const globalActions = {
            'toggle-logs': toggleLogPanel,
            'create-task': showCreateModal,
            'close-modal': closeModal,
            'clear-filters': clearFilters
        };

        const handler = globalActions[actionType];
        if (handler) handler();
    });
}

// Event delegation handler for task grid
function handleTaskGridClick(e) {
    const button = e.target.closest('[data-action]');
    if (!button) return;

    const action = button.dataset.action;
    const taskId = parseInt(button.dataset.taskId);

    if (AppState.ui.isLoading) return; // Prevent double-clicks

    const handlers = {
        'view-details': () => viewTaskDetails(taskId),
        'edit': () => editTask(taskId),
        'start-timer': () => startTimer(taskId),
        'stop-timer': () => stopTimer(taskId),
        'delete': () => deleteTask(taskId)
    };

    const handler = handlers[action];
    if (handler) handler();
}

// Keyboard Shortcuts
function initKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Esc to close modal
        if (e.key === 'Escape') {
            const taskModal = document.getElementById('taskModal');
            if (taskModal.classList.contains('active')) {
                closeModal();
            }
        }

        // Ctrl/Cmd + K to create task
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            showCreateModal();
        }
    });
}

// Loading State Management
function toggleLoadingState(isLoading) {
    const buttons = document.querySelectorAll('button:not(.btn-icon)');
    buttons.forEach(btn => {
        btn.disabled = isLoading;
    });
}

function showSkeletonLoader() {
    const grid = document.getElementById('taskGrid');
    grid.innerHTML = `
        <div class="skeleton-card"></div>
        <div class="skeleton-card"></div>
        <div class="skeleton-card"></div>
    `;
}

// Load tasks with filters
async function loadTasks() {
    const status = document.getElementById('statusFilter').value;
    const tags = document.getElementById('tagFilter').value;
    const dateAfter = document.getElementById('dateAfter').value;
    const dateBefore = document.getElementById('dateBefore').value;

    // Update state
    AppState.update('filters.status', status);
    AppState.update('filters.tags', tags);
    AppState.update('filters.dateAfter', dateAfter);
    AppState.update('filters.dateBefore', dateBefore);

    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (tags) params.append('tags', tags);
    if (dateAfter) params.append('created_after', new Date(dateAfter).toISOString());
    if (dateBefore) params.append('created_before', new Date(dateBefore).toISOString());

    showSkeletonLoader();
    AppState.setLoading(true);

    try {
        const response = await fetch(`${CONFIG.API_BASE}?${params}`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const tasks = await response.json();
        AppState.tasks = tasks;
        renderTasks(tasks);
    } catch (error) {
        console.error('Error loading tasks:', error);
        handleError(error, 'Failed to load tasks');
        document.getElementById('taskGrid').innerHTML =
            '<div class="loading">Error loading tasks. Please try again.</div>';
    } finally {
        AppState.setLoading(false);
    }
}

// Generate task card HTML (DRY approach)
function generateTaskCardHTML(task) {
    return `
        <div class="task-card" data-task-id="${task.id}">
            <div class="task-header">
                <div>
                    <h3 class="task-title">${escapeHtml(task.title)}</h3>
                    <div class="task-meta">
                        <span class="badge badge-${task.status}">${formatStatus(task.status)}</span>
                    </div>
                </div>
            </div>
            ${task.description ? `<p class="task-description">${escapeHtml(task.description)}</p>` : ''}
            ${task.tags && task.tags.length > 0 ? `
                <div class="task-tags">
                    ${task.tags.map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}
                </div>
            ` : ''}
            <div class="task-time">
                Created: ${formatDate(task.created_at)}
            </div>
            <div class="task-actions">
                <button class="btn btn-secondary btn-small" data-action="view-details" data-task-id="${task.id}">
                    View Details
                </button>
                <button class="btn btn-secondary btn-small" data-action="edit" data-task-id="${task.id}">
                    Edit
                </button>
                <button class="btn btn-secondary btn-small" data-action="start-timer" data-task-id="${task.id}">
                    ▶️ Start
                </button>
                <button class="btn btn-secondary btn-small" data-action="stop-timer" data-task-id="${task.id}">
                    ⏸️ Stop
                </button>
                <button class="btn btn-icon btn-small" data-action="delete" data-task-id="${task.id}" style="color: var(--danger);">
                    🗑️
                </button>
            </div>
        </div>
    `;
}

// Render tasks
function renderTasks(tasks) {
    const grid = document.getElementById('taskGrid');

    if (tasks.length === 0) {
        grid.innerHTML = '<div class="loading">No tasks found. Create your first task!</div>';
        return;
    }

    grid.innerHTML = tasks.map(task => generateTaskCardHTML(task)).join('');
}

// Add task card (differential rendering for new tasks)
function addTaskCard(task) {
    const grid = document.getElementById('taskGrid');

    // Remove "no tasks" message if present
    const loadingDiv = grid.querySelector('.loading');
    if (loadingDiv) {
        grid.innerHTML = '';
    }

    const newCard = document.createElement('div');
    newCard.innerHTML = generateTaskCardHTML(task);

    // Prepend to show new tasks first
    grid.insertBefore(newCard.firstChild, grid.firstChild);

    // Update state
    AppState.tasks.unshift(task);
}

// Update single task card (differential rendering)
function updateTaskCard(taskId, task) {
    const card = document.querySelector(`[data-task-id="${taskId}"]`);
    if (!card) {
        // If card not found, might be filtered out - just update state
        const taskIndex = AppState.tasks.findIndex(t => t.id === taskId);
        if (taskIndex !== -1) {
            AppState.tasks[taskIndex] = task;
        }
        return;
    }

    const newCard = document.createElement('div');
    newCard.innerHTML = generateTaskCardHTML(task);

    card.replaceWith(newCard.firstChild);

    // Update state
    const taskIndex = AppState.tasks.findIndex(t => t.id === taskId);
    if (taskIndex !== -1) {
        AppState.tasks[taskIndex] = task;
    }
}

// Remove task card (differential rendering)
function removeTaskCard(taskId) {
    const card = document.querySelector(`[data-task-id="${taskId}"]`);
    if (card) {
        card.classList.add('task-card-removing');
        setTimeout(() => {
            card.remove();

            // If no tasks left, show message
            const grid = document.getElementById('taskGrid');
            if (grid.children.length === 0) {
                grid.innerHTML = '<div class="loading">No tasks found. Create your first task!</div>';
            }
        }, 300);
    }

    // Update state
    AppState.tasks = AppState.tasks.filter(t => t.id !== taskId);
}

// View task details
async function viewTaskDetails(taskId) {
    AppState.setLoading(true);

    try {
        const response = await fetch(`${CONFIG.API_BASE}/${taskId}`);

        if (response.status === 404) {
            Toast.error('Task not found. It may have been deleted.');
            removeTaskCard(taskId);
            return;
        }

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const task = await response.json();
        const totalHours = (task.total_time / 3600).toFixed(2);

        // Create a modal-like panel instead of alert
        const details = `
            <strong>${escapeHtml(task.title)}</strong><br><br>
            <strong>Status:</strong> ${formatStatus(task.status)}<br>
            <strong>Total Time:</strong> ${totalHours} hours<br>
            <strong>Time Entries:</strong> ${task.time_entries.length}<br><br>
            <strong>Description:</strong><br>
            ${escapeHtml(task.description || 'No description')}
        `;

        Toast.info(details);
    } catch (error) {
        console.error('Error loading task details:', error);
        handleError(error, 'Failed to load task details');
    } finally {
        AppState.setLoading(false);
    }
}

// Show create modal
function showCreateModal() {
    AppState.update('ui.editingTaskId', null);
    document.getElementById('modalTitle').textContent = 'Create Task';
    document.getElementById('taskForm').reset();
    document.getElementById('taskModal').classList.add('active');
}

// Edit task
async function editTask(taskId) {
    AppState.setLoading(true);

    try {
        const response = await fetch(`${CONFIG.API_BASE}/${taskId}`);

        if (response.status === 404) {
            Toast.error('Task not found. It may have been deleted.');
            removeTaskCard(taskId);
            return;
        }

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const task = await response.json();

        AppState.update('ui.editingTaskId', taskId);
        document.getElementById('modalTitle').textContent = 'Edit Task';
        document.getElementById('taskTitle').value = task.title;
        document.getElementById('taskDescription').value = task.description || '';
        document.getElementById('taskStatus').value = task.status;
        document.getElementById('taskTags').value = task.tags.join(', ');
        document.getElementById('taskModal').classList.add('active');
    } catch (error) {
        console.error('Error loading task:', error);
        handleError(error, 'Failed to load task');
    } finally {
        AppState.setLoading(false);
    }
}

// Close modal
function closeModal() {
    document.getElementById('taskModal').classList.remove('active');
    AppState.update('ui.editingTaskId', null);
}

// Save task
async function saveTask(event) {
    event.preventDefault();

    const title = document.getElementById('taskTitle').value;
    const description = document.getElementById('taskDescription').value;
    const status = document.getElementById('taskStatus').value;
    const tagsInput = document.getElementById('taskTags').value;
    const tags = tagsInput ? tagsInput.split(',').map(t => t.trim()).filter(t => t) : [];

    const taskData = {
        title,
        description,
        status,
        tags
    };

    // Show saving state
    const submitBtn = event.target.querySelector('button[type="submit"]');
    const originalText = submitBtn.textContent;
    submitBtn.textContent = 'Saving...';
    submitBtn.disabled = true;

    try {
        let response;
        const isEdit = AppState.ui.editingTaskId !== null;

        if (isEdit) {
            // Update existing task
            response = await fetch(`${CONFIG.API_BASE}/${AppState.ui.editingTaskId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(taskData)
            });
        } else {
            // Create new task
            response = await fetch(CONFIG.API_BASE, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(taskData)
            });
        }

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `HTTP ${response.status}`);
        }

        const savedTask = await response.json();

        closeModal();

        // Differential update instead of full reload
        if (isEdit) {
            updateTaskCard(AppState.ui.editingTaskId, savedTask);
            Toast.success('Task updated successfully');
        } else {
            addTaskCard(savedTask);
            Toast.success('Task created successfully');
        }
    } catch (error) {
        console.error('Error saving task:', error);
        handleError(error, 'Failed to save task');
    } finally {
        submitBtn.textContent = originalText;
        submitBtn.disabled = false;
    }
}

// Delete task with confirmation modal (no confirm())
async function deleteTask(taskId) {
    // Get task title for confirmation message
    const task = AppState.tasks.find(t => t.id === taskId);
    const taskTitle = task ? task.title : 'this task';

    ConfirmDialog.show(
        `Are you sure you want to delete "${taskTitle}"? This action cannot be undone.`,
        async () => {
            // User confirmed
            AppState.setLoading(true);

            try {
                const response = await fetch(`${CONFIG.API_BASE}/${taskId}`, { method: 'DELETE' });

                if (response.status === 404) {
                    Toast.warning('Task already deleted');
                } else if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                } else {
                    Toast.success('Task deleted successfully');
                }

                // Optimistic UI removal
                removeTaskCard(taskId);
            } catch (error) {
                console.error('Error deleting task:', error);
                handleError(error, 'Failed to delete task');
                // Reload on error to sync state
                await loadTasks();
            } finally {
                AppState.setLoading(false);
            }
        },
        () => {
            // User cancelled - do nothing
        }
    );
}

// Start timer
async function startTimer(taskId) {
    AppState.setLoading(true);

    try {
        const response = await fetch(`${CONFIG.API_BASE}/${taskId}/start`, { method: 'POST' });

        if (response.status === 404) {
            Toast.error('Task not found');
            removeTaskCard(taskId);
            return;
        }

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const entry = await response.json();
        const time = new Date(entry.timestamp).toLocaleTimeString();
        Toast.success(`Timer started at ${time}`);
    } catch (error) {
        console.error('Error starting timer:', error);
        handleError(error, 'Failed to start timer');
    } finally {
        AppState.setLoading(false);
    }
}

// Stop timer
async function stopTimer(taskId) {
    AppState.setLoading(true);

    try {
        const response = await fetch(`${CONFIG.API_BASE}/${taskId}/stop`, { method: 'POST' });

        if (response.status === 404) {
            Toast.error('Task not found');
            removeTaskCard(taskId);
            return;
        }

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const entry = await response.json();
        const duration = entry.duration ? (entry.duration / 60).toFixed(2) : 'N/A';
        Toast.success(`Timer stopped! Duration: ${duration} minutes`);
    } catch (error) {
        console.error('Error stopping timer:', error);
        handleError(error, 'Failed to stop timer');
    } finally {
        AppState.setLoading(false);
    }
}

// Toggle log panel
function toggleLogPanel() {
    const panel = document.getElementById('logPanel');
    const isActive = panel.classList.toggle('active');
    AppState.update('ui.logPanelActive', isActive);

    if (isActive) {
        loadLogs();
        // Auto-refresh logs while panel is open
        AppState.ui.logRefreshInterval = setInterval(() => {
            if (AppState.ui.logPanelActive) {
                loadLogs();
            }
        }, CONFIG.LOG_REFRESH_INTERVAL);
    } else {
        // Stop auto-refresh
        if (AppState.ui.logRefreshInterval) {
            clearInterval(AppState.ui.logRefreshInterval);
            AppState.ui.logRefreshInterval = null;
        }
    }
}

// Load logs
async function loadLogs() {
    try {
        const response = await fetch(`${CONFIG.LOGS_BASE}?log_type=activity&limit=${CONFIG.DEFAULT_LOG_LIMIT}`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const logs = await response.json();
        renderLogs(logs);
    } catch (error) {
        console.error('Error loading logs:', error);
        document.getElementById('logContent').innerHTML =
            '<div class="loading">Error loading logs</div>';
    }
}

// Render logs
function renderLogs(logs) {
    const content = document.getElementById('logContent');

    if (logs.length === 0) {
        content.innerHTML = '<div class="loading">No logs found</div>';
        return;
    }

    content.innerHTML = logs.map(log => `
        <div class="log-entry">
            <div class="log-entry-time">${formatDate(log.timestamp)}</div>
            <div class="log-entry-message">${escapeHtml(log.message)}</div>
        </div>
    `).join('');
}

// Clear filters
function clearFilters() {
    document.getElementById('statusFilter').value = '';
    document.getElementById('tagFilter').value = '';
    document.getElementById('dateAfter').value = '';
    document.getElementById('dateBefore').value = '';
    loadTasks();
}

// Error Handler with Context
function handleError(error, context) {
    let message = context;

    if (error.message.includes('Failed to fetch')) {
        message = 'Connection failed. Please check your internet connection.';
    } else if (error.message.includes('404')) {
        message = `${context}: Not found`;
    } else if (error.message.includes('400')) {
        message = `${context}: Invalid request`;
    } else if (error.message.includes('500')) {
        message = `${context}: Server error`;
    }

    Toast.error(message);
}

// Utility functions
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatStatus(status) {
    return status.replace('_', ' ').split(' ').map(word =>
        word.charAt(0).toUpperCase() + word.slice(1)
    ).join(' ');
}

function formatDate(dateString) {
    return new Date(dateString).toLocaleString();
}


// Application State
