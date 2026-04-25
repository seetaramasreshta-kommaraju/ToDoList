document.addEventListener('DOMContentLoaded', () => {
    // Theme Toggle
    const themeToggleBtn = document.getElementById('theme-toggle');
    const themeIcon = document.getElementById('theme-icon');
    const htmlElement = document.documentElement;
    
    // Check local storage for theme
    const savedTheme = localStorage.getItem('theme') || 'light';
    htmlElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            const currentTheme = htmlElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            
            htmlElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });
    }

    function updateThemeIcon(theme) {
        if (!themeIcon) return;
        if (theme === 'dark') {
            themeIcon.classList.remove('ph-moon');
            themeIcon.classList.add('ph-sun');
        } else {
            themeIcon.classList.remove('ph-sun');
            themeIcon.classList.add('ph-moon');
        }
    }

    // Task Checkbox Toggle via AJAX
    const taskCheckboxes = document.querySelectorAll('.task-check');
    taskCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', async (e) => {
            const taskItem = e.target.closest('.task-item');
            const taskId = taskItem.dataset.id;
            const category = taskItem.dataset.category;
            const isCompleted = e.target.checked;

            try {
                const response = await fetch(`/toggle-task/${taskId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ completed: isCompleted })
                });

                const data = await response.json();

                if (data.success) {
                    if (isCompleted) {
                        taskItem.classList.add('completed');
                    } else {
                        taskItem.classList.remove('completed');
                    }

                    // Update progress bars
                    updateProgressBar(`cat-fill-${category}`, data.category_progress);
                    updateProgressBar('overall-progress-fill', data.overall_progress);
                    document.getElementById('overall-progress-text').textContent = `${data.overall_progress}%`;
                } else {
                    // Revert checkbox state on failure
                    e.target.checked = !isCompleted;
                    alert('Failed to update task.');
                }
            } catch (error) {
                console.error('Error toggling task:', error);
                e.target.checked = !isCompleted;
            }
        });
    });

    // Task Deletion via AJAX
    const deleteBtns = document.querySelectorAll('.delete-btn');
    deleteBtns.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!confirm('Delete this task?')) return;

            // Use currentTarget (the button) to safely find the parent task item,
            // because e.target may be the inner <i> icon element.
            const taskItem = e.currentTarget.closest('.task-item');
            const taskId = taskItem.dataset.id;

            try {
                const response = await fetch(`/delete-task/${taskId}`, {
                    method: 'DELETE',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });

                const data = await response.json();

                if (data.success) {
                    taskItem.remove();
                    window.location.reload();
                } else {
                    alert('Failed to delete task.');
                }
            } catch (error) {
                console.error('Error deleting task:', error);
            }
        });
    });

    function updateProgressBar(className, percentage) {
        const elements = document.getElementsByClassName(className);
        for (let i = 0; i < elements.length; i++) {
            elements[i].style.width = `${percentage}%`;
        }
        // Also support ID
        const elById = document.getElementById(className);
        if (elById) {
            elById.style.width = `${percentage}%`;
        }
    }
});
